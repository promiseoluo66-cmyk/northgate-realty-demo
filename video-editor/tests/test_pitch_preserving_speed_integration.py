"""Real-render acceptance test for pitch-preserving clip speed changes."""
from __future__ import annotations

import array
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from mlt_engine.renderer import render_project
from project_tool_executor import ProjectToolExecutor


def _make_video_with_tone(path: Path) -> None:
    subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-f", "lavfi", "-i", "color=c=blue:s=160x144:r=10:d=4",
            "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=44100:duration=4",
            "-map", "0:v:0", "-map", "1:a:0", "-t", "4",
            "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "128k", "-shortest", str(path),
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=120,
    )


def _tone_project(source: Path) -> dict:
    return {
        "schema_version": 1,
        "id": "pitch-speed-integration",
        "name": "Pitch-preserving speed integration",
        "revision": 1,
        "timeline_timebase": "microseconds",
        "video_profile": {
            "width": 160,
            "height": 144,
            "frame_rate": {"numerator": 10, "denominator": 1},
        },
        "assets": [{
            "id": "tone-video",
            "media_type": "video",
            "file_name": source.name,
            "storage_key": source.name,
            "size_bytes": source.stat().st_size,
            "duration_us": 4_000_000,
        }],
        "tracks": [{
            "id": "main-video",
            "type": "video",
            "name": "Video with 440 Hz tone",
            "order": 0,
            "locked": False,
            "clips": [{
                "id": "speed-clip",
                "kind": "video",
                "media_id": "tone-video",
                "start_us": 0,
                "duration_us": 2_000_000,
                "source_in_us": 0,
                "source_out_us": 4_000_000,
                "playback_rate": 2.0,
                "effects": [],
                "keyframes": [],
            }],
        }],
        "transitions": [],
    }


def _measure_tone_hz(rendered_video: Path) -> float:
    pcm = subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-loglevel", "error",
            "-ss", "0.5", "-t", "1.0", "-i", str(rendered_video),
            "-vn", "-ac", "1", "-ar", "11025", "-f", "s16le", "pipe:1",
        ],
        check=True,
        capture_output=True,
        timeout=60,
    ).stdout
    samples = array.array("h")
    samples.frombytes(pcm)
    if sys.byteorder != "little":
        samples.byteswap()
    if len(samples) < 10_000:
        raise AssertionError("Expected at least 10,000 decoded audio samples.")

    # Autocorrelation is more tolerant than raw zero-crossing counts of AAC
    # harmonics and phase changes introduced by pitch/time processing.
    stable = samples[1000:9000]
    minimum_lag = 11025 // 1000
    maximum_lag = 11025 // 120
    correlations = []
    for lag in range(minimum_lag, maximum_lag + 1):
        correlation = sum(
            stable[index] * stable[index + lag]
            for index in range(len(stable) - lag)
        )
        correlations.append((correlation, lag))
    _, best_lag = max(correlations)
    return 11025.0 / best_lag


class PitchPreservingSpeedIntegrationTests(unittest.TestCase):
    def test_double_speed_keeps_a_440_hz_source_tone_near_440_hz(self):
        if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
            self.fail("The pitch-preserving integration test requires FFmpeg and FFprobe.")

        with tempfile.TemporaryDirectory(prefix="pitch-speed-mlt-test-") as directory:
            root = Path(directory)
            source = root / "tone-source.mp4"
            output = root / "double-speed-render.mp4"
            _make_video_with_tone(source)

            # MLT's timewarp producer delegates pitch correction to rbpitch.
            import mlt7 as mlt
            factory = mlt.Factory()
            factory.init(None)
            self.assertTrue(
                mlt.Filter(mlt.Profile(), "rbpitch").is_valid(),
                "The installed MLT runtime does not provide its required pitch filter.",
            )

            executor = ProjectToolExecutor(_tone_project(source), asset_root=root)
            executor.execute("clip.set_speed", {
                "clip_id": "speed-clip",
                "playback_rate": 2.0,
            })
            project = executor.get_project()
            self.assertEqual(project["tracks"][0]["clips"][0]["playback_rate"], 2.0)

            result = render_project(project, root, output)
            self.assertEqual(result["backend"], "MLT Python API")
            self.assertTrue(output.is_file())
            self.assertGreater(output.stat().st_size, 0)

            measured_hz = _measure_tone_hz(output)
            self.assertGreater(
                measured_hz, 390.0,
                f"Expected pitch-compensated 440 Hz audio, measured {measured_hz:.1f} Hz.",
            )
            self.assertLess(
                measured_hz, 490.0,
                f"Expected pitch-compensated 440 Hz audio, measured {measured_hz:.1f} Hz.",
            )


if __name__ == "__main__":
    unittest.main()
