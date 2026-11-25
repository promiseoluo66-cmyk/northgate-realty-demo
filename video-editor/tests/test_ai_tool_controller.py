"""Offline tests for AI planning, registered project tools and transactions."""

import unittest

from ai_edit_controller import (
    AIEditControllerError,
    run_ai_edit,
    validate_tool_plan,
)
from project_tool_executor import (
    ProjectRevisionConflict,
    ProjectToolExecutionError,
    ProjectToolExecutor,
    ToolConfirmationRequired,
)


def make_project():
    return {
        "schema_version": 1,
        "id": "ai-tools-test",
        "name": "AI tool executor test",
        "revision": 1,
        "timeline_timebase": "microseconds",
        "video_profile": {
            "width": 320,
            "height": 240,
            "frame_rate": {"numerator": 25, "denominator": 1},
        },
        "assets": [
            {
                "id": "video-asset", "media_type": "video",
                "file_name": "video.mp4", "storage_key": "video.mp4",
                "size_bytes": 1000, "duration_us": 5_000_000,
            },
            {
                "id": "audio-asset", "media_type": "audio",
                "file_name": "audio.wav", "storage_key": "audio.wav",
                "size_bytes": 500, "duration_us": 5_000_000,
            },
            {
                "id": "image-asset", "media_type": "image",
                "file_name": "still.png", "storage_key": "still.png",
                "size_bytes": 300, "duration_us": 2_000_000,
            },
        ],
        "tracks": [
            {
                "id": "main-video", "type": "video", "name": "Main video",
                "order": 0,
                "clips": [{
                    "id": "clip-a", "kind": "video", "media_id": "video-asset",
                    "start_us": 0, "duration_us": 3_000_000,
                    "source_in_us": 0, "source_out_us": 3_000_000,
                    "playback_rate": 1.0, "effects": [], "keyframes": [],
                }],
            },
            {
                "id": "overlays", "type": "overlay", "name": "Overlays",
                "order": 1, "clips": [],
            },
            {
                "id": "titles", "type": "text", "name": "Titles",
                "order": 2, "clips": [],
            },
            {
                "id": "music", "type": "audio", "name": "Music",
                "order": 3,
                "clips": [{
                    "id": "music-clip", "kind": "audio", "media_id": "audio-asset",
                    "start_us": 0, "duration_us": 3_000_000,
                    "source_in_us": 0, "source_out_us": 3_000_000,
                    "playback_rate": 1.0, "effects": [], "keyframes": [],
                }],
            },
        ],
        "transitions": [],
    }


class ProjectToolExecutorTests(unittest.TestCase):
    def setUp(self):
        self.executor = ProjectToolExecutor(make_project())

    def test_ai_plan_can_inspect_and_apply_keyframes(self):
        plan = {
            "summary": "Add a smooth zoom to the first video clip.",
            "tool_calls": [
                {"name": "project.inspect", "arguments": {}},
                {
                    "name": "animation.set_keyframe",
                    "arguments": {
                        "clip_id": "clip-a",
                        "property": "scale_x",
                        "time_us": 1_000_000,
                        "value": 1.4,
                        "interpolation": "ease_in_out",
                    },
                },
            ],
        }
        prompts = []

        def provider(prompt):
            prompts.append(prompt)
            return plan

        result = run_ai_edit(
            "Add a smooth zoom to the first clip.",
            self.executor,
            expected_revision=1,
            provider=provider,
        )
        self.assertTrue(result["ok"])
        self.assertEqual(result["status"], "applied")
        self.assertEqual(self.executor.revision, 2)
        self.assertIn("REGISTERED TOOLS", prompts[0])
        self.assertIn("clip-a", prompts[0])
        self.assertEqual(
            self.executor.get_project()["tracks"][0]["clips"][0]["keyframes"][0]["value"],
            1.4,
        )

    def test_ai_plan_is_rejected_if_model_invents_a_tool(self):
        with self.assertRaises(AIEditControllerError):
            validate_tool_plan({
                "summary": "Run a shell command.",
                "tool_calls": [{
                    "name": "system.run_shell",
                    "arguments": {"command": "anything"},
                }],
            })

    def test_ai_plan_is_rejected_if_arguments_do_not_match_schema(self):
        with self.assertRaisesRegex(AIEditControllerError, "was rejected"):
            validate_tool_plan({
                "summary": "Set opacity.",
                "tool_calls": [{
                    "name": "clip.set_transform",
                    "arguments": {"clip_id": "clip-a", "opacity": 8},
                }],
            })

    def test_batch_is_atomic_on_failure(self):
        original = self.executor.get_project()
        with self.assertRaises(ProjectToolExecutionError):
            self.executor.execute_batch([
                {
                    "name": "clip.set_transform",
                    "arguments": {"clip_id": "clip-a", "scale_x": 2},
                },
                {
                    "name": "animation.set_keyframe",
                    "arguments": {
                        "clip_id": "clip-a", "property": "scale_x",
                        "time_us": 9_000_000, "value": 1.5,
                    },
                },
            ], expected_revision=1)
        self.assertEqual(self.executor.revision, 1)
        self.assertEqual(self.executor.get_project(), original)

    def test_undo_redo_history_survives_executor_recreation(self):
        self.executor.execute(
            "clip.set_transform",
            {"clip_id": "clip-a", "opacity": 0.4},
            expected_revision=1,
        )
        saved_project = self.executor.get_project()
        saved_history = self.executor.get_history_state()
        reopened = ProjectToolExecutor(saved_project, history_state=saved_history)

        reopened.execute("history.undo", {}, expected_revision=2)
        self.assertNotIn("transform", reopened.get_project()["tracks"][0]["clips"][0])

        reopened.execute("history.redo", {}, expected_revision=3)
        self.assertEqual(
            reopened.get_project()["tracks"][0]["clips"][0]["transform"]["opacity"],
            0.4,
        )

    def test_stale_revision_is_rejected(self):
        self.executor.execute(
            "clip.set_transform", {"clip_id": "clip-a", "opacity": 0.5},
            expected_revision=1,
        )
        with self.assertRaises(ProjectRevisionConflict):
            self.executor.execute(
                "clip.set_transform", {"clip_id": "clip-a", "opacity": 1},
                expected_revision=1,
            )

    def test_destructive_call_waits_for_confirmation_without_mutating(self):
        original = self.executor.get_project()
        plan = {
            "summary": "Remove the first clip.",
            "tool_calls": [{
                "name": "timeline.delete_clip",
                "arguments": {"clip_id": "clip-a"},
            }],
        }
        result = run_ai_edit(
            "Delete the first clip.",
            self.executor,
            expected_revision=1,
            preferred_plan=plan,
        )
        self.assertEqual(result["status"], "awaiting_confirmation")
        self.assertEqual(result["required_confirmations"], ["timeline.delete_clip"])
        self.assertEqual(self.executor.get_project(), original)

        applied = self.executor.execute(
            "timeline.delete_clip", {"clip_id": "clip-a"},
            expected_revision=1, confirmed=True,
        )
        self.assertTrue(applied["changed"])
        self.assertEqual(self.executor.revision, 2)
        self.assertEqual(self.executor.inspect()["clip_count"], 1)

    def test_undo_and_redo_restore_committed_project_snapshots(self):
        self.executor.execute(
            "clip.set_transform", {"clip_id": "clip-a", "opacity": 0.4},
            expected_revision=1,
        )
        self.executor.execute("history.undo", {}, expected_revision=2)
        self.assertEqual(self.executor.revision, 3)
        self.assertNotIn("transform", self.executor.get_project()["tracks"][0]["clips"][0])

        self.executor.execute("history.redo", {}, expected_revision=3)
        self.assertEqual(self.executor.revision, 4)
        self.assertEqual(
            self.executor.get_project()["tracks"][0]["clips"][0]["transform"]["opacity"],
            0.4,
        )

    def test_add_text_and_still_image_clips(self):
        text_result = self.executor.execute(
            "timeline.add_text_clip",
            {
                "track_id": "titles", "content": "Hello world",
                "start_us": 1_000_000, "duration_us": 2_000_000,
                "text_style": {"size": 56, "fgcolour": "#FFFF00"},
            },
            expected_revision=1,
        )
        text_id = text_result["results"][0]["result"]["clip_id"]
        image_result = self.executor.execute(
            "timeline.add_clip",
            {
                "track_id": "overlays", "kind": "image",
                "media_id": "image-asset", "start_us": 1_000_000,
                "duration_us": 1_000_000,
            },
            expected_revision=2,
        )
        image_id = image_result["results"][0]["result"]["clip_id"]
        project = self.executor.get_project()
        text_clip = next(c for t in project["tracks"] for c in t["clips"] if c["id"] == text_id)
        image_clip = next(c for t in project["tracks"] for c in t["clips"] if c["id"] == image_id)
        self.assertEqual(text_clip["text"]["content"], "Hello world")
        self.assertEqual(text_clip["text"]["size"], 56)
        self.assertEqual(image_clip["kind"], "image")
        self.assertEqual(self.executor.revision, 3)

    def test_constant_speed_visual_effects_and_audio_controls(self):
        self.executor.execute(
            "clip.set_speed",
            {"clip_id": "clip-a", "playback_rate": 1.5},
            expected_revision=1,
        )
        self.executor.execute(
            "effect.add",
            {"clip_id": "clip-a", "effect_type": "contrast",
             "parameters": {"value": 1.5}},
            expected_revision=2,
        )
        self.executor.execute(
            "audio.set_gain", {"clip_id": "music-clip", "gain_db": -6},
            expected_revision=3,
        )
        self.executor.execute(
            "audio.set_fade",
            {"clip_id": "music-clip", "fade_in_us": 250_000, "fade_out_us": 300_000},
            expected_revision=4,
        )
        project = self.executor.get_project()
        video = project["tracks"][0]["clips"][0]
        audio = project["tracks"][3]["clips"][0]
        self.assertEqual(video["playback_rate"], 1.5)
        self.assertEqual(video["effects"][0]["parameters"]["value"], 1.5)
        self.assertEqual({x["type"] for x in audio["effects"]}, {"gain", "fade"})

    def test_speed_curve_and_transform_conflict_is_rejected(self):
        with self.assertRaisesRegex(ProjectToolExecutionError, "cannot yet be combined"):
            self.executor.execute_batch([
                {
                    "name": "animation.set_keyframe",
                    "arguments": {
                        "clip_id": "clip-a", "property": "scale_x",
                        "time_us": 0, "value": 1.0,
                    },
                },
                {
                    "name": "animation.set_keyframe",
                    "arguments": {
                        "clip_id": "clip-a", "property": "playback_rate",
                        "time_us": 0, "value": 1.0,
                    },
                },
            ], expected_revision=1)
        self.assertEqual(self.executor.revision, 1)

    def test_split_preserves_source_ranges(self):
        result = self.executor.execute(
            "timeline.split_clip",
            {"clip_id": "clip-a", "at_us": 1_000_000},
            expected_revision=1,
        )
        ids = result["results"][0]["result"]
        project = self.executor.get_project()
        clips = {clip["id"]: clip for clip in project["tracks"][0]["clips"]}
        left, right = clips[ids["left_clip_id"]], clips[ids["right_clip_id"]]
        self.assertEqual(left["duration_us"], 1_000_000)
        self.assertEqual(right["start_us"], 1_000_000)
        self.assertEqual(left["source_out_us"], right["source_in_us"])
        self.assertEqual(right["source_out_us"], 3_000_000)

    def test_transition_requires_adjacent_overlapping_clips(self):
        project = make_project()
        first = project["tracks"][0]["clips"][0]
        first["duration_us"] = 2_000_000
        first["source_out_us"] = 2_000_000
        project["tracks"][0]["clips"].append({
            "id": "clip-b", "kind": "video", "media_id": "video-asset",
            "start_us": 1_500_000, "duration_us": 2_000_000,
            "source_in_us": 0, "source_out_us": 2_000_000,
            "playback_rate": 1.0, "effects": [], "keyframes": [],
        })
        executor = ProjectToolExecutor(project)
        executor.execute(
            "timeline.add_transition",
            {
                "from_clip_id": "clip-a", "to_clip_id": "clip-b",
                "transition_type": "wipe", "duration_us": 500_000,
                "parameters": {"direction": "right_to_left", "softness": 0.2},
            },
            expected_revision=1,
        )
        transition = executor.get_project()["transitions"][0]
        self.assertEqual(transition["type"], "wipe")
        self.assertEqual(transition["parameters"]["direction"], "right_to_left")

    def test_unknown_assets_and_wrong_track_types_are_rejected(self):
        with self.assertRaisesRegex(ProjectToolExecutionError, "does not exist"):
            self.executor.execute(
                "timeline.add_clip",
                {"track_id": "overlays", "kind": "video", "media_id": "missing",
                 "start_us": 0, "duration_us": 1_000_000},
            )
        with self.assertRaisesRegex(ProjectToolExecutionError, "cannot be placed"):
            self.executor.execute(
                "timeline.add_clip",
                {"track_id": "titles", "kind": "video", "media_id": "video-asset",
                 "start_us": 0, "duration_us": 1_000_000},
            )


if __name__ == "__main__":
    unittest.main()
