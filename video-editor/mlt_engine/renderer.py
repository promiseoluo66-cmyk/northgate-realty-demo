"""Compile canonical editor projects into MLT multi-track renders.

Verified prototype support:
- Video, overlay, still-image and text/caption tracks with audio mixing.
- Dissolves and horizontal luma-map wipes in both directions.
- Static transforms and position/scale/rotation/opacity keyframes, including
  hold, linear, ease-in, ease-out, ease-in-out and cubic Bezier interpolation.
- Constant playback speed and keyframed video speed ramps.
- Audio gain/fades and clip-level volume keyframes.
- Allowlisted brightness, chroma, contrast and saturation effects.
- Transparent text/title/caption PNG overlays and timed still-image overlays.

Known combinations and advanced capabilities remain explicitly rejected.
This is an isolated engine prototype, not the production renderer.
"""
from __future__ import annotations

import json
import math
import os
import re
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

from project_model import validate_project


class MltRenderError(RuntimeError):
    """Raised when an MLT render cannot be compiled or completed."""


def _frame_at_us(time_us: int, fps_num: int, fps_den: int) -> int:
    """Convert microseconds to the nearest project frame (half-up)."""
    numerator = time_us * fps_num
    denominator = 1_000_000 * fps_den
    return (2 * numerator + denominator) // (2 * denominator)


def _is_identity_transform(clip: dict[str, Any]) -> bool:
    transform = clip.get("transform")
    if transform is None:
        return True
    position = transform.get("position", {})
    scale = transform.get("scale", {})
    return (
        math.isclose(float(position.get("x", 0)), 0.0, abs_tol=1e-9)
        and math.isclose(float(position.get("y", 0)), 0.0, abs_tol=1e-9)
        and math.isclose(float(scale.get("x", 1)), 1.0, abs_tol=1e-9)
        and math.isclose(float(scale.get("y", 1)), 1.0, abs_tol=1e-9)
        and math.isclose(float(transform.get("rotation_deg", 0)), 0.0, abs_tol=1e-9)
        and math.isclose(float(transform.get("opacity", 1)), 1.0, abs_tol=1e-9)
        and math.isclose(float(transform.get("anchor_x", 0.5)), 0.5, abs_tol=1e-9)
        and math.isclose(float(transform.get("anchor_y", 0.5)), 0.5, abs_tol=1e-9)
        and not bool(transform.get("flip_horizontal", False))
        and not bool(transform.get("flip_vertical", False))
    )

_VISUAL_KEYFRAME_PROPERTIES = {
    "position_x", "position_y", "scale_x", "scale_y", "rotation_deg", "opacity",
    "crop_x", "crop_y", "crop_width", "crop_height",
}


def _bezier_coordinate(t: float, p1: float, p2: float) -> float:
    inverse = 1.0 - t
    return 3.0 * inverse * inverse * t * p1 + 3.0 * inverse * t * t * p2 + t * t * t


def _eased_ratio(ratio: float, keyframe: dict[str, Any]) -> float:
    """Evaluate the interpolation leaving this keyframe."""
    ratio = max(0.0, min(1.0, ratio))
    mode = keyframe.get("interpolation", "linear")
    if mode == "hold":
        return 0.0
    if mode == "linear":
        return ratio
    if mode in {"ease_in", "ease_in_cubic"}:
        return ratio ** 3
    if mode in {"ease_out", "ease_out_cubic"}:
        return 1.0 - (1.0 - ratio) ** 3
    if mode in {"ease_in_out", "ease_in_out_cubic"}:
        return 4.0 * ratio ** 3 if ratio < 0.5 else 1.0 - ((-2.0 * ratio + 2.0) ** 3) / 2.0
    if mode == "ease_in_quad":
        return ratio ** 2
    if mode == "ease_out_quad":
        return 1.0 - (1.0 - ratio) ** 2
    if mode == "ease_in_out_quad":
        return 2.0 * ratio ** 2 if ratio < 0.5 else 1.0 - ((-2.0 * ratio + 2.0) ** 2) / 2.0
    if mode == "ease_in_quart":
        return ratio ** 4
    if mode == "ease_out_quart":
        return 1.0 - (1.0 - ratio) ** 4
    if mode == "ease_in_out_quart":
        return 8.0 * ratio ** 4 if ratio < 0.5 else 1.0 - ((-2.0 * ratio + 2.0) ** 4) / 2.0
    if mode == "smoothstep":
        return ratio * ratio * (3.0 - 2.0 * ratio)
    if mode == "bezier":
        curve = keyframe.get("bezier", {})
        x1 = float(curve.get("x1", 0.25))
        y1 = float(curve.get("y1", 0.1))
        x2 = float(curve.get("x2", 0.25))
        y2 = float(curve.get("y2", 1.0))
        # Invert the Bezier x coordinate with a bounded binary search, then
        # evaluate y. The control points are validated by project_model.py.
        low, high = 0.0, 1.0
        for _ in range(28):
            middle = (low + high) / 2.0
            if _bezier_coordinate(middle, x1, x2) < ratio:
                low = middle
            else:
                high = middle
        return _bezier_coordinate((low + high) / 2.0, y1, y2)
    raise MltRenderError(f"Unsupported keyframe interpolation {mode!r}.")


def _compile_speed_segments(
    clip: dict[str, Any],
    duration_frames: int,
    fps_num: int,
    fps_den: int,
    source_in_frame: int,
) -> tuple[list[dict[str, Any]], float]:
    """Turn constant or keyframed speed into bounded MLT timewarp segments."""
    base_rate = float(clip.get("playback_rate", 1.0))
    keyframes = sorted(
        (
            item for item in clip.get("keyframes", [])
            if item["property"] == "playback_rate"
        ),
        key=lambda item: item["time_us"],
    )

    if keyframes and clip["kind"] != "video":
        raise MltRenderError("Speed-ramp keyframes are currently supported on video clips only.")
    if keyframes and any(
        item["property"] in _VISUAL_KEYFRAME_PROPERTIES
        for item in clip.get("keyframes", [])
    ):
        raise MltRenderError(
            "Speed-ramp keyframes cannot yet be combined with animated visual transforms."
        )
    if keyframes and clip.get("effects"):
        raise MltRenderError(
            "Speed-ramp keyframes cannot yet be combined with clip effects."
        )

    def speed_at_frame(frame: float) -> float:
        time_us = frame * 1_000_000 * fps_den / fps_num
        if not keyframes or time_us < keyframes[0]["time_us"]:
            return base_rate
        if len(keyframes) == 1:
            return float(keyframes[0]["value"])
        for left, right in zip(keyframes, keyframes[1:]):
            if time_us <= right["time_us"]:
                span = right["time_us"] - left["time_us"]
                if span <= 0:
                    raise MltRenderError("Playback speed keyframe times must increase.")
                ratio = (time_us - left["time_us"]) / span
                eased = _eased_ratio(ratio, left)
                return float(left["value"]) + (
                    float(right["value"]) - float(left["value"])
                ) * eased
        return float(keyframes[-1]["value"])

    # A curve is sampled into short constant-speed segments. The 1,024-segment
    # cap bounds the number of MLT producers even for long source clips.
    step = max(1, math.ceil(duration_frames / 1024)) if keyframes else duration_frames
    source_cursor = float(source_in_frame)
    segments: list[dict[str, Any]] = []
    for output_start in range(0, duration_frames, step):
        output_end = min(duration_frames, output_start + step)
        segment_frames = output_end - output_start
        rate = speed_at_frame((output_start + output_end) / 2.0)
        if not 0.05 <= rate <= 16.0 or not math.isfinite(rate):
            raise MltRenderError("Playback speed curve values must stay between 0.05x and 16x.")
        render_in = round(source_cursor / rate)
        segments.append({
            "output_start_frame": output_start,
            "duration_frames": segment_frames,
            "playback_rate": rate,
            "render_in_frame": render_in,
            "render_out_frame": render_in + segment_frames - 1,
        })
        source_cursor += rate * segment_frames

    if not segments:
        raise MltRenderError("A clip must contain at least one output frame.")
    return segments, source_cursor - source_in_frame


def _compile_clip_transform(
    clip: dict[str, Any], width: int, height: int,
    fps_num: int, fps_den: int, duration_frames: int,
    source_dimensions: tuple[int, int] | None = None,
) -> dict[str, Any] | None:
    """Compile visual transforms, animated crops and sampled easing into MLT."""
    raw_transform = clip.get("transform") or {}
    position = raw_transform.get("position", {})
    scale = raw_transform.get("scale", {})
    crop = clip.get("crop")
    crop_props = {"crop_x", "crop_y", "crop_width", "crop_height"}
    keyframes = clip.get("keyframes", [])
    crop_keyframes = any(item["property"] in crop_props for item in keyframes)
    crop_active = crop is not None or crop_keyframes
    framing = clip.get("framing")
    if crop_active and framing:
        raise MltRenderError("Manual crop cannot be combined with automatic framing.")
    if crop_active and source_dimensions is None:
        raise MltRenderError("Manual crop requires readable source width and height metadata.")
    base = {
        "position_x": float(position.get("x", 0.0)),
        "position_y": float(position.get("y", 0.0)),
        "scale_x": float(scale.get("x", 1.0)),
        "scale_y": float(scale.get("y", 1.0)),
        "rotation_deg": float(raw_transform.get("rotation_deg", 0.0)),
        "opacity": float(raw_transform.get("opacity", 1.0)),
        "anchor_x": float(raw_transform.get("anchor_x", 0.5)),
        "anchor_y": float(raw_transform.get("anchor_y", 0.5)),
        "flip_horizontal": bool(raw_transform.get("flip_horizontal", False)),
        "flip_vertical": bool(raw_transform.get("flip_vertical", False)),
        "crop_x": float((crop or {}).get("x", 0.0)),
        "crop_y": float((crop or {}).get("y", 0.0)),
        "crop_width": float((crop or {}).get("width", 1.0)),
        "crop_height": float((crop or {}).get("height", 1.0)),
    }
    if not keyframes and _is_identity_transform(clip) and not framing and not crop_active:
        return None

    grouped: dict[str, list[dict[str, Any]]] = {}
    for keyframe in keyframes:
        prop = keyframe["property"]
        if prop not in _VISUAL_KEYFRAME_PROPERTIES:
            if prop in {"playback_rate", "volume_db"}:
                continue
            raise MltRenderError(
                f"Keyframe property {prop!r} is not supported by this visual MLT adapter."
            )
        grouped.setdefault(prop, []).append(keyframe)
    for entries in grouped.values():
        entries.sort(key=lambda item: item["time_us"])

    def value_at(prop: str, time_us: int) -> float:
        entries = grouped.get(prop, [])
        if not entries or time_us < entries[0]["time_us"]:
            return base[prop]
        if len(entries) == 1:
            return float(entries[0]["value"])
        for left, right in zip(entries, entries[1:]):
            if time_us <= right["time_us"]:
                span = right["time_us"] - left["time_us"]
                if span <= 0:
                    raise MltRenderError("Keyframe times must increase.")
                ratio = (time_us - left["time_us"]) / span
                eased = _eased_ratio(ratio, left)
                return float(left["value"]) + (float(right["value"]) - float(left["value"])) * eased
        return float(entries[-1]["value"])

    framing_mode = framing.get("mode") if framing else None
    source_width = source_height = 0
    if crop_active or framing_mode in {"fit", "fill"}:
        if source_dimensions is None:
            requirement = "Manual crop" if crop_active else framing_mode.title() + " framing"
            raise MltRenderError(f"{requirement} requires readable source width and height metadata.")
        source_width, source_height = source_dimensions
        if source_width <= 0 or source_height <= 0:
            raise MltRenderError("Framing/crop requires positive source dimensions.")

    if framing_mode in {"fit", "fill"}:
        base_framing_scale = (
            min(width / source_width, height / source_height)
            if framing_mode == "fit" else max(width / source_width, height / source_height)
        )
        default_framing_width = source_width * base_framing_scale
        default_framing_height = source_height * base_framing_scale
    else:
        default_framing_width = float(width)
        default_framing_height = float(height)

    has_animation = any(len(entries) > 1 for entries in grouped.values())
    if has_animation:
        sample_step = max(1, math.ceil(duration_frames / 10000))
        sample_times = {
            frame: frame * 1_000_000 * fps_den // fps_num
            for frame in range(0, duration_frames, sample_step)
        }
        sample_times[duration_frames - 1] = (
            (duration_frames - 1) * 1_000_000 * fps_den // fps_num
        )
        for keyframe in keyframes:
            if keyframe["property"] in _VISUAL_KEYFRAME_PROPERTIES:
                frame = min(_frame_at_us(keyframe["time_us"], fps_num, fps_den), duration_frames - 1)
                sample_times[frame] = keyframe["time_us"]
    else:
        sample_times = {0: 0}

    points: list[tuple[int, str, float, float]] = []
    for frame, time_us in sorted(sample_times.items()):
        values = {prop: value_at(prop, time_us) for prop in base}
        framing_width = default_framing_width
        framing_height = default_framing_height
        crop_source_offset_x = crop_source_offset_y = 0.0
        crop_view_width, crop_view_height = float(width), float(height)
        if crop_active:
            crop_x, crop_y = values["crop_x"], values["crop_y"]
            crop_w, crop_h = values["crop_width"], values["crop_height"]
            if (
                crop_x < 0 or crop_y < 0 or crop_w <= 0 or crop_h <= 0
                or crop_x + crop_w > 1.000000001
                or crop_y + crop_h > 1.000000001
            ):
                raise MltRenderError("Animated crop rectangle must stay inside the source frame.")
            if values["flip_horizontal"]:
                crop_x = 1.0 - crop_x - crop_w
            if values["flip_vertical"]:
                crop_y = 1.0 - crop_y - crop_h
            crop_source_width = crop_w * source_width
            crop_source_height = crop_h * source_height
            crop_scale = max(width / crop_source_width, height / crop_source_height)
            framing_width, framing_height = source_width * crop_scale, source_height * crop_scale
            crop_source_offset_x = crop_x * source_width * crop_scale
            crop_source_offset_y = crop_y * source_height * crop_scale
            crop_view_width = crop_source_width * crop_scale
            crop_view_height = crop_source_height * crop_scale

        rect_width = framing_width * values["scale_x"]
        rect_height = framing_height * values["scale_y"]
        if rect_width > 8192 or rect_height > 8192:
            raise MltRenderError("Transformed clip dimensions exceed the 8192-pixel safety limit.")
        if rect_width <= 0 or rect_height <= 0:
            raise MltRenderError("Animated scale must remain greater than zero.")
        if crop_active:
            rect_x = (width - crop_view_width * values["scale_x"]) / 2.0
            rect_y = (height - crop_view_height * values["scale_y"]) / 2.0
            rect_x -= crop_source_offset_x * values["scale_x"]
            rect_y -= crop_source_offset_y * values["scale_y"]
        elif framing_mode in {"fit", "fill"}:
            horizontal = framing.get("horizontal_alignment", "center")
            vertical = framing.get("vertical_alignment", "middle")
            rect_x = 0.0 if horizontal == "left" else (
                (width - rect_width) / 2.0 if horizontal == "center" else width - rect_width
            )
            rect_y = 0.0 if vertical == "top" else (
                (height - rect_height) / 2.0 if vertical == "middle" else height - rect_height
            )
        else:
            rect_x, rect_y = (width - rect_width) / 2.0, (height - rect_height) / 2.0

        angle = math.radians(values["rotation_deg"])
        cosine, sine = math.cos(angle), math.sin(angle)
        center_to_pivot_x = (0.5 - values["anchor_x"]) * rect_width
        center_to_pivot_y = (0.5 - values["anchor_y"]) * rect_height
        pivot_shift_x = cosine * center_to_pivot_x - sine * center_to_pivot_y - center_to_pivot_x
        pivot_shift_y = sine * center_to_pivot_x + cosine * center_to_pivot_y - center_to_pivot_y
        rect_x += values["position_x"] + pivot_shift_x
        rect_y += values["position_y"] + pivot_shift_y
        rect = f"{rect_x:.3f}/{rect_y:.3f}:{rect_width:.3f}x{rect_height:.3f}:1.000"
        points.append((frame, rect, values["rotation_deg"], values["opacity"]))

    if len(points) == 1:
        rect_value = points[0][1]
        rotation_value: str | float = points[0][2]
    else:
        rect_value = ";".join(f"{frame}={rect}" for frame, rect, _, _ in points)
        rotation_value = ";".join(
            f"{frame}={rotation:.6f}" for frame, _, rotation, _ in points
        )
    opacity_alpha_value = (
        ";".join(f"{frame}={opacity:.3f}" for frame, _, _, opacity in points)
        if len(points) > 1 else f"{points[0][3]:.3f}"
    )
    return {
        "rect": rect_value,
        "rotation": rotation_value,
        "opacity_alpha": opacity_alpha_value,
        "opacity_enabled": (
            any(not math.isclose(point[3], 1.0, abs_tol=1e-9) for point in points)
            or len(grouped.get("opacity", [])) > 1
        ),
        "animated": has_animation,
        "rotation_animated": len(grouped.get("rotation_deg", [])) > 1,
        "framing": dict(framing) if framing else None,
        "crop": dict(crop) if crop else ({"animated": True} if crop_keyframes else None),
        "flip_horizontal": base["flip_horizontal"],
        "flip_vertical": base["flip_vertical"],
    }


def _compile_audio_keyframes(
    clip: dict[str, Any],
    fps_num: int,
    fps_den: int,
    duration_frames: int,
) -> str | None:
    """Compile clip-local volume keyframes to an animated linear-amplitude curve."""
    entries = [
        item for item in clip.get("keyframes", [])
        if item["property"] == "volume_db"
    ]
    unsupported = [
        item["property"] for item in clip.get("keyframes", [])
        if item["property"] != "volume_db"
    ]
    if unsupported:
        raise MltRenderError(
            "Audio clips currently support volume_db keyframes only; "
            + ", ".join(sorted(set(unsupported)))
        )
    if not entries:
        return None

    entries.sort(key=lambda item: item["time_us"])

    def db_at(time_us: int) -> float:
        if time_us < entries[0]["time_us"]:
            return 0.0
        if len(entries) == 1:
            return float(entries[0]["value"])
        for left, right in zip(entries, entries[1:]):
            if time_us <= right["time_us"]:
                span = right["time_us"] - left["time_us"]
                if span <= 0:
                    raise MltRenderError("Audio keyframe times must increase.")
                ratio = (time_us - left["time_us"]) / span
                eased = _eased_ratio(ratio, left)
                start = float(left["value"])
                return start + (float(right["value"]) - start) * eased
        return float(entries[-1]["value"])

    animated = len(entries) > 1 and any(
        item.get("interpolation", "linear") != "linear" for item in entries[:-1]
    )
    step = max(1, math.ceil(duration_frames / 10000)) if animated else duration_frames
    sample_frames = set(range(0, duration_frames, step))
    sample_frames.update(
        min(_frame_at_us(item["time_us"], fps_num, fps_den), duration_frames - 1)
        for item in entries
    )
    sample_frames.add(duration_frames - 1)

    points = []
    for frame in sorted(sample_frames):
        time_us = frame * 1_000_000 * fps_den // fps_num
        decibels = db_at(time_us)
        gain = 10.0 ** (decibels / 20.0)
        points.append(f"{frame}={gain:.9f}")
    return ";".join(points)


def _probe_media_dimensions(path: Path) -> tuple[int, int]:
    """Read the first video/image stream dimensions using bounded FFprobe input."""
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "error", "-select_streams", "v:0",
                "-show_entries", "stream=width,height", "-of", "json", str(path),
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
        report = json.loads(result.stdout)
    except FileNotFoundError as exc:
        raise MltRenderError("FFprobe is required for fill framing source dimensions.") from exc
    except subprocess.TimeoutExpired as exc:
        raise MltRenderError("FFprobe timed out while reading fill framing dimensions.") from exc
    except (subprocess.CalledProcessError, json.JSONDecodeError) as exc:
        raise MltRenderError("FFprobe could not read fill framing source dimensions.") from exc

    streams = report.get("streams", [])
    if not streams:
        raise MltRenderError("Fill framing source has no readable video/image stream.")
    width = streams[0].get("width")
    height = streams[0].get("height")
    if (
        isinstance(width, bool) or not isinstance(width, int) or not 1 <= width <= 32768
        or isinstance(height, bool) or not isinstance(height, int) or not 1 <= height <= 32768
    ):
        raise MltRenderError("Fill framing source dimensions are missing or outside safe limits.")
    return width, height


def _resolve_asset(asset: dict[str, Any], asset_root: Path) -> Path:
    storage_key = asset["storage_key"]
    candidate = (asset_root / storage_key).resolve(strict=True)
    try:
        candidate.relative_to(asset_root)
    except ValueError as exc:
        raise MltRenderError(
            f"Asset {asset['id']} resolves outside the approved media directory."
        ) from exc
    if not candidate.is_file():
        raise MltRenderError(f"Asset {asset['id']} is not a regular file.")
    return candidate


def _format_sox_time(microseconds: int) -> str:
    hours, remainder = divmod(microseconds, 3_600_000_000)
    minutes, remainder = divmod(remainder, 60_000_000)
    seconds, fraction = divmod(remainder, 1_000_000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}.{fraction:06d}"


def _validate_effects(clip: dict[str, Any], track_type: str) -> list[dict[str, Any]]:
    accepted: list[dict[str, Any]] = []
    for effect in clip.get("effects", []):
        if effect.get("enabled", True) is False:
            continue
        effect_type = effect["type"]
        parameters = effect.get("parameters", {})
        if track_type == "audio":
            if effect_type == "gain":
                gain_db = parameters.get("gain_db", 0.0)
                if isinstance(gain_db, bool) or not isinstance(gain_db, (int, float)):
                    raise MltRenderError("gain.gain_db must be a number.")
                if not math.isfinite(float(gain_db)) or not -96.0 <= float(gain_db) <= 24.0:
                    raise MltRenderError("gain.gain_db must be between -96 and 24 dB.")
                gain = 10.0 ** (float(gain_db) / 20.0)
                accepted.append({
                    "type": "avfilter.volume",
                    "volume": f"{gain:.9f}",
                })
            elif effect_type == "fade":
                fade_in_us = parameters.get("fade_in_us", 0)
                fade_out_us = parameters.get("fade_out_us", 0)
                for name, value in (("fade_in_us", fade_in_us), ("fade_out_us", fade_out_us)):
                    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                        raise MltRenderError(f"fade.{name} must be a non-negative integer.")
                duration_us = clip["duration_us"]
                if fade_in_us + fade_out_us > duration_us:
                    raise MltRenderError("Audio fade-in and fade-out cannot exceed the clip duration.")
                if fade_in_us == 0 and fade_out_us == 0:
                    raise MltRenderError("An audio fade must have a non-zero fade-in or fade-out.")
                if fade_in_us:
                    accepted.append({
                        "type": "avfilter.afade",
                        "direction": "in",
                        "start_time": f"{0.0:.6f}",
                        "duration": f"{fade_in_us / 1_000_000:.6f}",
                        "curve": "qsin",
                    })
                if fade_out_us:
                    start_time = (duration_us - fade_out_us) / 1_000_000
                    accepted.append({
                        "type": "avfilter.afade",
                        "direction": "out",
                        "start_time": f"{start_time:.6f}",
                        "duration": f"{fade_out_us / 1_000_000:.6f}",
                        "curve": "qsin",
                    })
            else:
                raise MltRenderError(
                    f"Audio effect {effect_type!r} is not in the approved SoX filter allowlist."
                )
            continue
        if effect_type == "brightness":
            level = parameters.get("level", 1.0)
            if isinstance(level, bool) or not isinstance(level, (int, float)):
                raise MltRenderError("brightness.level must be a number.")
            if not math.isfinite(float(level)) or not 0.0 <= float(level) <= 15.0:
                raise MltRenderError("brightness.level must be between 0 and 15.")
            accepted.append({"type": "brightness", "level": float(level)})
        elif effect_type in {"contrast", "saturation"}:
            value = parameters.get("value", 1.0)
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise MltRenderError(f"{effect_type}.value must be a number.")
            upper = 4.0 if effect_type == "contrast" else 3.0
            if not math.isfinite(float(value)) or not 0.0 <= float(value) <= upper:
                raise MltRenderError(f"{effect_type}.value must be between 0 and {upper:g}.")
            accepted.append({
                "type": "avfilter.eq",
                "contrast": float(value) if effect_type == "contrast" else 1.0,
                "saturation": float(value) if effect_type == "saturation" else 1.0,
            })
        elif effect_type == "chroma":
            key = parameters.get("key", "#00ff00")
            variance = parameters.get("variance", 0.15)
            if not isinstance(key, str) or not re.fullmatch(r"#[0-9A-Fa-f]{6}", key):
                raise MltRenderError("chroma.key must be a #RRGGBB colour.")
            if isinstance(variance, bool) or not isinstance(variance, (int, float)):
                raise MltRenderError("chroma.variance must be a number.")
            if not math.isfinite(float(variance)) or not 0.0 <= float(variance) <= 1.0:
                raise MltRenderError("chroma.variance must be between 0 and 1.")
            accepted.append({
                "type": "chroma",
                "key": key,
                "variance": float(variance),
            })
        else:
            raise MltRenderError(
                f"Effect {effect_type!r} is not in the approved MLT filter allowlist."
            )
    return accepted


def compile_render_plan(project_document: Any, asset_root: str | Path) -> dict[str, Any]:
    """Validate a project and produce a safe, frame-based MLT render plan."""
    project = validate_project(project_document)
    root = Path(asset_root).resolve(strict=True)
    if not root.is_dir():
        raise MltRenderError("The media root must be an existing directory.")

    profile = project["video_profile"]
    fps_num = profile["frame_rate"]["numerator"]
    fps_den = profile["frame_rate"]["denominator"]
    assets = {asset["id"]: asset for asset in project["assets"]}

    tracks = project["tracks"]
    enabled_tracks = [
        track for track in tracks
        if track.get("enabled", True)
        and track["type"] in {"video", "overlay", "text", "audio"}
        and not (track["type"] == "audio" and track.get("muted", False))
    ]

    # Solo is evaluated independently for visual layers and audio sources.
    # Soloing a video/overlay hides other visual layers but keeps separate
    # music/audio tracks. Soloing an audio track keeps the picture intact and
    # suppresses audio from every non-solo source.
    visual_types = {"video", "overlay", "text"}
    visual_solo_active = any(
        track.get("solo", False) and track["type"] in visual_types
        for track in enabled_tracks
    )
    audio_solo_active = any(
        track.get("solo", False) and track["type"] == "audio"
        for track in enabled_tracks
    )
    if visual_solo_active:
        enabled_tracks = [
            track for track in enabled_tracks
            if track["type"] not in visual_types or track.get("solo", False)
        ]
    if audio_solo_active:
        enabled_tracks = [
            track for track in enabled_tracks
            if track["type"] != "audio" or track.get("solo", False)
        ]

    # First transition increment: isolated dissolves between adjacent clips
    # on one visual track. More complex transition graphs remain rejected.
    ordered_by_track = {
        track["id"]: sorted(track["clips"], key=lambda item: item["start_us"])
        for track in enabled_tracks
    }
    clip_locations: dict[str, tuple[dict[str, Any], dict[str, Any]]] = {}
    clip_positions: dict[str, int] = {}
    for track in enabled_tracks:
        for position, clip in enumerate(ordered_by_track[track["id"]]):
            clip_locations[clip["id"]] = (track, clip)
            clip_positions[clip["id"]] = position

    transitions_by_track: dict[str, list[dict[str, Any]]] = {
        track["id"]: [] for track in enabled_tracks
    }
    transition_clip_ids: set[str] = set()
    for transition in project.get("transitions", []):
        transition_type = transition["type"]
        parameters = transition.get("parameters", {})
        if transition_type == "dissolve":
            if parameters:
                raise MltRenderError("Dissolve transition parameters are not enabled yet.")
            clean_parameters: dict[str, Any] = {}
        elif transition_type == "wipe":
            unknown = sorted(set(parameters) - {"direction", "softness"})
            if unknown:
                raise MltRenderError("Unsupported wipe parameter(s): " + ", ".join(unknown))
            direction = parameters.get("direction", "left_to_right")
            if not isinstance(direction, str) or direction not in {"left_to_right", "right_to_left"}:
                raise MltRenderError("wipe.direction must be left_to_right or right_to_left.")
            softness = parameters.get("softness", 0.08)
            if isinstance(softness, bool) or not isinstance(softness, (int, float)) or not math.isfinite(float(softness)) or not 0 <= float(softness) <= 1:
                raise MltRenderError("wipe.softness must be a number from 0 to 1.")
            clean_parameters = {"direction": direction, "softness": float(softness)}
        else:
            raise MltRenderError("Only dissolve and wipe transitions are enabled in this adapter stage.")
        from_id = transition["from_clip_id"]
        to_id = transition["to_clip_id"]
        if from_id not in clip_locations or to_id not in clip_locations:
            raise MltRenderError(
                "A transition must reference clips on enabled video or overlay tracks."
            )
        from_track, from_clip = clip_locations[from_id]
        to_track, to_clip = clip_locations[to_id]
        if from_track["id"] != to_track["id"] or from_track["type"] not in {"video", "overlay"}:
            raise MltRenderError(
                "A dissolve must connect two clips on the same visual track."
            )
        if clip_positions[to_id] != clip_positions[from_id] + 1:
            raise MltRenderError("A dissolve must connect adjacent clips on its track.")
        if from_id in transition_clip_ids or to_id in transition_clip_ids:
            raise MltRenderError(
                "This adapter stage allows only isolated dissolve pairs; a clip cannot "
                "belong to two transitions yet."
            )
        duration_frames = _frame_at_us(transition["duration_us"], fps_num, fps_den)
        from_end_frame = _frame_at_us(
            from_clip["start_us"] + from_clip["duration_us"], fps_num, fps_den
        )
        to_start_frame = _frame_at_us(to_clip["start_us"], fps_num, fps_den)
        overlap_frames = from_end_frame - to_start_frame
        if duration_frames < 1 or overlap_frames != duration_frames:
            raise MltRenderError(
                "The dissolve duration must exactly match the timeline overlap "
                "between its two clips at the project frame rate."
            )
        transitions_by_track[from_track["id"]].append({
            "from_clip_id": from_id,
            "to_clip_id": to_id,
            "type": transition_type,
            "parameters": clean_parameters,
            "duration_frames": duration_frames,
        })
        transition_clip_ids.update((from_id, to_id))

    planned_tracks: list[dict[str, Any]] = []
    maximum_end_frame = 0
    clip_count = 0

    for track in sorted(enabled_tracks, key=lambda item: item["order"]):
        if not track["clips"]:
            continue
        planned_clips: list[dict[str, Any]] = []
        cursor_frame = 0
        previous_clip_id: str | None = None

        for clip in ordered_by_track[track["id"]]:
            clip_count += 1
            if clip_count > 250:
                raise MltRenderError("This adapter stage supports at most 250 clips per project.")

            allowed_kinds = {
                "video": {"video"},
                "overlay": {"video", "image"},
                "text": {"text"},
                "audio": {"audio"},
            }[track["type"]]
            if clip["kind"] not in allowed_kinds:
                raise MltRenderError(
                    f"Clip type {clip['kind']!r} is not enabled on a {track['type']} track."
                )
            playback_rate = float(clip.get("playback_rate", 1.0))
            visual_asset = None
            visual_media_path = None
            source_dimensions = None
            if clip["kind"] in {"video", "image"}:
                visual_asset = assets[clip["media_id"]]
                expected_type = "video" if clip["kind"] == "video" else "image"
                if visual_asset["media_type"] != expected_type:
                    raise MltRenderError(
                        f"Asset type {visual_asset['media_type']!r} is not supported "
                        f"for a {clip['kind']} clip in this adapter stage."
                    )
                visual_media_path = _resolve_asset(visual_asset, root)
                if (
                    clip.get("framing", {}).get("mode") in {"fit", "fill"}
                    or clip.get("crop")
                    or any(item["property"] in {"crop_x", "crop_y", "crop_width", "crop_height"}
                           for item in clip.get("keyframes", []))
                ):
                    source_dimensions = _probe_media_dimensions(visual_media_path)
            if not 0.05 <= playback_rate <= 16.0:
                raise MltRenderError("Playback speed must be between 0.05x and 16x.")
            if clip["kind"] in {"image", "text"} and not math.isclose(
                playback_rate, 1.0, abs_tol=1e-9
            ):
                raise MltRenderError("Playback speed applies only to video and audio clips.")
            audio_keyframes = None
            if track["type"] == "audio":
                if clip.get("transform"):
                    raise MltRenderError("Audio clips cannot use visual transforms.")
                audio_keyframes = _compile_audio_keyframes(
                    clip, fps_num, fps_den,
                    _frame_at_us(clip["start_us"] + clip["duration_us"], fps_num, fps_den)
                    - _frame_at_us(clip["start_us"], fps_num, fps_den),
                )
                clip_transform = None
            elif clip["kind"] == "text":
                if clip.get("transform"):
                    raise MltRenderError(
                        "Text transforms are not enabled; use text geometry properties."
                    )
                if any(item["property"] != "opacity" for item in clip.get("keyframes", [])):
                    raise MltRenderError(
                        "Text clips currently support opacity keyframes only."
                    )
                _ffmpeg_text_opacity_filters(
                    clip.get("keyframes", []), fps_num, fps_den
                )
                clip_transform = None
            else:
                clip_transform = _compile_clip_transform(
                    clip, profile["width"], profile["height"],
                    fps_num, fps_den,
                    _frame_at_us(clip["start_us"] + clip["duration_us"], fps_num, fps_den)
                    - _frame_at_us(clip["start_us"], fps_num, fps_den),
                    source_dimensions=source_dimensions,
                )

            start_frame = _frame_at_us(clip["start_us"], fps_num, fps_den)
            end_frame = _frame_at_us(
                clip["start_us"] + clip["duration_us"], fps_num, fps_den
            )
            duration_frames = end_frame - start_frame
            if duration_frames < 1:
                raise MltRenderError("A clip is shorter than one output frame.")
            transition = (
                next(
                    (
                        item for item in transitions_by_track[track["id"]]
                        if item["from_clip_id"] == previous_clip_id
                        and item["to_clip_id"] == clip["id"]
                    ),
                    None,
                )
                if previous_clip_id is not None else None
            )
            if start_frame < cursor_frame:
                overlap_frames = cursor_frame - start_frame
                if transition is None or transition["duration_frames"] != overlap_frames:
                    raise MltRenderError(
                        f"Clips overlap on track {track['id']} without a matching "
                        "validated dissolve transition."
                    )
            elif transition is not None:
                raise MltRenderError(
                    "The dissolve duration must be represented as an overlap "
                    "between the two clips on the timeline."
                )

            if clip["kind"] == "text":
                source_in_frame = 0
                source_out_frame = duration_frames - 1
                render_in_frame = 0
                render_out_frame = duration_frames - 1
                speed_segments: list[dict[str, Any]] = []
                media_id = None
                media_path = None
                text_spec = dict(clip["text"])
            else:
                source_in_us = clip.get("source_in_us", 0)
                source_in_frame = _frame_at_us(source_in_us, fps_num, fps_den)
                speed_segments, expected_source_frames = _compile_speed_segments(
                    clip, duration_frames, fps_num, fps_den, source_in_frame
                )
                source_out_us = clip.get("source_out_us")
                if source_out_us is None:
                    source_out_us = source_in_us + round(
                        expected_source_frames * 1_000_000 * fps_den / fps_num
                    )
                source_out_exclusive = _frame_at_us(source_out_us, fps_num, fps_den)
                source_out_frame = source_out_exclusive - 1
                source_frames = source_out_exclusive - source_in_frame
                if abs(source_frames - expected_source_frames) > 1.01:
                    raise MltRenderError(
                        f"Clip {clip['id']} source range ({source_frames} frames) does not "
                        f"match the integrated playback speed curve "
                        f"({expected_source_frames:.3f} source frames)."
                    )
                render_in_frame = speed_segments[0]["render_in_frame"]
                render_out_frame = speed_segments[-1]["render_out_frame"]
                asset = assets[clip["media_id"]]
                expected_media_type = {
                    "video": "video", "image": "image", "audio": "audio",
                }[clip["kind"]]
                if asset["media_type"] != expected_media_type:
                    raise MltRenderError(
                        f"Asset type {asset['media_type']!r} is not supported for "
                        f"a {clip['kind']} clip in this adapter stage."
                    )
                media_id = clip["media_id"]
                media_path = (
                    visual_media_path if visual_media_path is not None
                    else _resolve_asset(asset, root)
                )
                text_spec = None

            effects = _validate_effects(clip, track["type"])
            planned_clips.append({
                "id": clip["id"],
                "kind": clip["kind"],
                "media_id": media_id,
                "path": media_path,
                "text": text_spec,
                "start_frame": start_frame,
                "duration_frames": duration_frames,
                "source_in_frame": source_in_frame,
                "source_out_frame": source_out_frame,
                "render_in_frame": render_in_frame,
                "render_out_frame": render_out_frame,
                "playback_rate": playback_rate,
                "speed_segments": speed_segments,
                "effects": effects,
                "transform": clip_transform,
                "audio_keyframes": audio_keyframes,
                "keyframes": clip.get("keyframes", []) if clip["kind"] == "text" else [],
            })
            cursor_frame = end_frame
            previous_clip_id = clip["id"]
            maximum_end_frame = max(maximum_end_frame, end_frame)

        if planned_clips:
            planned_tracks.append({
                "id": track["id"],
                "type": track["type"],
                "order": track["order"],
                "muted": bool(
                    track.get("muted", False)
                    or (audio_solo_active and track["type"] != "audio")
                ),
                "solo": bool(track.get("solo", False)),
                "visible": bool(track.get("visible", True)),
                "audio_gain_db": float(track.get("audio_gain_db", 0)),
                "audio_pan": float(track.get("audio_pan", 0)),
                "clips": planned_clips,
                "transitions": transitions_by_track[track["id"]],
            })

    if not any(track["type"] in {"video", "overlay"} for track in planned_tracks):
        raise MltRenderError("The project has no enabled video clips to render.")
    if maximum_end_frame > 30 * 60 * fps_num / fps_den:
        raise MltRenderError("The first MLT adapter stage is limited to 30 minutes per render.")

    return {
        "project_id": project["id"],
        "revision": project.get("revision", 1),
        "width": profile["width"],
        "height": profile["height"],
        "fps_num": fps_num,
        "fps_den": fps_den,
        "total_frames": maximum_end_frame,
        "tracks": planned_tracks,
    }


def _apply_track_audio_routing(
    mlt: Any, profile: Any, producer: Any, *, gain_db: float = 0.0, pan: float = 0.0,
) -> None:
    """Apply a track's volume and stereo-balance settings to its audio signal."""
    if not math.isfinite(float(gain_db)) or not -96.0 <= float(gain_db) <= 24.0:
        raise MltRenderError("Track audio gain must be between -96 and 24 dB.")
    if not math.isfinite(float(pan)) or not -1.0 <= float(pan) <= 1.0:
        raise MltRenderError("Track audio pan must be between -1 (left) and 1 (right).")
    if not math.isclose(float(gain_db), 0.0, abs_tol=1e-9):
        volume = mlt.Filter(profile, "avfilter.volume")
        if not volume.is_valid():
            raise MltRenderError("The required LGPL FFmpeg volume filter is not installed.")
        volume.set("av.volume", f"{10.0 ** (float(gain_db) / 20.0):.9f}")
        volume.set("av.precision", "double")
        producer.attach(volume)
    if not math.isclose(float(pan), 0.0, abs_tol=1e-9):
        panner = mlt.Filter(profile, "panner")
        if not panner.is_valid():
            raise MltRenderError("The required LGPL MLT panner filter is not installed.")
        panner.set("channel", -1)
        panner.set("gang", 1)
        panner.set("split", (float(pan) + 1.0) / 2.0)
        producer.attach(panner)


def _apply_clip_effects(mlt: Any, profile: Any, producer: Any,
                        effects: list[dict[str, Any]]) -> None:
    for effect in effects:
        service = effect["type"]
        filter_instance = mlt.Filter(profile, service)
        if not filter_instance.is_valid():
            raise MltRenderError(f"Required MLT filter {service!r} is not installed.")
        if service == "brightness":
            filter_instance.set("level", effect["level"])
        elif service == "chroma":
            filter_instance.set("key", effect["key"])
            filter_instance.set("variance", effect["variance"])
        elif service == "avfilter.eq":
            filter_instance.set("av.contrast", effect["contrast"])
            filter_instance.set("av.saturation", effect["saturation"])
        elif service == "avfilter.volume":
            filter_instance.set("av.volume", effect["volume"])
            filter_instance.set("av.precision", "double")
        elif service == "avfilter.afade":
            filter_instance.set("av.type", effect["direction"])
            filter_instance.set("av.start_time", effect["start_time"])
            filter_instance.set("av.duration", effect["duration"])
            filter_instance.set("av.curve", effect["curve"])
        producer.attach(filter_instance)


def _apply_clip_transform(mlt: Any, profile: Any, producer: Any,
                          transform: dict[str, Any] | None) -> None:
    if transform is None:
        return
    # Flip the source pixels before affine positioning/scaling. When a manual
    # crop is also active, compile_render_plan adjusts the source crop origin
    # so that the user's crop rectangle still refers to the unflipped source.
    for enabled, service, label in (
        (transform.get("flip_horizontal", False), "avfilter.hflip", "horizontal"),
        (transform.get("flip_vertical", False), "avfilter.vflip", "vertical"),
    ):
        if enabled:
            flip_filter = mlt.Filter(profile, service)
            if not flip_filter.is_valid():
                raise MltRenderError(
                    f"The required MLT {label} flip filter {service!r} is not installed."
                )
            producer.attach(flip_filter)

    filter_instance = mlt.Filter(profile, "affine")
    if not filter_instance.is_valid():
        raise MltRenderError(
            "The LGPL MLT affine transform filter is not installed."
        )
    filter_instance.set("transition.rect", transform["rect"])
    filter_instance.set("transition.fix_rotate_z", transform["rotation"])
    framing = transform.get("framing")
    if framing:
        mode = framing["mode"]
        filter_instance.set("transition.fill", 1)
        filter_instance.set("transition.distort", 1 if mode == "stretch" else 0)
        filter_instance.set(
            "transition.halign", framing.get("horizontal_alignment", "center")
        )
        filter_instance.set(
            "transition.valign", framing.get("vertical_alignment", "middle")
        )
    elif transform.get("crop"):
        filter_instance.set("transition.fill", 1)
        filter_instance.set("transition.distort", 0)
        filter_instance.set("transition.halign", "center")
        filter_instance.set("transition.valign", "middle")
    if transform.get("rotation_animated"):
        # The affine plugin requires keyed=1 for rotate/shear/offset animation.
        filter_instance.set("transition.keyed", 1)
    producer.attach(filter_instance)

    if transform.get("opacity_enabled"):
        # The LGPL brightness filter exposes a separate, key-framable alpha
        # multiplier. Keep level at 1 so RGB brightness is unchanged.
        opacity_filter = mlt.Filter(profile, "brightness")
        if not opacity_filter.is_valid():
            raise MltRenderError("The required LGPL brightness alpha filter is not installed.")
        opacity_filter.set("level", 1.0)
        opacity_filter.set("alpha", transform["opacity_alpha"])
        producer.attach(opacity_filter)


def _escape_filter_path(path: Path) -> str:
    """Escape a path for an FFmpeg filter option value."""
    return str(path).replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")


def _ffmpeg_text_color(value: str, fallback: str) -> str:
    color = value or fallback
    if re.fullmatch(r"#[0-9A-Fa-f]{6}", color):
        return color
    if re.fullmatch(r"0x[0-9A-Fa-f]{8}", color):
        return "#" + color[2:8] + "@" + str(int(color[8:10], 16) / 255.0)
    if color.lower() in {"white", "black", "red", "green", "blue", "yellow"}:
        return color.lower()
    raise MltRenderError(f"Unsupported text colour {color!r}.")


def _parse_text_colour(value: Any, fallback: str = "#FFFFFF") -> tuple[int, int, int, float]:
    """Return RGB and normalized opacity for supported editor colour values."""
    colour = str(value or fallback).strip()
    named = {
        "white": (255, 255, 255), "black": (0, 0, 0),
        "red": (255, 0, 0), "green": (0, 128, 0),
        "blue": (0, 0, 255), "yellow": (255, 255, 0),
    }
    if colour.lower() in named:
        return (*named[colour.lower()], 1.0)
    raw = colour[1:] if colour.startswith("#") else colour[2:] if colour.lower().startswith("0x") else ""
    if len(raw) not in {6, 8} or not re.fullmatch(r"[0-9A-Fa-f]+", raw):
        raise MltRenderError(f"Unsupported text colour {colour!r}.")
    red, green, blue = (int(raw[index:index + 2], 16) for index in (0, 2, 4))
    alpha = int(raw[6:8], 16) / 255.0 if len(raw) == 8 else 1.0
    return red, green, blue, alpha


def _ass_colour(value: Any, opacity: float = 1.0, fallback: str = "#FFFFFF") -> tuple[str, str]:
    red, green, blue, embedded_alpha = _parse_text_colour(value, fallback)
    effective_alpha = max(0.0, min(1.0, embedded_alpha * float(opacity)))
    alpha_byte = round((1.0 - effective_alpha) * 255)
    rgb = f"{blue:02X}{green:02X}{red:02X}"
    return f"&H{rgb}&", f"&H{alpha_byte:02X}&"


def _ass_escape_text(value: str) -> str:
    return value.replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}")


def _requires_ass_text_renderer(text_spec: dict[str, Any]) -> bool:
    return (
        int(text_spec.get("weight", 400)) != 400
        or bool(text_spec.get("background_fill", False))
        or float(text_spec.get("shadow_x", 0)) != 0
        or float(text_spec.get("shadow_y", 0)) != 0
        or float(text_spec.get("shadow_blur", 0)) > 0
        or float(text_spec.get("letter_spacing_px", 0)) != 0
        or int(text_spec.get("line_spacing_px", 0)) != 0
        or float(text_spec.get("opacity", 1)) != 1
        or text_spec.get("style", "normal") == "italic"
        or bool(text_spec.get("underline", False))
        or bool(text_spec.get("strikethrough", False))
    )


def _make_ass_text_overlay_image(
    text_spec: dict[str, Any],
    width: int,
    height: int,
    output_path: Path,
    text_directory: Path,
) -> Path:
    """Render advanced typography through libass onto a transparent RGBA frame."""
    text_directory.mkdir(parents=True, exist_ok=True)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    content = str(text_spec.get("content", ""))
    lines = content.splitlines() or [""]
    family = re.sub(r"[^A-Za-z0-9 _-]", "", str(text_spec.get("family", "Sans")))[:80] or "Sans"
    size = int(text_spec.get("size", 48))
    weight = max(100, min(900, int(round(int(text_spec.get("weight", 400)) / 100) * 100)))
    opacity = float(text_spec.get("opacity", 1.0))
    foreground, foreground_alpha = _ass_colour(text_spec.get("fgcolour", "#FFFFFF"), opacity)
    outline_colour, outline_alpha = _ass_colour(text_spec.get("olcolour", "#000000"), opacity)
    shadow_colour, shadow_alpha = _ass_colour(
        text_spec.get("shadow_color", "#000000"),
        float(text_spec.get("shadow_opacity", 0.7)),
    )
    outline = int(text_spec.get("outline", 0))
    shadow_x = int(text_spec.get("shadow_x", 0))
    shadow_y = int(text_spec.get("shadow_y", 0))
    shadow_blur = float(text_spec.get("shadow_blur", 0))
    spacing = float(text_spec.get("letter_spacing_px", 0))
    line_spacing = int(text_spec.get("line_spacing_px", 0))
    line_height = max(1, round(size * 1.2 + line_spacing))
    box_x = round(float(text_spec.get("x_percent", 5)) * width / 100)
    box_y = round(float(text_spec.get("y_percent", 68)) * height / 100)
    box_width = round(float(text_spec.get("width_percent", 90)) * width / 100)
    box_height = round(float(text_spec.get("height_percent", 25)) * height / 100)
    horizontal = text_spec.get("halign", text_spec.get("align", "center"))
    vertical = text_spec.get("valign", "middle")
    anchor = {"left": 7, "center": 8, "right": 9}.get(horizontal, 8)
    x = box_x if horizontal == "left" else box_x + box_width // 2 if horizontal == "center" else box_x + box_width
    text_height = line_height * len(lines)
    y = box_y if vertical == "top" else box_y + (box_height - text_height) // 2 if vertical == "middle" else box_y + box_height - text_height

    ass_colour_script = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{family},{size},&H00FFFFFF&,&H000000FF&,&H00000000&,&HFF000000&,0,0,0,0,100,100,{spacing:.2f},0,1,{outline},0,5,0,0,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    event_lines = []
    for index, line in enumerate(lines):
        y_position = y + index * line_height
        base_tags = (
            f"\\an{anchor}\\pos({x},{y_position})\\fn{family}\\fs{size}"
            f"\\b{weight}\\fsp{spacing:.2f}"
        )
        style_tags = ""
        if text_spec.get("style") == "italic":
            style_tags += "\\i1"
        if text_spec.get("underline"):
            style_tags += "\\u1"
        if text_spec.get("strikethrough"):
            style_tags += "\\s1"
        if shadow_blur > 0:
            # Render the blurred shadow on its own transparent ASS layer so
            # libass blur never softens the foreground glyphs or outline.
            shadow_tags = (
                f"{base_tags}\\1a&HFF&\\3a&HFF&"
                f"\\xshad{shadow_x}\\yshad{shadow_y}"
                f"\\4c{shadow_colour}\\4a{shadow_alpha}\\blur{shadow_blur:.2f}"
                f"{style_tags}"
            )
            text_tags = (
                f"{base_tags}\\1c{foreground}\\1a{foreground_alpha}"
                f"\\bord{outline}\\3c{outline_colour}\\3a{outline_alpha}"
                f"\\xshad0\\yshad0\\4a&HFF&{style_tags}"
            )
            event_lines.append(
                f"Dialogue: 0,0:00:00.00,0:00:01.00,Default,,0,0,0,,{{{shadow_tags}}}{_ass_escape_text(line)}"
            )
            event_lines.append(
                f"Dialogue: 1,0:00:00.00,0:00:01.00,Default,,0,0,0,,{{{text_tags}}}{_ass_escape_text(line)}"
            )
        else:
            tags = (
                f"{base_tags}\\1c{foreground}\\1a{foreground_alpha}"
                f"\\bord{outline}\\3c{outline_colour}\\3a{outline_alpha}"
                f"\\xshad{shadow_x}\\yshad{shadow_y}\\4c{shadow_colour}\\4a{shadow_alpha}"
                f"{style_tags}"
            )
            event_lines.append(
                f"Dialogue: 0,0:00:00.00,0:00:01.00,Default,,0,0,0,,{{{tags}}}{_ass_escape_text(line)}"
            )
    ass_path = text_directory / f"{output_path.stem}.ass"
    ass_path.write_text(ass_colour_script + "\n".join(event_lines) + "\n", encoding="utf-8")

    ass_file = str(ass_path).replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")
    canvas_source = f"color=c=black@0.0:s={width}x{height}:r=1:d=1,format=rgba"
    if text_spec.get("background_fill"):
        red, green, blue, bg_alpha = _parse_text_colour(text_spec.get("bgcolour", "#000000"), "#000000")
        bg_alpha *= float(text_spec.get("bgopacity", 0.5))
        pad = int(text_spec.get("pad", 8))
        rect_x = max(0, box_x - pad)
        rect_y = max(0, box_y - pad)
        rect_width = min(width - rect_x, box_width + 2 * pad)
        rect_height = min(height - rect_y, box_height + 2 * pad)
        background_filter = (
            f"drawbox=x={rect_x}:y={rect_y}:w={rect_width}:h={rect_height}:"
            f"color=0x{red:02X}{green:02X}{blue:02X}@{max(0.0, min(1.0, bg_alpha)):.4f}:t=fill:replace=1"
        )
        filter_complex = (
            f"[0:v]{background_filter}[background];"
            f"[1:v]ass=filename='{ass_file}':alpha=1[text];"
            "[background][text]overlay=x=0:y=0:format=auto:shortest=1,format=rgba[out]"
        )
        command = [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-f", "lavfi", "-i", canvas_source,
            "-f", "lavfi", "-i", canvas_source,
            "-filter_complex", filter_complex, "-map", "[out]",
            "-frames:v", "1", "-c:v", "png", "-pix_fmt", "rgba", str(output_path),
        ]
    else:
        command = [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-f", "lavfi", "-i", canvas_source,
            "-vf", f"ass=filename='{ass_file}':alpha=1",
            "-frames:v", "1", "-c:v", "png", "-pix_fmt", "rgba", str(output_path),
        ]
    result = subprocess.run(command, capture_output=True, text=True, timeout=60)
    if result.returncode != 0 or not output_path.is_file():
        raise MltRenderError(
            "Advanced text rendering failed: " + (result.stderr or "FFmpeg did not create the overlay.")[-600:]
        )
    return output_path


def _make_text_overlay_image(
    text_spec: dict[str, Any],
    width: int,
    height: int,
    output_path: Path,
    text_directory: Path,
) -> Path:
    """Create a real RGBA PNG title for the post-render overlay pass.

    Pango/QText producers on the tested headless runner have been returning an
    opaque black frame despite an alpha-zero bgcolour. FFmpeg drawtext renders
    onto a transparent RGBA canvas, so the alpha channel is explicit and
    testable before MLT composites the image.
    """
    if _requires_ass_text_renderer(text_spec):
        return _make_ass_text_overlay_image(text_spec, width, height, output_path, text_directory)

    text_file = text_directory / (output_path.stem + ".txt")
    text_file.write_text(text_spec["content"], encoding="utf-8")

    family = str(text_spec.get("family", "Sans")).strip() or "Sans"
    # FFmpeg drawtext's fontconfig matching is version-sensitive; use the
    # requested family without appending unsupported filter-option syntax.
    font_description = family

    font_size = int(text_spec.get("size", 48))
    foreground = _ffmpeg_text_color(text_spec.get("fgcolour", "#FFFFFF"), "#FFFFFF")
    outline_color = _ffmpeg_text_color(text_spec.get("olcolour", "#000000"), "#000000")
    outline = int(text_spec.get("outline", 0))
    x_percent = float(text_spec.get("x_percent", 5))
    y_percent = float(text_spec.get("y_percent", 68))
    width_percent = float(text_spec.get("width_percent", 90))
    height_percent = float(text_spec.get("height_percent", 25))
    halign = text_spec.get("halign", text_spec.get("align", "center"))
    valign = text_spec.get("valign", "middle")
    if halign == "left":
        x_expression = f"w*{x_percent / 100.0:.8f}"
    elif halign == "right":
        x_expression = (
            f"w*{x_percent / 100.0:.8f}+w*{width_percent / 100.0:.8f}-text_w"
        )
    else:
        x_expression = (
            f"w*{x_percent / 100.0:.8f}+"
            f"(w*{width_percent / 100.0:.8f}-text_w)/2"
        )
    if valign == "top":
        y_expression = f"h*{y_percent / 100.0:.8f}"
    elif valign == "bottom":
        y_expression = (
            f"h*{y_percent / 100.0:.8f}+h*{height_percent / 100.0:.8f}-text_h"
        )
    else:
        y_expression = (
            f"h*{y_percent / 100.0:.8f}+"
            f"(h*{height_percent / 100.0:.8f}-text_h)/2"
        )

    drawtext = (
        "drawtext="
        f"font='{font_description}':"
        f"textfile='{_escape_filter_path(text_file)}':"
        "expansion=none:"
        f"fontcolor={foreground}:"
        f"fontsize={font_size}:"
        f"borderw={outline}:"
        f"bordercolor={outline_color}:"
        f"x='{x_expression}':"
        f"y='{y_expression}'"
    )
    command = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-f", "lavfi", "-i",
        f"color=c=black@0.0:s={width}x{height}:r=1:d=1,format=rgba",
        "-vf", drawtext,
        "-frames:v", "1",
        "-c:v", "png", "-pix_fmt", "rgba",
        str(output_path),
    ]
    try:
        result = subprocess.run(command, check=True, capture_output=True, text=True)
    except FileNotFoundError as exc:
        raise MltRenderError("FFmpeg is required to render transparent title overlays.") from exc
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or str(exc)).strip()
        raise MltRenderError(f"FFmpeg could not render the title overlay: {detail[-1200:]}") from exc

    if not output_path.is_file() or output_path.stat().st_size == 0:
        raise MltRenderError("FFmpeg returned without creating a transparent title image.")

    # Confirm the source PNG really has alpha at a pixel outside the text box.
    alpha_probe = subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-loglevel", "error",
            "-i", str(output_path),
            "-vf", "crop=1:1:8:8,format=rgba",
            "-frames:v", "1", "-f", "rawvideo", "-",
        ],
        check=True, capture_output=True,
    )
    if len(alpha_probe.stdout) != 4 or alpha_probe.stdout[3] != 0:
        alpha = alpha_probe.stdout[3] if len(alpha_probe.stdout) == 4 else None
        raise MltRenderError(
            f"Generated title PNG is not transparent outside its glyphs (alpha={alpha})."
        )

    return output_path


def _ffmpeg_text_opacity_filters(
    keyframes: list[dict[str, Any]], fps_num: int, fps_den: int
) -> list[str]:
    """Compile the supported two-point text opacity fade to FFmpeg's alpha fade filter."""
    entries = sorted(
        (item for item in keyframes if item["property"] == "opacity"),
        key=lambda item: int(item["time_us"]),
    )
    if not entries:
        return []
    if len(entries) != 2:
        raise MltRenderError("Text opacity animation currently requires exactly two keyframes.")
    if any(item.get("interpolation", "linear") != "linear" for item in entries):
        raise MltRenderError("Text opacity animation currently supports linear interpolation only.")

    start_frame = _frame_at_us(int(entries[0]["time_us"]), fps_num, fps_den)
    end_frame = _frame_at_us(int(entries[1]["time_us"]), fps_num, fps_den)
    frame_count = end_frame - start_frame
    if frame_count < 1:
        raise MltRenderError("Text opacity keyframes must map to increasing output frames.")

    start_value = float(entries[0]["value"])
    end_value = float(entries[1]["value"])
    if math.isclose(start_value, 0.0, abs_tol=1e-9) and math.isclose(
        end_value, 1.0, abs_tol=1e-9
    ):
        if start_frame != 0:
            raise MltRenderError("A text fade-in must begin at the first frame of its clip.")
        return [f"fade=t=in:s=0:n={frame_count}:alpha=1"]
    if math.isclose(start_value, 1.0, abs_tol=1e-9) and math.isclose(
        end_value, 0.0, abs_tol=1e-9
    ):
        return [f"fade=t=out:s={start_frame}:n={frame_count}:alpha=1"]
    raise MltRenderError(
        "Text opacity animation currently supports 0-to-1 fade-in or 1-to-0 fade-out."
    )


def _apply_text_overlay_images_ffmpeg(
    base_output: Path,
    destination: Path,
    overlays: list[dict[str, Any]],
    plan: dict[str, Any],
) -> None:
    """Composite timed still-image and transparent title overlays over the MLT render."""
    fps_num = int(plan["fps_num"])
    fps_den = int(plan["fps_den"])
    inputs = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(base_output)]
    filters: list[str] = []
    previous = "[0:v]"

    for index, overlay in enumerate(overlays, start=1):
        inputs.extend([
            "-loop", "1", "-framerate", f"{fps_num}/{fps_den}",
            "-i", str(overlay["path"]),
        ])
        start = overlay["start_frame"] * fps_den / fps_num
        end = (overlay["start_frame"] + overlay["duration_frames"]) * fps_den / fps_num
        # Escape commas inside the enable expression for the filtergraph parser.
        enabled = f"gte(t\\,{start:.6f})*lt(t\\,{end:.6f})"
        label = f"[title{index}]"
        prepared = f"[prepared{index}]"
        keyframes = overlay.get("keyframes", [])
        if keyframes:
            opacity_filters = _ffmpeg_text_opacity_filters(keyframes, fps_num, fps_den)
            filters.append(
                f"[{index}:v]setpts=N*{fps_den}/({fps_num}*TB),format=yuva444p,"
                + ",".join(opacity_filters)
                + f",format=rgba,scale={int(plan['width'])}:{int(plan['height'])},"
                + f"format=rgba{prepared}"
            )
        else:
            filters.append(
                f"[{index}:v]scale={int(plan['width'])}:{int(plan['height'])},"
                f"format=rgba{prepared}"
            )
        filters.append(
            f"{previous}{prepared}"
            f"overlay=x=0:y=0:format=auto:eof_action=pass:"
            f"enable='{enabled}'{label}"
        )
        previous = label

    duration = int(plan["total_frames"]) * fps_den / fps_num
    if os.environ.get("MLT_DEBUG_TEXT_OVERLAY") == "1" and overlays:
        sample_pixels = {}
        for debug_time in (0.20, 0.80, 1.25, 1.75):
            pixels_at_time = {}
            for label, x, y in (("corner", 8, 8), ("center", plan["width"] // 2, plan["height"] // 2)):
                debug_pixel = subprocess.run(
                    [
                        "ffmpeg", "-hide_banner", "-loglevel", "error",
                        "-ss", f"{debug_time:.6f}", "-i", str(base_output),
                        "-vf", f"crop=2:2:{x}:{y},scale=1:1:flags=area,format=rgb24",
                        "-frames:v", "1", "-f", "rawvideo", "-",
                    ],
                    check=True, capture_output=True,
                ).stdout
                pixels_at_time[label] = tuple(debug_pixel[:3])
            sample_pixels[f"{debug_time:.2f}s"] = pixels_at_time
        duration_result = subprocess.run(
            [
                "ffprobe", "-v", "error", "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1", str(base_output),
            ],
            check=True, capture_output=True, text=True,
        )
        print(
            "MLT_DEBUG_TEXT_OVERLAY base_duration="
            + duration_result.stdout.strip()
            + " base_pixels="
            + repr(sample_pixels)
        )
    command = inputs + [
        "-filter_complex", ";".join(filters),
        "-map", previous,
        "-map", "0:a?",
        "-c:v", "mpeg4", "-q:v", "3", "-pix_fmt", "yuv420p",
        "-c:a", "copy",
        "-t", f"{duration:.9f}",
        "-movflags", "+faststart",
        str(destination),
    ]
    try:
        subprocess.run(command, check=True, capture_output=True, text=True)
    except FileNotFoundError as exc:
        raise MltRenderError("FFmpeg is required to composite still-image and title overlays.") from exc
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or str(exc)).strip()
        raise MltRenderError(f"FFmpeg could not composite visual overlays: {detail[-1600:]}") from exc

    if os.environ.get("MLT_DEBUG_TEXT_OVERLAY") == "1" and overlays:
        debug_overlay = next(
            (item for item in overlays if item.get("kind") == "text"), overlays[0]
        )
        final_time = (
            debug_overlay["start_frame"] + debug_overlay["duration_frames"] / 2
        ) * fps_den / fps_num
        final_pixel = subprocess.run(
            [
                "ffmpeg", "-hide_banner", "-loglevel", "error",
                "-ss", f"{final_time:.6f}", "-i", str(destination),
                "-vf", "crop=1:1:8:8,format=rgb24",
                "-frames:v", "1", "-f", "rawvideo", "-",
            ],
            check=True, capture_output=True,
        ).stdout
        print(
            "MLT_DEBUG_TEXT_OVERLAY final_pixel_rgb="
            + str(tuple(final_pixel[:3]))
        )



def _playlist_hide_flags(track_plan: dict[str, Any]) -> int:
    """Return MLT playlist hide bits: 1=video, 2=audio, 3=both."""
    hide = 1 if track_plan.get("type") == "audio" else (
        0 if track_plan.get("visible", True) else 1
    )
    if track_plan.get("muted", False):
        hide |= 2
    return hide


def render_project(
    project_document: Any,
    asset_root: str | Path,
    destination: str | Path,
    *,
    timeout_seconds: int = 120,
) -> dict[str, Any]:
    """Render the supported project subset through the LGPL MLT Python API."""
    plan = compile_render_plan(project_document, asset_root)
    target = Path(destination).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        raise MltRenderError("Refusing to overwrite an existing render output.")

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    try:
        import mlt7 as mlt
    except ImportError as exc:
        raise MltRenderError(
            "The MLT Python binding (mlt7) is unavailable in this worker interpreter."
        ) from exc

    factory = mlt.Factory()
    factory.init(None)
    profile = mlt.Profile()
    profile.set_width(plan["width"])
    profile.set_height(plan["height"])
    profile.set_frame_rate(plan["fps_num"], plan["fps_den"])
    profile.set_progressive(1)
    profile.set_explicit(1)

    playlists: list[Any] = []
    visual_track_indexes: list[int] = []
    visual_track_end_frames: dict[int, int] = {}
    audio_track_indexes: list[int] = []
    text_track_clips: list[dict[str, Any]] = []
    image_overlays: list[dict[str, Any]] = []

    visible_visual_tracks = [
        track for track in plan["tracks"]
        if track["type"] in {"video", "overlay"} and not track["muted"]
    ]
    top_visual_track_id = (
        max(visible_visual_tracks, key=lambda item: item["order"])["id"]
        if visible_visual_tracks else None
    )

    for track_plan in plan["tracks"]:
        if track_plan["type"] == "text":
            text_track_clips.extend(
                {**clip, "track_order": track_plan["order"]}
                for clip in track_plan["clips"]
            )
            continue

        render_clips = list(track_plan["clips"])
        if track_plan["type"] == "overlay" and track_plan["id"] == top_visual_track_id:
            transition_clip_ids = {
                clip_id
                for transition in track_plan["transitions"]
                for clip_id in (transition["from_clip_id"], transition["to_clip_id"])
            }
            remaining_clips = []
            for clip in render_clips:
                simple_image = (
                    clip["kind"] == "image"
                    and not clip.get("effects")
                    and not clip.get("transform")
                    and not clip.get("framing")
                    and not clip.get("keyframes")
                    and clip["id"] not in transition_clip_ids
                )
                if simple_image:
                    image_overlays.append({
                        "path": clip["path"],
                        "kind": "image",
                        "start_frame": clip["start_frame"],
                        "duration_frames": clip["duration_frames"],
                        "track_order": track_plan["order"],
                    })
                else:
                    remaining_clips.append(clip)
            render_clips = remaining_clips

        # A topmost still-image-only overlay track is composited after the base
        # render, avoiding MLT's opaque EOF frame on short image playlists.
        if not render_clips:
            continue

        playlist_track_index = len(playlists)
        playlist = mlt.Playlist(profile)
        playlist.set("hide", _playlist_hide_flags(track_plan))
        if track_plan["type"] == "audio":
            audio_track_indexes.append(playlist_track_index)
        else:
            visual_track_indexes.append(playlist_track_index)
            if not track_plan["muted"]:
                # An invisible video track can still contribute its source audio.
                audio_track_indexes.append(playlist_track_index)

        cursor_frame = 0
        clip_playlist_indexes: dict[str, int] = {}
        for clip in render_clips:
            gap = clip["start_frame"] - cursor_frame
            if gap > 0:
                playlist.blank(gap - 1)

            expected_output_start = 0
            for segment in clip["speed_segments"]:
                if segment["output_start_frame"] != expected_output_start:
                    raise MltRenderError(
                        f"Clip {clip['id']} speed segments are not contiguous."
                    )
                rate = float(segment["playback_rate"])
                if not math.isclose(rate, 1.0, abs_tol=1e-9):
                    producer = mlt.Producer(
                        profile, "timewarp", f"{rate:.9f}:{clip['path']}"
                    )
                    if not producer.is_valid():
                        raise MltRenderError(
                            f"MLT timewarp could not open source clip {clip['id']}."
                        )
                    # Do not set warp_pitch: MLT's timewarp already retains
                    # source pitch in this render path. warp_pitch=1 applies a
                    # second correction and halves the tone in real renders.
                else:
                    producer = mlt.Producer(profile, str(clip["path"]))
                    if not producer.is_valid():
                        raise MltRenderError(f"MLT could not open source clip {clip['id']}.")
                if clip["kind"] == "image":
                    producer.set("eof", "loop")
                    producer.set("length", clip["duration_frames"])
                _apply_clip_effects(mlt, profile, producer, clip["effects"])
                if clip["kind"] in {"video", "audio"}:
                    _apply_track_audio_routing(
                        mlt, profile, producer,
                        gain_db=track_plan["audio_gain_db"],
                        pan=track_plan["audio_pan"],
                    )
                # Static transforms are safe to attach to every speed segment.
                # Animated transforms are rejected when a speed curve is active because
                # their local keyframe clocks need a combined time-remapping pass.
                _apply_clip_transform(mlt, profile, producer, clip.get("transform"))
                if clip.get("audio_keyframes") is not None:
                    if len(clip["speed_segments"]) > 1:
                        raise MltRenderError(
                            "Audio volume keyframes cannot yet be combined with speed ramps."
                        )
                    audio_filter = mlt.Filter(profile, "avfilter.volume")
                    if not audio_filter.is_valid():
                        raise MltRenderError(
                            "The required LGPL FFmpeg volume filter is not installed."
                        )
                    audio_filter.set("av.volume", clip["audio_keyframes"])
                    audio_filter.set("av.precision", "double")
                    producer.attach(audio_filter)
                append_result = playlist.append(
                    producer, segment["render_in_frame"], segment["render_out_frame"]
                )
                if append_result not in (None, 0):
                    raise MltRenderError(
                        f"MLT could not append clip {clip['id']} speed segment to its track."
                    )
                expected_output_start += segment["duration_frames"]
            if expected_output_start != clip["duration_frames"]:
                raise MltRenderError(
                    f"Clip {clip['id']} speed segments do not fill the clip duration."
                )
            # Playlist.mix operates on the final segment of the outgoing clip.
            clip_playlist_indexes[clip["id"]] = playlist.count() - 1
            cursor_frame = clip["start_frame"] + clip["duration_frames"]

        # Playlist.mix creates overlaps for adjacent clips on this one track.
        for transition_plan in sorted(
            track_plan["transitions"],
            key=lambda item: clip_playlist_indexes[item["from_clip_id"]],
            reverse=True,
        ):
            luma = mlt.Transition(profile, "luma")
            if not luma.is_valid():
                raise MltRenderError("The MLT LGPL luma transition is not installed.")
            luma.set("progressive", 1)
            if transition_plan["type"] == "wipe":
                map_name = (
                    "wipe-horizontal.pgm"
                    if transition_plan["parameters"]["direction"] == "left_to_right"
                    else "wipe-horizontal-reverse.pgm"
                )
                wipe_map = Path(__file__).resolve().parent / "resources" / map_name
                if not wipe_map.is_file():
                    raise MltRenderError(f"The packaged horizontal wipe map {map_name!r} is missing.")
                luma.set("resource", str(wipe_map))
                luma.set("softness", transition_plan["parameters"]["softness"])
            mix_result = playlist.mix(
                clip_playlist_indexes[transition_plan["from_clip_id"]],
                transition_plan["duration_frames"],
                luma,
            )
            if mix_result not in (None, 0):
                raise MltRenderError("MLT could not create the requested clip transition.")

        playlists.append(playlist)
        if track_plan["type"] in {"video", "overlay"}:
            visual_track_end_frames[playlist_track_index] = cursor_frame

    # Plain still images on the topmost visual track and all text/title clips
    # are composited after the MLT base render. Their explicit timeline enables
    # avoid relying on MLT's opaque EOF frame for short overlay playlists.
    text_temp = tempfile.TemporaryDirectory(prefix="mlt-visual-overlays-", dir=target.parent)
    text_directory = Path(text_temp.name)
    visual_overlays: list[dict[str, Any]] = list(image_overlays)
    if os.environ.get("MLT_DEBUG_TEXT_OVERLAY") == "1":
        print(
            "MLT_DEBUG_TEXT_OVERLAY prepared="
            + repr([
                (
                    item.get("kind"), item["start_frame"],
                    item["duration_frames"], item["track_order"],
                    str(item["path"]),
                )
                for item in visual_overlays
            ])
        )
    if text_track_clips and not visual_track_indexes:
        raise MltRenderError("Text/caption clips require an enabled visual track underneath.")
    for index, text_clip in enumerate(
        sorted(text_track_clips, key=lambda item: (item["track_order"], item["start_frame"]))
    ):
        title_image = text_directory / f"title-{index:04d}.png"
        _make_text_overlay_image(
            text_clip["text"],
            plan["width"],
            plan["height"],
            title_image,
            text_directory,
        )
        visual_overlays.append({
            "path": title_image,
            "kind": "text",
            "start_frame": text_clip["start_frame"],
            "duration_frames": text_clip["duration_frames"],
            "track_order": text_clip["track_order"],
            "keyframes": text_clip.get("keyframes", []),
        })
    visual_overlays.sort(key=lambda item: (item["track_order"], item["start_frame"]))

    tractor = mlt.Tractor()
    for index, playlist in enumerate(playlists):
        tractor.set_track(playlist, index)

    # Composite video tracks only; audio is handled by explicit mix transitions below.
    for position, index in enumerate(visual_track_indexes[1:], start=1):
        lower_index = visual_track_indexes[position - 1]
        transition = mlt.Transition(profile, "qtblend")
        if not transition.is_valid():
            # The Ubuntu MLT build used by the prototype does not ship qtblend.
            # The LGPL composite transition is the tested compatibility fallback.
            transition = mlt.Transition(profile, "composite")
            if transition.is_valid():
                transition.set("fill", 1)
        if not transition.is_valid():
            raise MltRenderError(
                "Neither the MLT qtblend nor composite video transition is installed."
            )
        transition.set("progressive", 1)
        transition.set("in", 0)
        # Stop compositing when the upper track's final clip ends. An MLT
        # playlist that reaches EOF can emit black frames; leaving its composite
        # active for the full project would cover lower tracks after that point.
        transition.set("out", max(0, visual_track_end_frames.get(index, 1) - 1))
        tractor.plant_transition(transition, lower_index, index)

    # Mix every audible track with the first audible track at unity gain.
    # No GPL-only volume filter is used here.
    if len(audio_track_indexes) > 1:
        base_audio_index = audio_track_indexes[0]
        for index in audio_track_indexes[1:]:
            mix = mlt.Transition(profile, "mix")
            if not mix.is_valid():
                raise MltRenderError("The MLT core audio mix transition is not installed.")
            mix.set("start", 1.0)
            mix.set("end", 1.0)
            tractor.plant_transition(mix, base_audio_index, index)

    tractor.refresh()
    tractor.set_in_and_out(0, plan["total_frames"] - 1)
    base_output = (
        Path(text_directory) / "mlt-base-render.mp4"
        if visual_overlays else target
    )
    consumer = mlt.Consumer(profile, "avformat", str(base_output))
    if not consumer.is_valid():
        raise MltRenderError("The MLT avformat output consumer is not installed.")
    consumer.set("vcodec", "mpeg4")
    consumer.set("pix_fmt", "yuv420p")
    consumer.set("acodec", "aac")
    consumer.set("ab", "128k")
    consumer.set("ar", 48000)
    consumer.set("channels", 2)
    consumer.set("real_time", -1)

    connect_result = consumer.connect(tractor)
    if connect_result not in (None, 0):
        raise MltRenderError(f"MLT consumer could not connect to project: {connect_result}")
    start_result = consumer.start()
    if start_result not in (None, 0):
        raise MltRenderError(f"MLT consumer could not start: {start_result}")

    deadline = time.monotonic() + timeout_seconds
    while not consumer.is_stopped():
        if time.monotonic() >= deadline:
            consumer.stop()
            target.unlink(missing_ok=True)
            raise MltRenderError(
                f"MLT render exceeded its {timeout_seconds}-second limit."
            )
        time.sleep(0.05)
    consumer.stop()

    if not base_output.is_file() or base_output.stat().st_size == 0:
        base_output.unlink(missing_ok=True)
        target.unlink(missing_ok=True)
        raise MltRenderError("MLT finished without producing a non-empty output file.")

    if visual_overlays:
        _apply_text_overlay_images_ffmpeg(
            base_output, target, visual_overlays, plan
        )
        base_output.unlink(missing_ok=True)

    if not target.is_file() or target.stat().st_size == 0:
        target.unlink(missing_ok=True)
        raise MltRenderError("The final video with text overlays is empty.")

    text_temp.cleanup()
    return {
        "ok": True,
        "backend": "MLT Python API",
        "project_id": plan["project_id"],
        "revision": plan["revision"],
        "output": str(target),
        "width": plan["width"],
        "height": plan["height"],
        "fps": f"{plan['fps_num']}/{plan['fps_den']}",
        "frames": plan["total_frames"],
        "tracks": len(plan["tracks"]),
        "audio_tracks": len(audio_track_indexes),
        "bytes": target.stat().st_size,
        "audio": "mixed" if audio_track_indexes else "none",
    }
