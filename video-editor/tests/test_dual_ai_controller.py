"""Offline tests for the Gemini + DeepSeek collaborative editor."""
import unittest
from io import BytesIO
from pathlib import Path
import urllib.error
import urllib.request

from dual_ai_controller import (
    DualAIControllerError,
    build_deepseek_plan_prompt,
    plan_dual_ai_edit,
    validate_video_analysis,
    _groq_analyze_video,
    _request_json,
)
from project_tool_executor import ProjectToolExecutor
from ai_edit_controller import run_ai_edit
from dual_ai_controller import _deepseek_generate_plan
from unittest.mock import patch
import json
import os


def make_project():
    return {
        "schema_version": 1,
        "id": "dual-ai-test",
        "name": "Dual AI test",
        "revision": 1,
        "timeline_timebase": "microseconds",
        "video_profile": {
            "width": 720,
            "height": 1280,
            "frame_rate": {"numerator": 30, "denominator": 1},
        },
        "assets": [{
            "id": "source-video",
            "media_type": "video",
            "file_name": "sample.mp4",
            "storage_key": "sample.mp4",
            "size_bytes": 1000,
            "duration_us": 5_000_000,
        }],
        "tracks": [{
            "id": "main-video",
            "type": "video",
            "name": "Main video",
            "order": 0,
            "clips": [{
                "id": "main-clip",
                "kind": "video",
                "media_id": "source-video",
                "start_us": 0,
                "duration_us": 5_000_000,
                "source_in_us": 0,
                "source_out_us": 5_000_000,
                "playback_rate": 1.0,
                "effects": [],
                "keyframes": [],
            }],
        }, {
            "id": "titles",
            "type": "text",
            "name": "Titles",
            "order": 1,
            "clips": [],
        }],
        "transitions": [],
    }


def valid_analysis():
    return {
        "summary": "A person walks into frame and turns toward the camera.",
        "scenes": [{
            "start_us": 0,
            "end_us": 5_000_000,
            "description": "One continuous shot of a person approaching the camera.",
            "objects": ["person", "doorway"],
            "movement": "The person walks forward and turns.",
            "audio_notes": "Low background music; no clear speech.",
        }],
        "key_moments": [{
            "time_us": 2_000_000,
            "description": "The person turns to face the camera.",
            "editing_value": "A useful moment for a cut or title reveal.",
        }],
        "editing_notes": ["Keep the turn visible; avoid cutting through the action."],
        "tool_suggestions": [{
            "name": "clip.set_speed",
            "arguments": {"clip_id": "main-clip", "playback_rate": 1.25},
            "reason": "A slight speed increase may make the approach more energetic.",
        }],
    }


class DualAIControllerTests(unittest.TestCase):
    def setUp(self):
        self.executor = ProjectToolExecutor(make_project())

    def test_both_agents_receive_the_same_registered_tool_catalogue(self):
        prompts = []
        plan = {
            "summary": "Slightly speed up the approach.",
            "tool_calls": [{
                "name": "clip.set_speed",
                "arguments": {"clip_id": "main-clip", "playback_rate": 1.25},
            }],
        }

        def gemini(path, prompt):
            self.assertEqual(path.name, "sample.mp4")
            prompts.append(("gemini", prompt))
            return valid_analysis()

        def deepseek(prompt):
            prompts.append(("deepseek", prompt))
            return plan

        collaboration = plan_dual_ai_edit(
            "Make the clip slightly faster.",
            "sample.mp4",
            self.executor,
            video_analyzer=gemini,
            planner_provider=deepseek,
        )
        self.assertEqual(collaboration["agents"]["visual_analysis"], "Gemini")
        self.assertEqual(collaboration["agents"]["editing_reasoning"], "DeepSeek via GonkaRouter")
        self.assertIn("SHARED REGISTERED TOOL CATALOGUE", prompts[0][1])
        self.assertIn("clip.set_speed", prompts[0][1])
        self.assertIn("VISUAL ANALYSIS", prompts[1][1])
        self.assertIn("SHARED REGISTERED TOOL CATALOGUE", prompts[1][1])
        self.assertIn("editing_value", prompts[1][1])
        self.assertEqual(collaboration["plan"]["tool_calls"], plan["tool_calls"])

    def test_deepseek_plan_executes_through_the_existing_project_executor(self):
        plan = {
            "summary": "Increase the main clip playback speed.",
            "tool_calls": [{
                "name": "clip.set_speed",
                "arguments": {"clip_id": "main-clip", "playback_rate": 1.5},
            }],
        }
        collaboration = plan_dual_ai_edit(
            "Speed this clip up.",
            "sample.mp4",
            self.executor,
            video_analyzer=lambda _path, _prompt: valid_analysis(),
            planner_provider=lambda _prompt: plan,
        )
        result = run_ai_edit(
            "Speed this clip up.",
            self.executor,
            expected_revision=1,
            preferred_plan=collaboration["plan"],
        )
        self.assertTrue(result["ok"])
        self.assertEqual(result["status"], "applied")
        clip = self.executor.get_project()["tracks"][0]["clips"][0]
        self.assertEqual(clip["playback_rate"], 1.5)
        self.assertEqual(self.executor.revision, 2)

    def test_invalid_gemini_tool_suggestions_are_rejected_not_executed(self):
        report = valid_analysis()
        report["tool_suggestions"].append({
            "name": "system.run_shell",
            "arguments": {"command": "do something"},
            "reason": "not allowed",
        })
        checked = validate_video_analysis(report)
        self.assertEqual(len(checked["tool_suggestions"]), 1)
        self.assertEqual(len(checked["rejected_tool_suggestions"]), 1)
        self.assertNotIn("system.run_shell", str(checked["tool_suggestions"]))

    def test_invalid_timestamps_are_rejected(self):
        report = valid_analysis()
        report["scenes"][0]["end_us"] = 0
        with self.assertRaisesRegex(DualAIControllerError, "timestamps"):
            validate_video_analysis(report)

    def test_deepseek_cannot_invent_an_unregistered_editing_tool(self):
        with self.assertRaisesRegex(DualAIControllerError, "registered"):
            plan_dual_ai_edit(
                "Do an unsafe edit.",
                "sample.mp4",
                self.executor,
                video_analyzer=lambda _path, _prompt: valid_analysis(),
                planner_provider=lambda _prompt: {
                    "summary": "Run a shell command.",
                    "tool_calls": [{
                        "name": "system.run_shell",
                        "arguments": {"command": "anything"},
                    }],
                },
            )


    def test_deepseek_receives_function_schemas_and_returns_registered_calls(self):
        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self):
                return json.dumps({
                    "choices": [{
                        "message": {
                            "content": "Speed up the main clip.",
                            "tool_calls": [{
                                "id": "call-1",
                                "type": "function",
                                "function": {
                                    "name": "op__clip__set_speed",
                                    "arguments": json.dumps({
                                        "clip_id": "main-clip",
                                        "playback_rate": 1.4,
                                    }),
                                },
                            }],
                        },
                    }],
                }).encode("utf-8")

        def fake_urlopen(request, timeout):
            self.assertTrue(request.full_url.endswith("/chat/completions"))
            self.assertEqual(request.get_header("Authorization"), "Bearer test-router-key")
            payload = json.loads(request.data.decode("utf-8"))
            self.assertEqual(payload["model"], "deepseek-ai/DeepSeek-V4-Flash-0731")
            self.assertFalse(payload["parallel_tool_calls"])
            tool_names = {
                item["function"]["name"] for item in payload["tools"]
            }
            self.assertIn("op__clip__set_speed", tool_names)
            self.assertIn("op__timeline__add_text_clip", tool_names)
            return FakeResponse()

        with patch.dict(os.environ, {
            "GONKA_ROUTER_API_KEY": "test-router-key",
            "GONKA_ROUTER_BASE_URL": "https://api.gonkarouter.io/v1",
            "GONKA_DEEPSEEK_MODEL": "deepseek-ai/DeepSeek-V4-Flash-0731",
        }), patch("dual_ai_controller.urllib.request.urlopen", side_effect=fake_urlopen):
            plan = _deepseek_generate_plan("Make the main clip faster.")

        self.assertEqual(plan["summary"], "Speed up the main clip.")
        self.assertEqual(plan["tool_calls"][0]["name"], "clip.set_speed")
        self.assertEqual(plan["tool_calls"][0]["arguments"]["playback_rate"], 1.4)

    def test_planner_prompt_includes_visual_findings_and_project_context(self):
        prompt = build_deepseek_plan_prompt(
            "Add a title at the important moment.",
            self.executor,
            validate_video_analysis(valid_analysis()),
        )
        self.assertIn("2000000", prompt)
        self.assertIn("main-clip", prompt)
        self.assertIn("timeline.add_text_clip", prompt)


    def test_request_json_retries_temporary_503_before_succeeding(self):
        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self):
                return b'{"ok": true}'

        temporary_error = urllib.error.HTTPError(
            "https://provider.example/api",
            503,
            "Service Unavailable",
            {"Retry-After": "0"},
            BytesIO(b'{"error":"busy"}'),
        )
        request = urllib.request.Request("https://provider.example/api")
        with patch.dict(os.environ, {"AI_HTTP_MAX_ATTEMPTS": "2"}), \
             patch("dual_ai_controller.urllib.request.urlopen",
                   side_effect=[temporary_error, FakeResponse()]) as mocked, \
             patch("dual_ai_controller.time.sleep") as sleep:
            result = _request_json(request, timeout=5, stage="test provider call")

        self.assertEqual(result, {"ok": True})
        self.assertEqual(mocked.call_count, 2)
        sleep.assert_called_once_with(0.0)

    def test_groq_fallback_builds_timestamped_visual_only_analysis(self):
        frames = [
            {"timestamp_us": 600_000, "data_url": "data:image/jpeg;base64,AA=="},
            {"timestamp_us": 2_500_000, "data_url": "data:image/jpeg;base64,AQ=="},
            {"timestamp_us": 4_400_000, "data_url": "data:image/jpeg;base64,Ag=="},
        ]
        provider_payload = {
            "summary": "Three still frames show a person near a doorway.",
            "observations": [
                {"frame_index": 0, "description": "A person stands near a doorway.", "objects": ["person", "doorway"]},
                {"frame_index": 1, "description": "The person is centered in the frame.", "objects": ["person"]},
                {"frame_index": 2, "description": "The doorway is visible behind the person.", "objects": ["doorway"]},
            ],
            "editing_notes": ["Keep the person centered where possible."],
        }

        def fake_request(request, timeout, stage):
            self.assertEqual(request.full_url, "https://api.groq.com/openai/v1/chat/completions")
            self.assertEqual(request.get_header("Authorization"), "Bearer test-groq-key")
            body = json.loads(request.data.decode("utf-8"))
            self.assertEqual(body["model"], "qwen/qwen3.8-27b")
            self.assertEqual(body["max_completion_tokens"], 1200)
            self.assertEqual(body["response_format"], {"type": "json_object"})
            image_parts = [
                part for part in body["messages"][0]["content"]
                if part.get("type") == "image_url"
            ]
            self.assertEqual(len(image_parts), 3)
            return {
                "choices": [{
                    "message": {"content": json.dumps(provider_payload)}
                }]
            }

        with patch.dict(os.environ, {
            "GROQ_API_KEY": "test-groq-key",
            "GROQ_VISION_MODEL": "qwen/qwen3.8-27b",
        }), patch("dual_ai_controller._extract_groq_video_frames",
                  return_value=(5_000_000, frames)), \
             patch("dual_ai_controller._request_json", side_effect=fake_request):
            analysis = _groq_analyze_video(
                Path("sample.mp4"),
                "Make the clip cleaner and keep the person visible.",
            )

        self.assertEqual(analysis["analysis_provider"], "Groq Qwen 3.8 27B (sampled-frame fallback)")
        self.assertIn("motion between frames were not analysed", analysis["coverage_notes"])
        self.assertEqual([item["time_us"] for item in analysis["key_moments"]],
                         [600_000, 2_500_000, 4_400_000])
        self.assertIn("not analysed", analysis["scenes"][0]["audio_notes"].lower())
        self.assertEqual(analysis["tool_suggestions"], [])

    def test_groq_fallback_is_used_when_gemini_fails(self):
        groq_analysis = {
            **valid_analysis(),
            "analysis_provider": "Groq test fallback",
            "coverage_notes": "Still frames only; no audio analysis.",
        }
        plan = {
            "summary": "Keep the main clip intact.",
            "tool_calls": [{
                "name": "clip.set_speed",
                "arguments": {"clip_id": "main-clip", "playback_rate": 1.0},
            }],
        }
        planner_prompts = []

        def fake_planner(prompt):
            planner_prompts.append(prompt)
            return plan

        with patch.dict(os.environ, {
            "GEMINI_API_KEY": "test-gemini-key",
            "GROQ_API_KEY": "test-groq-key",
        }), patch("dual_ai_controller._gemini_analyze_video",
                  side_effect=DualAIControllerError("temporary Gemini 503")), \
             patch("dual_ai_controller._groq_analyze_video",
                  return_value=groq_analysis) as groq, \
             patch("builtins.print"):
            collaboration = plan_dual_ai_edit(
                "Keep this edit simple.",
                "sample.mp4",
                self.executor,
                planner_provider=fake_planner,
            )

        groq.assert_called_once()
        self.assertEqual(
            collaboration["agents"]["visual_analysis"],
            "Groq test fallback",
        )
        self.assertEqual(len(planner_prompts), 1)
        self.assertIn("VISUAL ANALYSIS", planner_prompts[0])
        self.assertIn("Still frames only; no audio analysis.", planner_prompts[0])


if __name__ == "__main__":
    unittest.main()
