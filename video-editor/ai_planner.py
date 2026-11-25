from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from typing import Any

from engine import EditPlan, plan_from_instruction, validate_plan


def _defaults_plan(defaults: dict[str, Any] | None) -> dict[str, Any]:
    settings = defaults or {}
    aspect = str(settings.get("aspect", "9:16"))
    if aspect not in {"9:16", "1:1", "16:9"}:
        aspect = "9:16"
    return {
        "trim_start": 0.0,
        "trim_end": None,
        "speed": float(settings.get("speed", 1.0)),
        "aspect": aspect,
        "width": int(settings.get("width", 1280 if aspect == "16:9" else 720)),
        "height": int(settings.get("height", 720 if aspect in {"16:9", "1:1"} else 1280)),
    }


def _validate_plan_data(data: dict[str, Any], defaults: dict[str, Any] | None) -> EditPlan:
    clean = _defaults_plan(defaults)
    allowed = {"trim_start", "trim_end", "speed", "aspect", "width", "height"}
    clean.update({key: data[key] for key in allowed if key in data})
    clean["trim_start"] = float(clean["trim_start"])
    clean["trim_end"] = None if clean["trim_end"] is None else float(clean["trim_end"])
    clean["speed"] = float(clean["speed"])
    clean["width"] = int(clean["width"])
    clean["height"] = int(clean["height"])
    clean["aspect"] = str(clean["aspect"])
    plan = EditPlan(**clean)
    validate_plan(plan)
    return plan


def _gemini_plan(instruction: str, defaults: dict[str, Any] | None) -> EditPlan:
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is not configured")
    model = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash-lite").strip()
    default_data = _defaults_plan(defaults)
    prompt = (
        "You are an editing-plan generator for a deterministic video editor. "
        "Return valid JSON only with fields trim_start (seconds), trim_end (seconds or null), "
        "speed (0.25 to 4), aspect (9:16, 1:1, or 16:9), width, height. "
        "Do not invent a trim range; if none was requested use trim_start 0 and trim_end null. "
        "Preserve skill defaults unless the user explicitly changes them. "
        "Do not return commands, code, effects, or unsupported operations.\n"
        f"Defaults: {json.dumps(default_data)}\n"
        f"User instruction: {instruction[:1500]}"
    )
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        + urllib.parse.quote(model, safe="")
        + ":generateContent?key=" + urllib.parse.quote(api_key, safe="")
    )
    payload = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"responseMimeType": "application/json", "temperature": 0.1},
    }).encode("utf-8")
    request = urllib.request.Request(
        url, data=payload,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=45) as response:
        result = json.loads(response.read().decode("utf-8"))
    text = result["candidates"][0]["content"]["parts"][0]["text"]
    generated = json.loads(text)
    if not isinstance(generated, dict):
        raise ValueError("Gemini did not return a plan object")
    return _validate_plan_data(generated, defaults)


def plan_edit(
    instruction: str,
    defaults: dict[str, Any] | None = None,
    preferred_plan: dict[str, Any] | None = None,
) -> EditPlan:
    """Shared AI planning contract for the API and cloud worker.

    An already-generated Apps Script plan is validated first. Otherwise Gemini
    is used when configured. Any unavailable/invalid AI response falls back to
    the deterministic instruction parser so model output never directly runs
    as code or bypasses engine validation.
    """
    if isinstance(preferred_plan, dict):
        try:
            return _validate_plan_data(preferred_plan, defaults)
        except (TypeError, ValueError, KeyError):
            pass
    if os.environ.get("GEMINI_API_KEY", "").strip():
        try:
            return _gemini_plan(instruction, defaults)
        except Exception:
            pass
    return plan_from_instruction(instruction, defaults)
