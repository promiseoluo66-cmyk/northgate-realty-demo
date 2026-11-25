"""AI planner/controller for safe multi-step project editing.

Gemini proposes registered tool calls as JSON. Every call is schema-checked and
then executed by ProjectToolExecutor against a validated project copy. Model
output is never evaluated as code or sent to a shell.
"""
from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from typing import Any, Callable

from project_tool_executor import (
    ProjectToolExecutor,
    ProjectRevisionConflict,
    ToolConfirmationRequired,
)
from tool_registry import get_tool_catalog, validate_tool_call


class AIEditControllerError(RuntimeError):
    """Raised when the AI cannot produce a safe, valid editing plan."""


def _project_context(executor: ProjectToolExecutor) -> dict[str, Any]:
    project = executor.get_project()
    # The project inspector returns IDs and editing details, but not the
    # private filesystem storage keys used by the render worker.
    context = executor.inspect()
    context["assets"] = [
        {
            key: value
            for key, value in asset.items()
            if key not in {"storage_key"}
        }
        for asset in project["assets"]
    ]
    context["transitions"] = project.get("transitions", [])
    return context


def build_tool_plan_prompt(
    instruction: str, executor: ProjectToolExecutor
) -> str:
    if not isinstance(instruction, str) or not instruction.strip():
        raise AIEditControllerError("Describe the edit you want the AI to make.")
    catalog = get_tool_catalog()
    context = _project_context(executor)
    return (
        "You are the editing brain for an independent multi-track video editor. "
        "Translate the user's request into a short, ordered sequence of registered tool calls. "
        "Return JSON only with this exact shape: "
        '{"summary":"plain-language plan","tool_calls":[{"name":"registered.tool","arguments":{}}]}. '
        "Use only the tools and exact argument schemas supplied below. "
        "Never return shell commands, Python, JavaScript, paths, URLs, or invented tool names. "
        "Inspect the project first when clip/track/media IDs or timings are uncertain. "
        "Use the existing clips and media IDs shown in the project context. "
        "Do not invent media, clip, track or asset IDs. "
        "Use microseconds for all timeline/source/time_us/duration values. "
        "Keyframe time_us is local to the clip, not the whole project. "
        "Speed-ramp playback_rate keyframes are video-only and cannot be combined with "
        "animated visual transforms or clip effects in the current renderer. "
        "Audio volume keyframes are audio-only and cannot be combined with speed ramps. "
        "Visual effects currently available are brightness, contrast, saturation and chroma; "
        "audio effects are gain and fade. "
        "Transitions are only dissolve or horizontal wipe, must connect adjacent clips on "
        "the same visual track, and their duration must exactly match the timeline overlap. "
        "To create an overlap, position the incoming clip so it starts before the outgoing "
        "clip ends, then add the transition. "
        "Undo and redo are standalone requests: if you choose history.undo or history.redo, "
        "return exactly that one tool call and no other operation. The runner exports the "
        "result after the history operation. "
        "For other edits, do not include render.export; the runner appends the export call "
        "after your edit batch when the user submits a render. Destructive edits require "
        "explicit user confirmation. "
        "Never silently claim that a requested unavailable effect was applied. "
        "If a requested feature is not in the registered tool catalogue, explain that in "
        "the summary and do not substitute an unrelated effect. "
        "Keep tool calls minimal and avoid changing anything the user did not request.\n\n"
        "REGISTERED TOOLS:\n"
        + json.dumps(catalog, ensure_ascii=False, separators=(",", ":"))
        + "\n\nCURRENT PROJECT:\n"
        + json.dumps(context, ensure_ascii=False, separators=(",", ":"))
        + "\n\nUSER INSTRUCTION:\n"
        + instruction.strip()[:4000]
    )


def _gemini_generate_json(prompt: str) -> dict[str, Any]:
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise AIEditControllerError(
            "GEMINI_API_KEY is not configured. The editing tools are ready, "
            "but the AI planner needs an enabled model connection."
        )
    model = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash-lite").strip()
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        + urllib.parse.quote(model, safe="")
        + ":generateContent?key="
        + urllib.parse.quote(api_key, safe="")
    )
    payload = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "responseMimeType": "application/json",
            "temperature": 0.1,
        },
    }).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            result = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        raise AIEditControllerError(
            f"The AI planning request failed: {type(exc).__name__}: {exc}"
        ) from exc
    try:
        raw = result["candidates"][0]["content"]["parts"][0]["text"]
        generated = json.loads(raw)
    except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
        raise AIEditControllerError("The AI did not return the required JSON tool plan.") from exc
    if not isinstance(generated, dict):
        raise AIEditControllerError("The AI plan must be a JSON object.")
    return generated


def validate_tool_plan(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise AIEditControllerError("The AI plan must be an object.")
    summary = data.get("summary", "")
    calls = data.get("tool_calls")
    if not isinstance(summary, str) or len(summary) > 1200:
        raise AIEditControllerError("The plan summary must be text of at most 1,200 characters.")
    if not isinstance(calls, list) or not calls or len(calls) > 40:
        raise AIEditControllerError("The AI must return between 1 and 40 tool calls.")
    validated: list[dict[str, Any]] = []
    for index, call in enumerate(calls):
        if not isinstance(call, dict) or set(call) != {"name", "arguments"}:
            raise AIEditControllerError(
                f"Tool call {index + 1} must contain only name and arguments."
            )
        name = call["name"]
        if not isinstance(name, str):
            raise AIEditControllerError(f"Tool call {index + 1} has an invalid name.")
        try:
            arguments = validate_tool_call(name, call["arguments"])
        except Exception as exc:
            raise AIEditControllerError(
                f"Tool call {index + 1} ({name}) was rejected: {exc}"
            ) from exc
        validated.append({"name": name, "arguments": arguments})
    return {"summary": summary.strip(), "tool_calls": validated}


def plan_project_edit(
    instruction: str,
    executor: ProjectToolExecutor,
    *,
    preferred_plan: dict[str, Any] | None = None,
    provider: Callable[[str], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Generate and validate a tool plan; provider injection supports offline tests."""
    prompt = build_tool_plan_prompt(instruction, executor)
    if preferred_plan is not None:
        generated = preferred_plan
    elif provider is not None:
        generated = provider(prompt)
    else:
        generated = _gemini_generate_json(prompt)
    return validate_tool_plan(generated)


def run_ai_edit(
    instruction: str,
    executor: ProjectToolExecutor,
    *,
    expected_revision: int | None = None,
    confirmed_tools: set[str] | None = None,
    preferred_plan: dict[str, Any] | None = None,
    provider: Callable[[str], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Plan, validate and atomically apply the AI's registered editing tools."""
    plan = plan_project_edit(
        instruction, executor,
        preferred_plan=preferred_plan,
        provider=provider,
    )
    try:
        result = executor.execute_batch(
            plan["tool_calls"],
            expected_revision=expected_revision,
            confirmed_tools=confirmed_tools,
        )
    except ToolConfirmationRequired as exc:
        return {
            "ok": False,
            "status": "awaiting_confirmation",
            "summary": plan["summary"],
            "tool_calls": plan["tool_calls"],
            "required_confirmations": exc.tool_names,
            "revision": executor.revision,
        }
    except ProjectRevisionConflict as exc:
        return {
            "ok": False,
            "status": "revision_conflict",
            "error": str(exc),
            "revision": executor.revision,
        }
    return {
        "ok": True,
        "status": "applied",
        "summary": plan["summary"],
        "tool_calls": plan["tool_calls"],
        "execution": result,
    }
