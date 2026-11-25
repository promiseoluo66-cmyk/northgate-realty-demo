"""Render proof for still-image overlays and Qt text/caption tracks."""
from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

HERE = Path(__file__).resolve()
ROOT = HERE.parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mlt_engine.renderer import render_project  # noqa: E402


def run(command: list[str]) -> None:
    subprocess.run(command, check=True, capture_output=True)


def sample_pixel(video: Path, seconds: float, x: int, y: int) -> tuple[int, int, int]:
    result = subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-loglevel", "error",
            "-ss", str(seconds), "-i", str(video),
            "-vf", f"crop=1:1:{x}:{y},format=rgb24",
            "-frames:v", "1", "-f", "rawvideo", "-"
        ],
        check=True, capture_output=True,
    )
    if len(result.stdout) != 3:
        raise RuntimeError("Could not sample a decoded output pixel.")
    return tuple(result.stdout)


def count_yellow_pixels(video: Path, seconds: float) -> int:
    result = subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-loglevel", "error",
            "-ss", str(seconds), "-i", str(video),
            "-vf", "format=rgb24",
            "-frames:v", "1", "-f", "rawvideo", "-"
        ],
        check=True, capture_output=True,
    )
    if len(result.stdout) != 320 * 240 * 3:
        raise RuntimeError("Could not decode the full caption frame.")
    pixels = result.stdout
    count = 0
    for index in range(0, len(pixels), 3):
        red, green, blue = pixels[index:index + 3]
        if red > 190 and green > 190 and blue < 90:
            count += 1
    return count


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="mlt-visual-assets-") as folder:
        root = Path(folder)
        background = root / "background.mp4"
        image = root / "overlay.png"
        run([
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-f", "lavfi", "-i", "color=c=red:s=320x240:r=25:d=2.4",
            "-an", "-c:v", "mpeg4", "-q:v", "3", "-pix_fmt", "yuv420p",
            str(background),
        ])
        run([
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-f", "lavfi", "-i", "color=c=green:s=320x240:r=25:d=1",
            "-frames:v", "1", str(image),
        ])
        source_samples = {
            "top_center": sample_pixel(background, 0.2, 160, 20),
            "middle_left": sample_pixel(background, 0.2, 20, 120),
            "middle_center": sample_pixel(background, 0.2, 160, 120),
            "middle_right": sample_pixel(background, 0.2, 300, 120),
        }
        if any(not (rgb[0] > 150 and rgb[1] < 80 and rgb[2] < 80) for rgb in source_samples.values()):
            raise SystemExit(f"Generated red source is not red across the frame: {source_samples}")

        project = {
            "schema_version": 1,
            "id": "mlt-visual-assets-proof",
            "name": "Generated still image and text render proof",
            "revision": 1,
            "timeline_timebase": "microseconds",
            "video_profile": {
                "width": 320, "height": 240,
                "frame_rate": {"numerator": 25, "denominator": 1},
            },
            "assets": [
                {
                    "id": "background", "media_type": "video",
                    "file_name": background.name, "storage_key": background.name,
                    "size_bytes": background.stat().st_size, "duration_us": 2_400_000,
                },
                {
                    "id": "green-still", "media_type": "image",
                    "file_name": image.name, "storage_key": image.name,
                    "size_bytes": image.stat().st_size, "duration_us": 1_000_000,
                },
            ],
            "tracks": [
                {
                    "id": "base", "type": "video", "name": "Background", "order": 0,
                    "clips": [{
                        "id": "red-bg", "kind": "video", "media_id": "background",
                        "start_us": 0, "duration_us": 2_400_000,
                        "source_in_us": 0, "source_out_us": 2_400_000,
                        "playback_rate": 1, "effects": [], "keyframes": [],
                    }],
                },
                {
                    "id": "still-overlay", "type": "overlay", "name": "Still image",
                    "order": 1, "clips": [{
                        "id": "green-overlay", "kind": "image", "media_id": "green-still",
                        "start_us": 520_000, "duration_us": 680_000,
                        "source_in_us": 0, "source_out_us": 680_000,
                        "playback_rate": 1, "effects": [], "keyframes": [],
                    }],
                },
                {
                    "id": "caption-track", "type": "text", "name": "Captions",
                    "order": 2, "clips": [{
                        "id": "yellow-title", "kind": "text", "start_us": 1_300_000,
                        "duration_us": 900_000,
                        "text": {
                            "content": "AI TITLE", "size": 42, "weight": 700,
                            "fgcolour": "#FFFF00", "bgcolour": "0x00000000",
                            "olcolour": "#000000", "outline": 2,
                            "halign": "center", "valign": "middle",
                            "x_percent": 5, "y_percent": 35,
                            "width_percent": 90, "height_percent": 30,
                        },
                        "effects": [], "keyframes": [],
                    }],
                },
            ],
            "transitions": [],
        }
        output = root / "visual-assets.mp4"
        render_result = render_project(project, root, output, timeout_seconds=60)
        if not render_result.get("ok") or not output.is_file() or output.stat().st_size == 0:
            raise RuntimeError("The visual-assets render did not produce a video.")

        before_image = sample_pixel(output, 0.2, 160, 120)
        during_image = sample_pixel(output, 0.8, 160, 120)
        after_image = sample_pixel(output, 1.25, 160, 120)
        if not (before_image[0] > 150 and before_image[1] < 80):
            raise SystemExit(f"Expected red before the still image; got {before_image}")
        if not (during_image[1] > 80 and during_image[0] < 80):
            raise SystemExit(f"Expected green still-image overlay; got {during_image}")
        if not (after_image[0] > 150 and after_image[1] < 80):
            raise SystemExit(f"Expected red after the still image; got {after_image}")

        yellow_pixels = count_yellow_pixels(output, 1.7)
        # Sample a known-red point above the title text, not the black top-left edge.
        outside_text = sample_pixel(output, 1.7, 160, 20)
        if yellow_pixels < 20:
            raise SystemExit(f"Expected visible yellow text pixels; found {yellow_pixels}")
        if not (outside_text[0] > 150 and outside_text[1] < 80):
            raise SystemExit(f"Text overlay background should be transparent; got {outside_text}")

        print({
            "before_image_rgb": before_image,
            "during_image_rgb": during_image,
            "after_image_rgb": after_image,
            "yellow_text_pixels": yellow_pixels,
            "outside_text_rgb": outside_text,
            "output_bytes": output.stat().st_size,
        })
        print("PASS: still-image duration and transparent Qt title render are verified.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
