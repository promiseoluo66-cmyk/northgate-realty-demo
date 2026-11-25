"""Real render proof for animated audio volume keyframes."""
from __future__ import annotations

import array
import json
import math
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


def rms_window(video: Path, start: float, duration: float) -> float:
    result = subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-loglevel", "error",
            "-ss", str(start), "-i", str(video), "-t", str(duration),
            "-vn", "-ac", "1", "-ar", "48000", "-f", "s16le", "-",
        ],
        check=True, capture_output=True,
    )
    samples = array.array("h")
    samples.frombytes(result.stdout[: len(result.stdout) // 2 * 2])
    if not samples:
        raise RuntimeError("Could not decode an audio sample window.")
    return math.sqrt(sum(sample * sample for sample in samples) / len(samples))


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="mlt-audio-keyframes-") as folder:
        root = Path(folder)
        video = root / "background.mp4"
        audio = root / "tone.wav"
        run([
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-f", "lavfi", "-i", "color=c=black:s=320x240:r=25:d=2",
            "-an", "-c:v", "mpeg4", "-q:v", "3", "-pix_fmt", "yuv420p",
            str(video),
        ])
        run([
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000:duration=2",
            "-c:a", "pcm_s16le", str(audio),
        ])

        project = {
            "schema_version": 1,
            "id": "mlt-audio-keyframes-proof",
            "name": "Generated audio volume keyframe proof",
            "revision": 1,
            "timeline_timebase": "microseconds",
            "video_profile": {
                "width": 320, "height": 240,
                "frame_rate": {"numerator": 25, "denominator": 1},
            },
            "assets": [
                {
                    "id": "video", "media_type": "video", "file_name": video.name,
                    "storage_key": video.name, "size_bytes": video.stat().st_size,
                    "duration_us": 2_000_000,
                },
                {
                    "id": "audio", "media_type": "audio", "file_name": audio.name,
                    "storage_key": audio.name, "size_bytes": audio.stat().st_size,
                    "duration_us": 2_000_000,
                },
            ],
            "tracks": [
                {
                    "id": "video-track", "type": "video", "name": "Background",
                    "order": 0,
                    "clips": [{
                        "id": "background-clip", "kind": "video", "media_id": "video",
                        "start_us": 0, "duration_us": 2_000_000,
                        "source_in_us": 0, "source_out_us": 2_000_000,
                        "playback_rate": 1, "effects": [], "keyframes": [],
                    }],
                },
                {
                    "id": "audio-track", "type": "audio", "name": "Music",
                    "order": 1,
                    "clips": [{
                        "id": "audio-clip", "kind": "audio", "media_id": "audio",
                        "start_us": 0, "duration_us": 2_000_000,
                        "source_in_us": 0, "source_out_us": 2_000_000,
                        "playback_rate": 1, "effects": [],
                        "keyframes": [
                            {"property": "volume_db", "time_us": 0, "value": 0.0},
                            {"property": "volume_db", "time_us": 1_000_000, "value": -24.0},
                        ],
                    }],
                },
            ],
            "transitions": [],
        }
        output = root / "audio-keyframes.mp4"
        result = render_project(project, root, output, timeout_seconds=60)
        if not result.get("ok") or not output.is_file() or output.stat().st_size == 0:
            raise RuntimeError("The audio keyframe render did not produce a video.")

        early = rms_window(output, 0.2, 0.25)
        late = rms_window(output, 1.65, 0.25)
        print(json.dumps({
            "early_rms": round(early, 2),
            "late_rms": round(late, 2),
            "attenuation_ratio": round(early / max(late, 1.0), 2),
            "expected_db_change": -24.0,
        }, indent=2, sort_keys=True))
        if not early > late * 4:
            raise SystemExit(
                f"Expected animated volume to attenuate by at least 4x; "
                f"early RMS={early:.2f}, late RMS={late:.2f}."
            )
        print("PASS: decoded audio proves volume_db keyframes change the rendered sound.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
