"""Verify MLT fit/fill/stretch framing with actual rendered pixels."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve()
VIDEO_EDITOR_ROOT = HERE.parents[1]
if str(VIDEO_EDITOR_ROOT) not in sys.path:
    sys.path.insert(0, str(VIDEO_EDITOR_ROOT))

from mlt_engine.renderer import render_project  # noqa: E402


def _pixel_at(video: Path, seconds: float, x: int, y: int) -> tuple[int, int, int]:
    result = subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-loglevel", "error",
            "-ss", f"{seconds:.4f}", "-i", str(video),
            "-vf", f"crop=1:1:{x}:{y},format=rgb24",
            "-frames:v", "1", "-f", "rawvideo", "-",
        ],
        check=True,
        capture_output=True,
        timeout=30,
    )
    if len(result.stdout) != 3:
        raise RuntimeError("FFmpeg could not decode a sample pixel from the framing render.")
    return tuple(result.stdout)


def _assert_dark(pixel: tuple[int, int, int], label: str) -> None:
    if max(pixel) > 55:
        raise AssertionError(f"{label} should be a letterbox bar; got RGB {pixel}")


def _assert_yellow(pixel: tuple[int, int, int], label: str) -> None:
    if not (pixel[0] > 150 and pixel[1] > 150 and pixel[2] < 110):
        raise AssertionError(f"{label} should retain the yellow source strip; got RGB {pixel}")


def _assert_blue(pixel: tuple[int, int, int], label: str) -> None:
    if not (pixel[2] > 130 and pixel[0] < 100 and pixel[1] < 120):
        raise AssertionError(f"{label} should show the blue source; got RGB {pixel}")


def main() -> int:
    if len(sys.argv) != 3:
        raise SystemExit("Usage: run_framing_probe.py ASSET_ROOT OUTPUT_MP4")
    asset_root = Path(sys.argv[1]).resolve(strict=True)
    output = Path(sys.argv[2]).resolve()
    source = asset_root / "framing-source.mp4"
    still = asset_root / "framing-still.png"
    if not source.is_file() or not still.is_file():
        raise SystemExit("The generated 4:3 framing video and still image must exist.")

    project = {
        "schema_version": 1,
        "id": "mlt-framing-ci-project",
        "name": "MLT fit fill stretch render verification",
        "revision": 1,
        "timeline_timebase": "microseconds",
        "video_profile": {
            "width": 320,
            "height": 180,
            "frame_rate": {"numerator": 25, "denominator": 1},
        },
        "assets": [
            {
                "id": "asset-framing-source",
                "media_type": "video",
                "file_name": source.name,
                "storage_key": source.name,
                "size_bytes": source.stat().st_size,
                "duration_us": 1_000_000,
            },
            {
                "id": "asset-framing-still",
                "media_type": "image",
                "file_name": still.name,
                "storage_key": still.name,
                "size_bytes": still.stat().st_size,
                "duration_us": 1_000_000,
            },
        ],
        "tracks": [{
            "id": "track-framing",
            "type": "video",
            "name": "Framing modes",
            "order": 0,
            "clips": [
                {
                    "id": f"clip-{mode}",
                    "kind": "video",
                    "media_id": "asset-framing-source",
                    "start_us": index * 1_000_000,
                    "duration_us": 1_000_000,
                    "source_in_us": 0,
                    "source_out_us": 1_000_000,
                    "playback_rate": 1,
                    "framing": {
                        "mode": mode,
                        "horizontal_alignment": "center",
                        "vertical_alignment": "middle",
                    },
                    "effects": [],
                    "keyframes": [],
                }
                for index, mode in enumerate(("fit", "fill", "stretch"))
            ],
        }, {
            "id": "track-framing-still",
            "type": "overlay",
            "name": "Framed still image",
            "order": 1,
            "clips": [{
                "id": "clip-framing-still",
                "kind": "image",
                "media_id": "asset-framing-still",
                "start_us": 3_000_000,
                "duration_us": 1_000_000,
                "source_in_us": 0,
                "source_out_us": 1_000_000,
                "playback_rate": 1,
                "framing": {
                    "mode": "fill",
                    "horizontal_alignment": "center",
                    "vertical_alignment": "middle",
                },
                "effects": [],
                "keyframes": [],
            }],
        }],
        "transitions": [],
    }

    result = render_project(project, asset_root, output, timeout_seconds=90)
    fit_bar = _pixel_at(output, 0.25, 10, 90)
    fit_strip = _pixel_at(output, 0.25, 160, 4)
    fill_edge = _pixel_at(output, 1.25, 10, 90)
    fill_top = _pixel_at(output, 1.25, 160, 4)
    stretch_edge = _pixel_at(output, 2.25, 10, 90)
    stretch_top = _pixel_at(output, 2.25, 160, 4)
    still_edge = _pixel_at(output, 3.25, 10, 90)
    still_top = _pixel_at(output, 3.25, 160, 4)

    _assert_dark(fit_bar, "Fit left edge")
    _assert_yellow(fit_strip, "Fit top strip")
    _assert_blue(fill_edge, "Fill left edge")
    _assert_blue(fill_top, "Fill cropped top")
    _assert_blue(stretch_edge, "Stretch left edge")
    _assert_yellow(stretch_top, "Stretch top strip")
    _assert_blue(still_edge, "Framed still-image left edge")
    _assert_blue(still_top, "Framed still-image cropped top")

    print(json.dumps({
        "status": "passed",
        "render": result,
        "sampled_pixels": {
            "fit_letterbox": fit_bar,
            "fit_source_top": fit_strip,
            "fill_edge": fill_edge,
            "fill_cropped_top": fill_top,
            "stretch_edge": stretch_edge,
            "stretch_source_top": stretch_top,
            "still_image_fill_edge": still_edge,
            "still_image_fill_cropped_top": still_top,
        },
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
