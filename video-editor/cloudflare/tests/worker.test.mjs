import test from "node:test";
import assert from "node:assert/strict";
import worker from "../src/index.js";


test("health endpoint is public", async () => {
  const response = await worker.fetch(new Request("https://studio.test/api/health"), {});
  assert.equal(response.status, 200);
  const data = await response.json();
  assert.equal(data.ok, true);
  assert.equal(data.service, "independent-video-editor");
});


test("skills endpoint rejects missing app token", async () => {
  const response = await worker.fetch(new Request("https://studio.test/api/v1/skills"), {});
  assert.equal(response.status, 401);
});


test("internal worker metadata endpoint rejects missing callback secret", async () => {
  const response = await worker.fetch(
    new Request("https://studio.test/api/internal/jobs/" + "a".repeat(32)),
    {}
  );
  assert.equal(response.status, 401);
});


test("job creation requires a declared content length", async () => {
  const response = await worker.fetch(
    new Request("https://studio.test/api/v1/jobs", {
      method: "POST",
      headers: { Authorization: "Bearer test-app-token" },
      body: new ReadableStream({
        start(controller) {
          controller.enqueue(new TextEncoder().encode("video"));
          controller.close();
        }
      }),
      duplex: "half"
    }),
    { APP_API_TOKEN: "test-app-token", GITHUB_TOKEN: "placeholder" }
  );
  assert.equal(response.status, 411);
});


test("invalid imported skill returns a client error", async () => {
  const response = await worker.fetch(
    new Request("https://studio.test/api/v1/skills/import", {
      method: "POST",
      headers: {
        Authorization: "Bearer test-app-token",
        "Content-Type": "application/json"
      },
      body: JSON.stringify({ skill: { id: "Bad ID", name: "Nope" } })
    }),
    { APP_API_TOKEN: "test-app-token" }
  );
  assert.equal(response.status, 400);
});


test("canonical project endpoint rejects missing app token", async () => {
  const response = await worker.fetch(
    new Request("https://studio.test/api/v1/jobs/" + "a".repeat(32) + "/project"), {}
  );
  assert.equal(response.status, 401);
});

test("AI project edit endpoint rejects missing app token", async () => {
  const response = await worker.fetch(
    new Request("https://studio.test/api/v1/jobs/" + "a".repeat(32) + "/ai-edit", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ instruction: "Add a title", expected_revision: 1 })
    }), {}
  );
  assert.equal(response.status, 401);
});


test("AI destructive-operation confirmation endpoint rejects missing app token", async () => {
  const response = await worker.fetch(
    new Request("https://studio.test/api/v1/jobs/" + "a".repeat(32) + "/ai-edit/confirm", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ expected_revision: 1, confirmed_tools: ["timeline.delete_clip"] })
    }), {}
  );
  assert.equal(response.status, 401);
});

test("source preview URL requires the app token", async () => {
  const response = await worker.fetch(
    new Request("https://studio.test/api/v1/jobs/" + "b".repeat(32) + "/source-url"), {}
  );
  assert.equal(response.status, 401);
});

test("manual Studio edit endpoint requires the app token", async () => {
  const response = await worker.fetch(
    new Request("https://studio.test/api/v1/jobs/" + "b".repeat(32) + "/manual-edit", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        expected_revision: 1,
        tool_calls: [{ name: "clip.set_speed", arguments: { clip_id: "main-clip", playback_rate: 1.5 } }]
      })
    }), {}
  );
  assert.equal(response.status, 401);
});

test("project media import route requires the app token", async () => {
  const response = await worker.fetch(
    new Request("https://studio.test/api/v1/jobs/" + "c".repeat(32) + "/assets", {
      method: "POST",
      headers: {
        "X-File-Name": "b-roll.mp4",
        "X-File-Size": "8",
        "X-Media-Type": "video",
        "Content-Type": "video/mp4"
      },
      body: new Uint8Array([1,2,3,4,5,6,7,8])
    }), {}
  );
  assert.equal(response.status, 401);
});


test("project media import stores a private asset and an undoable project revision", async () => {
  const originalFetch = globalThis.fetch;
  const originalFixedLengthStream = globalThis.FixedLengthStream;
  const project = {
    schema_version: 1,
    id: "project-123",
    name: "Import test",
    revision: 2,
    timeline_timebase: "microseconds",
    video_profile: { width: 720, height: 1280, frame_rate: { numerator: 30, denominator: 1 } },
    assets: [{ id: "source-video", media_type: "video", file_name: "source.mp4",
      storage_key: "input-video", size_bytes: 100 }],
    tracks: [],
    transitions: []
  };
  let updateValues = null;
  const env = {
    APP_API_TOKEN: "test-app-token",
    GITHUB_TOKEN: "github-test-token",
    GITHUB_OWNER: "owner",
    GITHUB_REPO: "repo",
    DB: {
      prepare(sql) {
        return {
          bind(...args) {
            if (sql.startsWith("SELECT status,release_id,project_json")) {
              return { first: async () => ({
                status: "completed", release_id: 987,
                project_json: JSON.stringify(project), project_revision: 2,
                history_state_json: JSON.stringify({ undo: [], redo: [] }),
                pending_plan_json: null
              }) };
            }
            if (sql.startsWith("UPDATE jobs SET project_json")) {
              updateValues = args;
              return { run: async () => ({ meta: { changes: 1 } }) };
            }
            throw new Error("Unexpected SQL in media-import test: " + sql);
          }
        };
      }
    }
  };
  globalThis.FixedLengthStream = class extends TransformStream {
    constructor() { super(); }
  };
  globalThis.fetch = async (url, options) => {
    assert.match(String(url), /uploads\.github\.com/);
    assert.equal(options.method, "POST");
    const bytes = await new Response(options.body).arrayBuffer();
    assert.equal(bytes.byteLength, 8);
    return new Response(JSON.stringify({ id: 456 }), {
      status: 201, headers: { "Content-Type": "application/json" }
    });
  };
  try {
    const response = await worker.fetch(
      new Request("https://studio.test/api/v1/jobs/" + "d".repeat(32) + "/assets", {
        method: "POST",
        headers: {
          Authorization: "Bearer test-app-token",
          "X-File-Name": "b-roll.mp4",
          "X-File-Size": "8",
          "X-Media-Type": "video",
          "X-Media-Duration-Us": "3250000",
          "Content-Type": "video/mp4"
        },
        body: new Uint8Array([1,2,3,4,5,6,7,8])
      }),
      env
    );
    assert.equal(response.status, 201);
    const payload = await response.json();
    assert.equal(payload.asset.media_type, "video");
    assert.equal(payload.asset.release_asset_id, 456);
    assert.equal(payload.project_revision, 3);
    const savedProject = JSON.parse(updateValues[0]);
    const savedHistory = JSON.parse(updateValues[2]);
    assert.equal(savedProject.revision, 3);
    assert.equal(savedProject.assets.length, 2);
    assert.equal(savedProject.assets[1].duration_us, 3250000);
    assert.equal(savedProject.assets[1].folder, "Unsorted");
    assert.deepEqual(savedProject.assets[1].tags, []);
    assert.equal(savedHistory.undo.length, 1);
    assert.equal(savedHistory.undo[0].revision, 2);
    assert.deepEqual(savedHistory.redo, []);
  } finally {
    globalThis.fetch = originalFetch;
    if (originalFixedLengthStream === undefined) delete globalThis.FixedLengthStream;
    else globalThis.FixedLengthStream = originalFixedLengthStream;
  }
});


test("saved-project list requires the app token", async () => {
  const response = await worker.fetch(
    new Request("https://studio.test/api/v1/projects"), {}
  );
  assert.equal(response.status, 401);
});

test("saved-project rename requires the app token", async () => {
  const response = await worker.fetch(
    new Request("https://studio.test/api/v1/projects/" + "e".repeat(32), {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: "Renamed", expected_revision: 1 })
    }), {}
  );
  assert.equal(response.status, 401);
});

test("saved-project listing returns safe project summaries", async () => {
  const project = {
    name: "Travel edit",
    revision: 4,
    assets: [{ id: "asset-1" }],
    video_profile: { width: 1080, height: 1920 },
    tracks: [{
      id: "track-1",
      clips: [{ id: "clip-1", start_us: 0, duration_us: 2500000 }]
    }]
  };
  const env = {
    APP_API_TOKEN: "test-app-token",
    DB: {
      prepare(sql) {
        assert.match(sql, /SELECT id,status,updated_at,project_revision,project_json/);
        assert.match(sql, /status='completed'/);
        return { all: async () => ({ results: [{
          id: "f".repeat(32), status: "completed",
          updated_at: "2026-11-24T12:00:00.000Z",
          project_revision: 4, project_json: JSON.stringify(project)
        }] }) };
      }
    }
  };
  const response = await worker.fetch(
    new Request("https://studio.test/api/v1/projects", {
      headers: { Authorization: "Bearer test-app-token" }
    }), env
  );
  assert.equal(response.status, 200);
  const payload = await response.json();
  assert.equal(payload.projects.length, 1);
  assert.equal(payload.projects[0].name, "Travel edit");
  assert.equal(payload.projects[0].revision, 4);
  assert.equal(payload.projects[0].clip_count, 1);
  assert.equal(payload.projects[0].duration_us, 2500000);
  assert.equal(payload.projects[0].width, 1080);
});

test("saved-project rename checks revision and persists an undo snapshot", async () => {
  const project = {
    schema_version: 1, id: "project-1", name: "Old name", revision: 2,
    video_profile: { width: 720, height: 1280, frame_rate: { numerator: 30, denominator: 1 } },
    assets: [], tracks: [], transitions: [], timeline_timebase: "microseconds"
  };
  let updateValues = null;
  const env = {
    APP_API_TOKEN: "test-app-token",
    DB: {
      prepare(sql) {
        return {
          bind(...args) {
            if (sql.startsWith("SELECT status,project_json,project_revision,history_state_json,pending_plan_json")) {
              return { first: async () => ({
                status: "completed",
                project_json: JSON.stringify(project),
                project_revision: 2,
                history_state_json: JSON.stringify({ undo: [], redo: [] }),
                pending_plan_json: null
              }) };
            }
            if (sql.startsWith("UPDATE jobs SET project_json")) {
              updateValues = args;
              return { run: async () => ({ meta: { changes: 1 } }) };
            }
            throw new Error("Unexpected SQL in saved-project rename test: " + sql);
          }
        };
      }
    }
  };
  const response = await worker.fetch(
    new Request("https://studio.test/api/v1/projects/" + "a".repeat(32), {
      method: "PATCH",
      headers: {
        Authorization: "Bearer test-app-token",
        "Content-Type": "application/json"
      },
      body: JSON.stringify({ name: "New name", expected_revision: 2 })
    }), env
  );
  assert.equal(response.status, 200);
  const payload = await response.json();
  assert.equal(payload.project.name, "New name");
  assert.equal(payload.revision, 3);
  const savedProject = JSON.parse(updateValues[0]);
  const savedHistory = JSON.parse(updateValues[2]);
  assert.equal(savedProject.revision, 3);
  assert.equal(savedHistory.undo.length, 1);
  assert.equal(savedHistory.undo[0].name, "Old name");
  assert.equal(savedHistory.undo[0].revision, 2);
  assert.deepEqual(savedHistory.redo, []);
});

test("saved-project rename rejects a stale project revision", async () => {
  const env = {
    APP_API_TOKEN: "test-app-token",
    DB: {
      prepare(sql) {
        return { bind: () => ({
          first: async () => ({
            status: "completed", project_json: JSON.stringify({ name: "Current" }),
            project_revision: 5, history_state_json: '{"undo":[],"redo":[]}',
            pending_plan_json: null
          })
        }) };
      }
    }
  };
  const response = await worker.fetch(
    new Request("https://studio.test/api/v1/projects/" + "b".repeat(32), {
      method: "PATCH",
      headers: {
        Authorization: "Bearer test-app-token",
        "Content-Type": "application/json"
      },
      body: JSON.stringify({ name: "Stale write", expected_revision: 4 })
    }), env
  );
  assert.equal(response.status, 409);
});
