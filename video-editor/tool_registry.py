"""Registered contracts for the independently implemented editor tools.

Only capabilities with a tested project operation or renderer path appear here.
The AI never receives a shell, filesystem, network, or arbitrary-code tool.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import math
from typing import Any


class ToolValidationError(ValueError):
    """Raised when an AI tool call is outside the approved contract."""


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    category: str
    description: str
    input_schema: dict[str, Any]
    requires_confirmation: bool = False
    read_only: bool = False


def _schema(properties: dict[str, Any] | None = None, required: tuple[str, ...] = ()) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties or {},
        "required": list(required),
        "additionalProperties": False,
    }


def _field(
    kind: str,
    *,
    minimum: float | int | None = None,
    maximum: float | int | None = None,
    choices: tuple[str, ...] | None = None,
    max_length: int | None = None,
    nested: dict[str, Any] | None = None,
) -> dict[str, Any]:
    result: dict[str, Any] = {"type": kind}
    if minimum is not None:
        result["minimum"] = minimum
    if maximum is not None:
        result["maximum"] = maximum
    if choices is not None:
        result["enum"] = list(choices)
    if kind == "array" and nested is not None:
        result.update(nested)
    if kind == "string":
        result["minLength"] = 1
    if max_length is not None:
        result["maxLength"] = max_length
    if nested is not None:
        result.update(nested)
    return result


_TEXT_STYLE_SCHEMA = {
    "type": "object",
    "properties": {
        "family": _field("string", max_length=80),
        "size": _field("integer", minimum=8, maximum=256),
        "weight": _field("integer", minimum=100, maximum=1000),
        "fgcolour": _field("string", max_length=16),
        "olcolour": _field("string", max_length=16),
        "outline": _field("integer", minimum=0, maximum=3),
        "halign": _field("string", choices=("left", "center", "right")),
        "valign": _field("string", choices=("top", "middle", "bottom")),
        "x_percent": _field("number", minimum=0, maximum=99),
        "y_percent": _field("number", minimum=0, maximum=99),
        "width_percent": _field("number", minimum=1, maximum=100),
        "height_percent": _field("number", minimum=1, maximum=100),
    },
    "additionalProperties": False,
}

_TEXT_UPDATE_SCHEMA = {
    "type": "object",
    "properties": {
        "family": _field("string", max_length=80),
        "size": _field("integer", minimum=8, maximum=256),
        "fgcolour": _field("string", max_length=16),
        "olcolour": _field("string", max_length=16),
        "outline": _field("integer", minimum=0, maximum=3),
        "halign": _field("string", choices=("left", "center", "right")),
        "valign": _field("string", choices=("top", "middle", "bottom")),
        "x_percent": _field("number", minimum=0, maximum=99),
        "y_percent": _field("number", minimum=0, maximum=99),
        "width_percent": _field("number", minimum=1, maximum=100),
        "height_percent": _field("number", minimum=1, maximum=100),
    },
    "additionalProperties": False,
}

_PARAMETER_SCHEMA = {
    "type": "object",
    "properties": {
        "level": _field("number", minimum=0, maximum=15),
        "value": _field("number", minimum=0, maximum=4),
        "key": _field("string", max_length=7),
        "variance": _field("number", minimum=0, maximum=1),
        "gain_db": _field("number", minimum=-96, maximum=24),
        "fade_in_us": _field("integer", minimum=0),
        "fade_out_us": _field("integer", minimum=0),
    },
    "additionalProperties": False,
}


TOOL_DEFINITIONS = (
    ToolDefinition(
        "project.inspect", "project",
        "Read the current project revision, profile, tracks, clips and assets.",
        _schema(), read_only=True,
    ),
    ToolDefinition(
        "media.list", "media",
        "List imported media assets and metadata; this does not search outside the project.",
        _schema({
            "media_type": _field("string", choices=("video", "audio", "image", "font")),
            "folder": _field("string", max_length=64),
        }),
        read_only=True,
    ),
    ToolDefinition(
        "media.organize_asset", "media",
        "Assign a project media asset to a simple folder and update its searchable tags.",
        _schema({
            "media_id": _field("string", max_length=64),
            "folder": _field("string", max_length=64),
            "tags": _field("array", nested={
                "minItems": 0,
                "maxItems": 12,
                "items": {"type": "string", "minLength": 1, "maxLength": 32},
            }),
        }, ("media_id", "folder")),
    ),
    ToolDefinition(
        "quality.inspect_media", "quality",
        "Measure a project's video asset: streams, dimensions, frame rate, black intervals and audio silence. This is technical evidence, not semantic visual approval.",
        _schema({
            "media_id": _field("string", max_length=64),
            "analysis_seconds": _field("integer", minimum=1, maximum=600),
        }, ("media_id",)),
        read_only=True,
    ),
    ToolDefinition(
        "audio.analyze_media", "audio",
        "Measure audio streams, bounded silence intervals and EBU-style loudness measurements when FFmpeg reports them. Read-only signal analysis; it does not identify speech, music or beats.",
        _schema({
            "media_id": _field("string", max_length=64),
            "analysis_seconds": _field("integer", minimum=1, maximum=600),
            "silence_threshold_db": _field("number", minimum=-80, maximum=-10),
        }, ("media_id",)),
        read_only=True,
    ),
    ToolDefinition(
        "media.detect_scenes", "analysis",
        "Find candidate visual scene changes in a video using FFmpeg's scene-change score. Results are timestamp candidates, not confirmed semantic cuts.",
        _schema({
            "media_id": _field("string", max_length=64),
            "threshold": _field("number", minimum=0.05, maximum=0.95),
            "analysis_seconds": _field("integer", minimum=1, maximum=600),
        }, ("media_id",)),
        read_only=True,
    ),
    ToolDefinition(
        "project.set_profile", "project",
        "Set the project frame size and frame rate.",
        _schema({
            "width": _field("integer", minimum=144, maximum=8192),
            "height": _field("integer", minimum=144, maximum=8192),
            "fps_numerator": _field("integer", minimum=1, maximum=240000),
            "fps_denominator": _field("integer", minimum=1, maximum=100000),
        }, ("width", "height", "fps_numerator", "fps_denominator")),
    ),
    ToolDefinition(
        "timeline.add_track", "timeline",
        "Create a video, overlay, text or audio track.",
        _schema({
            "track_type": _field("string", choices=("video", "overlay", "text", "audio")),
            "name": _field("string", max_length=80),
            "order": _field("integer", minimum=0),
        }, ("track_type", "name")),
    ),
    ToolDefinition(
        "timeline.remove_track", "timeline",
        "Remove a track and all its clips; this destructive change needs approval.",
        _schema({"track_id": _field("string", max_length=64)}, ("track_id",)),
        requires_confirmation=True,
    ),
    ToolDefinition(
        "timeline.replace_clip_media", "timeline",
        "Replace the source asset of an existing clip with another asset of the same media type while preserving its timeline position and supported clip properties.",
        _schema({
            "clip_id": _field("string", max_length=64),
            "media_id": _field("string", max_length=64),
        }, ("clip_id", "media_id")),
    ),
    ToolDefinition(
        "timeline.ripple_insert_clip", "timeline",
        "Insert a video, image or audio asset on one track and shift later clips on that track forward by the inserted duration. It rejects an insertion point that cuts through an existing clip or transition.",
        _schema({
            "track_id": _field("string", max_length=64),
            "kind": _field("string", choices=("video", "image", "audio")),
            "media_id": _field("string", max_length=64),
            "start_us": _field("integer", minimum=0),
            "duration_us": _field("integer", minimum=1),
            "source_in_us": _field("integer", minimum=0),
            "source_out_us": _field("integer", minimum=1),
            "playback_rate": _field("number", minimum=0.05, maximum=16),
        }, ("track_id", "kind", "media_id", "start_us", "duration_us")),
    ),
    ToolDefinition(
        "timeline.add_clip", "timeline",
        "Place an existing video, image or audio asset on a compatible track.",
        _schema({
            "track_id": _field("string", max_length=64),
            "kind": _field("string", choices=("video", "image", "audio")),
            "media_id": _field("string", max_length=64),
            "start_us": _field("integer", minimum=0),
            "duration_us": _field("integer", minimum=1),
            "source_in_us": _field("integer", minimum=0),
            "source_out_us": _field("integer", minimum=1),
            "playback_rate": _field("number", minimum=0.05, maximum=16),
        }, ("track_id", "kind", "media_id", "start_us", "duration_us")),
    ),
    ToolDefinition(
        "timeline.add_text_clip", "timeline",
        "Add a timed text, title or caption clip on a text track.",
        _schema({
            "track_id": _field("string", max_length=64),
            "content": _field("string", max_length=20000),
            "start_us": _field("integer", minimum=0),
            "duration_us": _field("integer", minimum=1),
            "text_style": _field("object", nested=_TEXT_STYLE_SCHEMA),
        }, ("track_id", "content", "start_us", "duration_us")),
    ),
    ToolDefinition(
        "captions.add_word_timed", "captions",
        "Create sequential word-synchronised caption clips from a supplied transcript and verified word start/end timestamps. This tool does not transcribe audio.",
        _schema({
            "track_id": _field("string", max_length=64),
            "words": _field("array", nested={
                "minItems": 1,
                "maxItems": 500,
                "items": {
                    "type": "object",
                    "properties": {
                        "text": _field("string", max_length=100),
                        "start_us": _field("integer", minimum=0),
                        "end_us": _field("integer", minimum=1),
                    },
                    "required": ["text", "start_us", "end_us"],
                    "additionalProperties": False,
                },
            }),
            "text_style": _field("object", nested=_TEXT_STYLE_SCHEMA),
        }, ("track_id", "words")),
    ),
    ToolDefinition(
        "text.update_clip", "text",
        "Update a caption/title's content and renderer-supported text styling.",
        _schema({
            "clip_id": _field("string", max_length=64),
            "content": _field("string", max_length=20000),
            "text_style": _field("object", nested=_TEXT_UPDATE_SCHEMA),
        }, ("clip_id",)),
    ),
    ToolDefinition(
        "timeline.move_clip", "timeline",
        "Move a clip to a new timeline position and optionally to another compatible track.",
        _schema({
            "clip_id": _field("string", max_length=64),
            "start_us": _field("integer", minimum=0),
            "track_id": _field("string", max_length=64),
        }, ("clip_id", "start_us")),
    ),
    ToolDefinition(
        "timeline.duplicate_clip", "timeline",
        "Duplicate an existing clip with its effects, keyframes and media reference.",
        _schema({
            "clip_id": _field("string", max_length=64),
            "start_us": _field("integer", minimum=0),
            "track_id": _field("string", max_length=64),
        }, ("clip_id", "start_us")),
    ),
    ToolDefinition(
        "timeline.slip_clip", "timeline",
        "Shift the source in/out window of a video/audio clip while keeping its timeline start and duration unchanged.",
        _schema({
            "clip_id": _field("string", max_length=64),
            "delta_us": _field("integer", minimum=-86400000000, maximum=86400000000),
        }, ("clip_id", "delta_us")),
    ),
    ToolDefinition(
        "timeline.trim_clip", "timeline",
        "Trim source in/out points of a clip without changing its source file.",
        _schema({
            "clip_id": _field("string", max_length=64),
            "source_in_us": _field("integer", minimum=0),
            "source_out_us": _field("integer", minimum=1),
        }, ("clip_id", "source_in_us", "source_out_us")),
    ),
    ToolDefinition(
        "timeline.split_clip", "timeline",
        "Split a clip at a timeline-local position measured from its beginning.",
        _schema({
            "clip_id": _field("string", max_length=64),
            "at_us": _field("integer", minimum=1),
        }, ("clip_id", "at_us")),
    ),
    ToolDefinition(
        "timeline.delete_clip", "timeline",
        "Delete a clip and transitions that reference it; this destructive change needs approval.",
        _schema({"clip_id": _field("string", max_length=64)}, ("clip_id",)),
        requires_confirmation=True,
    ),
    ToolDefinition(
        "timeline.ripple_delete_clip", "timeline",
        "Delete a clip and close the resulting gap by shifting later clips on the same track left by the deleted clip duration. This destructive change needs approval.",
        _schema({"clip_id": _field("string", max_length=64)}, ("clip_id",)),
        requires_confirmation=True,
    ),
    ToolDefinition(
        "track.set_state", "timeline",
        "Enable/disable a track or mute/unmute an audio/video track.",
        _schema({
            "track_id": _field("string", max_length=64),
            "enabled": _field("boolean"),
            "muted": _field("boolean"),
            "solo": _field("boolean"),
            "visible": _field("boolean"),
        }, ("track_id",)),
    ),
    ToolDefinition(
        "track.reorder", "timeline",
        "Move a track to a new position in the project track stack without changing its clips.",
        _schema({
            "track_id": _field("string", max_length=64),
            "order": _field("integer", minimum=0, maximum=999),
        }, ("track_id", "order")),
    ),
    ToolDefinition(
        "track.rename", "timeline",
        "Rename an existing timeline track without changing its clips.",
        _schema({
            "track_id": _field("string", max_length=64),
            "name": _field("string", max_length=80),
        }, ("track_id", "name")),
    ),
    ToolDefinition(
        "track.set_locked", "timeline",
        "Lock or unlock a track to prevent or allow clip edits on it.",
        _schema({
            "track_id": _field("string", max_length=64),
            "locked": _field("boolean"),
        }, ("track_id", "locked")),
    ),
    ToolDefinition(
        "clip.set_speed", "speed",
        "Set constant playback speed on an existing video or audio clip.",
        _schema({
            "clip_id": _field("string", max_length=64),
            "playback_rate": _field("number", minimum=0.05, maximum=16),
        }, ("clip_id", "playback_rate")),
    ),
    ToolDefinition(
        "clip.set_transform", "transform",
        "Set static position, scale, rotation or opacity on a visual clip.",
        _schema({
            "clip_id": _field("string", max_length=64),
            "position_x": _field("number", minimum=-100000, maximum=100000),
            "position_y": _field("number", minimum=-100000, maximum=100000),
            "scale_x": _field("number", minimum=0.001, maximum=100),
            "scale_y": _field("number", minimum=0.001, maximum=100),
            "rotation_deg": _field("number", minimum=-360000, maximum=360000),
            "opacity": _field("number", minimum=0, maximum=1),
            "anchor_x": _field("number", minimum=0, maximum=1),
            "anchor_y": _field("number", minimum=0, maximum=1),
            "flip_horizontal": _field("boolean"),
            "flip_vertical": _field("boolean"),
        }, ("clip_id",)),
    ),
    ToolDefinition(
        "clip.set_framing", "framing",
        "Set how a video/image clip fits the project frame: fit keeps the whole image visible, fill preserves aspect ratio and crops overflow, stretch fills the frame without preserving aspect ratio, and none restores default framing.",
        _schema({
            "clip_id": _field("string", max_length=64),
            "mode": _field("string", choices=("fit", "fill", "stretch", "none")),
            "horizontal_alignment": _field("string", choices=("left", "center", "right")),
            "vertical_alignment": _field("string", choices=("top", "middle", "bottom")),
        }, ("clip_id", "mode")),
    ),
    ToolDefinition(
        "clip.set_crop", "framing",
        "Set or clear a normalized manual source crop rectangle for a video or image clip. Coordinates and dimensions are fractions of the original source frame.",
        _schema({
            "clip_id": _field("string", max_length=64),
            "mode": _field("string", choices=("custom", "none")),
            "x": _field("number", minimum=0, maximum=1),
            "y": _field("number", minimum=0, maximum=1),
            "width": _field("number", minimum=0.001, maximum=1),
            "height": _field("number", minimum=0.001, maximum=1),
        }, ("clip_id", "mode")),
    ),
    ToolDefinition(
        "animation.set_keyframe", "animation",
        "Add or replace a visual, volume or video playback-speed keyframe.",
        _schema({
            "clip_id": _field("string", max_length=64),
            "property": _field("string", choices=(
                "position_x", "position_y", "scale_x", "scale_y",
                "rotation_deg", "opacity", "volume_db", "playback_rate",
            )),
            "time_us": _field("integer", minimum=0),
            "value": _field("number"),
            "interpolation": _field("string", choices=(
                "hold", "linear", "ease_in", "ease_out", "ease_in_out", "bezier",
            )),
            "bezier": _field("object", nested={
                "properties": {
                    "x1": _field("number", minimum=0, maximum=1),
                    "y1": _field("number", minimum=0, maximum=1),
                    "x2": _field("number", minimum=0, maximum=1),
                    "y2": _field("number", minimum=0, maximum=1),
                },
                "required": ["x1", "y1", "x2", "y2"],
                "additionalProperties": False,
            }),
        }, ("clip_id", "property", "time_us", "value")),
    ),
    ToolDefinition(
        "animation.clear_keyframes", "animation",
        "Remove all keyframes from a clip, or only the selected property when supplied.",
        _schema({
            "clip_id": _field("string", max_length=64),
            "property": _field("string", choices=(
                "position_x", "position_y", "scale_x", "scale_y",
                "rotation_deg", "opacity", "volume_db", "playback_rate",
            )),
        }, ("clip_id",)),
    ),
    ToolDefinition(
        "animation.remove_keyframe", "animation",
        "Remove one keyframe from a clip by property and clip-local time.",
        _schema({
            "clip_id": _field("string", max_length=64),
            "property": _field("string", choices=(
                "position_x", "position_y", "scale_x", "scale_y",
                "rotation_deg", "opacity", "volume_db", "playback_rate",
            )),
            "time_us": _field("integer", minimum=0),
        }, ("clip_id", "property", "time_us")),
    ),
    ToolDefinition(
        "effect.add", "effects",
        "Add a verified brightness, contrast, saturation, chroma-key, gain or fade effect.",
        _schema({
            "clip_id": _field("string", max_length=64),
            "effect_type": _field("string", choices=(
                "brightness", "contrast", "saturation", "chroma", "gain", "fade",
            )),
            "parameters": _field("object", nested=_PARAMETER_SCHEMA),
        }, ("clip_id", "effect_type", "parameters")),
    ),
    ToolDefinition(
        "effect.remove", "effects",
        "Remove an effect from a clip by effect ID.",
        _schema({
            "clip_id": _field("string", max_length=64),
            "effect_id": _field("string", max_length=64),
        }, ("clip_id", "effect_id")),
    ),
    ToolDefinition(
        "effect.set_enabled", "effects",
        "Enable or bypass an existing allowlisted clip effect without deleting it.",
        _schema({
            "clip_id": _field("string", max_length=64),
            "effect_id": _field("string", max_length=64),
            "enabled": _field("boolean"),
        }, ("clip_id", "effect_id", "enabled")),
    ),
    ToolDefinition(
        "timeline.add_transition", "transitions",
        "Add a dissolve or horizontal wipe between adjacent overlapping visual clips.",
        _schema({
            "from_clip_id": _field("string", max_length=64),
            "to_clip_id": _field("string", max_length=64),
            "transition_type": _field("string", choices=("dissolve", "wipe")),
            "duration_us": _field("integer", minimum=1),
            "parameters": _field("object", nested={
                "properties": {
                    "direction": _field("string", choices=("left_to_right", "right_to_left")),
                    "softness": _field("number", minimum=0, maximum=1),
                },
                "additionalProperties": False,
            }),
        }, ("from_clip_id", "to_clip_id", "transition_type", "duration_us")),
    ),
    ToolDefinition(
        "audio.set_gain", "audio",
        "Set an audio clip's gain in decibels.",
        _schema({
            "clip_id": _field("string", max_length=64),
            "gain_db": _field("number", minimum=-96, maximum=24),
        }, ("clip_id", "gain_db")),
    ),
    ToolDefinition(
        "audio.set_fade", "audio",
        "Set an audio clip's fade-in and/or fade-out duration in microseconds.",
        _schema({
            "clip_id": _field("string", max_length=64),
            "fade_in_us": _field("integer", minimum=0),
            "fade_out_us": _field("integer", minimum=0),
        }, ("clip_id",)),
    ),
    ToolDefinition(
        "history.undo", "history",
        "Undo the last committed project-edit transaction.",
        _schema(), read_only=False,
    ),
    ToolDefinition(
        "history.redo", "history",
        "Redo the most recently undone project-edit transaction.",
        _schema(), read_only=False,
    ),
    ToolDefinition(
        "render.export", "export",
        "Render the current canonical project to MP4 using the verified MLT adapter.",
        _schema({"output_filename": _field("string", max_length=100)}, ("output_filename",)),
        requires_confirmation=True,
    ),
)

_TOOL_MAP = {item.name: item for item in TOOL_DEFINITIONS}


def _validate_value(value: Any, definition: dict[str, Any], path: str) -> None:
    expected = definition["type"]
    if expected == "array":
        if not isinstance(value, list):
            raise ToolValidationError(f"{path} must be an array.")
        if len(value) < definition.get("minItems", 0):
            raise ToolValidationError(f"{path} has too few items.")
        if "maxItems" in definition and len(value) > definition["maxItems"]:
            raise ToolValidationError(f"{path} has too many items.")
        item_schema = definition.get("items")
        if item_schema:
            for index, item in enumerate(value):
                _validate_value(item, item_schema, f"{path}[{index}]")
        return

    if expected == "object":
        if not isinstance(value, dict):
            raise ToolValidationError(f"{path} must be an object.")
        properties = definition.get("properties", {})
        missing = [key for key in definition.get("required", []) if key not in value]
        if missing:
            raise ToolValidationError(
                f"{path} is missing required field(s): {', '.join(missing)}."
            )
        if definition.get("additionalProperties") is False:
            unknown = sorted(set(value) - set(properties))
            if unknown:
                raise ToolValidationError(
                    f"{path} contains unsupported field(s): {', '.join(unknown)}."
                )
        for key, item in value.items():
            if key in properties:
                _validate_value(item, properties[key], f"{path}.{key}")
        return

    if expected == "string":
        if not isinstance(value, str):
            raise ToolValidationError(f"{path} must be text.")
        if definition.get("minLength") and len(value) < definition["minLength"]:
            raise ToolValidationError(f"{path} cannot be empty.")
        if "maxLength" in definition and len(value) > definition["maxLength"]:
            raise ToolValidationError(f"{path} is too long.")
    elif expected == "boolean":
        if not isinstance(value, bool):
            raise ToolValidationError(f"{path} must be true or false.")
    elif expected == "integer":
        if isinstance(value, bool) or not isinstance(value, int):
            raise ToolValidationError(f"{path} must be a whole number.")
    elif expected == "number":
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ToolValidationError(f"{path} must be a finite number.")
    else:
        raise ToolValidationError(f"{path} uses an unsupported schema type.")

    if expected in {"integer", "number"}:
        if "minimum" in definition and value < definition["minimum"]:
            raise ToolValidationError(f"{path} is below the allowed minimum.")
        if "maximum" in definition and value > definition["maximum"]:
            raise ToolValidationError(f"{path} is above the allowed maximum.")
    if "enum" in definition and value not in definition["enum"]:
        raise ToolValidationError(f"{path} is not one of the allowed choices.")


def get_tool_catalog() -> list[dict[str, Any]]:
    """Return only tools that have an execution handler."""
    return [
        {
            "name": item.name,
            "category": item.category,
            "description": item.description,
            "input_schema": deepcopy(item.input_schema),
            "requires_confirmation": item.requires_confirmation,
            "read_only": item.read_only,
        }
        for item in TOOL_DEFINITIONS
    ]


def get_tool_definition(name: str) -> ToolDefinition:
    definition = _TOOL_MAP.get(name)
    if definition is None:
        raise ToolValidationError("This tool is not registered.")
    return definition


def validate_tool_call(name: str, arguments: Any) -> dict[str, Any]:
    """Validate a proposed call and return a copy of its accepted arguments."""
    definition = get_tool_definition(name)
    if not isinstance(arguments, dict):
        raise ToolValidationError("Tool arguments must be an object.")
    clean = deepcopy(arguments)
    _validate_value(clean, definition.input_schema, name)

    if name in {"timeline.trim_clip", "timeline.add_clip"}:
        source_in = clean.get("source_in_us", 0)
        source_out = clean.get("source_out_us")
        if source_out is not None and source_out <= source_in:
            raise ToolValidationError("source_out_us must be greater than source_in_us.")
    if name == "timeline.add_transition":
        if clean["from_clip_id"] == clean["to_clip_id"]:
            raise ToolValidationError("A transition must connect two different clips.")
        parameters = clean.get("parameters", {})
        if clean["transition_type"] == "dissolve" and parameters:
            raise ToolValidationError("Dissolve does not accept parameters in this engine.")
    if name == "clip.set_transform" and not any(key != "clip_id" for key in clean):
        raise ToolValidationError("Set at least one transform property.")
    if name == "animation.set_keyframe":
        prop = clean["property"]
        value = clean["value"]
        limits = {
            "scale_x": (0.001, 100), "scale_y": (0.001, 100),
            "opacity": (0, 1), "volume_db": (-96, 24),
            "playback_rate": (0.05, 16),
            "position_x": (-100000, 100000), "position_y": (-100000, 100000),
            "rotation_deg": (-360000, 360000),
        }
        low, high = limits[prop]
        if not low <= value <= high:
            raise ToolValidationError(f"value is outside the allowed range for {prop}.")
        if clean.get("interpolation") == "bezier" and "bezier" not in clean:
            raise ToolValidationError("Bezier interpolation requires control points.")
        if clean.get("interpolation") != "bezier" and "bezier" in clean:
            raise ToolValidationError("Bezier control points require bezier interpolation.")
    if name == "audio.set_fade":
        if clean.get("fade_in_us", 0) == 0 and clean.get("fade_out_us", 0) == 0:
            raise ToolValidationError("At least one audio fade duration must be greater than zero.")
    if name == "text.update_clip" and not any(
        key in clean for key in ("content", "text_style")
    ):
        raise ToolValidationError("text.update_clip must change content and/or text_style.")
    return clean


def tool_requires_confirmation(name: str) -> bool:
    return get_tool_definition(name).requires_confirmation
