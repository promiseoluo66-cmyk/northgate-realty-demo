"""Verify that playback-rate keyframes time-remap a project video correctly."""
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


def pixel_patch(video: Path, seconds: float) -> tuple[int, int, int]:
    result = subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-loglevel", "error",
            "-ss", f"{seconds:.6f}", "-i", str(video),
            "-vf", "crop=16:16:152:112,scale=1:1:flags=area,format=rgb24",
            "-frames:v", "1", "-f", "rawvideo", "-",
        ],
        check=True, capture_output=True,
    )
    if len(result.stdout) != 3:
        raise RuntimeError(f"Could not sample decoded video at {seconds:.3f}s.")
    return tuple(result.stdout)


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="mlt-speed-curve-") as folder:
        root = Path(folder)
        source = root / "three-second-source.mp4"
        output = root / "speed-curve.mp4"
        run([
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-f", "lavfi", "-i", "testsrc2=size=320x240:rate=25:duration=3",
            "-an", "-c:v", "mpeg4", "-q:v", "2", "-pix_fmt", "yuv420p",
            str(source),
        ])

        project = {
            "schema_version": 1,
            "id": "mlt-speed-curve-proof",
            "name": "Generated 1x to 2x playback curve proof",
            "revision": 1,
            "timeline_timebase": "microseconds",
            "video_profile": {
                "width": 320, "height": 240,
                "frame_rate": {"numerator": 25, "denominator": 1},
            },
            "assets": [{
                "id": "source", "media_type": "video",
                "file_name": source.name, "storage_key": source.name,
                "size_bytes": source.stat().st_size, "duration_us": 3_000_000,
            }],
            "tracks": [{
                "id": "video-track", "type": "video", "name": "Video", "order": 0,
                "clips": [{
                    "id": "ramp-clip", "kind": "video", "media_id": "source",
                    "start_us": 0, "duration_us": 2_000_000,
                    "source_in_us": 0, "source_out_us": 3_000_000,
                    "playback_rate": 1.0, "effects": [],
                    "keyframes": [
                        {"property": "playback_rate", "time_us": 0, "value": 1.0},
                        {"property": "playback_rate", "time_us": 1_999_999, "value": 2.0},
                    ],
                }],
            }],
            "transitions": [],
        }

        result = render_project(project, root, output, timeout_seconds=90)
        if not result.get("ok") or not output.is_file() or output.stat().st_size == 0:
            raise RuntimeError("The speed-curve project did not produce a video.")

        probe = subprocess.run([
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "json", str(output),
        ], check=True, capture_output=True, text=True)
        duration = float(json.loads(probe.stdout)["format"]["duration"])

        output_late = pixel_patch(output, 1.90)
        source_late = pixel_patch(source, 2.80)
        distance = sum(abs(a - b) for a, b in zip(output_late, source_late))
        print(json.dumps({
            "timeline_duration_seconds": 2.0,
            "source_duration_seconds": 3.0,
            "curve": "1.0x at 0s to 2.0x at 2s",
            "rendered_duration_seconds": duration,
            "output_pixel_at_1_90s": output_late,
            "expected_source_pixel_at_2_80s": source_late,
            "rgb_distance": distance,
        }, indent=2, sort_keys=True))

        if not 1.92 <= duration <= 2.08:
            raise SystemExit(f"Expected a 2-second ramp output, got {duration:.3f}s.")
        if distance > 60:
            raise SystemExit(
                "The late ramp frame does not match the expected later source frame; "
                f"RGB distance={distance}."
            )
        print("PASS: rendered speed-curve output follows the expected source time remapping.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
