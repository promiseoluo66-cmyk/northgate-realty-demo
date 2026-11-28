"""End-to-end MLT acceptance for editable title templates.

The test inspects decoded output frames: static text must be visible only inside
its clip, and the animated template must visibly change during its entrance.
"""
from __future__ import annotations

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from mlt_engine.renderer import render_project
from project_tool_executor import ProjectToolExecutor


def _make_base_video(path: Path) -> None:
    subprocess.run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-f", "lavfi", "-i", "color=c=blue:s=320x240:r=10:d=4",
        "-an", "-c:v", "libx264", "-preset", "ultrafast",
        "-pix_fmt", "yuv420p", str(path),
    ], check=True, capture_output=True, text=True, timeout=120)


def _read_rgb_frame(path: Path, timestamp: float) -> bytes:
    result = subprocess.run([
        "ffmpeg", "-hide_banner", "-loglevel", "error",
        "-ss", f"{timestamp:.3f}", "-i", str(path),
        "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1",
    ], check=True, capture_output=True, timeout=60)
    expected = 320 * 240 * 3
    if len(result.stdout) != expected:
        raise AssertionError(f"Expected {expected} decoded RGB bytes, got {len(result.stdout)}.")
    return result.stdout


def _bright_pixel_count(frame: bytes) -> int:
    return sum(
        1 for offset in range(0, len(frame), 3)
        if frame[offset] > 150 and frame[offset + 1] > 150 and frame[offset + 2] > 150
    )


class EditableTitleTemplateMltIntegrationTests(unittest.TestCase):
    def test_static_and_animated_templates_render_as_editable_clips(self):
        if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
            self.fail("The title-template MLT test requires FFmpeg and FFprobe.")
        with tempfile.TemporaryDirectory(prefix="title-template-mlt-") as directory:
            root = Path(directory)
            source = root / "blue-base.mp4"
            output = root / "title-template-output.mp4"
            _make_base_video(source)
            project = {
                "schema_version": 1,
                "id": "title-template-integration",
                "name": "Title template integration",
                "revision": 1,
                "timeline_timebase": "microseconds",
                "video_profile": {
                    "width": 320, "height": 240,
                    "frame_rate": {"numerator": 10, "denominator": 1},
                },
                "assets": [{
                    "id": "base-video", "media_type": "video",
                    "file_name": source.name, "storage_key": source.name,
                    "size_bytes": source.stat().st_size, "duration_us": 4_000_000,
                }],
                "tracks": [
                    {
                        "id": "main-video", "type": "video", "name": "Main",
                        "order": 0, "locked": False, "clips": [{
                            "id": "base-clip", "kind": "video", "media_id": "base-video",
                            "start_us": 0, "duration_us": 4_000_000,
                            "source_in_us": 0, "source_out_us": 4_000_000,
                            "playback_rate": 1.0, "effects": [], "keyframes": [],
                        }],
                    },
                    {
                        "id": "title-track", "type": "text", "name": "Titles",
                        "order": 1, "locked": False, "clips": [],
                    },
                ],
                "transitions": [],
            }
            executor = ProjectToolExecutor(project, asset_root=root)
            executor.execute("timeline.add_text_clip", {
                "track_id": "title-track", "content": "STATIC TITLE",
                "start_us": 500_000, "duration_us": 1_000_000,
                "template_id": "bold-section-v1",
                "text_style": {"size": 36},
            })
            executor.execute("timeline.add_text_clip", {
                "track_id": "title-track", "content": "ANIMATED TITLE",
                "start_us": 2_000_000, "duration_us": 1_500_000,
                "template_id": "animated-rise-v1",
                "text_style": {"size": 32},
            })
            saved_project = executor.get_project()
            clips = saved_project["tracks"][1]["clips"]
            self.assertEqual([clip["kind"] for clip in clips], ["text", "text"])
            self.assertNotIn("template_id", clips[0])
            self.assertNotIn("template_id", clips[1])
            reopened = ProjectToolExecutor(saved_project, asset_root=root)
            render_project(reopened.get_project(), root, output)
            self.assertTrue(output.is_file())
            self.assertGreater(output.stat().st_size, 1000)

            before = _read_rgb_frame(output, 0.25)
            static = _read_rgb_frame(output, 0.8)
            gap = _read_rgb_frame(output, 1.8)
            animated_early = _read_rgb_frame(output, 2.1)
            animated_late = _read_rgb_frame(output, 2.6)
            after = _read_rgb_frame(output, 3.8)

            self.assertEqual(_bright_pixel_count(before), 0, "Title appeared before its clip.")
            self.assertGreater(_bright_pixel_count(static), 50, "Static title was not visible in decoded output.")
            self.assertEqual(_bright_pixel_count(gap), 0, "Static title escaped its clip duration.")
            self.assertGreater(_bright_pixel_count(animated_early), 5, "Animated title entrance was not rendered.")
            self.assertGreater(_bright_pixel_count(animated_late), 50, "Animated title did not reach visible state.")
            self.assertNotEqual(animated_early, animated_late, "Animated title frames did not change.")
            self.assertEqual(_bright_pixel_count(after), 0, "Title remained visible after its clip ended.")


if __name__ == "__main__":
    unittest.main()
