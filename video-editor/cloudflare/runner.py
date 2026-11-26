from __future__ import annotations
import hashlib, json, math, os, re, subprocess, sys, urllib.parse, urllib.request, urllib.error
from pathlib import Path
from typing import Any

EDITOR_ROOT = Path(__file__).resolve().parents[1]
if str(EDITOR_ROOT) not in sys.path:
    sys.path.insert(0, str(EDITOR_ROOT))
from ai_edit_controller import run_ai_edit, validate_tool_plan
from dual_ai_controller import plan_dual_ai_edit
from project_tool_executor import ProjectToolExecutor
from project_model import validate_project

MAX_INPUT_VIDEO = 50 * 1024 * 1024
MAX_RENDER_OUTPUT = 300 * 1024 * 1024
MAX_PROJECT_MEDIA_BYTES = 200 * 1024 * 1024

WORKER_USER_AGENT = "independent-video-editor/0.2 (+https://github.com/promiseoluo66-cmyk/northgate-realty-demo/tree/video-editor-lab)"

class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None

def download_release_asset(owner: str, repo: str, asset_id: int, token: str, path: Path) -> None:
    request = urllib.request.Request(
        f"https://api.github.com/repos/{owner}/{repo}/releases/assets/{asset_id}",
        headers={"Authorization":"Bearer "+token,"Accept":"application/octet-stream",
                 "X-GitHub-Api-Version":"2022-11-28","User-Agent":"independent-video-editor"})
    total = 0
    opener = urllib.request.build_opener(_NoRedirectHandler)
    try:
        response = opener.open(request, timeout=300)
    except urllib.error.HTTPError as error:
        if error.code not in {301,302,303,307,308}: raise
        location = error.headers.get("Location")
        if not location: raise RuntimeError("GitHub asset redirect did not include a download URL.") from error
        response = urllib.request.urlopen(location, timeout=300)
    with response, path.open("wb") as target:
        while chunk := response.read(1024*1024):
            total += len(chunk)
            if total > MAX_INPUT_VIDEO: raise ValueError("Input video exceeds the 50 MB prototype limit.")
            target.write(chunk)
    if total == 0: raise ValueError("GitHub returned an empty source video.")

def _probe_project_asset_duration_us(path: Path, media_type: str) -> int:
    """Probe imported audio/video duration and confirm its expected stream exists."""
    probe = subprocess.run(
        [
            "ffprobe", "-v", "error", "-show_entries",
            "format=duration:stream=codec_type", "-of", "json", str(path),
        ],
        check=True, capture_output=True, text=True, timeout=60,
    )
    try:
        data = json.loads(probe.stdout)
        streams = data.get("streams", [])
        expected = "video" if media_type == "video" else "audio"
        if not any(isinstance(item, dict) and item.get("codec_type") == expected for item in streams):
            raise ValueError(f"Imported {media_type} asset has no readable {expected} stream.")
        duration = float(data.get("format", {}).get("duration", 0))
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError("FFprobe could not read the imported media duration.") from exc
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError("Imported media must have a positive duration.")
    return max(1, int(round(duration * 1_000_000)))


def download_project_media_assets(
    job: dict[str, Any], project: dict[str, Any], output_dir: Path,
    owner: str, repo: str, token: str,
) -> None:
    """Download current and history-referenced private assets for render and redo."""
    root = output_dir.resolve()
    documents = [project]
    history = job.get("history_state") or {}
    for key in ("undo", "redo"):
        documents.extend(item for item in history.get(key, []) if isinstance(item, dict))
    assets_by_id = {}
    for document in documents:
        for asset in document.get("assets", []):
            if asset.get("release_asset_id") is not None:
                assets_by_id[asset.get("id")] = asset
    for asset in assets_by_id.values():
        release_asset_id = asset.get("release_asset_id")
        if release_asset_id is None:
            continue
        storage_key = asset.get("storage_key")
        if (
            not isinstance(storage_key, str)
            or not storage_key
            or Path(storage_key).name != storage_key
            or storage_key in {".", "..", "input-video"}
        ):
            raise ValueError("Imported asset contains an unsafe storage key.")
        target = (root / storage_key).resolve()
        try:
            target.relative_to(root)
        except ValueError as exc:
            raise ValueError("Imported asset storage path escapes the render directory.") from exc
        target.parent.mkdir(parents=True, exist_ok=True)
        download_release_asset(owner, repo, int(release_asset_id), token, target)
        media_type = asset.get("media_type")
        if media_type in {"video", "audio"}:
            asset["duration_us"] = _probe_project_asset_duration_us(target, media_type)


def require_private_storage_repository(owner: str, repo: str, token: str) -> None:
    """Fail closed unless the configured Release storage repository is private."""
    request = urllib.request.Request(
        f"https://api.github.com/repos/{owner}/{repo}",
        headers={"Authorization": "Bearer " + token,
                 "Accept": "application/vnd.github+json",
                 "X-GitHub-Api-Version": "2022-11-28",
                 "User-Agent": WORKER_USER_AGENT},
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        metadata = json.loads(response.read().decode("utf-8"))
    if metadata.get("private") is not True:
        raise ValueError(
            "Generated media storage must be a private GitHub repository. "
            "The configured repository is public or its visibility could not be verified."
        )


def upload_release_asset(owner: str, repo: str, release_id: int, token: str,
                         path: Path, asset_name: str | None = None,
                         content_type: str = "video/mp4") -> int:
    require_private_storage_repository(owner, repo, token)
    size = path.stat().st_size
    if size <= 0 or size > MAX_RENDER_OUTPUT:
        raise ValueError("Edited video is empty or larger than the 300 MB output limit.")
    name = urllib.parse.quote(asset_name or path.name, safe="")
    request = urllib.request.Request(
        f"https://uploads.github.com/repos/{owner}/{repo}/releases/{release_id}/assets?name={name}",
        data=path.read_bytes(), method="POST",
        headers={"Authorization":"Bearer "+token,"Accept":"application/vnd.github+json",
                 "Content-Type":content_type,"Content-Length":str(size),
                 "X-GitHub-Api-Version":"2022-11-28","User-Agent":"independent-video-editor"})
    with urllib.request.urlopen(request, timeout=600) as response:
        result = json.loads(response.read().decode("utf-8"))
    return int(result["id"])

def delete_release_asset(owner: str, repo: str, asset_id: int, token: str) -> None:
    request = urllib.request.Request(
        f"https://api.github.com/repos/{owner}/{repo}/releases/assets/{asset_id}",
        method="DELETE",
        headers={"Authorization": "Bearer " + token,
                 "Accept": "application/vnd.github+json",
                 "X-GitHub-Api-Version": "2022-11-28",
                 "User-Agent": "independent-video-editor"},
    )
    try:
        with urllib.request.urlopen(request, timeout=60):
            pass
    except Exception:
        # Orphan cleanup is best-effort; never hide the original transaction error.
        pass


def persist_generated_project_assets(
    executor: ProjectToolExecutor, output_dir: Path, owner: str, repo: str,
    release_id: int, token: str,
) -> list[int]:
    """Upload generated media privately, then attach IDs to the current project/history."""
    root = output_dir.resolve()
    uploaded: list[int] = []
    project_assets = executor.get_project().get("assets", [])
    pending = [
        item for item in project_assets
        if item.get("generated") is True and item.get("release_asset_id") is None
    ]
    current_total = sum(int(item.get("size_bytes") or 0) for item in project_assets)
    if current_total > MAX_PROJECT_MEDIA_BYTES:
        raise ValueError("Project media storage is limited to 200 MB total.")
    persisted: list[tuple[str, int]] = []
    try:
        for asset in pending:
            storage_key = asset.get("storage_key")
            if not isinstance(storage_key, str) or not storage_key or Path(storage_key).name != storage_key:
                raise ValueError("Generated media contains an unsafe storage key.")
            path = (root / storage_key).resolve()
            try:
                path.relative_to(root)
            except ValueError as exc:
                raise ValueError("Generated media path escapes the private asset directory.") from exc
            if not path.is_file():
                raise ValueError("Generated media file is missing before private upload.")
            size = path.stat().st_size
            if size <= 0 or size > MAX_INPUT_VIDEO:
                raise ValueError("Each generated project asset must be between 1 byte and 50 MB.")
            extension = path.suffix.lower()
            content_types = {
                ".m4a": "audio/mp4", ".mp3": "audio/mpeg", ".wav": "audio/wav",
                ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
                ".webp": "image/webp",
            }
            content_type = content_types.get(extension)
            if content_type is None:
                raise ValueError("Generated media format is not supported for private storage.")
            remote_id = upload_release_asset(
                owner, repo, release_id, token, path,
                asset_name="project-" + str(asset["id"]) + "-" + path.name,
                content_type=content_type,
            )
            uploaded.append(remote_id)
            persisted.append((str(asset["id"]), remote_id))
        # Only mutate project/history after every upload succeeded.
        for media_id, remote_id in persisted:
            executor.set_persisted_asset_id(media_id, remote_id)
    except Exception:
        for remote_id in uploaded:
            delete_release_asset(owner, repo, remote_id, token)
        raise
    return uploaded


def callback(worker_url: str, secret: str, job_id: str, status: str, message: str,
             output_asset_id: int | None = None, **extra: Any) -> None:
    body: dict[str, Any] = {"status":status,"message":message}
    if output_asset_id is not None: body["output_asset_id"] = output_asset_id
    body.update(extra)
    body["run_url"] = (os.environ.get("GITHUB_SERVER_URL","https://github.com")+"/"+
                       os.environ.get("GITHUB_REPOSITORY","")+"/actions/runs/"+
                       os.environ.get("GITHUB_RUN_ID",""))
    request = urllib.request.Request(worker_url.rstrip("/")+"/api/internal/jobs/"+job_id,
        data=json.dumps(body).encode("utf-8"), method="POST",
        headers={"Content-Type":"application/json","X-Callback-Secret":secret,
                 "User-Agent":WORKER_USER_AGENT})
    with urllib.request.urlopen(request, timeout=90) as response:
        result = json.loads(response.read().decode("utf-8"))
    if not result.get("ok"): raise RuntimeError("Cloudflare job callback was rejected.")


def inspect_render_output(path: Path) -> dict[str, Any]:
    """Create a technical render receipt; flags are review warnings, not semantic verdicts."""
    size = path.stat().st_size
    if size <= 0 or size > MAX_RENDER_OUTPUT:
        raise ValueError("Rendered video is empty or exceeds the 300 MB output limit.")
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries",
         "format=duration:stream=codec_type,codec_name,width,height",
         "-of", "json", str(path)],
        check=True, capture_output=True, text=True, timeout=60,
    )
    data = json.loads(probe.stdout)
    streams = data.get("streams", [])
    video = next((item for item in streams if item.get("codec_type") == "video"), None)
    if not video:
        raise ValueError("Rendered output has no readable video stream.")
    duration = float(data.get("format", {}).get("duration") or 0)
    if not 0 < duration <= 1800:
        raise ValueError("Rendered output duration is missing or exceeds the 30-minute limit.")
    scan_seconds = min(duration, 1800.0)
    video_check = subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "info", "-i", str(path),
         "-t", f"{scan_seconds:.3f}", "-vf",
         "blackdetect=d=0.5:pix_th=0.10,freezedetect=n=-60dB:d=2",
         "-an", "-f", "null", "-"],
        check=True, capture_output=True, text=True, timeout=240,
    )
    video_log = video_check.stderr or ""
    black = [
        {"start_seconds": float(start), "end_seconds": float(end)}
        for start, end in re.findall(
            r"black_start:([0-9.]+)\s+black_end:([0-9.]+)", video_log
        )
    ]
    freeze_starts = [float(value) for value in re.findall(
        r"freeze_start:([0-9.]+)", video_log
    )]
    freeze_ends = [float(value) for value in re.findall(
        r"freeze_end:([0-9.]+)", video_log
    )]
    freezes = [
        {"start_seconds": start, "end_seconds": end}
        for start, end in zip(freeze_starts, freeze_ends) if end >= start
    ]
    audio_streams = [item for item in streams if item.get("codec_type") == "audio"]
    silence = []
    if audio_streams:
        audio_check = subprocess.run(
            ["ffmpeg", "-hide_banner", "-loglevel", "info", "-i", str(path),
             "-map", "0:a:0", "-t", f"{scan_seconds:.3f}",
             "-af", "silencedetect=n=-50dB:d=0.5", "-f", "null", "-"],
            check=True, capture_output=True, text=True, timeout=240,
        )
        audio_log = audio_check.stderr or ""
        starts = re.findall(r"silence_start:\s*([0-9.]+)", audio_log)
        ends = re.findall(r"silence_end:\s*([0-9.]+)", audio_log)
        silence = [
            {"start_seconds": float(start), "end_seconds": float(end)}
            for start, end in zip(starts, ends)
        ]
    flags = []
    if black:
        flags.append("black_intervals_detected")
    if freezes:
        flags.append("freeze_intervals_detected")
    if silence:
        flags.append("silence_intervals_detected")
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return {
        "technical_status": "passed",
        "file_size_bytes": size,
        "sha256": digest.hexdigest(),
        "duration_seconds": round(duration, 3),
        "video": {
            "codec": video.get("codec_name"),
            "width": video.get("width"),
            "height": video.get("height"),
        },
        "audio_stream_count": len(audio_streams),
        "analysis_coverage_seconds": round(scan_seconds, 3),
        "black_intervals": black[:100],
        "freeze_intervals": freezes[:100],
        "silence_intervals": silence[:100],
        "review_flags": flags,
        "semantic_visual_assessment": "not_evaluated",
        "semantic_audio_assessment": "not_evaluated",
        "limitations": [
            "Black, freeze and silence detections are technical review signals, not proof of an editing defect.",
            "A technically valid file is not a semantic or artistic quality approval.",
            "The full output is scanned up to the renderer's 30-minute limit.",
        ],
    }

def _probe_media(path: Path) -> dict[str,int]:
    result = subprocess.run(["ffprobe","-v","error","-show_entries",
        "format=duration:stream=codec_type,width,height,avg_frame_rate","-of","json",str(path)],
        check=True,capture_output=True,text=True,timeout=60)
    data=json.loads(result.stdout)
    stream=next((x for x in data.get("streams",[]) if x.get("codec_type")=="video"),None)
    if not stream: raise ValueError("The uploaded file does not contain a video stream.")
    duration=float(data.get("format",{}).get("duration",0))
    if duration<=0: raise ValueError("Could not read a positive video duration.")
    try:
        numerator,denominator=(int(x) for x in str(stream.get("avg_frame_rate") or "30/1").split("/",1))
        if numerator<=0 or denominator<=0 or numerator/denominator>120: raise ValueError
    except (ValueError,ZeroDivisionError): numerator,denominator=30,1
    return {"duration_us":max(1,round(duration*1_000_000)),
            "source_width":int(stream.get("width") or 1280),
            "source_height":int(stream.get("height") or 720),
            "fps_num":numerator,"fps_den":denominator}

def _build_initial_project(job: dict[str,Any], *, duration_us:int, fps_num:int, fps_den:int,
                           source_width:int, source_height:int, size_bytes:int) -> dict[str,Any]:
    skill=job.get("skill") or {}
    settings=skill.get("default_settings") if isinstance(skill,dict) else {}
    settings=settings if isinstance(settings,dict) else {}
    width,height=int(settings.get("width") or 720),int(settings.get("height") or 1280)
    if not (144<=width<=1920 and 144<=height<=1920): width,height=720,1280
    filename=str(job.get("input_filename") or "input-video")
    document={
        "schema_version":1,"id":"project-"+str(job["job_id"])[:48],
        "name":filename[:120] or "Video project","revision":1,
        "timeline_timebase":"microseconds",
        "video_profile":{"width":width,"height":height,
                         "frame_rate":{"numerator":fps_num,"denominator":fps_den}},
        "assets":[{"id":"source-video","media_type":"video","file_name":filename[:255],
                   "storage_key":"input-video","size_bytes":max(1,int(size_bytes)),
                   "duration_us":int(duration_us)}],
        "tracks":[
            {"id":"main-video","type":"video","name":"Main video","order":0,
             "enabled":True,"muted":False,"locked":False,
             "clips":[{"id":"main-clip","kind":"video","media_id":"source-video",
                       "start_us":0,"duration_us":int(duration_us),"source_in_us":0,
                       "source_out_us":int(duration_us),"playback_rate":1.0,
                       "effects":[],"keyframes":[]}]},
            {"id":"overlays","type":"overlay","name":"Overlays","order":1,"clips":[]},
            {"id":"titles","type":"text","name":"Titles and captions","order":2,"clips":[]},
            {"id":"music","type":"audio","name":"Music and audio","order":3,"clips":[]},
        ],
        "transitions":[],
        "metadata":{"source_width":source_width,"source_height":source_height,
                    "created_by":"studio-upload"}}
    return validate_project(document)

def _load_project(job:dict[str,Any],source:Path)->dict[str,Any]:
    raw=job.get("project_json")
    if raw: return validate_project(json.loads(raw) if isinstance(raw,str) else raw)
    return _build_initial_project(job,**_probe_media(source),size_bytes=source.stat().st_size)

def _make_plan(
    instruction: str,
    executor: ProjectToolExecutor,
    pending_plan: Any,
    source_video: Path,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    if pending_plan:
        plan = validate_tool_plan(pending_plan)
        if isinstance(pending_plan, dict) and pending_plan.get("mode") == "manual":
            video_analysis = {
                "analysis_provider": "not_run_manual_registered_operation",
                "analysis_status": "not_run",
                "reason": "The user selected a specific registered editing operation in Studio."
            }
        else:
            video_analysis = (
                pending_plan.get("video_analysis")
                if isinstance(pending_plan, dict) else None
            )
    else:
        collaboration = plan_dual_ai_edit(instruction, source_video, executor)
        plan = collaboration["plan"]
        video_analysis = collaboration["video_analysis"]

    # Keep project mutation and video rendering as separate transactions.
    # The caller checkpoints the edited project before starting the expensive export,
    # so a render failure cannot discard the user's latest edit.
    calls = [call for call in plan["tool_calls"] if call["name"] != "render.export"]
    return validate_tool_plan({"summary": plan["summary"], "tool_calls": calls}), video_analysis

def main()->int:
    job_id=os.environ["JOB_ID"]; worker_url=os.environ["CF_WORKER_URL"]
    callback_secret=os.environ["CF_CALLBACK_SECRET"]; github_token=os.environ["GH_TOKEN"]
    owner=os.environ["GITHUB_OWNER"]; repo=os.environ["GITHUB_REPOSITORY_NAME"]
    if not job_id or not worker_url or not callback_secret or not github_token:
        raise RuntimeError("A required worker environment variable is missing.")
    output_dir=Path("output"); output_dir.mkdir(parents=True,exist_ok=True)
    source,edited=output_dir/"input-video",output_dir/"edited-video.mp4"
    metadata_request=urllib.request.Request(worker_url.rstrip("/")+"/api/internal/jobs/"+job_id,
        headers={"X-Callback-Secret":callback_secret,
                 "User-Agent":WORKER_USER_AGENT})
    executor = None
    try:
        with urllib.request.urlopen(metadata_request,timeout=90) as response:
            job=json.loads(response.read().decode("utf-8"))
        if job.get("error"): raise RuntimeError(job["error"])
        pending_plan=job.get("pending_plan")
        if isinstance(pending_plan,str):
            pending_plan=json.loads(pending_plan)
        manual_mode=isinstance(pending_plan,dict) and pending_plan.get("mode")=="manual"
        if not manual_mode:
            if not os.environ.get("GEMINI_API_KEY") and not os.environ.get("GROQ_API_KEY"):
                raise RuntimeError("No visual AI provider is configured. Add GEMINI_API_KEY or GROQ_API_KEY to GitHub Actions secrets.")
            if not os.environ.get("GONKA_ROUTER_API_KEY"):
                raise RuntimeError("GONKA_ROUTER_API_KEY is missing. Add it to GitHub Actions secrets to enable DeepSeek editing intelligence.")
        callback(worker_url,callback_secret,job_id,"running",
            "Applying your direct Studio editing operation and rendering the updated project."
            if manual_mode else
            "Visual AI is analysing the video; DeepSeek is preparing the registered editing operations.",
            ai_status="queued" if manual_mode else "planning")
        download_release_asset(owner,repo,int(job["input_asset_id"]),github_token,source)
        project=_load_project(job,source)
        download_project_media_assets(job,project,output_dir,owner,repo,github_token)
        project=validate_project(project)
        executor=ProjectToolExecutor(project,asset_root=output_dir,output_dir=output_dir,
                                     render_timeout_seconds=1200,
                                     history_state=job.get("history_state"))

        # Save the initialized/base project before AI planning or any render work.
        # This gives recovery a valid revision even if planning or rendering stops early.
        callback(worker_url,callback_secret,job_id,"running",
            "Project initialized and autosaved as revision "+str(executor.revision)+".",
            project_json=executor.get_project(),
            project_revision=executor.revision,
            history_state=executor.get_history_state(),
            ai_status="planning",pending_plan=None)

        plan,video_analysis=_make_plan(
            str(job.get("instruction") or ""),executor,pending_plan,source
        )
        confirmed=set(job.get("confirmed_tools") or [])
        confirmed.add("render.export")  # explicit submit action authorizes export
        result=run_ai_edit(str(job.get("instruction") or ""),executor,
            expected_revision=int(job.get("project_revision") or project["revision"]),
            confirmed_tools=confirmed,preferred_plan=plan)
        if result.get("status")=="awaiting_confirmation":
            pending={"summary":result.get("summary",""),"tool_calls":result.get("tool_calls",[]),
                     "required_confirmations":result.get("required_confirmations",[]),
                     "video_analysis":video_analysis}
            callback(worker_url,callback_secret,job_id,"running",
                "The AI prepared an edit, but it needs your approval before changing the project.",
                project_json=project,project_revision=executor.revision,
                history_state=executor.get_history_state(),
                ai_status="awaiting_confirmation",pending_plan=pending)
            print(json.dumps({"job_id":job_id,"status":"awaiting_confirmation","pending":pending}))
            return 0
        if not result.get("ok"):
            raise RuntimeError(result.get("error") or "The AI edit could not be applied safely.")
        execution=result["execution"]
        # Generated audio/still assets must reach private Release storage before
        # their project references are checkpointed. The executor attaches the
        # returned IDs to current state and history snapshots for later undo/redo.
        persist_generated_project_assets(
            executor, output_dir, owner, repo, int(job["release_id"]), github_token
        )
        project_document=executor.get_project()

        # Durable autosave boundary: persist the fully validated edit transaction
        # before rendering. If export or upload fails, this revision remains recoverable.
        callback(worker_url,callback_secret,job_id,"running",
            "Edit applied and saved as revision "+str(project_document["revision"])+
            ". Rendering the saved checkpoint now.",
            project_json=project_document,
            project_revision=project_document["revision"],
            history_state=executor.get_history_state(),
            ai_status="applied",pending_plan=None)

        export_plan = {
            "summary": "Render the latest saved project checkpoint.",
            "tool_calls": [{
                "name": "render.export",
                "arguments": {"output_filename": "edited-video.mp4"}
            }]
        }
        export_result = run_ai_edit(
            "Render the saved project checkpoint.",
            executor,
            expected_revision=executor.revision,
            confirmed_tools={"render.export"},
            preferred_plan=export_plan,
        )
        if not export_result.get("ok"):
            raise RuntimeError(export_result.get("error") or "The saved project could not be rendered.")
        export=next((item["result"] for item in export_result["execution"].get("results",[])
                     if item.get("name")=="render.export"),None)
        output_path=Path(export["output_path"]) if export else edited
        if not output_path.is_file(): raise RuntimeError("The MLT export tool did not create the requested MP4.")
        render_receipt = inspect_render_output(output_path)
        run_id=os.environ.get("GITHUB_RUN_ID","local")
        asset_name="edited-video-"+"".join(ch for ch in run_id if ch.isalnum())[:32]+".mp4"
        output_asset_id=upload_release_asset(owner,repo,int(job["release_id"]),github_token,
                                             output_path,asset_name=asset_name)
        visual_provider = (
            video_analysis.get("analysis_provider", "not_run")
            if isinstance(video_analysis, dict) else "not_run"
        )
        report={"job_id":job_id,"engine":"mlt-project-renderer",
            "planner":"registered-manual-tool-operation" if manual_mode else "visual-analysis+deepseek-tool-plan",
            "agents":{
                "visual_analysis":visual_provider,
                "editing_reasoning":"User-selected registered operation" if manual_mode else "DeepSeek via GonkaRouter"
            },
            "video_analysis":video_analysis,"project_id":project_document["id"],
            "project_revision":project_document["revision"],"plan_summary":result.get("summary"),
            "tool_calls":result.get("tool_calls"),"output_asset_id":output_asset_id,
            "render_receipt":render_receipt}
        (output_dir/"report.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
        callback(worker_url,callback_secret,job_id,"completed",
            "Studio operation applied and MLT export completed. The saved project is ready."
            if manual_mode else
            "Visual analysis, DeepSeek editing and MLT export completed. Open the project in Studio to continue editing.",
            output_asset_id,project_json=project_document,
            project_revision=project_document["revision"],
            history_state=executor.get_history_state(),
            ai_status="applied",pending_plan=None)
        print(json.dumps(report)); return 0
    except Exception as exc:
        try:
            checkpoint = {}
            if executor is not None:
                checkpoint = {
                    "project_json": executor.get_project(),
                    "project_revision": executor.revision,
                    "history_state": executor.get_history_state(),
                    "ai_status": "error",
                    "pending_plan": None,
                }
            callback(worker_url,callback_secret,job_id,"failed",
                "AI/MLT render failed: "+(str(exc)[:350] or type(exc).__name__),
                **checkpoint)
        except Exception as callback_error:
            print("Could not report failure to Cloudflare: "+str(callback_error),file=sys.stderr)
        raise
    finally:
        try: source.unlink(missing_ok=True)
        except OSError: pass

if __name__=="__main__":
    try: raise SystemExit(main())
    except Exception as exc:
        print(f"AI/MLT RENDER WORKER ERROR: {type(exc).__name__}: {exc}",file=sys.stderr)
        raise
