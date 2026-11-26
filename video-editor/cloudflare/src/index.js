const MAX_UPLOAD_BYTES = 50 * 1024 * 1024;
const MAX_PROJECT_MEDIA_BYTES = 200 * 1024 * 1024;
const ALLOWED_EXTENSIONS = new Set([".mp4", ".mov", ".m4v", ".webm", ".mkv"]);

function json(data, status = 200, headers = {}) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "content-type": "application/json; charset=utf-8", "cache-control": "no-store", ...headers }
  });
}

function cleanText(value, max = 1500) {
  return String(value ?? "").trim().slice(0, max);
}

function safeFilename(value) {
  const name = String(value || "video.mp4").split(/[\/]/).pop().replace(/[^\w.-]+/g, "_").slice(0, 100);
  return name || "video.mp4";
}

function fileExtension(name) {
  const match = String(name).toLowerCase().match(/\.[a-z0-9]{2,5}$/);
  return match ? match[0] : "";
}

function slug(value) {
  return String(value || "custom-style").toLowerCase().replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "").slice(0, 54) || "custom-style";
}

function equalSecret(provided, expected) {
  if (!provided || !expected || provided.length !== expected.length) return false;
  let diff = 0;
  for (let i = 0; i < expected.length; i++) diff |= provided.charCodeAt(i) ^ expected.charCodeAt(i);
  return diff === 0;
}

function authorized(request, env) {
  const header = request.headers.get("authorization") || "";
  const supplied = header.startsWith("Bearer ") ? header.slice(7) : "";
  return equalSecret(supplied, env.APP_API_TOKEN || "");
}

function callbackAuthorized(request, env) {
  return equalSecret(request.headers.get("x-callback-secret") || "", env.CALLBACK_SECRET || "");
}

function validateSkill(input) {
  if (!input || typeof input !== "object" || Array.isArray(input)) throw new Error("Skill must be a JSON object.");
  const id = String(input.id || "");
  if (!/^[a-z0-9][a-z0-9-]{0,63}$/.test(id)) throw new Error("Skill ID must contain lowercase letters, numbers and hyphens.");
  const settings = input.default_settings || {};
  const aspect = String(settings.aspect || "9:16");
  if (!["9:16", "1:1", "16:9"].includes(aspect)) throw new Error("Unsupported aspect ratio.");
  const width = Number(settings.width ?? (aspect === "16:9" ? 1280 : 720));
  const height = Number(settings.height ?? (aspect === "16:9" || aspect === "1:1" ? 720 : 1280));
  const speed = Number(settings.speed ?? 1);
  if (!Number.isInteger(width) || !Number.isInteger(height) || width < 144 || height < 144 || width > 1920 || height > 1920) {
    throw new Error("Skill dimensions must be whole numbers from 144 to 1920.");
  }
  if (!Number.isFinite(speed) || speed < 0.25 || speed > 4) throw new Error("Skill speed must be between 0.25x and 4x.");
  const operations = Array.isArray(input.operations) ? input.operations : ["trim", "speed", "reframe"];
  if (operations.some(x => !["trim", "speed", "reframe"].includes(x))) throw new Error("Skill contains an unsupported operation.");
  return {
    id,
    version: 1,
    name: cleanText(input.name || id, 80),
    description: cleanText(input.description || "", 300),
    default_settings: { aspect, width, height, speed },
    operations
  };
}

async function githubRequest(env, path, options = {}) {
  const response = await fetch("https://api.github.com" + path, {
    ...options,
    headers: {
      authorization: "Bearer " + env.GITHUB_TOKEN,
      accept: "application/vnd.github+json",
      "x-github-api-version": "2022-11-28",
      "user-agent": "independent-video-editor",
      ...(options.headers || {})
    }
  });
  if (!response.ok) {
    const detail = (await response.text()).slice(0, 700);
    throw new Error("GitHub API returned " + response.status + ": " + detail);
  }
  if (response.status === 204) return {};
  return response.json();
}

async function createInputRelease(env, jobId) {
  const tag = "ve-input-" + jobId;
  const release = await githubRequest(env, "/repos/" + env.GITHUB_OWNER + "/" + env.GITHUB_REPO + "/releases", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({
      tag_name: tag,
      target_commitish: env.GITHUB_REF || "mlt-integration",
      name: "Private editor job " + jobId,
      body: "Temporary private input for the Independent Video Editor. Managed by the editor service.",
      draft: true,
      prerelease: true
    })
  });
  return { id: release.id, tag, uploadUrl: release.upload_url };
}

async function uploadReleaseAsset(env, release, filename, body, contentType, contentLength) {
  const endpoint = "https://uploads.github.com/repos/" + env.GITHUB_OWNER + "/" + env.GITHUB_REPO +
    "/releases/" + release.id + "/assets?name=" + encodeURIComponent(filename);
  // FixedLengthStream preserves the exact Content-Length while streaming the
  // user's video through the Worker without buffering the entire upload.
  const fixed = new FixedLengthStream(contentLength);
  const pipePromise = body.pipeTo(fixed.writable);
  const responsePromise = fetch(endpoint, {
    method: "POST",
    headers: {
      authorization: "Bearer " + env.GITHUB_TOKEN,
      accept: "application/vnd.github+json",
      "x-github-api-version": "2022-11-28",
      "content-type": contentType || "application/octet-stream",
      "user-agent": "independent-video-editor"
    },
    body: fixed.readable,
    redirect: "manual"
  });
  const [response] = await Promise.all([responsePromise, pipePromise]);
  if (!response.ok) {
    const detail = (await response.text()).slice(0, 700);
    throw new Error("GitHub asset upload returned " + response.status + ": " + detail);
  }
  return response.json();
}

async function deleteRelease(env, releaseId, tag) {
  try {
    await githubRequest(env, "/repos/" + env.GITHUB_OWNER + "/" + env.GITHUB_REPO + "/releases/" + releaseId, { method: "DELETE" });
  } catch (_) {}
  if (tag) {
    try {
      await githubRequest(env, "/repos/" + env.GITHUB_OWNER + "/" + env.GITHUB_REPO + "/git/refs/tags/" + encodeURIComponent(tag), { method: "DELETE" });
    } catch (_) {}
  }
}

async function dispatchRender(env, jobId) {
  const path = "/repos/" + env.GITHUB_OWNER + "/" + env.GITHUB_REPO +
    "/actions/workflows/" + encodeURIComponent(env.GITHUB_WORKFLOW || "video-editor-render.yml") + "/dispatches";
  await githubRequest(env, path, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({
      ref: env.GITHUB_REF || "mlt-integration",
      inputs: { job_id: jobId }
    })
  });
}

async function getSkill(env, id) {
  const row = await env.DB.prepare("SELECT skill_json FROM skills WHERE id = ?").bind(id).first();
  if (!row) return null;
  return validateSkill(JSON.parse(row.skill_json));
}

async function listSkills(env) {
  const result = await env.DB.prepare(
    "SELECT id,name,description,version,skill_json FROM skills ORDER BY name"
  ).all();
  return (result.results || []).map(row => validateSkill(JSON.parse(row.skill_json)));
}

async function createJob(request, env) {
  if (!env.GITHUB_TOKEN || !env.APP_API_TOKEN) return json({ error: "Worker secrets are not configured." }, 503);
  const length = Number(request.headers.get("x-file-size") || request.headers.get("content-length") || 0);
  if (!Number.isFinite(length) || length < 1) return json({ error: "A video with a known Content-Length is required." }, 411);
  if (length > MAX_UPLOAD_BYTES) return json({ error: "Maximum input size is 50 MB in this prototype." }, 413);

  const filename = safeFilename(request.headers.get("x-file-name") || "upload.mp4");
  if (!ALLOWED_EXTENSIONS.has(fileExtension(filename))) return json({ error: "Unsupported video format." }, 415);
  let instruction;
  try {
    instruction = cleanText(decodeURIComponent(request.headers.get("x-edit-instruction") || "Make a clean vertical short"));
  } catch (_) {
    return json({ error: "The edit instructions could not be decoded. Please submit again." }, 400);
  }
  if (!instruction) return json({ error: "Describe the edit you want." }, 400);
  const skillId = cleanText(request.headers.get("x-edit-skill-id") || "clean-shorts", 64);
  if (!/^[a-z0-9][a-z0-9-]{0,63}$/.test(skillId)) return json({ error: "Invalid skill ID." }, 400);

  let skill;
  try {
    skill = await getSkill(env, skillId);
  } catch (error) {
    return json({ error: error.message }, 400);
  }
  if (!skill) return json({ error: "Unknown editing skill." }, 404);

  const jobId = crypto.randomUUID().replace(/-/g, "");
  let release;
  try {
    release = await createInputRelease(env, jobId);
    const asset = await uploadReleaseAsset(
      env, release, "input" + fileExtension(filename), request.body,
      request.headers.get("content-type") || "application/octet-stream", length
    );
    const now = new Date().toISOString();
    await env.DB.prepare(
      "INSERT INTO jobs (id,status,message,instruction,skill_id,skill_json,release_id,release_tag,input_asset_id,input_filename,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)"
    ).bind(
      jobId, "queued", "Video uploaded. Waiting for the cloud renderer.",
      instruction, skill.id, JSON.stringify(skill), release.id, release.tag, asset.id, filename, now, now
    ).run();
    try {
      await dispatchRender(env, jobId);
    } catch (error) {
      await env.DB.prepare("UPDATE jobs SET status='failed',message=?,updated_at=? WHERE id=?")
        .bind("Could not start GitHub Actions: " + error.message.slice(0, 350), new Date().toISOString(), jobId).run();
      return json({ error: "Upload succeeded, but the cloud render could not start. " + error.message, job_id: jobId }, 502);
    }
    return json({ job_id: jobId, status: "queued", message: "Upload complete. The cloud render has been queued." }, 202);
  } catch (error) {
    if (release) await deleteRelease(env, release.id, release.tag);
    return json({ error: "Video upload failed: " + error.message }, 502);
  }
}

async function getJob(request, env, id) {
  if (!authorized(request, env)) return json({ error: "Unauthorized. Enter your app/API token." }, 401);
  const row = await env.DB.prepare(
    "SELECT id,status,message,instruction,skill_id,created_at,updated_at,run_url,artifact_url,output_asset_id,project_revision,ai_status,pending_plan_json FROM jobs WHERE id=?"
  ).bind(id).first();
  if (!row) return json({ error: "Job not found." }, 404);
  return json({
    job_id: row.id,
    status: row.ai_status === "awaiting_confirmation" ? "awaiting_confirmation" : row.status,
    ai_status: row.ai_status || "idle", message: row.message,
    instruction: row.instruction, skill_id: row.skill_id,
    project_revision: row.project_revision || null,
    pending_plan: row.pending_plan_json ? JSON.parse(row.pending_plan_json) : null,
    created_at: row.created_at, updated_at: row.updated_at,
    run_url: row.run_url, artifact_url: row.artifact_url,
    download_url: row.output_asset_id ? "/api/v1/jobs/" + row.id + "/download" : null
  });
}

async function downloadJob(request, env, id) {
  if (!authorized(request, env)) return json({ error: "Unauthorized." }, 401);
  const row = await env.DB.prepare("SELECT status,output_asset_id FROM jobs WHERE id=?").bind(id).first();
  if (!row) return json({ error: "Job not found." }, 404);
  if (row.status !== "completed" || !row.output_asset_id) return json({ error: "The edited video is not ready yet." }, 409);
  const endpoint = "https://api.github.com/repos/" + env.GITHUB_OWNER + "/" + env.GITHUB_REPO +
    "/releases/assets/" + row.output_asset_id;
  const response = await fetch(endpoint, {
    headers: {
      authorization: "Bearer " + env.GITHUB_TOKEN,
      accept: "application/octet-stream",
      "x-github-api-version": "2022-11-28",
      "user-agent": "independent-video-editor"
    },
    redirect: "manual"
  });
  if ([301, 302, 303, 307, 308].includes(response.status)) {
    const location = response.headers.get("location");
    if (!location) return json({ error: "GitHub did not provide a download location." }, 502);
    // Return the short-lived signed storage URL as JSON. The browser must first
    // authenticate to this Worker, then navigate to the signed URL. A normal
    // anchor cannot attach the required Bearer token to this Worker endpoint.
    return json({ download_url: location, expires_soon: true }, 200);
  }
  if (!response.ok) return json({ error: "Could not retrieve output asset (HTTP " + response.status + ")." }, 502);
  return new Response(response.body, {
    headers: {
      "content-type": "video/mp4",
      "content-disposition": 'attachment; filename="edited-video.mp4"',
      "cache-control": "private, no-store"
    }
  });
}

async function generateSkill(request, env) {
  if (!authorized(request, env)) return json({ error: "Unauthorized." }, 401);
  if (!env.GEMINI_API_KEY) return json({ error: "Add GEMINI_API_KEY as a Worker secret to enable AI skill creation." }, 503);
  let body;
  try { body = await request.json(); } catch (_) { return json({ error: "Send valid JSON." }, 400); }
  const description = cleanText(body.description, 1200);
  if (!description) return json({ error: "Describe the editing style first." }, 400);
  const prompt = [
    "Create a reusable video editing skill as JSON only.",
    "The supported operations are trim, speed, and reframe.",
    "Return fields: id, version=1, name, description, default_settings with aspect, width, height, speed, and operations array.",
    "aspect must be 9:16, 1:1 or 16:9; width and height integers 144..1920; speed 0.25..4.",
    "Do not return code, commands, URLs, external files or unsupported operations.",
    "User style: " + description
  ].join("\n");
  const model = env.GEMINI_MODEL || "gemini-3.5-flash-lite";
  const endpoint = "https://generativelanguage.googleapis.com/v1beta/models/" +
    encodeURIComponent(model) + ":generateContent?key=" + encodeURIComponent(env.GEMINI_API_KEY);
  const response = await fetch(endpoint, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({
      contents: [{ parts: [{ text: prompt }] }],
      generationConfig: { responseMimeType: "application/json", temperature: 0.2 }
    })
  });
  if (!response.ok) return json({ error: "Gemini returned HTTP " + response.status + "." }, 502);
  const data = await response.json();
  const text = data.candidates?.[0]?.content?.parts?.[0]?.text;
  if (!text) return json({ error: "Gemini returned no skill." }, 502);
  let skill;
  try {
    skill = JSON.parse(text);
    if (!skill.id) skill.id = slug(skill.name || description);
    skill = validateSkill(skill);
  } catch (error) {
    return json({ error: "Gemini returned an invalid skill: " + error.message }, 502);
  }
  return saveSkill(env, skill);
}

async function saveSkill(env, skill) {
  const now = new Date().toISOString();
  await env.DB.prepare(
    "INSERT INTO skills (id,name,description,version,skill_json,created_at,updated_at) VALUES (?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET name=excluded.name,description=excluded.description,version=excluded.version,skill_json=excluded.skill_json,updated_at=excluded.updated_at"
  ).bind(skill.id, skill.name, skill.description, skill.version, JSON.stringify(skill), now, now).run();
  return json({ skill }, 201);
}

async function internalJob(request, env, id) {
  if (!callbackAuthorized(request, env)) return json({ error: "Unauthorized worker." }, 401);
  const row = await env.DB.prepare(
    "SELECT id,status,message,instruction,skill_id,skill_json,release_id,release_tag,input_asset_id,input_filename,project_json,project_revision,pending_plan_json,confirmed_tools_json,history_state_json FROM jobs WHERE id=?"
  ).bind(id).first();
  if (!row) return json({ error: "Job not found." }, 404);
  return json({
    job_id: row.id, status: row.status, message: row.message,
    instruction: row.instruction, skill_id: row.skill_id,
    skill: JSON.parse(row.skill_json),
    release_id: row.release_id, release_tag: row.release_tag,
    input_asset_id: row.input_asset_id, input_filename: row.input_filename,
    project_json: row.project_json ? JSON.parse(row.project_json) : null,
    project_revision: row.project_revision || null,
    pending_plan: row.pending_plan_json ? JSON.parse(row.pending_plan_json) : null,
    confirmed_tools: JSON.parse(row.confirmed_tools_json || "[]"),
    history_state: JSON.parse(row.history_state_json || '{"undo":[],"redo":[]}')
  });
}

async function internalCallback(request, env, id) {
  if (!callbackAuthorized(request, env)) return json({ error: "Unauthorized worker." }, 401);
  let body;
  try { body = await request.json(); } catch (_) { return json({ error: "Send valid JSON." }, 400); }
  const status = String(body.status || "");
  if (!["running", "completed", "failed"].includes(status)) return json({ error: "Invalid job status." }, 400);
  const outputAssetId = body.output_asset_id ? Number(body.output_asset_id) : null;
  if (status === "completed" && (!Number.isInteger(outputAssetId) || outputAssetId <= 0)) return json({ error: "Completed jobs must include a valid output asset ID." }, 400);
  let projectJson = null, projectRevision = null;
  if (body.project_json !== undefined && body.project_json !== null) {
    if (!body.project_json || typeof body.project_json !== "object" || Array.isArray(body.project_json)) return json({ error: "project_json must be a project object." }, 400);
    projectJson = JSON.stringify(body.project_json);
    if (projectJson.length > 1500000) return json({ error: "Project document exceeds the 1.5 MB prototype limit." }, 413);
    projectRevision = Number(body.project_revision ?? body.project_json.revision);
    if (!Number.isInteger(projectRevision) || projectRevision < 1) return json({ error: "Project revision must be a positive integer." }, 400);
  }
  let historyStateJson = null;
  if (body.history_state !== undefined && body.history_state !== null) {
    if (!body.history_state || typeof body.history_state !== "object" || Array.isArray(body.history_state)
        || !Array.isArray(body.history_state.undo) || !Array.isArray(body.history_state.redo)
        || body.history_state.undo.length > 10 || body.history_state.redo.length > 10) {
      return json({ error: "history_state must contain at most ten undo and redo project snapshots." }, 400);
    }
    historyStateJson = JSON.stringify(body.history_state);
    if (historyStateJson.length > 900000) return json({ error: "Project history exceeds the 900 KB limit." }, 413);
  }
  const aiStatus = body.ai_status === undefined ? null : String(body.ai_status);
  if (aiStatus !== null && !["planning", "queued", "applied", "awaiting_confirmation", "error"].includes(aiStatus)) return json({ error: "Invalid AI status." }, 400);
  const hasPendingPlan = Object.prototype.hasOwnProperty.call(body, "pending_plan");
  const pendingPlanJson = hasPendingPlan && body.pending_plan !== null ? JSON.stringify(body.pending_plan) : null;
  if (pendingPlanJson && pendingPlanJson.length > 100000) return json({ error: "Pending AI plan exceeds the allowed size." }, 413);
  const now = new Date().toISOString();
  const result = await env.DB.prepare(
    "UPDATE jobs SET status=?,message=?,output_asset_id=COALESCE(?,output_asset_id),run_url=COALESCE(?,run_url),artifact_url=COALESCE(?,artifact_url),updated_at=?,project_json=COALESCE(?,project_json),project_revision=COALESCE(?,project_revision),ai_status=COALESCE(?,ai_status),history_state_json=COALESCE(?,history_state_json),pending_plan_json=CASE WHEN ?=1 THEN ? ELSE pending_plan_json END WHERE id=?"
  ).bind(status, cleanText(body.message, 500), outputAssetId,
    cleanText(body.run_url, 500) || null, cleanText(body.artifact_url, 500) || null,
    now, projectJson, projectRevision, aiStatus, historyStateJson, hasPendingPlan ? 1 : 0, pendingPlanJson, id).run();
  if (!result.meta?.changes) return json({ error: "Job not found." }, 404);
  return json({ ok: true, project_revision: projectRevision });
}

async function listProjects(request, env) {
  if (!authorized(request, env)) return json({ error: "Unauthorized." }, 401);
  const result = await env.DB.prepare(
    "SELECT id,status,updated_at,project_revision,project_json FROM jobs WHERE project_json IS NOT NULL ORDER BY updated_at DESC LIMIT 100"
  ).all();
  const projects = [];
  for (const row of result.results || []) {
    let project;
    try { project = JSON.parse(row.project_json); }
    catch (_) { continue; }
    if (!project || typeof project !== "object" || !Array.isArray(project.tracks)) continue;
    let durationUs = 0, clipCount = 0;
    for (const track of project.tracks) {
      for (const clip of track.clips || []) {
        clipCount += 1;
        durationUs = Math.max(
          durationUs,
          Number(clip.start_us || 0) + Number(clip.duration_us || 0)
        );
      }
    }
    projects.push({
      id: row.id,
      name: cleanText(project.name || "Untitled project", 120),
      status: row.status,
      revision: Number(row.project_revision || project.revision || 1),
      updated_at: row.updated_at,
      width: project.video_profile?.width || null,
      height: project.video_profile?.height || null,
      asset_count: Array.isArray(project.assets) ? project.assets.length : 0,
      track_count: project.tracks.length,
      clip_count: clipCount,
      duration_us: durationUs
    });
  }
  return json({ projects });
}

async function renameProject(request, env, id) {
  if (!authorized(request, env)) return json({ error: "Unauthorized." }, 401);
  let body;
  try { body = await request.json(); } catch (_) { return json({ error: "Send valid JSON." }, 400); }
  const name = cleanText(body.name, 120);
  const expectedRevision = Number(body.expected_revision);
  if (!name) return json({ error: "Project name cannot be empty." }, 400);
  if (!Number.isInteger(expectedRevision) || expectedRevision < 1) {
    return json({ error: "Load the project and send its current revision before renaming." }, 400);
  }
  const row = await env.DB.prepare(
    "SELECT status,project_json,project_revision,history_state_json,pending_plan_json FROM jobs WHERE id=?"
  ).bind(id).first();
  if (!row) return json({ error: "Project not found." }, 404);
  if (!["completed", "failed"].includes(row.status) || !row.project_json) {
    return json({ error: "This project has no recoverable saved checkpoint to rename." }, 409);
  }
  if (row.pending_plan_json) return json({ error: "Resolve the pending edit before renaming this project." }, 409);
  const revision = Number(row.project_revision || 1);
  if (revision !== expectedRevision) {
    return json({ error: "Project revision conflict. Reload before renaming.", current_revision: revision }, 409);
  }
  let project, history;
  try {
    project = JSON.parse(row.project_json);
    history = JSON.parse(row.history_state_json || '{"undo":[],"redo":[]}');
  } catch (_) {
    return json({ error: "The saved project or history data is invalid." }, 500);
  }
  if (!Array.isArray(history.undo) || !Array.isArray(history.redo)) {
    return json({ error: "The saved project history is invalid." }, 500);
  }
  if (project.name === name) {
    return json({ project, revision, changed: false, message: "Project name is already up to date." });
  }
  const snapshot = JSON.parse(JSON.stringify(project));
  snapshot.revision = revision;
  history.undo.push(snapshot);
  history.undo = history.undo.slice(-10);
  history.redo = [];
  project.name = name;
  project.revision = revision + 1;
  const projectJson = JSON.stringify(project);
  const historyJson = JSON.stringify(history);
  if (projectJson.length > 1500000 || historyJson.length > 900000) {
    return json({ error: "The project or its history exceeds the saved-size limit." }, 413);
  }
  const now = new Date().toISOString();
  const update = await env.DB.prepare(
    "UPDATE jobs SET project_json=?,project_revision=?,history_state_json=?,updated_at=? WHERE id=? AND status IN ('completed','failed') AND project_revision=? AND pending_plan_json IS NULL"
  ).bind(projectJson, project.revision, historyJson, now, id, revision).run();
  if (!update.meta?.changes) {
    return json({ error: "The project changed while renaming. Reload and try again." }, 409);
  }
  return json({
    project,
    revision: project.revision,
    changed: true,
    message: "Project renamed and saved as revision " + project.revision + "."
  });
}

async function getProject(request, env, id) {
  if (!authorized(request, env)) return json({ error: "Unauthorized." }, 401);
  const row = await env.DB.prepare("SELECT project_json,project_revision,updated_at FROM jobs WHERE id=?").bind(id).first();
  if (!row) return json({ error: "Job not found." }, 404);
  if (!row.project_json) return json({ error: "The canonical project has not been initialized yet." }, 409);
  return json({ project: JSON.parse(row.project_json), revision: row.project_revision || 1, updated_at: row.updated_at });
}

async function importMediaAsset(request, env, id) {
  if (!authorized(request, env)) return json({ error: "Unauthorized." }, 401);
  if (!env.GITHUB_TOKEN || !env.GITHUB_OWNER || !env.GITHUB_REPO) {
    return json({ error: "Private media storage is not configured." }, 503);
  }
  const length = Number(request.headers.get("x-file-size") || request.headers.get("content-length") || 0);
  if (!Number.isSafeInteger(length) || length < 1) return json({ error: "A media file with a known size is required." }, 411);
  if (length > MAX_UPLOAD_BYTES) return json({ error: "Each imported media file is limited to 50 MB." }, 413);
  let rawFilename = request.headers.get("x-file-name") || "media.bin";
  try { rawFilename = decodeURIComponent(rawFilename); } catch (_) {
    return json({ error: "The media filename could not be decoded." }, 400);
  }
  const filename = safeFilename(rawFilename);
  const extension = fileExtension(filename);
  const mediaType = String(request.headers.get("x-media-type") || "").toLowerCase();
  const allowed = {
    video: new Set([".mp4", ".mov", ".m4v", ".webm", ".mkv"]),
    audio: new Set([".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac"]),
    image: new Set([".jpg", ".jpeg", ".png", ".webp", ".gif"])
  };
  if (!allowed[mediaType] || !allowed[mediaType].has(extension)) {
    return json({ error: "Unsupported media type or file extension." }, 415);
  }
  const durationHeader = request.headers.get("x-media-duration-us");
  let durationUs = null;
  if (durationHeader !== null && durationHeader !== "") {
    durationUs = Number(durationHeader);
    if (!Number.isSafeInteger(durationUs) || durationUs < 1) {
      return json({ error: "Media duration must be a positive integer number of microseconds." }, 400);
    }
  }
  if (!request.body) return json({ error: "The media file body is missing." }, 400);
  const row = await env.DB.prepare(
    "SELECT status,release_id,project_json,project_revision,history_state_json,pending_plan_json FROM jobs WHERE id=?"
  ).bind(id).first();
  if (!row) return json({ error: "Job not found." }, 404);
  if (!["completed", "failed"].includes(row.status) || !row.project_json) {
    return json({ error: "Wait for the current edit to stop before importing media into its saved checkpoint." }, 409);
  }
  if (row.pending_plan_json) return json({ error: "Resolve the pending edit before importing media." }, 409);
  let project, history;
  try {
    project = JSON.parse(row.project_json);
    history = JSON.parse(row.history_state_json || '{"undo":[],"redo":[]}');
  } catch (_) {
    return json({ error: "The saved project or history data is invalid." }, 500);
  }
  if (!project || !Array.isArray(project.assets) || project.assets.length >= 100) {
    return json({ error: "This project has reached the 100-asset limit." }, 409);
  }
  const existingBytes = project.assets.reduce((total, asset) =>
    total + (Number.isSafeInteger(Number(asset.size_bytes)) ? Number(asset.size_bytes) : 0), 0);
  if (existingBytes + length > MAX_PROJECT_MEDIA_BYTES) {
    return json({ error: "Project media storage is limited to 200 MB total, including the original source." }, 413);
  }
  if (!Array.isArray(history.undo) || !Array.isArray(history.redo)) {
    return json({ error: "The saved project history is invalid." }, 500);
  }
  const revision = Number(row.project_revision || project.revision || 1);
  if (!Number.isSafeInteger(revision) || revision < 1) return json({ error: "The saved project revision is invalid." }, 500);
  const assetId = "media-" + crypto.randomUUID().replace(/-/g, "").slice(0, 16);
  const storageKey = assetId + extension;
  const uploadName = assetId + "-" + filename;
  let releaseAssetId = null;
  try {
    const uploaded = await uploadReleaseAsset(
      env, { id: row.release_id }, uploadName, request.body,
      request.headers.get("content-type") || "application/octet-stream", length
    );
    releaseAssetId = Number(uploaded.id);
    if (!Number.isSafeInteger(releaseAssetId) || releaseAssetId < 1) {
      throw new Error("GitHub returned an invalid media asset ID.");
    }
    const snapshot = JSON.parse(JSON.stringify(project));
    snapshot.revision = revision;
    history.undo.push(snapshot);
    history.undo = history.undo.slice(-10);
    history.redo = [];
    const asset = {
      id: assetId,
      media_type: mediaType,
      file_name: filename,
      storage_key: storageKey,
      size_bytes: length,
      release_asset_id: releaseAssetId,
      folder: "Unsorted",
      tags: []
    };
    if (durationUs !== null) asset.duration_us = durationUs;
    project.assets.push(asset);
    project.revision = revision + 1;
    const update = await env.DB.prepare(
      "UPDATE jobs SET project_json=?,project_revision=?,history_state_json=?,updated_at=? WHERE id=? AND status IN ('completed','failed') AND project_revision=? AND pending_plan_json IS NULL"
    ).bind(
      JSON.stringify(project), project.revision, JSON.stringify(history),
      new Date().toISOString(), id, revision
    ).run();
    if (!update.meta?.changes) throw new Error("The project changed during import. Reopen it and try again.");
    return json({
      asset,
      project_revision: project.revision,
      message: "Media imported and saved to the project. It will be downloaded by the cloud renderer on the next edit."
    }, 201);
  } catch (error) {
    if (releaseAssetId) {
      try {
        await githubRequest(env, "/repos/" + env.GITHUB_OWNER + "/" + env.GITHUB_REPO +
          "/releases/assets/" + releaseAssetId, { method: "DELETE" });
      } catch (_) {}
    }
    return json({ error: "Media import failed: " + error.message.slice(0, 350) }, 502);
  }
}


async function updateMediaPreview(request, env, id, assetId) {
  if (!authorized(request, env)) return json({ error: "Unauthorized." }, 401);
  let body;
  try { body = await request.json(); } catch (_) { return json({ error: "Send valid JSON." }, 400); }
  if (!body || typeof body !== "object" || Array.isArray(body)) return json({ error: "Invalid preview metadata." }, 400);
  const expectedRevision = Number(body.expected_revision);
  if (!Number.isSafeInteger(expectedRevision) || expectedRevision < 1) {
    return json({ error: "A valid expected_revision is required." }, 400);
  }
  const allowedKeys = new Set(["expected_revision", "thumbnail_data_url", "waveform"]);
  if (Object.keys(body).some(key => !allowedKeys.has(key))) return json({ error: "Unsupported preview metadata field." }, 400);
  if (body.thumbnail_data_url !== undefined &&
      (typeof body.thumbnail_data_url !== "string" ||
       body.thumbnail_data_url.length > 12000 ||
       !/^data:image\/jpeg;base64,[A-Za-z0-9+/]+={0,2}$/.test(body.thumbnail_data_url))) {
    return json({ error: "Thumbnail must be a small base64 JPEG preview." }, 400);
  }
  if (body.waveform !== undefined) {
    const samples = body.waveform && body.waveform.samples;
    if (!Array.isArray(samples) || samples.length < 1 || samples.length > 128 ||
        samples.some(value => typeof value !== "number" || !Number.isFinite(value) || value < 0 || value > 1)) {
      return json({ error: "Waveform must contain 1 to 128 peak values between 0 and 1." }, 400);
    }
  }
  if (body.thumbnail_data_url === undefined && body.waveform === undefined) {
    return json({ error: "No preview metadata was supplied." }, 400);
  }
  const row = await env.DB.prepare(
    "SELECT status,project_json,project_revision,history_state_json,pending_plan_json FROM jobs WHERE id=?"
  ).bind(id).first();
  if (!row) return json({ error: "Project not found." }, 404);
  if (!["completed", "failed"].includes(row.status) || !row.project_json || row.pending_plan_json) {
    return json({ error: "Wait until the project is idle before saving media previews." }, 409);
  }
  if (Number(row.project_revision) !== expectedRevision) {
    return json({ error: "Project revision conflict. Reload before saving previews." }, 409);
  }
  let project, history;
  try {
    project = JSON.parse(row.project_json);
    history = JSON.parse(row.history_state_json || '{"undo":[],"redo":[]}');
  } catch (_) { return json({ error: "Saved project or history is invalid." }, 500); }
  const asset = (project.assets || []).find(item => item.id === assetId);
  if (!asset) return json({ error: "Media asset not found." }, 404);
  if (!Array.isArray(history.undo) || !Array.isArray(history.redo)) return json({ error: "Saved project history is invalid." }, 500);
  const snapshot = JSON.parse(JSON.stringify(project));
  snapshot.revision = expectedRevision;
  history.undo.push(snapshot);
  history.undo = history.undo.slice(-10);
  history.redo = [];
  if (body.thumbnail_data_url !== undefined) asset.thumbnail_data_url = body.thumbnail_data_url;
  if (body.waveform !== undefined) asset.waveform = body.waveform;
  project.revision = expectedRevision + 1;
  const update = await env.DB.prepare(
    "UPDATE jobs SET project_json=?,project_revision=?,history_state_json=?,updated_at=? WHERE id=? AND status IN ('completed','failed') AND project_revision=? AND pending_plan_json IS NULL"
  ).bind(JSON.stringify(project), project.revision, JSON.stringify(history), new Date().toISOString(), id, expectedRevision).run();
  if (!update.meta?.changes) return json({ error: "Project changed while saving media previews. Reload and retry." }, 409);
  return json({ project_revision: project.revision, asset_id: assetId, message: "Media preview metadata saved." });
}

async function relinkMediaAsset(request, env, id, assetId) {
  if (!authorized(request, env)) return json({ error: "Unauthorized." }, 401);
  if (!env.GITHUB_TOKEN || !env.GITHUB_OWNER || !env.GITHUB_REPO) {
    return json({ error: "Private media storage is not configured." }, 503);
  }
  const length = Number(request.headers.get("x-file-size") || request.headers.get("content-length") || 0);
  if (!Number.isSafeInteger(length) || length < 1) return json({ error: "A media file with a known size is required." }, 411);
  if (length > MAX_UPLOAD_BYTES) return json({ error: "Each replacement file is limited to 50 MB." }, 413);
  if (!request.body) return json({ error: "The replacement media body is missing." }, 400);
  let filename;
  try { filename = safeFilename(decodeURIComponent(request.headers.get("x-file-name") || "media.bin")); }
  catch (_) { return json({ error: "The replacement filename could not be decoded." }, 400); }
  const extension = fileExtension(filename);
  const mediaType = String(request.headers.get("x-media-type") || "").toLowerCase();
  const allowed = {
    video: new Set([".mp4", ".mov", ".m4v", ".webm", ".mkv"]),
    audio: new Set([".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac"]),
    image: new Set([".jpg", ".jpeg", ".png", ".webp", ".gif"])
  };
  if (!allowed[mediaType] || !allowed[mediaType].has(extension)) return json({ error: "Unsupported replacement media type or extension." }, 415);
  const expectedRevision = Number(request.headers.get("x-expected-revision"));
  if (!Number.isSafeInteger(expectedRevision) || expectedRevision < 1) return json({ error: "A valid expected project revision is required." }, 400);
  const durationHeader = request.headers.get("x-media-duration-us");
  let durationUs = null;
  if (durationHeader) {
    durationUs = Number(durationHeader);
    if (!Number.isSafeInteger(durationUs) || durationUs < 1) return json({ error: "Replacement duration must be a positive integer." }, 400);
  }
  const row = await env.DB.prepare(
    "SELECT status,release_id,input_asset_id,project_json,project_revision,history_state_json,pending_plan_json FROM jobs WHERE id=?"
  ).bind(id).first();
  if (!row) return json({ error: "Project not found." }, 404);
  if (!["completed", "failed"].includes(row.status) || !row.project_json || row.pending_plan_json) {
    return json({ error: "Wait until the project is idle before relinking media." }, 409);
  }
  if (Number(row.project_revision) !== expectedRevision) return json({ error: "Project revision conflict. Reload before relinking." }, 409);
  let project, history;
  try {
    project = JSON.parse(row.project_json);
    history = JSON.parse(row.history_state_json || '{"undo":[],"redo":[]}');
  } catch (_) { return json({ error: "Saved project or history is invalid." }, 500); }
  const asset = (project.assets || []).find(item => item.id === assetId);
  if (!asset) return json({ error: "Media asset not found." }, 404);
  if (asset.media_type !== mediaType) return json({ error: "The replacement file must be the same media type as the missing asset." }, 415);
  const existingBytes = project.assets.reduce((total, item) =>
    total + (Number.isSafeInteger(Number(item.size_bytes)) ? Number(item.size_bytes) : 0), 0);
  const oldBytes = Number(asset.size_bytes || 0);
  if (existingBytes - oldBytes + length > MAX_PROJECT_MEDIA_BYTES) {
    return json({ error: "Project media storage is limited to 200 MB total." }, 413);
  }
  if (!Array.isArray(history.undo) || !Array.isArray(history.redo)) return json({ error: "Saved project history is invalid." }, 500);
  const assetIdNew = "relinked-" + crypto.randomUUID().replace(/-/g, "").slice(0, 16);
  const storageKey = assetIdNew + extension;
  let newReleaseAssetId = null;
  try {
    const uploaded = await uploadReleaseAsset(
      env, { id: row.release_id }, assetIdNew + "-" + filename, request.body,
      request.headers.get("content-type") || "application/octet-stream", length
    );
    newReleaseAssetId = Number(uploaded.id);
    if (!Number.isSafeInteger(newReleaseAssetId) || newReleaseAssetId < 1) throw new Error("GitHub returned an invalid replacement asset ID.");
    const oldReleaseAssetId = Number(asset.release_asset_id || 0);
    const snapshot = JSON.parse(JSON.stringify(project));
    snapshot.revision = expectedRevision;
    history.undo.push(snapshot);
    history.undo = history.undo.slice(-10);
    history.redo = [];
    asset.file_name = filename;
    asset.storage_key = storageKey;
    asset.size_bytes = length;
    asset.release_asset_id = newReleaseAssetId;
    delete asset.thumbnail_data_url;
    delete asset.waveform;
    if (durationUs !== null) asset.duration_us = durationUs;
    else delete asset.duration_us;
    project.revision = expectedRevision + 1;
    const nextInputAssetId = assetId === "source-video" ? newReleaseAssetId : row.input_asset_id;
    const update = await env.DB.prepare(
      "UPDATE jobs SET project_json=?,project_revision=?,history_state_json=?,input_asset_id=?,updated_at=? WHERE id=? AND status IN ('completed','failed') AND project_revision=? AND pending_plan_json IS NULL"
    ).bind(JSON.stringify(project), project.revision, JSON.stringify(history), nextInputAssetId, new Date().toISOString(), id, expectedRevision).run();
    if (!update.meta?.changes) throw new Error("The project changed during relinking. Reload and retry.");
    if (oldReleaseAssetId > 0 && oldReleaseAssetId !== newReleaseAssetId) {
      try { await githubRequest(env, "/repos/" + env.GITHUB_OWNER + "/" + env.GITHUB_REPO + "/releases/assets/" + oldReleaseAssetId, { method: "DELETE" }); } catch (_) {}
    }
    return json({ asset, project_revision: project.revision, message: "Media relinked. All clips still reference the same project asset." });
  } catch (error) {
    if (newReleaseAssetId) {
      try { await githubRequest(env, "/repos/" + env.GITHUB_OWNER + "/" + env.GITHUB_REPO + "/releases/assets/" + newReleaseAssetId, { method: "DELETE" }); } catch (_) {}
    }
    return json({ error: "Media relink failed: " + error.message.slice(0, 350) }, 502);
  }
}

async function getSourceUrl(request, env, id) {
  if (!authorized(request, env)) return json({ error: "Unauthorized." }, 401);
  if (!env.GITHUB_TOKEN || !env.GITHUB_OWNER || !env.GITHUB_REPO) {
    return json({ error: "Private media storage is not configured." }, 503);
  }
  const row = await env.DB.prepare("SELECT input_asset_id FROM jobs WHERE id=?").bind(id).first();
  if (!row) return json({ error: "Job not found." }, 404);
  const endpoint = "https://api.github.com/repos/" + env.GITHUB_OWNER + "/" + env.GITHUB_REPO +
    "/releases/assets/" + row.input_asset_id;
  const response = await fetch(endpoint, {
    headers: {
      authorization: "Bearer " + env.GITHUB_TOKEN,
      accept: "application/octet-stream",
      "x-github-api-version": "2022-11-28",
      "user-agent": "independent-video-editor"
    },
    redirect: "manual"
  });
  if ([301, 302, 303, 307, 308].includes(response.status)) {
    const location = response.headers.get("location");
    if (!location) return json({ error: "GitHub did not provide a media preview location." }, 502);
    return json({ source_url: location, expires_soon: true }, 200);
  }
  return json({ error: "Could not create a private source preview (HTTP " + response.status + ")." }, 502);
}

async function queueManualEdit(request, env, id) {
  if (!authorized(request, env)) return json({ error: "Unauthorized." }, 401);
  if (!env.GITHUB_TOKEN) return json({ error: "The cloud render token is not configured." }, 503);
  let body;
  try { body = await request.json(); } catch (_) { return json({ error: "Send valid JSON." }, 400); }
  const expectedRevision = Number(body.expected_revision);
  const calls = body.tool_calls;
  if (!Number.isInteger(expectedRevision) || expectedRevision < 1) {
    return json({ error: "Load the project and send its current revision before editing." }, 400);
  }
  if (!Array.isArray(calls) || calls.length < 1 || calls.length > 20) {
    return json({ error: "Send between 1 and 20 registered editing operations." }, 400);
  }
  if (calls.some(call => !call || typeof call !== "object" || Array.isArray(call) ||
      typeof call.name !== "string" || !call.arguments || typeof call.arguments !== "object" ||
      Array.isArray(call.arguments) || Object.keys(call).some(key => !["name", "arguments"].includes(key)))) {
    return json({ error: "Each operation must contain only a tool name and an arguments object." }, 400);
  }
  const readOnly = new Set([
    "project.inspect", "media.list", "quality.inspect_media",
    "audio.analyze_media", "media.detect_scenes", "render.export"
  ]);
  if (calls.some(call => readOnly.has(call.name))) {
    return json({ error: "This endpoint accepts editing operations only; inspection and export are handled separately." }, 400);
  }
  const needsApproval = new Set([
    "timeline.delete_clip", "timeline.ripple_delete_clip", "timeline.remove_track"
  ]);
  const required = [...new Set(calls.filter(call => needsApproval.has(call.name)).map(call => call.name))].sort();
  const supplied = Array.isArray(body.confirmed_tools) ? [...new Set(body.confirmed_tools)].sort() : [];
  if (required.length !== supplied.length || required.some(name => !supplied.includes(name)) ||
      supplied.some(name => !needsApproval.has(name))) {
    return json({
      error: required.length
        ? "Confirm the destructive operation in Studio before applying it."
        : "Unexpected destructive-operation confirmation was supplied.",
      required_confirmations: required
    }, 409);
  }
  const row = await env.DB.prepare(
    "SELECT status,project_json,project_revision,pending_plan_json FROM jobs WHERE id=?"
  ).bind(id).first();
  if (!row) return json({ error: "Job not found." }, 404);
  if (!["completed", "failed"].includes(row.status) || !row.project_json) {
    return json({ error: "Wait for the current edit to stop and load a saved project checkpoint before editing." }, 409);
  }
  if (row.pending_plan_json) return json({ error: "Resolve the pending edit before starting a manual operation." }, 409);
  if (Number(row.project_revision) !== expectedRevision) {
    return json({ error: "Project revision conflict. Reload the project before editing.", current_revision: row.project_revision }, 409);
  }
  const pending = {
    mode: "manual",
    summary: "Apply direct Studio editing operations.",
    tool_calls: calls
  };
  const update = await env.DB.prepare(
    "UPDATE jobs SET status='queued',message='Direct Studio edit queued.',instruction='Apply the manually selected Studio operations.',ai_status='queued',pending_plan_json=?,confirmed_tools_json=?,updated_at=? WHERE id=? AND status IN ('completed','failed') AND project_revision=? AND pending_plan_json IS NULL"
  ).bind(
    JSON.stringify(pending), JSON.stringify(supplied), new Date().toISOString(), id, expectedRevision
  ).run();
  if (!update.meta?.changes) return json({ error: "The project changed or another edit started. Reload and try again." }, 409);
  try {
    await dispatchRender(env, id);
  } catch (error) {
    await env.DB.prepare("UPDATE jobs SET status='failed',ai_status='error',message=?,updated_at=? WHERE id=?")
      .bind("Could not start Studio edit: " + error.message.slice(0, 350), new Date().toISOString(), id).run();
    return json({ error: "The Studio edit could not be queued. " + error.message }, 502);
  }
  return json({ job_id: id, status: "queued", message: "Studio edit queued. The cloud editor will apply it and save a new project revision." }, 202);
}

async function requestAiEdit(request, env, id) {
  if (!authorized(request, env)) return json({ error: "Unauthorized." }, 401);
  if (!env.GITHUB_TOKEN) return json({ error: "The cloud render token is not configured." }, 503);
  let body;
  try { body = await request.json(); } catch (_) { return json({ error: "Send valid JSON." }, 400); }
  const instruction = cleanText(body.instruction, 4000), expectedRevision = Number(body.expected_revision);
  if (!instruction) return json({ error: "Describe the edit you want." }, 400);
  if (!Number.isInteger(expectedRevision) || expectedRevision < 1) return json({ error: "A valid expected_revision is required. Load the project before editing." }, 400);
  const row = await env.DB.prepare("SELECT status,project_json,project_revision,ai_status,pending_plan_json FROM jobs WHERE id=?").bind(id).first();
  if (!row) return json({ error: "Job not found." }, 404);
  if (!row.project_json) return json({ error: "The project is not ready for another AI edit." }, 409);
  if (!["completed", "failed"].includes(row.status)) return json({ error: "Wait for the current edit to stop before starting another edit." }, 409);
  if (row.ai_status === "awaiting_confirmation" || row.pending_plan_json) return json({ error: "Approve or reject the pending AI plan before requesting another edit." }, 409);
  if (Number(row.project_revision) !== expectedRevision) return json({ error: "Project revision conflict. Reload the project before editing.", current_revision: row.project_revision }, 409);
  await env.DB.prepare("UPDATE jobs SET status='queued',message=?,instruction=?,ai_status='queued',pending_plan_json=NULL,confirmed_tools_json='[]',updated_at=? WHERE id=?")
    .bind("A new AI edit has been queued.", instruction, new Date().toISOString(), id).run();
  try { await dispatchRender(env, id); }
  catch (error) {
    await env.DB.prepare("UPDATE jobs SET status='failed',ai_status='error',message=?,updated_at=? WHERE id=?").bind("Could not start AI edit: " + error.message.slice(0, 350), new Date().toISOString(), id).run();
    return json({ error: "The AI edit could not be queued. " + error.message }, 502);
  }
  return json({ job_id: id, status: "queued", message: "AI edit queued." }, 202);
}

async function confirmAiEdit(request, env, id) {
  if (!authorized(request, env)) return json({ error: "Unauthorized." }, 401);
  let body;
  try { body = await request.json(); } catch (_) { return json({ error: "Send valid JSON." }, 400); }
  const row = await env.DB.prepare("SELECT status,project_revision,pending_plan_json FROM jobs WHERE id=?").bind(id).first();
  if (!row) return json({ error: "Job not found." }, 404);
  if (row.status !== "running" || !row.pending_plan_json) return json({ error: "There is no pending AI edit awaiting approval." }, 409);
  const expectedRevision = Number(body.expected_revision);
  if (!Number.isInteger(expectedRevision) || expectedRevision !== Number(row.project_revision)) return json({ error: "Project revision changed. Reload before approving this plan." }, 409);
  const plan = JSON.parse(row.pending_plan_json);
  const required = Array.isArray(plan.required_confirmations) ? [...new Set(plan.required_confirmations)] : [];
  const supplied = Array.isArray(body.confirmed_tools) ? [...new Set(body.confirmed_tools)] : [];
  if (!required.length || required.length !== supplied.length || required.some(name => !supplied.includes(name))) return json({ error: "Approval must match every operation listed in the pending plan." }, 400);
  const permitted = new Set(["timeline.delete_clip", "timeline.ripple_delete_clip", "timeline.remove_track"]);
  if (supplied.some(name => !permitted.has(name))) return json({ error: "The pending plan requested an unsupported approval." }, 400);
  await env.DB.prepare("UPDATE jobs SET status='queued',message='Approved AI edit queued for execution.',ai_status='queued',confirmed_tools_json=?,updated_at=? WHERE id=?")
    .bind(JSON.stringify(supplied), new Date().toISOString(), id).run();
  try { await dispatchRender(env, id); }
  catch (error) {
    await env.DB.prepare("UPDATE jobs SET status='failed',ai_status='error',message=?,updated_at=? WHERE id=?").bind("Could not restart approved AI edit: " + error.message.slice(0, 350), new Date().toISOString(), id).run();
    return json({ error: "The approved AI edit could not be queued. " + error.message }, 502);
  }
  return json({ job_id: id, status: "queued", message: "Approved edit queued." }, 202);
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const path = url.pathname;
    try {
      if (request.method === "GET" && path === "/api/health") {
        return json({ ok: true, service: "independent-video-editor", version: "0.2.0" });
      }
      if (path === "/api/v1/projects" && request.method === "GET") return await listProjects(request, env);
      const projectManagerMatch = path.match(/^\/api\/v1\/projects\/([a-f0-9]{32})$/);
      if (projectManagerMatch && request.method === "PATCH") return await renameProject(request, env, projectManagerMatch[1]);
      if (path === "/api/v1/jobs" && request.method === "POST") {
        if (!authorized(request, env)) return json({ error: "Unauthorized. Enter your app/API token." }, 401);
        return await createJob(request, env);
      }
      if (path === "/api/v1/skills" && request.method === "GET") {
        if (!authorized(request, env)) return json({ error: "Unauthorized." }, 401);
        return json({ skills: await listSkills(env) });
      }
      if (path === "/api/v1/skills/import" && request.method === "POST") {
        if (!authorized(request, env)) return json({ error: "Unauthorized." }, 401);
        let body;
        try { body = await request.json(); } catch (_) { return json({ error: "Send valid JSON." }, 400); }
        let skill;
        try { skill = validateSkill(body.skill); }
        catch (error) { return json({ error: error.message }, 400); }
        return await saveSkill(env, skill);
      }
      if (path === "/api/v1/skills/generate" && request.method === "POST") {
        return await generateSkill(request, env);
      }
      const jobMatch = path.match(/^\/api\/v1\/jobs\/([a-f0-9]{32})$/);
      if (jobMatch && request.method === "GET") return await getJob(request, env, jobMatch[1]);
      const downloadMatch = path.match(/^\/api\/v1\/jobs\/([a-f0-9]{32})\/download$/);
      if (downloadMatch && request.method === "GET") return await downloadJob(request, env, downloadMatch[1]);
      const mediaImportMatch = path.match(/^\/api\/v1\/jobs\/([a-f0-9]{32})\/assets$/);
      if (mediaImportMatch && request.method === "POST") return await importMediaAsset(request, env, mediaImportMatch[1]);
      const previewMatch = path.match(/^\/api\/v1\/jobs\/([a-f0-9]{32})\/assets\/([A-Za-z0-9_-]{1,64})\/preview$/);
      if (previewMatch && request.method === "POST") return await updateMediaPreview(request, env, previewMatch[1], previewMatch[2]);
      const relinkMatch = path.match(/^\/api\/v1\/jobs\/([a-f0-9]{32})\/assets\/([A-Za-z0-9_-]{1,64})\/relink$/);
      if (relinkMatch && request.method === "PUT") return await relinkMediaAsset(request, env, relinkMatch[1], relinkMatch[2]);
      const sourceUrlMatch = path.match(/^\/api\/v1\/jobs\/([a-f0-9]{32})\/source-url$/);      const sourceUrlMatch = path.match(/^\/api\/v1\/jobs\/([a-f0-9]{32})\/source-url$/);
      if (sourceUrlMatch && request.method === "GET") return await getSourceUrl(request, env, sourceUrlMatch[1]);
      const manualEditMatch = path.match(/^\/api\/v1\/jobs\/([a-f0-9]{32})\/manual-edit$/);
      if (manualEditMatch && request.method === "POST") return await queueManualEdit(request, env, manualEditMatch[1]);
      const projectMatch = path.match(/^\/api\/v1\/jobs\/([a-f0-9]{32})\/project$/);
      if (projectMatch && request.method === "GET") return await getProject(request, env, projectMatch[1]);
      const confirmEditMatch = path.match(/^\/api\/v1\/jobs\/([a-f0-9]{32})\/ai-edit\/confirm$/);
      if (confirmEditMatch && request.method === "POST") return await confirmAiEdit(request, env, confirmEditMatch[1]);
      const aiEditMatch = path.match(/^\/api\/v1\/jobs\/([a-f0-9]{32})\/ai-edit$/);
      if (aiEditMatch && request.method === "POST") return await requestAiEdit(request, env, aiEditMatch[1]);
      const internalMatch = path.match(/^\/api\/internal\/jobs\/([a-f0-9]{32})$/);
      if (internalMatch && request.method === "GET") return await internalJob(request, env, internalMatch[1]);
      if (internalMatch && request.method === "POST") return await internalCallback(request, env, internalMatch[1]);
      if (path.startsWith("/api/")) return json({ error: "Not found." }, 404);
      return env.ASSETS.fetch(request);
    } catch (error) {
      console.error("Worker request failed:", error?.message || String(error));
      return json({ error: "Request failed: " + cleanText(error?.message || error, 400) }, 500);
    }
  }
};
