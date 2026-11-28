"""Versioned, data-only built-in title templates.

Templates are copied into ordinary text clips. No template code, files, fonts,
or external resources are loaded by the renderer.
"""
from __future__ import annotations

from copy import deepcopy
import math
import re
from typing import Any


TEMPLATE_SCHEMA_VERSION = 1
_TEMPLATE_FIELDS = {"id", "name", "schema_version", "text_defaults", "animation_defaults"}
_ID_RE = re.compile(r"^[a-z][a-z0-9-]{1,47}$")
_COLOUR_RE = re.compile(r"^#[0-9A-Fa-f]{6}(?:[0-9A-Fa-f]{2})?$")
_ALLOWED_PROPERTIES = {
    "opacity", "scale_x", "scale_y", "position_x", "position_y", "rotation_deg"
}
_ALLOWED_INTERPOLATIONS = {"linear", "ease_in_out", "ease_out"}
_STYLE_RULES = {
    "family": ("string", 1, 80),
    "size": ("int", 8, 256),
    "weight": ("int", 100, 1000),
    "fgcolour": ("colour",),
    "highlight_colour": ("colour",),
    "bgcolour": ("colour",),
    "bgopacity": ("number", 0, 1),
    "background_fill": ("bool",),
    "pad": ("int", 0, 128),
    "shadow_color": ("colour",),
    "shadow_x": ("int", -32, 32),
    "shadow_y": ("int", -32, 32),
    "shadow_opacity": ("number", 0, 1),
    "shadow_blur": ("number", 0, 10),
    "letter_spacing_px": ("number", -10, 40),
    "line_spacing_px": ("int", -40, 120),
    "opacity": ("number", 0, 1),
    "style": ("choice", {"normal", "italic"}),
    "underline": ("bool",),
    "strikethrough": ("bool",),
    "olcolour": ("colour",),
    "outline": ("int", 0, 3),
    "halign": ("choice", {"left", "center", "right"}),
    "valign": ("choice", {"top", "middle", "bottom"}),
    "x_percent": ("number", 0, 99),
    "y_percent": ("number", 0, 99),
    "width_percent": ("number", 1, 100),
    "height_percent": ("number", 1, 100),
}

_BUILTIN_TEMPLATES = (
    {
        "id": "clean-centre-v1",
        "name": "Clean Centre Title",
        "schema_version": 1,
        "text_defaults": {
            "family": "Sans", "size": 56, "weight": 700,
            "fgcolour": "#FFFFFF", "outline": 1, "olcolour": "#101010",
            "halign": "center", "valign": "middle",
            "x_percent": 5, "y_percent": 35, "width_percent": 90, "height_percent": 30,
        },
        "animation_defaults": [],
    },
    {
        "id": "editorial-lower-third-v1",
        "name": "Editorial Lower Third",
        "schema_version": 1,
        "text_defaults": {
            "family": "Sans", "size": 42, "weight": 700,
            "fgcolour": "#FFFFFF", "outline": 0,
            "halign": "left", "valign": "middle",
            "x_percent": 8, "y_percent": 74, "width_percent": 84, "height_percent": 20,
            "background_fill": True, "bgcolour": "#101820", "bgopacity": 0.78,
            "pad": 16, "shadow_color": "#000000", "shadow_x": 1, "shadow_y": 2,
            "shadow_opacity": 0.45, "shadow_blur": 2,
        },
        "animation_defaults": [],
    },
    {
        "id": "bold-section-v1",
        "name": "Bold Section Title",
        "schema_version": 1,
        "text_defaults": {
            "family": "Sans", "size": 64, "weight": 900,
            "fgcolour": "#F8FAFC", "outline": 2, "olcolour": "#111827",
            "halign": "center", "valign": "middle",
            "x_percent": 5, "y_percent": 36, "width_percent": 90, "height_percent": 28,
            "letter_spacing_px": 1.5,
        },
        "animation_defaults": [],
    },
    {
        "id": "animated-rise-v1",
        "name": "Animated Rise Title",
        "schema_version": 1,
        "text_defaults": {
            "family": "Sans", "size": 56, "weight": 700,
            "fgcolour": "#FFFFFF", "outline": 1, "olcolour": "#000000",
            "halign": "center", "valign": "middle",
            "x_percent": 5, "y_percent": 38, "width_percent": 90, "height_percent": 26,
        },
        "animation_defaults": [
            {"property": "opacity", "time_ratio": 0.0, "value": 0.0, "interpolation": "linear"},
            {"property": "opacity", "time_ratio": 0.3, "value": 1.0, "interpolation": "linear"},
            {"property": "position_y", "time_ratio": 0.0, "value": 28.0, "interpolation": "ease_out"},
            {"property": "position_y", "time_ratio": 0.3, "value": 0.0, "interpolation": "ease_out"},
        ],
    },
)


class TitleTemplateValidationError(ValueError):
    """Raised when a title template is malformed or unsupported."""


def _finite_number(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise TitleTemplateValidationError(f"{field} must be a finite number.")
    return float(value)


def _validate_style(style: Any, path: str) -> None:
    if not isinstance(style, dict) or not style or len(style) > len(_STYLE_RULES):
        raise TitleTemplateValidationError(f"{path} must be a non-empty supported style object.")
    unknown = set(style) - set(_STYLE_RULES)
    if unknown:
        raise TitleTemplateValidationError(f"{path} contains unsupported field(s): {', '.join(sorted(unknown))}.")
    for key, value in style.items():
        rule = _STYLE_RULES[key]
        kind = rule[0]
        if kind == "string":
            if not isinstance(value, str) or not value.strip() or len(value) > rule[2] or value != value.strip():
                raise TitleTemplateValidationError(f"{path}.{key} must be trimmed text of at most {rule[2]} characters.")
        elif kind == "colour":
            if not isinstance(value, str) or not _COLOUR_RE.fullmatch(value):
                raise TitleTemplateValidationError(f"{path}.{key} must be a #RRGGBB or #RRGGBBAA colour.")
        elif kind == "bool":
            if not isinstance(value, bool):
                raise TitleTemplateValidationError(f"{path}.{key} must be a boolean.")
        elif kind == "choice":
            if not isinstance(value, str) or value not in rule[1]:
                raise TitleTemplateValidationError(f"{path}.{key} has an unsupported value.")
        else:
            number = _finite_number(value, f"{path}.{key}")
            if kind == "int" and (isinstance(value, bool) or not isinstance(value, int)):
                raise TitleTemplateValidationError(f"{path}.{key} must be an integer.")
            if not rule[1] <= number <= rule[2]:
                raise TitleTemplateValidationError(f"{path}.{key} is outside its supported range.")
    x = style.get("x_percent", 0)
    y = style.get("y_percent", 0)
    width = style.get("width_percent", 100)
    height = style.get("height_percent", 100)
    if x + width > 100 or y + height > 100:
        raise TitleTemplateValidationError(f"{path} text box must stay inside the video frame.")


def validate_template_catalogue(catalogue: Any) -> list[dict[str, Any]]:
    """Validate a closed, bounded catalogue and return an independent copy."""
    if not isinstance(catalogue, (list, tuple)) or not 1 <= len(catalogue) <= 20:
        raise TitleTemplateValidationError("Template catalogue must contain between 1 and 20 entries.")
    seen_ids: set[str] = set()
    seen_names: set[str] = set()
    validated: list[dict[str, Any]] = []
    for index, template in enumerate(catalogue):
        path = f"templates[{index}]"
        if not isinstance(template, dict) or set(template) != _TEMPLATE_FIELDS:
            raise TitleTemplateValidationError(f"{path} must contain exactly the supported template fields.")
        identifier = template["id"]
        name = template["name"]
        version = template["schema_version"]
        if not isinstance(identifier, str) or not _ID_RE.fullmatch(identifier):
            raise TitleTemplateValidationError(f"{path}.id is invalid.")
        if identifier in seen_ids:
            raise TitleTemplateValidationError("Template IDs must be unique.")
        if not isinstance(name, str) or not name.strip() or name != name.strip() or len(name) > 80:
            raise TitleTemplateValidationError(f"{path}.name must be trimmed text of at most 80 characters.")
        if name.casefold() in seen_names:
            raise TitleTemplateValidationError("Template names must be unique, ignoring case.")
        if isinstance(version, bool) or version != TEMPLATE_SCHEMA_VERSION:
            raise TitleTemplateValidationError(f"{path}.schema_version is unsupported.")
        seen_ids.add(identifier)
        seen_names.add(name.casefold())
        _validate_style(template["text_defaults"], f"{path}.text_defaults")
        frames = template["animation_defaults"]
        if not isinstance(frames, list) or len(frames) > 24:
            raise TitleTemplateValidationError(f"{path}.animation_defaults must contain at most 24 keyframes.")
        seen_frames: set[tuple[str, float]] = set()
        for frame_index, frame in enumerate(frames):
            frame_path = f"{path}.animation_defaults[{frame_index}]"
            if not isinstance(frame, dict) or set(frame) != {"property", "time_ratio", "value", "interpolation"}:
                raise TitleTemplateValidationError(f"{frame_path} has unsupported or missing fields.")
            prop = frame["property"]
            if prop not in _ALLOWED_PROPERTIES:
                raise TitleTemplateValidationError(f"{frame_path}.property is unsupported.")
            ratio = _finite_number(frame["time_ratio"], f"{frame_path}.time_ratio")
            if not 0 <= ratio <= 1:
                raise TitleTemplateValidationError(f"{frame_path}.time_ratio must be from 0 to 1.")
            interpolation = frame["interpolation"]
            if interpolation not in _ALLOWED_INTERPOLATIONS:
                raise TitleTemplateValidationError(f"{frame_path}.interpolation is unsupported.")
            value = _finite_number(frame["value"], f"{frame_path}.value")
            low, high = {
                "opacity": (0, 1), "scale_x": (0.001, 100), "scale_y": (0.001, 100),
                "position_x": (-100000, 100000), "position_y": (-100000, 100000),
                "rotation_deg": (-360000, 360000),
            }[prop]
            if not low <= value <= high:
                raise TitleTemplateValidationError(f"{frame_path}.value is outside the supported range for {prop}.")
            marker = (prop, ratio)
            if marker in seen_frames:
                raise TitleTemplateValidationError(f"{frame_path} duplicates a property/time keyframe.")
            seen_frames.add(marker)
        validated.append(deepcopy(template))
    return validated


def list_title_templates() -> list[dict[str, Any]]:
    """Return safe copies of the built-in catalogue."""
    return validate_template_catalogue(_BUILTIN_TEMPLATES)


def resolve_title_template(template_id: str, duration_us: int) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Resolve a built-in template into copied text style and clip-local keyframes."""
    if not isinstance(template_id, str):
        raise TitleTemplateValidationError("A valid template ID is required.")
    if isinstance(duration_us, bool) or not isinstance(duration_us, int) or duration_us < 1:
        raise TitleTemplateValidationError("Title duration must be a positive integer number of microseconds.")
    template = next((item for item in _BUILTIN_TEMPLATES if item["id"] == template_id), None)
    if template is None:
        raise TitleTemplateValidationError("The selected title template does not exist.")
    validated = validate_template_catalogue([template])[0]
    style = deepcopy(validated["text_defaults"])
    frames = []
    seen_times: set[tuple[str, int]] = set()
    for frame in validated["animation_defaults"]:
        time_us = round(frame["time_ratio"] * duration_us)
        marker = (frame["property"], time_us)
        if marker in seen_times:
            raise TitleTemplateValidationError("The selected duration is too short for this template's animation keyframes.")
        seen_times.add(marker)
        frames.append({
            "property": frame["property"],
            "time_us": time_us,
            "value": frame["value"],
            "interpolation": frame["interpolation"],
        })
    return style, frames
