"""Render a project-level constant-speed clip through the MLT adapter."""
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


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="mlt-project-speed-") as folder:
        root = Path(folder)
        source = root / "two-second-source.mp4"
        output = root / "project-speed-2x.mp4"
        subprocess.run([
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-f", "lavfi", "-i", "testsrc2=size=320x240:rate=25:duration=2",
            "-an", "-c:v", "mpeg4", "-q:v", "3", "-pix_fmt", "yuv420p",
            str(source),
        ], check=True, capture_output=True)

        project = {
            "schema_version": 1,
            "id": "mlt-project-speed-proof",
            "name": "Project-level 2x playback proof",
            "revision": 1,
            "timeline_timebase": "microseconds",
            "video_profile": {
                "width": 320, "height": 240,
                "frame_rate": {"numerator": 25, "denominator": 1},
            },
            "assets": [{
                "id": "source", "media_type": "video",
                "file_name": source.name, "storage_key": source.name,
                "size_bytes": source.stat().st_size, "duration_us": 2_000_000,
            }],
            "tracks": [{
                "id": "video-track", "type": "video", "name": "Video", "order": 0,
                "clips": [{
                    "id": "speed-clip", "kind": "video", "media_id": "source",
                    "start_us": 0, "duration_us": 1_000_000,
                    "source_in_us": 0, "source_out_us": 2_000_000,
                    "playback_rate": 2.0, "effects": [], "keyframes": [],
                }],
            }],
            "transitions": [],
        }

        result = render_project(project, root, output, timeout_seconds=60)
        if not result.get("ok") or not output.is_file() or output.stat().st_size == 0:
            raise RuntimeError("The project speed render did not produce an output.")

        probe = subprocess.run([
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration:stream=width,height",
            "-of", "json", str(output),
        ], check=True, capture_output=True, text=True)
        metadata = json.loads(probe.stdout)
        duration = float(metadata["format"]["duration"])
        video_streams = [
            stream for stream in metadata.get("streams", [])
            if stream.get("width") == 320 and stream.get("height") == 240
        ]
        print(json.dumps({
            "source_duration_seconds": 2.0,
            "timeline_duration_seconds": 1.0,
            "playback_rate": 2.0,
            "rendered_duration_seconds": duration,
            "renderer": result,
        }, indent=2, sort_keys=True))
        if not 0.92 <= duration <= 1.08:
            raise SystemExit(
                f"Expected the project renderer to produce about 1 second at 2x; "
                f"got {duration:.3f}s."
            )
        if len(video_streams) != 1:
            raise SystemExit("Expected one 320x240 output video stream.")
        print("PASS: canonical project playback_rate=2 renders at double speed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
