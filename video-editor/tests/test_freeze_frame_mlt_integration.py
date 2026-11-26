"""End-to-end MLT render acceptance test for generated freeze-frame holds.

This test deliberately exercises the real editor operation, the MLT renderer,
and the final encoded video. It samples decoded RGB pixels so a still PNG
existing on disk is not mistaken for a successfully rendered timeline overlay.
"""
from __future__ import annotations

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from mlt_engine.renderer import render_project
from project_tool_executor import ProjectToolExecutor


def _make_color_video(path: Path, color: str, duration: int) -> None:
    subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-f", "lavfi", "-i",
            f"color=c={color}:s=160x120:r=10:d={duration}",
            "-an", "-c:v", "libx264", "-preset", "ultrafast",
            "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(path),
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=120,
    )


def _project_for_freeze_frame(base_video: Path, source_video: Path) -> dict:
    return {
        "schema_version": 1,
        "id": "freeze-frame-mlt-integration",
        "name": "MLT freeze-frame integration",
        "revision": 1,
        "timeline_timebase": "microseconds",
        "video_profile": {
            "width": 160,
            "height": 120,
            "frame_rate": {"numerator": 10, "denominator": 1},
        },
        "assets": [
            {
                "id": "base-video",
                "media_type": "video",
                "file_name": base_video.name,
                "storage_key": base_video.name,
                "size_bytes": base_video.stat().st_size,
                "duration_us": 4_000_000,
            },
            {
                "id": "freeze-source",
                "media_type": "video",
                "file_name": source_video.name,
                "storage_key": source_video.name,
                "size_bytes": source_video.stat().st_size,
                "duration_us": 2_000_000,
            },
        ],
        "tracks": [
            {
                "id": "main-video",
                "type": "video",
                "name": "Blue base",
                "order": 0,
                "locked": False,
                "clips": [
                    {
                        "id": "base-clip",
                        "kind": "video",
                        "media_id": "base-video",
                        "start_us": 0,
                        "duration_us": 4_000_000,
                        "source_in_us": 0,
                        "source_out_us": 4_000_000,
                        "playback_rate": 1.0,
                        "effects": [],
                        "keyframes": [],
                    }
                ],
            },
            {
                "id": "overlay-track",
                "type": "overlay",
                "name": "Freeze overlay",
                "order": 1,
                "locked": False,
                "clips": [],
            },
        ],
        "transitions": [],
    }


def _read_center_rgb(video: Path, timestamp_seconds: float) -> tuple[int, int, int]:
    result = subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-loglevel", "error",
            "-ss", f"{timestamp_seconds:.3f}", "-i", str(video),
            "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1",
        ],
        check=True,
        capture_output=True,
        timeout=60,
    )
    expected_bytes = 160 * 120 * 3
    if len(result.stdout) != expected_bytes:
        raise AssertionError(
            f"Expected one {expected_bytes}-byte RGB frame at "
            f"{timestamp_seconds}s, got {len(result.stdout)} bytes."
        )
    center_offset = (60 * 160 + 80) * 3
    return tuple(result.stdout[center_offset:center_offset + 3])


class FreezeFrameMltRenderIntegrationTests(unittest.TestCase):
    def test_freeze_frame_is_visible_only_during_the_rendered_hold(self):
        if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
            self.fail("The MLT integration test requires FFmpeg and FFprobe.")

        with tempfile.TemporaryDirectory(prefix="freeze-frame-mlt-test-") as directory:
            root = Path(directory)
            base_video = root / "blue-base.mp4"
            source_video = root / "red-source.mp4"
            output_video = root / "freeze-frame-render.mp4"

            _make_color_video(base_video, "blue", 4)
            _make_color_video(source_video, "red", 2)

            executor = ProjectToolExecutor(
                _project_for_freeze_frame(base_video, source_video),
                asset_root=root,
            )
            operation = executor.execute(
                "timeline.create_freeze_frame",
                {
                    "media_id": "freeze-source",
                    "track_id": "overlay-track",
                    "timestamp_us": 500_000,
                    "start_us": 1_000_000,
                    "duration_us": 1_500_000,
                },
            )
            result = operation["results"][0]["result"]
            project = executor.get_project()

            still = next(
                asset for asset in project["assets"]
                if asset["id"] == result["media_id"]
            )
            still_path = root / still["storage_key"]
            self.assertTrue(still_path.is_file(), "Freeze-frame PNG was not created.")
            self.assertGreater(still_path.stat().st_size, 0)

            render_result = render_project(project, root, output_video)
            self.assertEqual(render_result["backend"], "MLT Python API")
            self.assertTrue(output_video.is_file())
            self.assertGreater(output_video.stat().st_size, 0)

            before = _read_center_rgb(output_video, 0.5)
            during_early = _read_center_rgb(output_video, 1.25)
            during_late = _read_center_rgb(output_video, 2.25)
            after = _read_center_rgb(output_video, 3.0)

            # The base clip is blue throughout. The extracted still must cover
            # the center only between 1.0s and 2.5s, including both inner samples.
            self.assertGreater(before[2], 150, f"Expected blue before hold, got {before}")
            self.assertGreater(before[2], before[0] + 100, f"Expected blue before hold, got {before}")

            for timestamp, pixel in (
                ("1.25s", during_early),
                ("2.25s", during_late),
            ):
                self.assertGreater(
                    pixel[0], 150,
                    f"Expected red freeze-frame during hold at {timestamp}, got {pixel}",
                )
                self.assertGreater(
                    pixel[0], pixel[2] + 100,
                    f"Expected red freeze-frame during hold at {timestamp}, got {pixel}",
                )

            self.assertGreater(after[2], 150, f"Expected blue after hold, got {after}")
            self.assertGreater(after[2], after[0] + 100, f"Expected blue after hold, got {after}")


if __name__ == "__main__":
    unittest.main()
