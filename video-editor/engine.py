from __future__ import annotations

import json
import re
import shutil
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass
class EditPlan:
    trim_start: float = 0.0
    trim_end: float | None = None
    speed: float = 1.0
    aspect: str = "9:16"
    width: int = 720
    height: int = 1280


def plan_from_instruction(instruction: str, defaults: dict[str, Any] | None = None) -> EditPlan:
    """Small deterministic planner; an AI planner can replace this behind the same contract."""
    data = dict(defaults or {})
    text = (instruction or "").lower()

    match = re.search(r"(?:from|start(?:ing)? at)\s*(\d+(?:\.\d+)?)\s*(?:s|sec|seconds)?\s*(?:to|until|through)\s*(\d+(?:\.\d+)?)", text)
    if match:
        data["trim_start"] = float(match.group(1))
        data["trim_end"] = float(match.group(2))
    else:
        match = re.search(r"trim (?:the )?first\s*(\d+(?:\.\d+)?)\s*(?:s|sec|seconds)", text)
        if match:
            data["trim_start"] = float(match.group(1))

    speed = re.search(r"(\d+(?:\.\d+)?)\s*x\s*(?:speed)?|speed\s*(?:of\s*)?(\d+(?:\.\d+)?)", text)
    if speed:
        data["speed"] = float(next(v for v in speed.groups() if v is not None))
    if any(x in text for x in ("vertical", "portrait", "9:16", "shorts", "reels", "tiktok")):
        data["aspect"] = "9:16"
        data["width"], data["height"] = 720, 1280
    elif "square" in text or "1:1" in text:
        data["aspect"] = "1:1"
        data["width"], data["height"] = 720, 720
    elif "landscape" in text or "16:9" in text:
        data["aspect"] = "16:9"
        data["width"], data["height"] = 1280, 720

    plan = EditPlan(**{k: v for k, v in data.items() if k in EditPlan.__dataclass_fields__})
    validate_plan(plan)
    return plan


def validate_plan(plan: EditPlan) -> None:
    if plan.trim_start < 0:
        raise ValueError("trim_start must be zero or greater")
    if plan.trim_end is not None and plan.trim_end <= plan.trim_start:
        raise ValueError("trim_end must be greater than trim_start")
    if not 0.25 <= plan.speed <= 4.0:
        raise ValueError("speed must be between 0.25x and 4x")
    if plan.aspect not in {"9:16", "1:1", "16:9"}:
        raise ValueError("Unsupported aspect ratio")
    if plan.width < 144 or plan.height < 144 or plan.width > 1920 or plan.height > 1920:
        raise ValueError("Output dimensions are outside the allowed range")


def probe_media(path: Path) -> dict[str, Any]:
    if not shutil.which("ffprobe"):
        raise RuntimeError("ffprobe is not installed")
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration:stream=codec_type,width,height",
         "-of", "json", str(path)],
        check=True, capture_output=True, text=True, timeout=60,
    )
    return json.loads(result.stdout)


def render_video(source: Path, destination: Path, plan: EditPlan) -> dict[str, Any]:
    validate_plan(plan)
    if not shutil.which("ffmpeg"):
        raise RuntimeError("FFmpeg is not installed")
    probe = probe_media(source)
    duration = float(probe.get("format", {}).get("duration", 0))
    if duration <= 0 or plan.trim_start >= duration:
        raise ValueError("The requested trim starts outside the video")
    end = min(plan.trim_end, duration) if plan.trim_end is not None else duration
    if end <= plan.trim_start:
        raise ValueError("The selected video segment is empty")

    vf = (
        f"scale={plan.width}:{plan.height}:force_original_aspect_ratio=increase,"
        f"crop={plan.width}:{plan.height},setsar=1,setpts=PTS/{plan.speed}"
    )
    streams = probe.get("streams", [])
    has_audio = any(stream.get("codec_type") == "audio" for stream in streams)
    atempo_parts = []
    remaining_speed = plan.speed
    while remaining_speed > 2.0:
        atempo_parts.append("atempo=2.0")
        remaining_speed /= 2.0
    while remaining_speed < 0.5:
        atempo_parts.append("atempo=0.5")
        remaining_speed /= 0.5
    atempo_parts.append(f"atempo={remaining_speed:.6f}")

    command = ["ffmpeg", "-y", "-v", "error", "-ss", str(plan.trim_start),
               "-i", str(source), "-t", str(end - plan.trim_start),
               "-map", "0:v:0", "-map", "0:a?"]
    command += ["-vf", vf]
    if has_audio:
        command += ["-af", ",".join(atempo_parts), "-c:a", "aac", "-b:a", "128k"]
    command += ["-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
                "-movflags", "+faststart", str(destination)]
    subprocess.run(command, check=True, capture_output=True, text=True, timeout=3600)
    return {"plan": asdict(plan), "source_duration": duration,
            "selected_duration": end - plan.trim_start, "output": str(destination)}
