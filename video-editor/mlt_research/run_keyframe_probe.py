"""End-to-end proof for scale, position, rotation and opacity keyframes.

Only generated colour media is used. Each assertion samples decoded MP4 frames,
so this checks the actual MLT render rather than only the compiled plan.
"""
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


def pixel_at(video: Path, seconds: float, x: int, y: int) -> tuple[int, int, int]:
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


def make_project(
    project_id: str,
    source: Path,
    keyframes: list[dict],
    transform: dict | None = None,
    background: Path | None = None,
) -> dict:
    clip = {
        "id": "animated-clip", "kind": "video", "media_id": "green-source",
        "start_us": 0, "duration_us": 2_000_000,
        "source_in_us": 0, "source_out_us": 2_000_000,
        "playback_rate": 1, "effects": [],
        "keyframes": keyframes,
    }
    if transform is not None:
        clip["transform"] = transform

    assets = [{
        "id": "green-source", "media_type": "video",
        "file_name": source.name, "storage_key": source.name,
        "size_bytes": source.stat().st_size, "duration_us": 2_000_000,
    }]
    tracks = []
    if background is not None:
        assets.append({
            "id": "red-background", "media_type": "video",
            "file_name": background.name, "storage_key": background.name,
            "size_bytes": background.stat().st_size, "duration_us": 2_000_000,
        })
        tracks.append({
            "id": "background", "type": "video", "name": "Background", "order": 0,
            "clips": [{
                "id": "background-clip", "kind": "video", "media_id": "red-background",
                "start_us": 0, "duration_us": 2_000_000,
                "source_in_us": 0, "source_out_us": 2_000_000,
                "playback_rate": 1, "effects": [], "keyframes": [],
            }],
        })
    tracks.append({
        "id": "animated-track",
        "type": "overlay" if background is not None else "video",
        "name": "Animated clip",
        "order": len(tracks),
        "clips": [clip],
    })
    return {
        "schema_version": 1,
        "id": project_id,
        "name": "Generated transform keyframe proof",
        "revision": 1,
        "timeline_timebase": "microseconds",
        "video_profile": {
            "width": 320, "height": 240,
            "frame_rate": {"numerator": 25, "denominator": 1},
        },
        "assets": assets,
        "tracks": tracks,
        "transitions": [],
    }


def render_case(root: Path, source: Path, name: str, keyframes: list[dict],
                transform: dict | None = None,
                background: Path | None = None) -> Path:
    output = root / f"{name}.mp4"
    result = render_project(
        make_project(f"mlt-{name}-proof", source, keyframes, transform, background),
        root, output, timeout_seconds=60,
    )
    if not result.get("ok") or not output.is_file() or output.stat().st_size == 0:
        raise RuntimeError(f"{name} keyframe render did not produce a video.")
    return output


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="mlt-keyframes-") as folder:
        root = Path(folder)
        source = root / "green.mp4"
        red_background = root / "red-background.mp4"
        run([
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-f", "lavfi", "-i", "color=c=green:s=320x240:r=25:d=2",
            "-an", "-c:v", "mpeg4", "-q:v", "3", "-pix_fmt", "yuv420p",
            str(source),
        ])
        run([
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-f", "lavfi", "-i", "color=c=red:s=320x240:r=25:d=2",
            "-an", "-c:v", "mpeg4", "-q:v", "3", "-pix_fmt", "yuv420p",
            str(red_background),
        ])

        # Animated scale: a half-size frame grows to fill the output.
        scale = render_case(root, source, "scale", [
            {"property": "scale_x", "time_us": 0, "value": 0.5},
            {"property": "scale_y", "time_us": 0, "value": 0.5},
            {"property": "scale_x", "time_us": 1_600_000, "value": 1.0},
            {"property": "scale_y", "time_us": 1_600_000, "value": 1.0},
        ])
        early_corner = pixel_at(scale, 0.2, 20, 20)
        early_center = pixel_at(scale, 0.2, 160, 120)
        late_corner = pixel_at(scale, 1.8, 20, 20)
        if not (early_center[1] > 80 and early_corner[1] < 50):
            raise SystemExit(
                f"Scale proof expected a small centred image early; "
                f"corner={early_corner}, center={early_center}"
            )
        if late_corner[1] < 80:
            raise SystemExit(f"Scale proof expected a full-frame image late; got {late_corner}")

        # Animated position: the half-size image travels from left to right.
        position = render_case(root, source, "position", [
            {"property": "position_x", "time_us": 0, "value": -80},
            {"property": "position_x", "time_us": 1_600_000, "value": 80},
        ], {
            "position": {"x": -80, "y": 0},
            "scale": {"x": 0.5, "y": 0.5},
            "rotation_deg": 0,
            "opacity": 1,
        })
        position_early_left = pixel_at(position, 0.0, 40, 120)
        position_early_right = pixel_at(position, 0.0, 280, 120)
        position_late_left = pixel_at(position, 1.8, 40, 120)
        position_late_right = pixel_at(position, 1.8, 280, 120)
        if not (
            position_early_left[1] > 80 and position_early_right[1] < 50
            and position_late_left[1] < 50 and position_late_right[1] > 80
        ):
            raise SystemExit(
                "Position keyframes did not move the rendered image left-to-right: "
                f"early=({position_early_left}, {position_early_right}), "
                f"late=({position_late_left}, {position_late_right})"
            )

        # Non-linear ease-in must keep the clip nearer its starting position
        # at the midpoint than a linear animation would.
        ease_in = render_case(root, source, "ease-in", [
            {"property": "position_x", "time_us": 0, "value": -80, "interpolation": "ease_in"},
            {"property": "position_x", "time_us": 1_600_000, "value": 80},
        ], {
            "position": {"x": -80, "y": 0},
            "scale": {"x": 0.5, "y": 0.5},
            "rotation_deg": 0,
            "opacity": 1,
        })
        ease_in_left = pixel_at(ease_in, 0.8, 30, 120)
        ease_in_right = pixel_at(ease_in, 0.8, 250, 120)
        if not (ease_in_left[1] > 80 and ease_in_right[1] < 50):
            raise SystemExit(
                "Ease-in keyframes did not preserve the expected early-side position: "
                f"left={ease_in_left}, right={ease_in_right}"
            )

        # Custom cubic Bezier interpolation must also affect the rendered path.
        bezier = render_case(root, source, "bezier", [
            {
                "property": "position_x", "time_us": 0, "value": -80,
                "interpolation": "bezier",
                "bezier": {"x1": 0.25, "y1": 0.1, "x2": 0.25, "y2": 1.0},
            },
            {"property": "position_x", "time_us": 1_600_000, "value": 80},
        ], {
            "position": {"x": -80, "y": 0},
            "scale": {"x": 0.5, "y": 0.5},
            "rotation_deg": 0,
            "opacity": 1,
        })
        bezier_left = pixel_at(bezier, 0.8, 30, 120)
        bezier_right = pixel_at(bezier, 0.8, 250, 120)
        if not (bezier_left[1] < 50 and bezier_right[1] > 80):
            raise SystemExit(
                "Bezier keyframes did not affect the rendered interpolation: "
                f"left={bezier_left}, right={bezier_right}"
            )

        # Animated rotation: a 45-degree turn moves the source's corner region
        # outside the output canvas while the centre remains visible.
        rotation = render_case(root, source, "rotation", [
            {"property": "rotation_deg", "time_us": 0, "value": 0},
            {"property": "rotation_deg", "time_us": 1_600_000, "value": 45},
        ], {
            "position": {"x": 0, "y": 0},
            "scale": {"x": 1, "y": 1},
            "rotation_deg": 0,
            "opacity": 1,
        })
        rotation_early_corner = pixel_at(rotation, 0.2, 40, 40)
        rotation_late_corner = pixel_at(rotation, 1.8, 5, 5)
        rotation_late_center = pixel_at(rotation, 1.8, 160, 120)
        if not (
            rotation_early_corner[1] > 80
            and rotation_late_corner[1] < 50
            and rotation_late_center[1] > 80
        ):
            raise SystemExit(
                "Rotation keyframes did not rotate the rendered image: "
                f"early corner={rotation_early_corner}, late corner={rotation_late_corner}, "
                f"late centre={rotation_late_center}"
            )

        # Animated opacity: the image fades from full strength to 20 percent.
        # Fade an overlay over a red background so the opacity change is
        # observable as a real composite, not an isolated producer frame.
        opacity = render_case(root, source, "opacity", [
            {"property": "opacity", "time_us": 0, "value": 1},
            {"property": "opacity", "time_us": 1_600_000, "value": 0.2},
        ], {
            "position": {"x": 0, "y": 0},
            "scale": {"x": 1, "y": 1},
            "rotation_deg": 0,
            "opacity": 1,
        }, background=red_background)
        opacity_early = pixel_at(opacity, 0.0, 160, 120)
        opacity_late = pixel_at(opacity, 1.8, 160, 120)
        if not (
            opacity_early[1] > opacity_early[0] + 50
            and opacity_late[0] > opacity_late[1] + 50
        ):
            raise SystemExit(
                "Opacity keyframes did not fade the green overlay to reveal red: "
                f"early={opacity_early}, late={opacity_late}"
            )

        print(json.dumps({
            "scale": {
                "early_corner_rgb": early_corner,
                "early_center_rgb": early_center,
                "late_corner_rgb": late_corner,
            },
            "position": {
                "early_left_rgb": position_early_left,
                "early_right_rgb": position_early_right,
                "late_left_rgb": position_late_left,
                "late_right_rgb": position_late_right,
            },
            "rotation": {
                "early_corner_rgb": rotation_early_corner,
                "late_corner_rgb": rotation_late_corner,
                "late_center_rgb": rotation_late_center,
            },
            "opacity": {
                "early_center_rgb": opacity_early,
                "late_center_rgb": opacity_late,
            },
        }, indent=2, sort_keys=True))
        print(
            "PASS: decoded MLT renders prove animated scale, position, rotation and opacity."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
