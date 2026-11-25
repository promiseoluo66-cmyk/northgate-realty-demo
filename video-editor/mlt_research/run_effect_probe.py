"""Real-render proof for safe contrast and saturation adjustments."""
from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path
import sys

HERE = Path(__file__).resolve()
ROOT = HERE.parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mlt_engine.renderer import render_project  # noqa: E402


def run(command: list[str]) -> None:
    subprocess.run(command, check=True, capture_output=True)


def sample_pixel(video: Path, seconds: float = 0.4) -> tuple[int, int, int]:
    result = subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-loglevel", "error",
            "-ss", str(seconds), "-i", str(video),
            "-vf", "crop=2:2:160:120,scale=1:1:flags=area,format=rgb24",
            "-frames:v", "1", "-f", "rawvideo", "-",
        ],
        check=True, capture_output=True,
    )
    if len(result.stdout) != 3:
        raise RuntimeError("Could not sample the decoded effect output.")
    return tuple(result.stdout)


def make_project(source: Path, effect_type: str, value: float) -> dict:
    return {
        "schema_version": 1,
        "id": f"mlt-{effect_type}-proof",
        "name": f"Generated {effect_type} effect proof",
        "revision": 1,
        "timeline_timebase": "microseconds",
        "video_profile": {
            "width": 320, "height": 240,
            "frame_rate": {"numerator": 25, "denominator": 1},
        },
        "assets": [{
            "id": "source", "media_type": "video",
            "file_name": source.name, "storage_key": source.name,
            "size_bytes": source.stat().st_size, "duration_us": 1_000_000,
        }],
        "tracks": [{
            "id": "video-track", "type": "video", "name": "Video", "order": 0,
            "clips": [{
                "id": "effect-clip", "kind": "video", "media_id": "source",
                "start_us": 0, "duration_us": 1_000_000,
                "source_in_us": 0, "source_out_us": 1_000_000,
                "playback_rate": 1, "effects": [{
                    "id": f"{effect_type}-1", "type": effect_type,
                    "parameters": {"value": value},
                }],
                "keyframes": [],
            }],
        }],
        "transitions": [],
    }


def render_effect(root: Path, source: Path, effect_type: str, value: float) -> tuple[Path, tuple[int, int, int]]:
    output = root / f"{effect_type}.mp4"
    result = render_project(make_project(source, effect_type, value), root, output, timeout_seconds=60)
    if not result.get("ok") or not output.is_file() or output.stat().st_size == 0:
        raise RuntimeError(f"{effect_type} render did not produce a video.")
    return output, sample_pixel(output)


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="mlt-effects-") as folder:
        root = Path(folder)
        source = root / "muted-red.mp4"
        run([
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-f", "lavfi", "-i", "color=c=0xB46464:s=320x240:r=25:d=1",
            "-an", "-c:v", "mpeg4", "-q:v", "2", "-pix_fmt", "yuv420p",
            str(source),
        ])
        original = sample_pixel(source)
        contrast_output, contrast_pixel = render_effect(root, source, "contrast", 1.5)
        saturation_output, saturation_pixel = render_effect(root, source, "saturation", 1.8)

        original_contrast = sum(abs(channel - 128) for channel in original)
        adjusted_contrast = sum(abs(channel - 128) for channel in contrast_pixel)
        original_chroma = max(original) - min(original)
        adjusted_chroma = max(saturation_pixel) - min(saturation_pixel)
        report = {
            "source_rgb": original,
            "contrast_rgb": contrast_pixel,
            "saturation_rgb": saturation_pixel,
            "contrast_distance_from_midpoint": [original_contrast, adjusted_contrast],
            "saturation_channel_spread": [original_chroma, adjusted_chroma],
            "outputs": [contrast_output.stat().st_size, saturation_output.stat().st_size],
        }
        print(json.dumps(report, indent=2, sort_keys=True))
        if adjusted_contrast <= original_contrast * 1.02:
            raise SystemExit("Contrast effect did not visibly increase the rendered contrast.")
        if adjusted_chroma <= original_chroma * 1.15:
            raise SystemExit("Saturation effect did not visibly increase the rendered saturation.")
        print("PASS: contrast and saturation visibly change decoded rendered pixels.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
