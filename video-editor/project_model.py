"""Versioned, non-destructive project model for the Independent AI Video Editor.

This module validates the first project-document contract. It deliberately does
not render media or execute editing tools.
"""
from __future__ import annotations

from copy import deepcopy
import math
import re
from typing import Any


PROJECT_SCHEMA_VERSION = 1
_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
_TRACK_TYPES = {"video", "overlay", "text", "audio"}
_CLIP_KINDS = {"video", "image", "audio", "text"}
_MEDIA_TYPES = {"video", "image", "audio", "font"}
_KEYFRAME_PROPERTIES = {
    "position_x", "position_y", "scale_x", "scale_y",
    "rotation_deg", "opacity", "volume_db", "playback_rate",
    "crop_x", "crop_y", "crop_width", "crop_height",
}
_INTERPOLATIONS = {
    "hold", "linear", "ease_in", "ease_out", "ease_in_out",
    "ease_in_quad", "ease_out_quad", "ease_in_out_quad",
    "ease_in_cubic", "ease_out_cubic", "ease_in_out_cubic",
    "ease_in_quart", "ease_out_quart", "ease_in_out_quart",
    "smoothstep", "bezier",
}


class ProjectValidationError(ValueError):
    """Raised when a project document violates the version 1 contract."""


def _object(value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ProjectValidationError(f"{path} must be an object.")
    return value


def _array(value: Any, path: str) -> list[Any]:
    if not isinstance(value, list):
        raise ProjectValidationError(f"{path} must be an array.")
    return value


def _string(value: Any, path: str, *, max_length: int = 512) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ProjectValidationError(f"{path} must be a non-empty string.")
    value = value.strip()
    if len(value) > max_length:
        raise ProjectValidationError(f"{path} is too long.")
    return value


def _identifier(value: Any, path: str) -> str:
    value = _string(value, path, max_length=64)
    if not _ID_RE.fullmatch(value):
        raise ProjectValidationError(
            f"{path} must use letters, numbers, underscores or hyphens."
        )
    return value


def _integer(value: Any, path: str, *, minimum: int = 0, maximum: int | None = None) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ProjectValidationError(f"{path} must be a whole number.")
    if value < minimum or (maximum is not None and value > maximum):
        bound = f" between {minimum} and {maximum}" if maximum is not None else f" at least {minimum}"
        raise ProjectValidationError(f"{path} must be{bound}.")
    return value


def _number(value: Any, path: str, *, minimum: float | None = None,
            maximum: float | None = None) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ProjectValidationError(f"{path} must be a finite number.")
    result = float(value)
    if minimum is not None and result < minimum:
        raise ProjectValidationError(f"{path} must be at least {minimum}.")
    if maximum is not None and result > maximum:
        raise ProjectValidationError(f"{path} must be no greater than {maximum}.")
    return result


def _validate_transform(value: Any, path: str) -> None:
    transform = _object(value, path)
    position = _object(transform.get("position"), f"{path}.position")
    scale = _object(transform.get("scale"), f"{path}.scale")
    _number(position.get("x"), f"{path}.position.x", minimum=-100000, maximum=100000)
    _number(position.get("y"), f"{path}.position.y", minimum=-100000, maximum=100000)
    _number(scale.get("x"), f"{path}.scale.x", minimum=0.001, maximum=100)
    _number(scale.get("y"), f"{path}.scale.y", minimum=0.001, maximum=100)
    _number(transform.get("rotation_deg", 0), f"{path}.rotation_deg",
            minimum=-360000, maximum=360000)
    _number(transform.get("opacity", 1), f"{path}.opacity", minimum=0, maximum=1)
    _number(transform.get("anchor_x", 0.5), f"{path}.anchor_x", minimum=0, maximum=1)
    _number(transform.get("anchor_y", 0.5), f"{path}.anchor_y", minimum=0, maximum=1)
    for flag in ("flip_horizontal", "flip_vertical"):
        if flag in transform and not isinstance(transform[flag], bool):
            raise ProjectValidationError(f"{path}.{flag} must be true or false.")


def _validate_framing(value: Any, path: str) -> None:
    framing = _object(value, path)
    mode = _string(framing.get("mode"), f"{path}.mode", max_length=16)
    if mode not in {"fit", "fill", "stretch"}:
        raise ProjectValidationError(f"{path}.mode is unsupported.")
    horizontal = _string(
        framing.get("horizontal_alignment", "center"),
        f"{path}.horizontal_alignment",
        max_length=8,
    )
    if horizontal not in {"left", "center", "right"}:
        raise ProjectValidationError(f"{path}.horizontal_alignment is unsupported.")
    vertical = _string(
        framing.get("vertical_alignment", "middle"),
        f"{path}.vertical_alignment",
        max_length=8,
    )
    if vertical not in {"top", "middle", "bottom"}:
        raise ProjectValidationError(f"{path}.vertical_alignment is unsupported.")


def _validate_crop(value: Any, path: str) -> None:
    crop = _object(value, path)
    x = _number(crop.get("x"), f"{path}.x", minimum=0, maximum=1)
    y = _number(crop.get("y"), f"{path}.y", minimum=0, maximum=1)
    width = _number(crop.get("width"), f"{path}.width", minimum=0.001, maximum=1)
    height = _number(crop.get("height"), f"{path}.height", minimum=0.001, maximum=1)
    if x + width > 1.000000001:
        raise ProjectValidationError(f"{path}.x plus width must stay within the source frame.")
    if y + height > 1.000000001:
        raise ProjectValidationError(f"{path}.y plus height must stay within the source frame.")


def _validate_keyframes(value: Any, path: str, clip_duration_us: int) -> None:
    keyframes = _array(value, path)
    seen: set[tuple[str, int]] = set()
    for index, raw in enumerate(keyframes):
        item_path = f"{path}[{index}]"
        item = _object(raw, item_path)
        prop = _string(item.get("property"), f"{item_path}.property", max_length=40)
        if prop not in _KEYFRAME_PROPERTIES:
            raise ProjectValidationError(f"{item_path}.property is not supported.")
        at = _integer(item.get("time_us"), f"{item_path}.time_us")
        if at > clip_duration_us:
            raise ProjectValidationError(f"{item_path}.time_us is outside the clip.")
        marker = (prop, at)
        if marker in seen:
            raise ProjectValidationError(f"{item_path} duplicates a keyframe time for {prop}.")
        seen.add(marker)
        keyframe_value = _number(item.get("value"), f"{item_path}.value")
        value_limits = {
            "scale_x": (0.001, 100.0), "scale_y": (0.001, 100.0),
            "opacity": (0.0, 1.0), "volume_db": (-96.0, 24.0),
            "playback_rate": (0.05, 16.0),
            "crop_x": (0.0, 1.0), "crop_y": (0.0, 1.0),
            "crop_width": (0.001, 1.0), "crop_height": (0.001, 1.0),
            "position_x": (-100000.0, 100000.0),
            "position_y": (-100000.0, 100000.0),
            "rotation_deg": (-360000.0, 360000.0),
        }
        low, high = value_limits[prop]
        if not low <= keyframe_value <= high:
            raise ProjectValidationError(
                f"{item_path}.value must be between {low} and {high} for {prop}."
            )
        interpolation = item.get("interpolation", "linear")
        if not isinstance(interpolation, str) or interpolation not in _INTERPOLATIONS:
            raise ProjectValidationError(f"{item_path}.interpolation is unsupported.")
        if "bezier" in item:
            curve = _object(item["bezier"], f"{item_path}.bezier")
            if interpolation != "bezier":
                raise ProjectValidationError(
                    f"{item_path}.bezier is only valid with bezier interpolation."
                )
            for control in ("x1", "y1", "x2", "y2"):
                _number(curve.get(control), f"{item_path}.bezier.{control}",
                        minimum=0, maximum=1)


def _validate_effects(value: Any, path: str) -> None:
    effects = _array(value, path)
    ids: set[str] = set()
    for index, raw in enumerate(effects):
        item_path = f"{path}[{index}]"
        effect = _object(raw, item_path)
        effect_id = _identifier(effect.get("id"), f"{item_path}.id")
        if effect_id in ids:
            raise ProjectValidationError(f"{item_path}.id is duplicated.")
        ids.add(effect_id)
        _string(effect.get("type"), f"{item_path}.type", max_length=80)
        if "enabled" in effect and not isinstance(effect["enabled"], bool):
            raise ProjectValidationError(f"{item_path}.enabled must be true or false.")
        _object(effect.get("parameters", {}), f"{item_path}.parameters")


def validate_project(document: Any) -> dict[str, Any]:
    """Validate a version 1 project and return an independent copy.

    Times are integer microseconds. Media storage references are opaque internal
    keys, never public/signed download URLs.
    """
    project = _object(document, "project")
    if isinstance(project.get("schema_version"), bool) or project.get("schema_version") != PROJECT_SCHEMA_VERSION:
        raise ProjectValidationError(
            f"schema_version must be {PROJECT_SCHEMA_VERSION}."
        )
    _identifier(project.get("id"), "project.id")
    _string(project.get("name"), "project.name", max_length=120)
    _integer(project.get("revision", 1), "project.revision", minimum=1)

    profile = _object(project.get("video_profile"), "project.video_profile")
    _integer(profile.get("width"), "video_profile.width", minimum=144, maximum=8192)
    _integer(profile.get("height"), "video_profile.height", minimum=144, maximum=8192)
    fps = _object(profile.get("frame_rate"), "video_profile.frame_rate")
    _integer(fps.get("numerator"), "frame_rate.numerator", minimum=1, maximum=240000)
    _integer(fps.get("denominator"), "frame_rate.denominator", minimum=1, maximum=100000)
    if project.get("timeline_timebase") != "microseconds":
        raise ProjectValidationError("timeline_timebase must be 'microseconds'.")

    assets: dict[str, dict[str, Any]] = {}
    for index, raw in enumerate(_array(project.get("assets"), "project.assets")):
        path = f"project.assets[{index}]"
        asset = _object(raw, path)
        asset_id = _identifier(asset.get("id"), f"{path}.id")
        if asset_id in assets:
            raise ProjectValidationError(f"{path}.id is duplicated.")
        media_type = _string(asset.get("media_type"), f"{path}.media_type", max_length=20)
        if media_type not in _MEDIA_TYPES:
            raise ProjectValidationError(f"{path}.media_type is unsupported.")
        _string(asset.get("file_name"), f"{path}.file_name", max_length=255)
        storage_key = _string(asset.get("storage_key"), f"{path}.storage_key", max_length=512)
        if "://" in storage_key or storage_key.startswith("//") or ".." in storage_key.split("/"):
            raise ProjectValidationError(f"{path}.storage_key must be a safe internal key, not a URL or traversal path.")
        _integer(asset.get("size_bytes"), f"{path}.size_bytes", minimum=1)
        if "duration_us" in asset:
            _integer(asset["duration_us"], f"{path}.duration_us", minimum=1)
        if "folder" in asset:
            folder = _string(asset["folder"], f"{path}.folder", max_length=64)
            if folder in {".", ".."} or "/" in folder or "\\" in folder:
                raise ProjectValidationError(f"{path}.folder must be a simple folder name.")
        if "tags" in asset:
            tags = _array(asset["tags"], f"{path}.tags")
            if len(tags) > 12:
                raise ProjectValidationError(f"{path}.tags supports at most 12 tags.")
            normalized_tags = set()
            for tag_index, tag in enumerate(tags):
                clean_tag = _string(tag, f"{path}.tags[{tag_index}]", max_length=32)
                if clean_tag.casefold() in normalized_tags:
                    raise ProjectValidationError(f"{path}.tags contains duplicate tags.")
                normalized_tags.add(clean_tag.casefold())
        if "thumbnail_data_url" in asset:
            thumbnail = _string(asset["thumbnail_data_url"], f"{path}.thumbnail_data_url", max_length=60000)
            if not re.fullmatch(r"data:image/jpeg;base64,[A-Za-z0-9+/]+={0,2}", thumbnail):
                raise ProjectValidationError(f"{path}.thumbnail_data_url must be a base64 JPEG data URL.")
        if "waveform" in asset:
            waveform = _object(asset["waveform"], f"{path}.waveform")
            samples = _array(waveform.get("samples"), f"{path}.waveform.samples")
            if not 1 <= len(samples) <= 128:
                raise ProjectValidationError(f"{path}.waveform.samples must contain 1 to 128 peaks.")
            for sample_index, sample in enumerate(samples):
                _number(sample, f"{path}.waveform.samples[{sample_index}]", minimum=0, maximum=1)
        assets[asset_id] = asset

    transcripts = _array(project.get("transcripts", []), "project.transcripts")
    if len(transcripts) > 100:
        raise ProjectValidationError("project.transcripts must contain at most 100 transcripts.")
    transcript_ids: set[str] = set()
    project_word_count = 0
    project_transcript_characters = 0
    for transcript_index, raw_transcript in enumerate(transcripts):
        path = f"project.transcripts[{transcript_index}]"
        transcript = _object(raw_transcript, path)
        if set(transcript) - {"id", "name", "source_media_id", "language", "words"}:
            raise ProjectValidationError(f"{path} contains unsupported fields.")
        transcript_id = _identifier(transcript.get("id"), f"{path}.id")
        if transcript_id in transcript_ids:
            raise ProjectValidationError(f"{path}.id is duplicated.")
        transcript_ids.add(transcript_id)
        _string(transcript.get("name", "Transcript"), f"{path}.name", max_length=120)
        source_media_id = _identifier(transcript.get("source_media_id"), f"{path}.source_media_id")
        if source_media_id not in assets:
            raise ProjectValidationError(f"{path}.source_media_id does not exist.")
        source_asset = assets[source_media_id]
        if source_asset.get("media_type") not in {"video", "audio"}:
            raise ProjectValidationError(f"{path}.source_media_id must reference video or audio media.")
        language = _string(transcript.get("language", "und"), f"{path}.language", max_length=35)
        if not re.fullmatch(r"[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8})*", language):
            raise ProjectValidationError(f"{path}.language must be a valid short language tag such as en or en-US.")
        words = _array(transcript.get("words"), f"{path}.words")
        if not 1 <= len(words) <= 20000:
            raise ProjectValidationError(f"{path}.words must contain 1 to 20000 timed words.")
        project_word_count += len(words)
        if project_word_count > 100000:
            raise ProjectValidationError("Project transcripts exceed the 100,000-word limit.")
        previous_start = -1
        source_duration = source_asset.get("duration_us")
        for word_index, raw_word in enumerate(words):
            word_path = f"{path}.words[{word_index}]"
            word = _object(raw_word, word_path)
            if set(word) - {"text", "start_us", "end_us", "speaker_id", "confidence"}:
                raise ProjectValidationError(f"{word_path} contains unsupported fields.")
            word_text = _string(word.get("text"), f"{word_path}.text", max_length=100)
            if not any(character.isalnum() for character in word_text):
                raise ProjectValidationError(f"{word_path}.text must contain a word or spoken token.")
            start_us = _integer(word.get("start_us"), f"{word_path}.start_us", maximum=2**53 - 1)
            end_us = _integer(word.get("end_us"), f"{word_path}.end_us", minimum=1, maximum=2**53 - 1)
            if end_us <= start_us:
                raise ProjectValidationError(f"{word_path}.end_us must be after start_us.")
            if start_us < previous_start:
                raise ProjectValidationError(f"{path}.words must be ordered by source start time.")
            if source_duration is not None and end_us > int(source_duration):
                raise ProjectValidationError(f"{word_path}.end_us exceeds the source media duration.")
            previous_start = start_us
            project_transcript_characters += len(word_text)
            if project_transcript_characters > 1000000:
                raise ProjectValidationError("Project transcript text exceeds the 1,000,000-character limit.")
            if "speaker_id" in word:
                _identifier(word["speaker_id"], f"{word_path}.speaker_id")
            if "confidence" in word:
                _number(word["confidence"], f"{word_path}.confidence", minimum=0, maximum=1)

    tracks: dict[str, dict[str, Any]] = {}
    track_orders: set[int] = set()
    clips: dict[str, dict[str, Any]] = {}
    for track_index, raw_track in enumerate(_array(project.get("tracks"), "project.tracks")):
        track_path = f"project.tracks[{track_index}]"
        track = _object(raw_track, track_path)
        track_id = _identifier(track.get("id"), f"{track_path}.id")
        if track_id in tracks:
            raise ProjectValidationError(f"{track_path}.id is duplicated.")
        track_type = _string(track.get("type"), f"{track_path}.type", max_length=20)
        if track_type not in _TRACK_TYPES:
            raise ProjectValidationError(f"{track_path}.type is unsupported.")
        _string(track.get("name"), f"{track_path}.name", max_length=80)
        track_order = _integer(track.get("order"), f"{track_path}.order", minimum=0)
        if track_order in track_orders:
            raise ProjectValidationError(f"{track_path}.order is duplicated.")
        track_orders.add(track_order)
        for flag in ("enabled", "locked", "muted", "solo", "visible"):
            if flag in track and not isinstance(track[flag], bool):
                raise ProjectValidationError(f"{track_path}.{flag} must be true or false.")
        if track_type == "text" and any(key in track for key in ("audio_gain_db", "audio_pan")):
            raise ProjectValidationError(f"{track_path} text tracks cannot carry audio routing settings.")
        _number(track.get("audio_gain_db", 0), f"{track_path}.audio_gain_db", minimum=-96, maximum=24)
        _number(track.get("audio_pan", 0), f"{track_path}.audio_pan", minimum=-1, maximum=1)
        tracks[track_id] = track

        for clip_index, raw_clip in enumerate(_array(track.get("clips"), f"{track_path}.clips")):
            path = f"{track_path}.clips[{clip_index}]"
            clip = _object(raw_clip, path)
            clip_id = _identifier(clip.get("id"), f"{path}.id")
            if clip_id in clips:
                raise ProjectValidationError(f"{path}.id is duplicated.")
            kind = _string(clip.get("kind"), f"{path}.kind", max_length=20)
            if kind not in _CLIP_KINDS:
                raise ProjectValidationError(f"{path}.kind is unsupported.")
            compatible = {
                "video": {"video": "video"},
                "overlay": {"video": "video", "image": "image"},
                "text": {"text": None},
                "audio": {"audio": "audio"},
            }[track_type]
            if kind not in compatible:
                raise ProjectValidationError(f"{path}.kind cannot be placed on a {track_type} track.")

            if kind == "text":
                if "media_id" in clip and clip["media_id"] is not None:
                    raise ProjectValidationError(f"{path}.media_id must be omitted for text clips.")
                text_data = _object(clip.get("text"), f"{path}.text")
                _string(text_data.get("content"), f"{path}.text.content", max_length=20000)
                if "family" in text_data:
                    _string(text_data["family"], f"{path}.text.family", max_length=80)
                if "style" in text_data:
                    style = _string(text_data["style"], f"{path}.text.style", max_length=20)
                    if style not in {"normal", "italic"}:
                        raise ProjectValidationError(f"{path}.text.style is unsupported.")
                if "size" in text_data:
                    _integer(text_data["size"], f"{path}.text.size", minimum=8, maximum=256)
                if "weight" in text_data:
                    _integer(text_data["weight"], f"{path}.text.weight", minimum=100, maximum=1000)
                for colour_key in ("fgcolour", "bgcolour", "olcolour", "shadow_color"):
                    if colour_key in text_data:
                        colour = _string(text_data[colour_key], f"{path}.text.{colour_key}", max_length=16)
                        if not (
                            re.fullmatch(r"#[0-9A-Fa-f]{6}(?:[0-9A-Fa-f]{2})?", colour)
                            or re.fullmatch(r"0x[0-9A-Fa-f]{8}", colour)
                            or colour.lower() in {"white", "black", "red", "green", "blue", "yellow"}
                        ):
                            raise ProjectValidationError(
                                f"{path}.text.{colour_key} must be a supported colour value."
                            )
                if "outline" in text_data:
                    _integer(text_data["outline"], f"{path}.text.outline", minimum=0, maximum=3)
                if "pad" in text_data:
                    _integer(text_data["pad"], f"{path}.text.pad", minimum=0, maximum=128)
                if "background_fill" in text_data and not isinstance(text_data["background_fill"], bool):
                    raise ProjectValidationError(f"{path}.text.background_fill must be true or false.")
                for opacity_key in ("bgopacity", "shadow_opacity"):
                    if opacity_key in text_data:
                        _number(text_data[opacity_key], f"{path}.text.{opacity_key}", minimum=0, maximum=1)
                for offset_key in ("shadow_x", "shadow_y"):
                    if offset_key in text_data:
                        _integer(text_data[offset_key], f"{path}.text.{offset_key}", minimum=-32, maximum=32)
                if "letter_spacing_px" in text_data:
                    _number(text_data["letter_spacing_px"], f"{path}.text.letter_spacing_px", minimum=-10, maximum=40)
                if "line_spacing_px" in text_data:
                    _integer(text_data["line_spacing_px"], f"{path}.text.line_spacing_px", minimum=-40, maximum=120)
                for align_key in ("align", "halign"):
                    if align_key in text_data:
                        align_value = _string(text_data[align_key], f"{path}.text.{align_key}", max_length=12)
                        if align_value not in {"left", "center", "right"}:
                            raise ProjectValidationError(f"{path}.text.{align_key} is unsupported.")
                if "valign" in text_data and text_data["valign"] not in {"top", "middle", "bottom"}:
                    raise ProjectValidationError(f"{path}.text.valign is unsupported.")
                for geometry_key, minimum, maximum in (
                    ("x_percent", 0, 99),
                    ("y_percent", 0, 99),
                    ("width_percent", 1, 100),
                    ("height_percent", 1, 100),
                ):
                    if geometry_key in text_data:
                        _number(
                            text_data[geometry_key], f"{path}.text.{geometry_key}",
                            minimum=minimum, maximum=maximum,
                        )
                x = float(text_data.get("x_percent", 5))
                y = float(text_data.get("y_percent", 68))
                width = float(text_data.get("width_percent", 90))
                height = float(text_data.get("height_percent", 25))
                if x + width > 100 or y + height > 100:
                    raise ProjectValidationError(f"{path}.text geometry must stay inside the frame.")
                if "opacity" in text_data:
                    _number(text_data["opacity"], f"{path}.text.opacity", minimum=0, maximum=1)
                for flag in ("underline", "strikethrough"):
                    if flag in text_data and not isinstance(text_data[flag], bool):
                        raise ProjectValidationError(f"{path}.text.{flag} must be true or false.")
            else:
                media_id = _identifier(clip.get("media_id"), f"{path}.media_id")
                if media_id not in assets:
                    raise ProjectValidationError(f"{path}.media_id does not exist.")
                expected_media = compatible[kind]
                if assets[media_id]["media_type"] != expected_media:
                    raise ProjectValidationError(f"{path}.media_id has the wrong media type.")

            start = _integer(clip.get("start_us"), f"{path}.start_us")
            duration = _integer(clip.get("duration_us"), f"{path}.duration_us", minimum=1)
            source_in = _integer(clip.get("source_in_us", 0), f"{path}.source_in_us")
            source_out = clip.get("source_out_us")
            if source_out is not None:
                source_out = _integer(source_out, f"{path}.source_out_us", minimum=1)
                if source_out <= source_in:
                    raise ProjectValidationError(f"{path}.source_out_us must be after source_in_us.")
            rate = _number(clip.get("playback_rate", 1), f"{path}.playback_rate",
                           minimum=0.05, maximum=16)
            if kind != "text" and source_out is not None:
                asset = assets[clip["media_id"]]
                asset_duration = asset.get("duration_us")
                if asset_duration is not None and source_out > asset_duration:
                    raise ProjectValidationError(f"{path}.source_out_us exceeds the source duration.")
            if "group_id" in clip:
                _identifier(clip["group_id"], f"{path}.group_id")
            if "transform" in clip:
                _validate_transform(clip["transform"], f"{path}.transform")
            if "framing" in clip:
                if kind not in {"video", "image"}:
                    raise ProjectValidationError(f"{path}.framing is only valid for video/image clips.")
                _validate_framing(clip["framing"], f"{path}.framing")
            if "crop" in clip:
                if kind not in {"video", "image"}:
                    raise ProjectValidationError(f"{path}.crop is only valid for video/image clips.")
                if "framing" in clip:
                    raise ProjectValidationError(f"{path}.crop cannot be combined with automatic framing.")
                _validate_crop(clip["crop"], f"{path}.crop")
            _validate_keyframes(clip.get("keyframes", []), f"{path}.keyframes", duration)
            crop_keyframes = {item["property"] for item in clip.get("keyframes", [])
                              if item["property"] in {"crop_x", "crop_y", "crop_width", "crop_height"}}
            if crop_keyframes and kind not in {"video", "image"}:
                raise ProjectValidationError(f"{path} crop keyframes require a video or image clip.")
            if crop_keyframes and clip.get("framing"):
                raise ProjectValidationError(f"{path} crop keyframes cannot be combined with automatic framing.")
            if crop_keyframes and any(item["property"] == "playback_rate" for item in clip.get("keyframes", [])):
                raise ProjectValidationError(f"{path} crop keyframes cannot be combined with speed ramps.")
            _validate_effects(clip.get("effects", []), f"{path}.effects")
            clips[clip_id] = clip
            # Keep local values referenced here to make the timing contract explicit.
            _ = start, rate

    groups = _array(project.get("clip_groups", []), "project.clip_groups")
    group_ids: set[str] = set()
    grouped_clips: set[str] = set()
    for index, raw in enumerate(groups):
        path = f"project.clip_groups[{index}]"
        group = _object(raw, path)
        group_id = _identifier(group.get("id"), f"{path}.id")
        if group_id in group_ids:
            raise ProjectValidationError(f"{path}.id is duplicated.")
        group_ids.add(group_id)
        _string(group.get("name", "Linked group"), f"{path}.name", max_length=80)
        raw_member_ids = _array(group.get("clip_ids"), f"{path}.clip_ids")
        if not 2 <= len(raw_member_ids) <= 40:
            raise ProjectValidationError(f"{path}.clip_ids must contain 2 to 40 clips.")
        member_ids = [
            _identifier(raw_clip_id, f"{path}.clip_ids[{member_index}]")
            for member_index, raw_clip_id in enumerate(raw_member_ids)
        ]
        if len(set(member_ids)) != len(member_ids):
            raise ProjectValidationError(f"{path}.clip_ids must not contain duplicates.")
        for member_index, member_id in enumerate(member_ids):
            if member_id not in clips:
                raise ProjectValidationError(f"{path}.clip_ids references a missing clip.")
            if member_id in grouped_clips:
                raise ProjectValidationError(f"{path}.clip_ids contains a clip already in another group.")
            if clips[member_id].get("group_id") != group_id:
                raise ProjectValidationError(f"{path}.clip_ids and clip group_id values do not match.")
            grouped_clips.add(member_id)
    for clip_id, clip in clips.items():
        if clip.get("group_id") is not None and clip["group_id"] not in group_ids:
            raise ProjectValidationError(f"Clip {clip_id!r} references a missing clip group.")
        if clip.get("group_id") is not None and clip_id not in next(
            group["clip_ids"] for group in groups if group["id"] == clip["group_id"]
        ):
            raise ProjectValidationError(f"Clip {clip_id!r} is not listed in its linked group.")

    markers = _array(project.get("markers", []), "project.markers")
    marker_ids: set[str] = set()
    for index, raw in enumerate(markers):
        path = f"project.markers[{index}]"
        marker = _object(raw, path)
        marker_id = _identifier(marker.get("id"), f"{path}.id")
        if marker_id in marker_ids:
            raise ProjectValidationError(f"{path}.id is duplicated.")
        marker_ids.add(marker_id)
        _integer(marker.get("time_us"), f"{path}.time_us", maximum=2**53 - 1)
        _string(marker.get("label"), f"{path}.label", max_length=120)
        if "colour" in marker:
            colour = _string(marker["colour"], f"{path}.colour", max_length=16)
            if not re.fullmatch(r"#[0-9A-Fa-f]{6}", colour):
                raise ProjectValidationError(f"{path}.colour must be a six-digit hex colour.")

    transition_ids: set[str] = set()
    for index, raw in enumerate(_array(project.get("transitions", []), "project.transitions")):
        path = f"project.transitions[{index}]"
        transition = _object(raw, path)
        transition_id = _identifier(transition.get("id"), f"{path}.id")
        if transition_id in transition_ids:
            raise ProjectValidationError(f"{path}.id is duplicated.")
        transition_ids.add(transition_id)
        _string(transition.get("type"), f"{path}.type", max_length=80)
        outgoing = _identifier(transition.get("from_clip_id"), f"{path}.from_clip_id")
        incoming = _identifier(transition.get("to_clip_id"), f"{path}.to_clip_id")
        if outgoing == incoming or outgoing not in clips or incoming not in clips:
            raise ProjectValidationError(f"{path} must reference two different existing clips.")
        if clips[outgoing].get("kind") not in {"video", "image"} or clips[incoming].get("kind") not in {"video", "image"}:
            raise ProjectValidationError(f"{path} can only connect visual clips.")
        _integer(transition.get("duration_us"), f"{path}.duration_us", minimum=1)
        _object(transition.get("parameters", {}), f"{path}.parameters")

    return deepcopy(project)
