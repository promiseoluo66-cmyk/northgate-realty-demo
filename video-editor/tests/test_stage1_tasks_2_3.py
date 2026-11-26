"""Acceptance tests for Stage 1 Tasks 2 and 3."""
import unittest

from project_model import ProjectValidationError, validate_project
from project_tool_executor import ProjectToolExecutionError, ProjectToolExecutor
from tool_registry import ToolValidationError, validate_tool_call, get_tool_catalog


def make_project():
    return {
        "schema_version": 1, "id": "stage1-task23", "name": "Task 2 and 3",
        "revision": 1, "timeline_timebase": "microseconds",
        "video_profile": {"width": 720, "height": 1280, "frame_rate": {"numerator": 30, "denominator": 1}},
        "assets": [
            {"id": "video-a", "media_type": "video", "file_name": "a.mp4", "storage_key": "a.mp4", "size_bytes": 100, "duration_us": 12000000},
            {"id": "video-b", "media_type": "video", "file_name": "b.mp4", "storage_key": "b.mp4", "size_bytes": 100, "duration_us": 5000000},
            {"id": "audio-a", "media_type": "audio", "file_name": "a.wav", "storage_key": "a.wav", "size_bytes": 100, "duration_us": 12000000},
        ],
        "tracks": [
            {"id": "v1", "type": "video", "name": "Video", "order": 0, "clips": [
                {"id": "c1", "kind": "video", "media_id": "video-a", "start_us": 0, "duration_us": 2000000, "source_in_us": 0, "source_out_us": 2000000, "playback_rate": 1, "effects": [], "keyframes": []},
                {"id": "c2", "kind": "video", "media_id": "video-a", "start_us": 4000000, "duration_us": 2000000, "source_in_us": 4000000, "source_out_us": 6000000, "playback_rate": 1, "effects": [], "keyframes": []},
            ]},
            {"id": "v2", "type": "overlay", "name": "Overlay", "order": 1, "clips": [
                {"id": "o1", "kind": "video", "media_id": "video-a", "start_us": 5000000, "duration_us": 1000000, "source_in_us": 0, "source_out_us": 1000000, "playback_rate": 1, "effects": [], "keyframes": []}
            ]},
            {"id": "t1", "type": "text", "name": "Titles", "order": 2, "clips": []},
            {"id": "a1", "type": "audio", "name": "Audio", "order": 3, "clips": [
                {"id": "a1c", "kind": "audio", "media_id": "audio-a", "start_us": 5000000, "duration_us": 1000000, "source_in_us": 0, "source_out_us": 1000000, "playback_rate": 1, "effects": [], "keyframes": []}
            ]},
        ],
        "transitions": [],
    }


class Stage1Tasks23Tests(unittest.TestCase):
    def setUp(self):
        self.executor = ProjectToolExecutor(make_project())

    def run_tool(self, name, arguments):
        return self.executor.execute(name, arguments)

    def test_media_preview_metadata_is_validated_and_preserved(self):
        project = make_project()
        project["assets"][0]["thumbnail_data_url"] = "data:image/jpeg;base64,QUJD"
        project["assets"][0]["waveform"] = {"samples": [0, 0.25, 1, 0.5]}
        saved = validate_project(project)
        self.assertEqual(saved["assets"][0]["waveform"]["samples"], [0, 0.25, 1, 0.5])
        project["assets"][0]["waveform"] = {"samples": [1.2]}
        with self.assertRaises(ProjectValidationError):
            validate_project(project)

    def test_cross_track_ripple_insert_shifts_requested_unlocked_tracks(self):
        result = self.run_tool("timeline.ripple_insert_clip", {
            "track_id": "v1", "ripple_track_ids": ["v1", "v2", "a1"],
            "kind": "video", "media_id": "video-b", "start_us": 2000000,
            "duration_us": 1000000, "source_in_us": 0, "source_out_us": 1000000,
        })
        self.assertEqual(result["results"][0]["result"]["ripple_track_ids"], ["v1", "v2", "a1"])
        clips = {clip["id"]: clip for track in self.executor.get_project()["tracks"] for clip in track["clips"]}
        self.assertEqual(clips["c2"]["start_us"], 5000000)
        self.assertEqual(clips["o1"]["start_us"], 6000000)
        self.assertEqual(clips["a1c"]["start_us"], 6000000)

    def test_cross_track_ripple_insert_rejects_locked_track_without_mutation(self):
        self.run_tool("track.set_locked", {"track_id": "v2", "locked": True})
        before = self.executor.get_project()
        with self.assertRaises(ProjectToolExecutionError):
            self.run_tool("timeline.ripple_insert_clip", {
                "track_id": "v1", "ripple_track_ids": ["v1", "v2"],
                "kind": "video", "media_id": "video-b", "start_us": 2000000,
                "duration_us": 1000000,
            })
        self.assertEqual(self.executor.get_project(), before)

    def test_ripple_overwrite_changes_source_and_shifts_later_clips(self):
        result = self.run_tool("timeline.ripple_overwrite_clip", {
            "clip_id": "c1", "media_id": "video-b", "duration_us": 3000000,
        })
        self.assertEqual(result["results"][0]["result"]["old_duration_us"], 2000000)
        clips = {clip["id"]: clip for track in self.executor.get_project()["tracks"] for clip in track["clips"]}
        self.assertEqual(clips["c1"]["media_id"], "video-b")
        self.assertEqual(clips["c1"]["duration_us"], 3000000)
        self.assertEqual(clips["c2"]["start_us"], 5000000)

    def test_ripple_overwrite_rejects_incompatible_source_without_changes(self):
        before = self.executor.get_project()
        with self.assertRaises(ProjectToolExecutionError):
            self.run_tool("timeline.ripple_overwrite_clip", {"clip_id": "c1", "media_id": "audio-a"})
        self.assertEqual(self.executor.get_project(), before)

    def test_linked_group_move_keeps_cross_track_members_in_sync(self):
        self.run_tool("timeline.group_clips", {"clip_ids": ["c1", "o1"], "name": "Linked pair"})
        self.run_tool("timeline.move_clip", {"clip_id": "c1", "start_us": 1000000})
        clips = {clip["id"]: clip for track in self.executor.get_project()["tracks"] for clip in track["clips"]}
        self.assertEqual(clips["c1"]["start_us"], 1000000)
        self.assertEqual(clips["o1"]["start_us"], 6000000)
        self.assertEqual(clips["c1"]["group_id"], clips["o1"]["group_id"])

    def test_linked_group_move_rejects_overlap_atomically(self):
        self.run_tool("timeline.group_clips", {"clip_ids": ["c1", "o1"]})
        before = self.executor.get_project()
        with self.assertRaises(ProjectToolExecutionError):
            self.run_tool("timeline.move_clip", {"clip_id": "c1", "start_us": 3000000})
        self.assertEqual(self.executor.get_project(), before)

    def test_ungrouping_one_member_preserves_remaining_group(self):
        grouped = self.run_tool("timeline.group_clips", {"clip_ids": ["c1", "o1", "a1c"]})
        group_id = grouped["results"][0]["result"]["group_id"]
        self.run_tool("timeline.ungroup_clips", {"clip_ids": ["c1"]})
        clips = {clip["id"]: clip for track in self.executor.get_project()["tracks"] for clip in track["clips"]}
        self.assertNotIn("group_id", clips["c1"])
        self.assertEqual(clips["o1"]["group_id"], group_id)
        self.assertEqual(clips["a1c"]["group_id"], group_id)

    def test_splitting_a_grouped_clip_adds_the_new_segment_to_its_group(self):
        self.run_tool("timeline.group_clips", {"clip_ids": ["c1", "o1"]})
        split = self.run_tool("timeline.split_clip", {"clip_id": "c1", "at_us": 1000000})
        right_id = split["results"][0]["result"]["right_clip_id"]
        project = self.executor.get_project()
        group = project["clip_groups"][0]
        self.assertIn(right_id, group["clip_ids"])
        clips = {clip["id"]: clip for track in project["tracks"] for clip in track["clips"]}
        self.assertEqual(clips[right_id]["group_id"], group["id"])

    def test_deleting_a_grouped_clip_cleans_up_single_member_group(self):
        self.run_tool("timeline.group_clips", {"clip_ids": ["c1", "o1"]})
        self.executor.execute("timeline.delete_clip", {"clip_id": "c1"}, confirmed=True)
        project = self.executor.get_project()
        remaining = next(clip for track in project["tracks"] for clip in track["clips"] if clip["id"] == "o1")
        self.assertNotIn("group_id", remaining)
        self.assertEqual(project.get("clip_groups", []), [])

    def test_markers_can_be_added_moved_and_removed(self):
        added = self.run_tool("timeline.add_marker", {"time_us": 1250000, "label": "Beat"})
        marker_id = added["results"][0]["result"]["id"]
        self.run_tool("timeline.move_marker", {"marker_id": marker_id, "time_us": 2000000, "label": "Drop"})
        self.assertEqual(self.executor.get_project()["markers"][0]["label"], "Drop")
        self.run_tool("timeline.remove_marker", {"marker_id": marker_id})
        self.assertEqual(self.executor.get_project()["markers"], [])

    def test_subtitle_import_creates_phrase_timed_text_clips(self):
        result = self.run_tool("captions.import_subtitles", {
            "track_id": "t1",
            "cues": [
                {"text": "A complete first line", "start_us": 0, "end_us": 1200000},
                {"text": "A second sentence", "start_us": 1500000, "end_us": 2500000},
            ],
        })
        self.assertEqual(result["results"][0]["result"]["cue_count"], 2)
        captions = self.executor.get_project()["tracks"][2]["clips"]
        self.assertEqual(captions[0]["text"]["content"], "A complete first line")
        self.assertEqual(captions[1]["start_us"], 1500000)

    def test_subtitle_import_rejects_overlap_without_mutating(self):
        before = self.executor.get_project()
        with self.assertRaises(ProjectToolExecutionError):
            self.run_tool("captions.import_subtitles", {
                "track_id": "t1",
                "cues": [
                    {"text": "one", "start_us": 0, "end_us": 2000000},
                    {"text": "two", "start_us": 1000000, "end_us": 3000000},
                ],
            })
        self.assertEqual(self.executor.get_project(), before)

    def test_model_rejects_orphaned_groups_and_bad_markers(self):
        project = make_project()
        project["tracks"][0]["clips"][0]["group_id"] = "missing-group"
        with self.assertRaises(ProjectValidationError):
            validate_project(project)
        project = make_project()
        project["markers"] = [{"id": "marker-a", "time_us": -1, "label": "Bad"}]
        with self.assertRaises(ProjectValidationError):
            validate_project(project)

    def test_new_task_operations_are_registered_and_schema_checked(self):
        names = {tool["name"] for tool in get_tool_catalog()}
        expected = {
            "captions.import_subtitles", "timeline.ripple_overwrite_clip",
            "timeline.group_clips", "timeline.ungroup_clips",
            "timeline.add_marker", "timeline.move_marker", "timeline.remove_marker",
        }
        self.assertTrue(expected.issubset(names))
        validate_tool_call("timeline.group_clips", {"clip_ids": ["c1", "o1"]})
        with self.assertRaises(ToolValidationError):
            validate_tool_call("timeline.group_clips", {"clip_ids": ["c1"]})


if __name__ == "__main__":
    unittest.main()
