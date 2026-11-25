"""Collaborative visual-analysis + DeepSeek-editing controller.

Gemini can inspect the full source video. When it is unavailable, an optional
Groq vision fallback reviews timestamped still frames. DeepSeek receives the
validated findings and plans through the same registered tool catalogue.
Only ProjectToolExecutor can apply operations; model output is never evaluated
as code or sent to a shell.
"""
from __future__ import annotations

import base64
import json
import mimetypes
import os
import subprocess
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Callable

from ai_edit_controller import AIEditControllerError, validate_tool_plan
from project_tool_executor import ProjectToolExecutor
from tool_registry import get_tool_catalog, validate_tool_call


class DualAIControllerError(AIEditControllerError):
    """Raised when either AI agent cannot complete its assigned stage."""


def _project_context(executor: ProjectToolExecutor) -> dict[str, Any]:
    project = executor.get_project()
    context = executor.inspect()
    context["assets"] = [
        {key: value for key, value in asset.items() if key != "storage_key"}
        for asset in project["assets"]
    ]
    context["transitions"] = project.get("transitions", [])
    return context


def _available_tool_names() -> set[str]:
    return {item["name"] for item in get_tool_catalog()}


_RETRYABLE_HTTP_STATUS = {408, 425, 429, 500, 502, 503, 504}


def _request_json(request: urllib.request.Request, *, timeout: int, stage: str) -> dict[str, Any]:
    """Request JSON with bounded retries for temporary provider/network failures."""
    try:
        max_attempts = int(os.environ.get("AI_HTTP_MAX_ATTEMPTS", "3"))
    except ValueError:
        max_attempts = 3
    max_attempts = max(1, min(max_attempts, 5))

    raw = ""
    for attempt in range(max_attempts):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                raw = response.read().decode("utf-8")
            break
        except urllib.error.HTTPError as exc:
            detail = exc.read(2000).decode("utf-8", errors="replace")
            if exc.code in _RETRYABLE_HTTP_STATUS and attempt + 1 < max_attempts:
                retry_after = ""
                try:
                    retry_after = exc.headers.get("Retry-After", "")
                except Exception:
                    pass
                try:
                    delay = float(retry_after) if retry_after else float(2 ** attempt)
                except (TypeError, ValueError):
                    delay = float(2 ** attempt)
                delay = max(0.0, min(delay, 10.0))
                print(
                    f"{stage}: temporary HTTP {exc.code}; retrying "
                    f"({attempt + 2}/{max_attempts}) after {delay:g}s.",
                    flush=True,
                )
                time.sleep(delay)
                continue
            raise DualAIControllerError(
                f"{stage} returned HTTP {exc.code}: {detail[:1200]}"
            ) from exc
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as exc:
            if attempt + 1 < max_attempts:
                delay = min(float(2 ** attempt), 8.0)
                print(
                    f"{stage}: temporary network failure; retrying "
                    f"({attempt + 2}/{max_attempts}) after {delay:g}s.",
                    flush=True,
                )
                time.sleep(delay)
                continue
            raise DualAIControllerError(
                f"{stage} failed after {max_attempts} attempts: "
                f"{type(exc).__name__}: {exc}"
            ) from exc
        except Exception as exc:
            raise DualAIControllerError(
                f"{stage} failed: {type(exc).__name__}: {exc}"
            ) from exc

    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise DualAIControllerError(f"{stage} returned invalid JSON.") from exc
    if not isinstance(value, dict):
        raise DualAIControllerError(f"{stage} returned an unexpected response.")
    if isinstance(value.get("error"), dict):
        message = str(value["error"].get("message") or "provider error")
        raise DualAIControllerError(f"{stage} failed: {message[:1200]}")
    return value

def _upload_video_to_gemini(video_path: Path, api_key: str) -> dict[str, str]:
    if not video_path.is_file():
        raise DualAIControllerError("The source video is missing before Gemini analysis.")
    size = video_path.stat().st_size
    if size <= 0 or size > 50 * 1024 * 1024:
        raise DualAIControllerError("Gemini analysis supports source videos up to the 50 MB runner limit.")
    mime_type = mimetypes.guess_type(video_path.name)[0] or "video/mp4"
    start_payload = json.dumps({
        "file": {"display_name": video_path.name[:120]}
    }).encode("utf-8")
    start_request = urllib.request.Request(
        "https://generativelanguage.googleapis.com/upload/v1beta/files",
        data=start_payload,
        method="POST",
        headers={
            "x-goog-api-key": api_key,
            "X-Goog-Upload-Protocol": "resumable",
            "X-Goog-Upload-Command": "start",
            "X-Goog-Upload-Header-Content-Length": str(size),
            "X-Goog-Upload-Header-Content-Type": mime_type,
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(start_request, timeout=60) as response:
            upload_url = response.headers.get("x-goog-upload-url")
    except Exception as exc:
        raise DualAIControllerError(
            f"Gemini video upload could not be started: {type(exc).__name__}: {exc}"
        ) from exc
    if not upload_url or not upload_url.startswith("https://"):
        raise DualAIControllerError("Gemini did not return a valid resumable upload URL.")

    upload_request = urllib.request.Request(
        upload_url,
        data=video_path.read_bytes(),
        method="POST",
        headers={
            "Content-Length": str(size),
            "X-Goog-Upload-Offset": "0",
            "X-Goog-Upload-Command": "upload, finalize",
        },
    )
    uploaded = _request_json(upload_request, timeout=300, stage="Gemini video upload")
    file_info = uploaded.get("file")
    if not isinstance(file_info, dict):
        raise DualAIControllerError("Gemini video upload did not return a file record.")
    name = file_info.get("name")
    uri = file_info.get("uri")
    if not isinstance(name, str) or not name.startswith("files/"):
        raise DualAIControllerError("Gemini video upload returned an invalid file identifier.")
    if not isinstance(uri, str) or not uri.startswith("https://"):
        raise DualAIControllerError("Gemini video upload returned an invalid file URI.")
    return {"name": name, "uri": uri, "mime_type": str(file_info.get("mimeType") or mime_type)}


def _wait_for_gemini_video(file_name: str, api_key: str) -> None:
    encoded_name = urllib.parse.quote(file_name, safe="/")
    url = "https://generativelanguage.googleapis.com/v1beta/" + encoded_name
    deadline = time.monotonic() + int(os.environ.get("GEMINI_FILE_PROCESSING_TIMEOUT_SECONDS", "600"))
    while time.monotonic() < deadline:
        request = urllib.request.Request(url, headers={"x-goog-api-key": api_key})
        info = _request_json(request, timeout=30, stage="Gemini video processing check")
        state = str(info.get("state") or "").upper()
        if state == "ACTIVE":
            return
        if state == "FAILED":
            raise DualAIControllerError("Gemini could not process the uploaded video.")
        time.sleep(5)
    raise DualAIControllerError("Gemini video processing timed out before the file became ACTIVE.")


def _delete_gemini_video(file_name: str, api_key: str) -> None:
    encoded_name = urllib.parse.quote(file_name, safe="/")
    request = urllib.request.Request(
        "https://generativelanguage.googleapis.com/v1beta/" + encoded_name,
        method="DELETE",
        headers={"x-goog-api-key": api_key},
    )
    try:
        with urllib.request.urlopen(request, timeout=30):
            pass
    except Exception:
        # Gemini file cleanup must not hide the primary analysis or planning result.
        pass


def build_gemini_video_prompt(instruction: str, executor: ProjectToolExecutor) -> str:
    return (
        "You are Gemini, the visual video-intelligence agent in a collaborative video editor. "
        "You MUST inspect the actual attached video, not infer its contents from the filename. "
        "Analyse scenes, objects, actions, camera movement, motion changes, visual style, "
        "important moments, and audible speech/music/sound when intelligible. "
        "Use precise timestamps in integer microseconds from the beginning of the video. "
        "Identify useful cut points and explain why they matter. "
        "You and the DeepSeek editing agent share the full registered tool catalogue below. "
        "You must return candidate registered tool calls when visual evidence supports them; "
        "these are passed to DeepSeek for reconciliation and final execution planning. "
        "Never invent a tool, ID, track, asset, timing, or unsupported editing capability. "
        "Do not claim to have changed the project. DeepSeek will create the final plan and "
        "the validated project executor will apply it. Return JSON only with exactly this shape: "
        '{"summary":"...","scenes":[{"start_us":0,"end_us":1000000,"description":"...",'
        '"objects":["..."],"movement":"...","audio_notes":"..."}],'
        '"key_moments":[{"time_us":0,"description":"...","editing_value":"..."}],'
        '"editing_notes":["..."],"tool_suggestions":[{"name":"registered.tool",'
        '"arguments":{},"reason":"..."}]}. '
        "Every array may be empty when evidence is unavailable. "
        "Do not add markdown fences or explanatory text outside the JSON.\n\n"
        "USER EDIT REQUEST:\n" + instruction.strip()[:4000]
        + "\n\nCURRENT PROJECT AND MEDIA IDS:\n"
        + json.dumps(_project_context(executor), ensure_ascii=False, separators=(",", ":"))
        + "\n\nSHARED REGISTERED TOOL CATALOGUE:\n"
        + json.dumps(get_tool_catalog(), ensure_ascii=False, separators=(",", ":"))
    )


def validate_video_analysis(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise DualAIControllerError("Visual analysis must be a JSON object.")
    summary = data.get("summary", "")
    if not isinstance(summary, str) or len(summary) > 1200:
        raise DualAIControllerError("Visual analysis summary must be text up to 1,200 characters.")
    provider = data.get("analysis_provider", "Gemini")
    if not isinstance(provider, str) or not provider.strip() or len(provider) > 120:
        raise DualAIControllerError("Visual analysis provider label is invalid.")
    coverage_notes = data.get("coverage_notes", "")
    if not isinstance(coverage_notes, str) or len(coverage_notes) > 600:
        raise DualAIControllerError("Visual analysis coverage notes must be text up to 600 characters.")
    normalized: dict[str, Any] = {
        "summary": summary.strip(),
        "analysis_provider": provider.strip(),
        "coverage_notes": coverage_notes.strip(),
    }
    for key, limit in (("scenes", 120), ("key_moments", 200), ("editing_notes", 100)):
        items = data.get(key, [])
        if not isinstance(items, list) or len(items) > limit:
            raise DualAIControllerError(f"Visual analysis field {key} must be an array of at most {limit} items.")
        normalized[key] = items

    for index, scene in enumerate(normalized["scenes"]):
        if not isinstance(scene, dict):
            raise DualAIControllerError(f"Visual scene {index + 1} is invalid.")
        start, end = scene.get("start_us"), scene.get("end_us")
        if (isinstance(start, bool) or not isinstance(start, int) or start < 0
                or isinstance(end, bool) or not isinstance(end, int) or end <= start):
            raise DualAIControllerError(f"Visual scene {index + 1} has invalid timestamps.")
        for field in ("description", "movement", "audio_notes"):
            value = scene.get(field, "")
            if not isinstance(value, str) or len(value) > 1200:
                raise DualAIControllerError(f"Visual scene {index + 1} has invalid {field}.")
        objects = scene.get("objects", [])
        if not isinstance(objects, list) or len(objects) > 30 or any(
            not isinstance(item, str) or len(item) > 160 for item in objects
        ):
            raise DualAIControllerError(f"Visual scene {index + 1} has invalid objects.")

    for index, moment in enumerate(normalized["key_moments"]):
        if not isinstance(moment, dict):
            raise DualAIControllerError(f"Visual key moment {index + 1} is invalid.")
        stamp = moment.get("time_us")
        if isinstance(stamp, bool) or not isinstance(stamp, int) or stamp < 0:
            raise DualAIControllerError(f"Visual key moment {index + 1} has invalid timestamp.")
        for field in ("description", "editing_value"):
            value = moment.get(field, "")
            if not isinstance(value, str) or len(value) > 800:
                raise DualAIControllerError(f"Visual key moment {index + 1} has invalid {field}.")

    for note in normalized["editing_notes"]:
        if not isinstance(note, str) or len(note) > 800:
            raise DualAIControllerError("Visual editing notes must be short text strings.")

    suggestions = data.get("tool_suggestions", [])
    if not isinstance(suggestions, list) or len(suggestions) > 40:
        raise DualAIControllerError("Visual tool suggestions must be an array of at most 40 items.")
    valid_suggestions = []
    rejected = []
    for index, suggestion in enumerate(suggestions):
        if not isinstance(suggestion, dict):
            rejected.append(f"Suggestion {index + 1} was not an object.")
            continue
        name, arguments = suggestion.get("name"), suggestion.get("arguments", {})
        reason = suggestion.get("reason", "")
        if not isinstance(name, str) or not isinstance(arguments, dict) or not isinstance(reason, str):
            rejected.append(f"Suggestion {index + 1} had invalid fields.")
            continue
        try:
            checked = validate_tool_call(name, arguments)
        except Exception as exc:
            rejected.append(f"{name[:100]} was rejected by the shared tool registry: {str(exc)[:240]}")
            continue
        valid_suggestions.append({
            "name": name,
            "arguments": checked,
            "reason": reason[:500],
        })
    normalized["tool_suggestions"] = valid_suggestions
    normalized["rejected_tool_suggestions"] = rejected[:40]
    return normalized


def _extract_groq_video_frames(video_path: Path) -> tuple[int, list[dict[str, Any]]]:
    """Extract three small, timestamped JPEG samples for the vision fallback."""
    if not video_path.is_file():
        raise DualAIControllerError("The source video is missing before visual fallback analysis.")

    try:
        probe = subprocess.run(
            [
                "ffprobe", "-v", "error", "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1", str(video_path),
            ],
            check=True, capture_output=True, text=True, timeout=30,
        )
        duration_seconds = float(probe.stdout.strip())
    except Exception as exc:
        raise DualAIControllerError(
            f"FFprobe could not read the source-video duration for visual fallback: {exc}"
        ) from exc
    if duration_seconds <= 0:
        raise DualAIControllerError("The source video has no usable duration for visual fallback.")

    duration_us = max(1, round(duration_seconds * 1_000_000))
    timestamps_us = [
        min(duration_us - 1, max(0, round(duration_us * fraction)))
        for fraction in (0.12, 0.50, 0.88)
    ]
    frames: list[dict[str, Any]] = []

    try:
        with tempfile.TemporaryDirectory(prefix="video-editor-groq-") as temp_dir:
            for index, timestamp_us in enumerate(timestamps_us):
                frame_path = Path(temp_dir) / f"frame-{index}.jpg"
                subprocess.run(
                    [
                        "ffmpeg", "-hide_banner", "-loglevel", "error",
                        "-ss", f"{timestamp_us / 1_000_000:.6f}",
                        "-i", str(video_path),
                        "-frames:v", "1",
                        "-vf", "scale=768:768:force_original_aspect_ratio=decrease",
                        "-q:v", "6", "-y", str(frame_path),
                    ],
                    check=True, capture_output=True, text=True, timeout=90,
                )
                if not frame_path.is_file():
                    raise DualAIControllerError(
                        f"FFmpeg did not create sampled frame {index + 1}."
                    )
                image_bytes = frame_path.read_bytes()
                if not image_bytes or len(image_bytes) > 3 * 1024 * 1024:
                    raise DualAIControllerError(
                        f"Sampled frame {index + 1} is empty or unexpectedly large."
                    )
                frames.append({
                    "timestamp_us": timestamp_us,
                    "data_url": "data:image/jpeg;base64,"
                    + base64.b64encode(image_bytes).decode("ascii"),
                })
    except DualAIControllerError:
        raise
    except Exception as exc:
        raise DualAIControllerError(
            f"FFmpeg could not extract visual fallback frames: {type(exc).__name__}: {exc}"
        ) from exc

    if not frames:
        raise DualAIControllerError("No usable video frames were extracted for visual fallback.")
    return duration_us, frames


def _groq_analyze_video(video_path: Path, instruction: str) -> dict[str, Any]:
    """Analyse a few sampled still frames when full-video Gemini analysis is unavailable."""
    api_key = os.environ.get("GROQ_API_KEY", "").strip()
    if not api_key:
        raise DualAIControllerError("GROQ_API_KEY is missing; the visual fallback is not configured.")

    model = os.environ.get("GROQ_VISION_MODEL", "qwen/qwen3.8-27b").strip()
    duration_us, frames = _extract_groq_video_frames(video_path)
    timestamp_lines = "\n".join(
        f"- frame_index {index}: timestamp_us={frame['timestamp_us']}"
        for index, frame in enumerate(frames)
    )
    prompt = (
        "You are a fallback visual reviewer for a video-editing application. "
        "You receive only timestamped still frames, not the original video stream. "
        "Describe only details directly visible in each supplied frame. "
        "Do not infer movement between frames, scene transitions, audio, speech, or events "
        "that cannot be confirmed from the still images. "
        "Return JSON only with this shape: "
        '{"summary":"...","observations":[{"frame_index":0,'
        '"description":"...","objects":["..."]}],"editing_notes":["..."]}. '
        "Return one observation for each frame, preserve the supplied frame indexes, "
        "and do not invent timestamps or editing-tool calls.\n\n"
        "FRAME INDEX AND TIMESTAMP MAP:\n" + timestamp_lines
        + "\n\nUSER EDIT REQUEST:\n" + instruction.strip()[:1200]
    )

    content: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
    content.extend(
        {
            "type": "image_url",
            "image_url": {"url": frame["data_url"]},
        }
        for frame in frames
    )
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": content}],
        "response_format": {"type": "json_object"},
        "temperature": 0.1,
        "max_completion_tokens": 1200,
    }
    request = urllib.request.Request(
        "https://api.groq.com/openai/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={
            "Authorization": "Bearer " + api_key,
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    result = _request_json(request, timeout=180, stage="Groq sampled-frame visual analysis")
    try:
        message = result["choices"][0]["message"]
        raw = message.get("content")
        if isinstance(raw, list):
            raw = "".join(
                part.get("text", "") for part in raw if isinstance(part, dict)
            )
        parsed = json.loads(raw) if isinstance(raw, str) else None
    except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
        raise DualAIControllerError(
            "Groq did not return the required sampled-frame JSON observations."
        ) from exc
    if not isinstance(parsed, dict):
        raise DualAIControllerError("Groq sampled-frame analysis must be a JSON object.")

    observations = parsed.get("observations")
    if not isinstance(observations, list) or not observations or len(observations) > len(frames):
        raise DualAIControllerError("Groq did not return valid observations for the sampled frames.")

    normalized_observations: list[dict[str, Any]] = []
    seen_indexes: set[int] = set()
    for item in observations:
        if not isinstance(item, dict):
            raise DualAIControllerError("Groq returned an invalid sampled-frame observation.")
        frame_index = item.get("frame_index")
        description = item.get("description", "")
        objects = item.get("objects", [])
        if (isinstance(frame_index, bool) or not isinstance(frame_index, int)
                or frame_index < 0 or frame_index >= len(frames) or frame_index in seen_indexes):
            raise DualAIControllerError("Groq returned an invalid or repeated frame index.")
        if not isinstance(description, str) or not description.strip() or len(description) > 1200:
            raise DualAIControllerError("Groq returned an invalid frame description.")
        if not isinstance(objects, list) or len(objects) > 30 or any(
            not isinstance(value, str) or len(value) > 160 for value in objects
        ):
            raise DualAIControllerError("Groq returned invalid frame objects.")
        seen_indexes.add(frame_index)
        normalized_observations.append({
            "frame_index": frame_index,
            "timestamp_us": frames[frame_index]["timestamp_us"],
            "description": description.strip(),
            "objects": objects,
        })
    normalized_observations.sort(key=lambda value: value["frame_index"])

    summary = parsed.get("summary", "Visual review based on three representative still frames.")
    if not isinstance(summary, str) or len(summary) > 1200:
        raise DualAIControllerError("Groq returned an invalid sampled-frame summary.")
    notes = parsed.get("editing_notes", [])
    if not isinstance(notes, list) or len(notes) > 30 or any(
        not isinstance(note, str) or len(note) > 800 for note in notes
    ):
        raise DualAIControllerError("Groq returned invalid sampled-frame editing notes.")

    frame_descriptions = [
        f"At {item['timestamp_us']} microseconds: {item['description']}"
        for item in normalized_observations
    ]
    scene_description = ("Sparse still-frame observations: " + " ".join(frame_descriptions))[:1200]
    all_objects: list[str] = []
    for item in normalized_observations:
        for value in item["objects"]:
            if value not in all_objects:
                all_objects.append(value)

    analysis = {
        "summary": summary.strip(),
        "analysis_provider": "Groq Qwen 3.8 27B (sampled-frame fallback)",
        "coverage_notes": (
            "Only three representative timestamped still frames were reviewed. "
            "Audio and motion between frames were not analysed; sampled timestamps are not "
            "verified scene cuts."
        ),
        "scenes": [{
            "start_us": 0,
            "end_us": duration_us,
            "description": scene_description,
            "objects": all_objects[:30],
            "movement": "Not analysed; this fallback reviews still frames only.",
            "audio_notes": "Not analysed by the sampled-frame visual fallback.",
        }],
        "key_moments": [{
            "time_us": item["timestamp_us"],
            "description": item["description"],
            "editing_value": "Representative frame only; not a verified scene cut or action.",
        } for item in normalized_observations],
        "editing_notes": [note.strip() for note in notes]
        + ["Fallback limitation: audio and motion between sampled frames were not analysed."],
        "tool_suggestions": [],
    }
    return validate_video_analysis(analysis)


def _analyze_video_with_fallback(
    video_path: Path,
    instruction: str,
    executor: ProjectToolExecutor,
) -> dict[str, Any]:
    """Prefer full-video Gemini; fall back to sampled-frame Groq vision when configured."""
    failures: list[str] = []
    gemini_key = os.environ.get("GEMINI_API_KEY", "").strip()
    groq_key = os.environ.get("GROQ_API_KEY", "").strip()

    if gemini_key:
        try:
            return _gemini_analyze_video(
                video_path, build_gemini_video_prompt(instruction, executor)
            )
        except Exception as exc:
            detail = f"{type(exc).__name__}: {exc}"
            failures.append("Gemini: " + detail[:700])
            print(
                "Gemini visual analysis failed; trying the configured sampled-frame fallback. "
                + detail[:300],
                flush=True,
            )
    else:
        failures.append("Gemini: GEMINI_API_KEY is not configured.")

    if groq_key:
        try:
            return _groq_analyze_video(video_path, instruction)
        except Exception as exc:
            detail = f"{type(exc).__name__}: {exc}"
            failures.append("Groq frame fallback: " + detail[:700])
    else:
        failures.append("Groq fallback: GROQ_API_KEY is not configured.")

    raise DualAIControllerError(
        "Visual analysis could not complete with any configured provider. "
        + " | ".join(failures)
    )


def _gemini_analyze_video(video_path: Path, prompt: str) -> dict[str, Any]:
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise DualAIControllerError("GEMINI_API_KEY is missing; Gemini cannot analyse the source video.")
    model = os.environ.get("GEMINI_VIDEO_MODEL", "gemini-3.8-flash").strip()
    uploaded = _upload_video_to_gemini(video_path, api_key)
    try:
        _wait_for_gemini_video(uploaded["name"], api_key)
        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            + urllib.parse.quote(model, safe="")
            + ":generateContent"
        )
        payload = {
            "contents": [{
                "parts": [
                    {"text": prompt},
                    {"file_data": {
                        "mime_type": uploaded["mime_type"],
                        "file_uri": uploaded["uri"],
                    }},
                ],
            }],
            "generationConfig": {
                "responseMimeType": "application/json",
                "temperature": 0.1,
                "maxOutputTokens": 8192,
            },
        }
        request = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            method="POST",
            headers={"x-goog-api-key": api_key, "Content-Type": "application/json"},
        )
        result = _request_json(request, timeout=600, stage="Gemini visual video analysis")
        parts = result.get("candidates", [{}])[0].get("content", {}).get("parts", [])
        raw = next((part.get("text") for part in parts if isinstance(part, dict)
                    and isinstance(part.get("text"), str)), None)
        if not raw:
            raise DualAIControllerError("Gemini did not return a video-analysis JSON response.")
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise DualAIControllerError("Gemini video analysis was not valid JSON.") from exc
        if isinstance(parsed, dict):
            parsed.setdefault("analysis_provider", "Gemini")
        return validate_video_analysis(parsed)
    finally:
        _delete_gemini_video(uploaded["name"], api_key)


def build_deepseek_plan_prompt(
    instruction: str,
    executor: ProjectToolExecutor,
    video_analysis: dict[str, Any],
) -> str:
    return (
        "You are DeepSeek, the reasoning and editing-execution planner. "
        "The visual-analysis provider has inspected the source footage or representative frames. "
        "Combine the user's request and the supplied timestamped visual findings into one "
        "coherent editing plan. "
        "You also have access to every registered operation in the shared tool catalogue. "
        "Return JSON only with this exact shape: "
        '{"summary":"plain-language plan","tool_calls":[{"name":"registered.tool","arguments":{}}]}. '
        "Use only exact registered tool names and their exact schemas. "
        "The final operations will be executed, not merely displayed, so check every ID, "
        "timestamp, media/track compatibility, operation order, and feature constraint. "
        "Use project IDs only; do not invent clips, tracks, media, or assets. "
        "Use integer microseconds for all times. "
        "Use the supplied visual evidence for cuts, titles, transitions, effects and timing. "
        "Do not claim motion, scene boundaries, or audio facts that are not in the supplied findings. "
        "If the visual reviewer suggested a tool call, you may correct or reject it after reasoning, "
        "but explain important omissions in the summary. "
        "Do not include render.export; the render runner adds export after the edit batch. "
        "Undo/redo must be a single standalone call. Destructive calls must remain in the plan "
        "so the executor can pause for user approval. Never bypass the executor or confirmation. "
        "Never invent tools for masks, tracking, stabilisation or other unavailable capabilities. "
        "Keep the edit minimal and aligned with the user's request.\n\n"
        "USER EDIT REQUEST:\n" + instruction.strip()[:4000]
        + "\n\nVISUAL ANALYSIS:\n"
        + json.dumps(video_analysis, ensure_ascii=False, separators=(",", ":"))
        + "\n\nCURRENT PROJECT:\n"
        + json.dumps(_project_context(executor), ensure_ascii=False, separators=(",", ":"))
        + "\n\nSHARED REGISTERED TOOL CATALOGUE:\n"
        + json.dumps(get_tool_catalog(), ensure_ascii=False, separators=(",", ":"))
    )


def _deepseek_generate_plan(prompt: str) -> dict[str, Any]:
    api_key = os.environ.get("GONKA_ROUTER_API_KEY", "").strip()
    if not api_key:
        raise DualAIControllerError(
            "GONKA_ROUTER_API_KEY is missing; DeepSeek cannot prepare the executable edit plan."
        )
    model = os.environ.get(
        "GONKA_DEEPSEEK_MODEL", "deepseek-ai/DeepSeek-V4-Flash-0731"
    ).strip()
    base_url = os.environ.get(
        "GONKA_ROUTER_BASE_URL", "https://api.gonkarouter.io/v1"
    ).strip().rstrip("/")
    if not base_url.startswith("https://"):
        raise DualAIControllerError("GONKA_ROUTER_BASE_URL must use HTTPS.")
    catalog = get_tool_catalog()
    function_name_to_tool = {}
    function_tools = []
    for item in catalog:
        # Function-calling names use underscores; the executor keeps the
        # canonical dotted registry names (for example clip.set_speed).
        function_name = "op__" + item["name"].replace(".", "__")
        function_name_to_tool[function_name] = item["name"]
        function_tools.append({
            "type": "function",
            "function": {
                "name": function_name,
                "description": item["description"],
                "parameters": item["input_schema"],
            },
        })
    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a precise video-editing planner. Use the supplied functions "
                    "to return the final ordered editing operations. Function calls are "
                    "requests for registered editor operations, not permission to bypass "
                    "the host executor. Do not invent IDs or unavailable tools."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        "tools": function_tools,
        "tool_choice": "auto",
        "parallel_tool_calls": False,
        "temperature": 0.1,
        "max_tokens": int(os.environ.get("GONKA_MAX_OUTPUT_TOKENS", "6144")),
    }
    request = urllib.request.Request(
        base_url + "/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={
            "Authorization": "Bearer " + api_key,
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    result = _request_json(request, timeout=180, stage="GonkaRouter DeepSeek planning")
    try:
        message = result["choices"][0]["message"]
        content = message.get("content")
        if isinstance(content, list):
            content = "".join(
                part.get("text", "") for part in content if isinstance(part, dict)
            )
        native_calls = message.get("tool_calls") or []
        if native_calls:
            calls = []
            for call in native_calls:
                function = call.get("function", {})
                function_name = function.get("name")
                registered_name = function_name_to_tool.get(function_name)
                if not registered_name:
                    raise DualAIControllerError(
                        "DeepSeek requested a function outside the shared tool catalogue."
                    )
                raw_arguments = function.get("arguments", "{}")
                arguments = (
                    json.loads(raw_arguments)
                    if isinstance(raw_arguments, str) else raw_arguments
                )
                calls.append({"name": registered_name, "arguments": arguments})
            summary = "DeepSeek planned the requested edit using the supplied visual analysis."
            if isinstance(content, str) and content.strip():
                try:
                    text_result = json.loads(content)
                    if isinstance(text_result, dict) and isinstance(text_result.get("summary"), str):
                        summary = text_result["summary"]
                except json.JSONDecodeError:
                    summary = content.strip()[:1200]
            return {"summary": summary, "tool_calls": calls}
        generated = json.loads(content) if isinstance(content, str) else None
    except DualAIControllerError:
        raise
    except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
        raise DualAIControllerError(
            "DeepSeek did not return the required JSON editing plan."
        ) from exc
    if not isinstance(generated, dict):
        raise DualAIControllerError("DeepSeek editing plan must be a JSON object.")
    return generated


def plan_dual_ai_edit(
    instruction: str,
    video_path: str | Path,
    executor: ProjectToolExecutor,
    *,
    video_analyzer: Callable[[Path, str], dict[str, Any]] | None = None,
    planner_provider: Callable[[str], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Run visual analysis, DeepSeek planning, and shared tool validation."""
    if not isinstance(instruction, str) or not instruction.strip():
        raise DualAIControllerError("Describe the edit you want the AI team to make.")
    path = Path(video_path)
    if video_analyzer is not None:
        raw_analysis = video_analyzer(
            path, build_gemini_video_prompt(instruction, executor)
        )
    else:
        raw_analysis = _analyze_video_with_fallback(path, instruction, executor)
    analysis = validate_video_analysis(raw_analysis)
    deepseek_prompt = build_deepseek_plan_prompt(instruction, executor, analysis)
    generated_plan = (
        planner_provider(deepseek_prompt)
        if planner_provider is not None
        else _deepseek_generate_plan(deepseek_prompt)
    )
    try:
        plan = validate_tool_plan(generated_plan)
    except AIEditControllerError as exc:
        raise DualAIControllerError(
            "DeepSeek's editing plan was rejected by the shared tool validator: " + str(exc)
        ) from exc
    return {
        "plan": plan,
        "video_analysis": analysis,
        "agents": {
            "visual_analysis": analysis.get("analysis_provider", "Gemini"),
            "editing_reasoning": "DeepSeek via GonkaRouter",
            "execution": "ProjectToolExecutor and MLT",
        },
    }
