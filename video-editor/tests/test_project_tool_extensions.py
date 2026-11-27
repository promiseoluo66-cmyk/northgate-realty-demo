"""Regression tests for the first editor-tool expansion batch."""

import unittest

from project_model import ProjectValidationError
from project_tool_executor import (
    ProjectRevisionConflict,
    ProjectToolExecutionError,
    ProjectToolExecutor,
    ToolConfirmationRequired,
)
from tool_registry import ToolValidationError, get_tool_catalog, validate_tool_call


def make_project():
    return {
        "schema_version": 1,
        "id": "tool-expansion-test",
        "name": "Tool expansion test",
        "revision": 1,
        "timeline_timebase": "microseconds",
        "video_profile": {
            "width": 720,
            "height": 1280,
            "frame_rate": {"numerator": 30, "denominator": 1},
        },
        "assets": [{
            "id": "video-asset",
            "media_type": "video",
            "file_name": "source.mp4",
            "storage_key": "private/source.mp4",
            "size_bytes": 1024,
            "duration_us": 8_000_000,
        }],
        "tracks": [
            {
                "id": "main-video",
                "type": "video",
                "name": "Main video",
                "order": 0,
                "locked": False,
                "clips": [{
                    "id": "main-clip",
                    "kind": "video",
                    "media_id": "video-asset",
                    "start_us": 0,
                    "duration_us": 2_000_000,
                    "source_in_us": 0,
                    "source_out_us": 2_000_000,
                    "playback_rate": 1.0,
                    "effects": [{
                        "id": "brightness-1",
                        "type": "brightness",
                        "enabled": True,
                        "parameters": {"level": 1.2},
                    }],
                    "keyframes": [],
                }],
            },
            {
                "id": "overlay-track",
                "type": "overlay",
                "name": "Overlays",
                "order": 1,
                "locked": False,
                "clips": [],
            },
            {
                "id": "title-track",
                "type": "text",
                "name": "Titles",
                "order": 2,
                "locked": False,
                "clips": [{
                    "id": "title-clip",
                    "kind": "text",
                    "start_us": 500_000,
                    "duration_us": 1_000_000,
                    "text": {
                        "content": "Original title",
                        "family": "Sans",
                        "size": 48,
                        "fgcolour": "#FFFFFF",
                        "olcolour": "#000000",
                        "outline": 1,
                        "halign": "center",
                        "valign": "middle",
                        "x_percent": 5,
                        "y_percent": 68,
                        "width_percent": 90,
                        "height_percent": 25,
                    },
                    "effects": [],
                    "keyframes": [],
                }],
            },
        ],
        "transitions": [],
    }


class EditorToolExpansionTests(unittest.TestCase):
    def setUp(self):
        self.executor = ProjectToolExecutor(make_project())

    def run_tool(self, name, arguments, confirmed_tools=None):
        return self.executor.execute_batch(
            [{"name": name, "arguments": arguments}],
            confirmed_tools=confirmed_tools,
        )

    def add_audio_track(self):
        project = self.executor.get_project()
        project["tracks"].append({
            "id": "music-track",
            "type": "audio",
            "name": "Music",
            "order": 3,
            "enabled": True,
            "locked": False,
            "muted": False,
            "solo": False,
            "visible": True,
            "clips": [],
        })
        self.executor = ProjectToolExecutor(project)

    def test_new_tools_are_exposed_to_the_ai_catalogue(self):
        names = {item["name"] for item in get_tool_catalog()}
        self.assertTrue({
            "timeline.duplicate_clip",
            "timeline.ripple_delete_clip",
            "track.rename",
            "track.reorder",
            "track.set_locked",
            "effect.set_enabled",
            "text.update_clip",
        }.issubset(names))

    def test_animation_keyframes_can_be_reset_for_property_or_entire_clip(self):
        for property_name in ("opacity", "scale_x"):
            self.run_tool("animation.set_keyframe", {
                "clip_id": "main-clip", "property": property_name,
                "time_us": 250_000, "value": 0.5 if property_name == "opacity" else 1.2,
            })
        self.run_tool("animation.clear_keyframes", {
            "clip_id": "main-clip", "property": "opacity",
        })
        clip = self.executor.get_project()["tracks"][0]["clips"][0]
        self.assertEqual([item["property"] for item in clip["keyframes"]], ["scale_x"])
        self.run_tool("animation.clear_keyframes", {"clip_id": "main-clip"})
        self.assertEqual(self.executor.get_project()["tracks"][0]["clips"][0]["keyframes"], [])

    def test_animation_keyframe_can_be_removed_by_property_and_clip_time(self):
        self.run_tool("animation.set_keyframe", {
            "clip_id": "main-clip", "property": "opacity",
            "time_us": 500_000, "value": 0.5, "interpolation": "ease_in",
        })
        self.run_tool("animation.remove_keyframe", {
            "clip_id": "main-clip", "property": "opacity",
            "time_us": 500_000,
        })
        clip = self.executor.get_project()["tracks"][0]["clips"][0]
        self.assertEqual(clip["keyframes"], [])
        with self.assertRaisesRegex(ProjectToolExecutionError, "No keyframe exists"):
            self.run_tool("animation.remove_keyframe", {
                "clip_id": "main-clip", "property": "opacity", "time_us": 500_000,
            })

    def test_clip_framing_sets_alignment_and_can_be_reset(self):
        result = self.run_tool("clip.set_framing", {
            "clip_id": "main-clip",
            "mode": "fill",
            "horizontal_alignment": "right",
        })
        framing = self.executor.get_project()["tracks"][0]["clips"][0]["framing"]
        self.assertEqual(framing, {
            "mode": "fill",
            "horizontal_alignment": "right",
            "vertical_alignment": "middle",
        })
        self.assertEqual(result["results"][0]["result"]["framing"], framing)

        reset = self.run_tool("clip.set_framing", {
            "clip_id": "main-clip", "mode": "none",
        })
        self.assertEqual(reset["results"][0]["result"]["mode"], "none")
        self.assertNotIn("framing", self.executor.get_project()["tracks"][0]["clips"][0])

    def test_clip_framing_rejects_audio_clips(self):
        project = self.executor.get_project()
        project["tracks"].append({
            "id": "audio-track",
            "type": "audio",
            "name": "Audio",
            "order": 3,
            "locked": False,
            "clips": [{
                "id": "audio-clip",
                "kind": "audio",
                "media_id": "audio-asset",
                "start_us": 0,
                "duration_us": 1_000_000,
                "source_in_us": 0,
                "source_out_us": 1_000_000,
                "playback_rate": 1.0,
                "effects": [],
                "keyframes": [],
            }],
        })
        project["assets"].append({
            "id": "audio-asset",
            "media_type": "audio",
            "file_name": "sound.wav",
            "storage_key": "private/sound.wav",
            "size_bytes": 128,
            "duration_us": 1_000_000,
        })
        self.executor = ProjectToolExecutor(project)
        with self.assertRaisesRegex(ProjectToolExecutionError, "video/image"):
            self.run_tool("clip.set_framing", {
                "clip_id": "audio-clip", "mode": "fit",
            })

    def test_ripple_delete_closes_gap_on_only_the_target_track(self):
        project = self.executor.get_project()
        project["tracks"][0]["clips"].append({
            "id": "later-clip",
            "kind": "video",
            "media_id": "video-asset",
            "start_us": 4_000_000,
            "duration_us": 1_000_000,
            "source_in_us": 4_000_000,
            "source_out_us": 5_000_000,
            "playback_rate": 1.0,
            "effects": [],
            "keyframes": [],
        })
        self.executor = ProjectToolExecutor(project)
        result = self.run_tool(
            "timeline.ripple_delete_clip", {"clip_id": "main-clip"},
            confirmed_tools={"timeline.ripple_delete_clip"},
        )
        payload = result["results"][0]["result"]
        self.assertEqual(payload["removed_duration_us"], 2_000_000)
        self.assertEqual(payload["shifted_clip_ids"], ["later-clip"])
        clips = self.executor.get_project()["tracks"][0]["clips"]
        self.assertEqual(len(clips), 1)
        self.assertEqual(clips[0]["start_us"], 2_000_000)
        # A clip on another track is not shifted.
        self.assertEqual(self.executor.get_project()["tracks"][2]["clips"][0]["start_us"], 500_000)

    def test_ripple_delete_rejects_overlapping_clips_without_mutation(self):
        project = self.executor.get_project()
        overlapping = {
            "id": "overlap-clip",
            "kind": "video",
            "media_id": "video-asset",
            "start_us": 1_000_000,
            "duration_us": 1_000_000,
            "source_in_us": 1_000_000,
            "source_out_us": 2_000_000,
            "playback_rate": 1.0,
            "effects": [],
            "keyframes": [],
        }
        project["tracks"][0]["clips"].append(overlapping)
        self.executor = ProjectToolExecutor(project)
        before = self.executor.get_project()
        with self.assertRaisesRegex(ProjectToolExecutionError, "non-overlapping"):
            self.run_tool(
                "timeline.ripple_delete_clip", {"clip_id": "main-clip"},
                confirmed_tools={"timeline.ripple_delete_clip"},
            )
        self.assertEqual(self.executor.get_project(), before)

    def test_duplicate_clip_copies_edit_data_with_a_fresh_id(self):
        result = self.run_tool("timeline.duplicate_clip", {
            "clip_id": "main-clip",
            "start_us": 2_000_000,
        })
        clips = self.executor.get_project()["tracks"][0]["clips"]
        self.assertEqual(len(clips), 2)
        duplicate = clips[1]
        self.assertEqual(result["results"][0]["result"]["new_clip_id"], duplicate["id"])
        self.assertNotEqual(duplicate["id"], "main-clip")
        self.assertEqual(duplicate["effects"], clips[0]["effects"])
        self.assertEqual(duplicate["media_id"], "video-asset")
        self.assertEqual(duplicate["start_us"], 2_000_000)

    def test_duplicate_clip_can_move_to_a_compatible_overlay_track(self):
        result = self.run_tool("timeline.duplicate_clip", {
            "clip_id": "main-clip",
            "start_us": 3_000_000,
            "track_id": "overlay-track",
        })
        self.assertEqual(result["results"][0]["result"]["track_id"], "overlay-track")
        self.assertEqual(len(self.executor.get_project()["tracks"][1]["clips"]), 1)

    def test_duplicate_clip_rejects_overlap_and_wrong_track_type(self):
        with self.assertRaisesRegex(ProjectToolExecutionError, "overlap"):
            self.run_tool("timeline.duplicate_clip", {
                "clip_id": "main-clip", "start_us": 1_000_000,
            })
        with self.assertRaisesRegex(ProjectToolExecutionError, "cannot be placed"):
            self.run_tool("timeline.duplicate_clip", {
                "clip_id": "main-clip", "start_us": 3_000_000,
                "track_id": "title-track",
            })

    def test_media_asset_folder_and_tags_are_persisted_and_searchable(self):
        result = self.executor.execute("media.organize_asset", {
            "media_id": "video-asset",
            "folder": "B-roll",
            "tags": ["wildlife", "forest"],
        })
        asset = result["project"]["assets"][0]
        self.assertEqual(asset["folder"], "B-roll")
        self.assertEqual(asset["tags"], ["wildlife", "forest"])
        listed = self.executor.execute("media.list", {"folder": "B-roll"})
        self.assertEqual(listed["results"][0]["result"][0]["id"], "video-asset")
        self.assertEqual(listed["results"][0]["result"][0]["tags"], ["wildlife", "forest"])
        missing = self.executor.execute("media.list", {"folder": "Unsorted"})
        self.assertEqual(missing["results"][0]["result"], [])

    def test_manual_crop_can_be_applied_and_reset_on_video_clip(self):
        result = self.executor.execute("clip.set_crop", {
            "clip_id": "main-clip",
            "mode": "custom",
            "x": 0.25,
            "y": 0.1,
            "width": 0.5,
            "height": 0.8,
        })
        crop = result["project"]["tracks"][0]["clips"][0]["crop"]
        self.assertEqual(crop, {
            "x": 0.25, "y": 0.1, "width": 0.5, "height": 0.8,
        })
        self.executor.execute("clip.set_crop", {
            "clip_id": "main-clip", "mode": "none",
        })
        self.assertNotIn("crop", self.executor.get_project()["tracks"][0]["clips"][0])

    def test_manual_crop_rejects_out_of_frame_and_automatic_framing(self):
        with self.assertRaisesRegex(ProjectToolExecutionError, "stay inside"):
            self.executor.execute("clip.set_crop", {
                "clip_id": "main-clip", "mode": "custom",
                "x": 0.75, "y": 0, "width": 0.5, "height": 1,
            })
        self.executor.execute("clip.set_framing", {
            "clip_id": "main-clip", "mode": "fill",
        })
        with self.assertRaisesRegex(ProjectToolExecutionError, "Clear automatic framing"):
            self.executor.execute("clip.set_crop", {
                "clip_id": "main-clip", "mode": "custom",
                "x": 0, "y": 0, "width": 0.5, "height": 0.5,
            })

    def test_custom_rotation_pivot_is_saved_and_can_be_reset_to_center(self):
        result = self.executor.execute("clip.set_transform", {
            "clip_id": "main-clip",
            "anchor_x": 0.2,
            "anchor_y": 0.8,
        })
        transform = result["project"]["tracks"][0]["clips"][0]["transform"]
        self.assertEqual(transform["anchor_x"], 0.2)
        self.assertEqual(transform["anchor_y"], 0.8)
        self.executor.execute("clip.set_transform", {
            "clip_id": "main-clip",
            "anchor_x": 0.5,
            "anchor_y": 0.5,
        })
        transform = self.executor.get_project()["tracks"][0]["clips"][0]["transform"]
        self.assertEqual(transform["anchor_x"], 0.5)
        self.assertEqual(transform["anchor_y"], 0.5)

    def test_transform_horizontal_and_vertical_flip_flags_are_persisted(self):
        result = self.executor.execute("clip.set_transform", {
            "clip_id": "main-clip",
            "flip_horizontal": True,
            "flip_vertical": True,
        })
        transform = result["project"]["tracks"][0]["clips"][0]["transform"]
        self.assertTrue(transform["flip_horizontal"])
        self.assertTrue(transform["flip_vertical"])
        self.executor.execute("clip.set_transform", {
            "clip_id": "main-clip",
            "flip_horizontal": False,
        })
        transform = self.executor.get_project()["tracks"][0]["clips"][0]["transform"]
        self.assertFalse(transform["flip_horizontal"])
        self.assertTrue(transform["flip_vertical"])

    def test_ripple_insert_shifts_only_later_clips_on_the_selected_track(self):
        project = self.executor.get_project()
        project["tracks"][0]["clips"].append({
            "id": "later-video",
            "kind": "video",
            "media_id": "video-asset",
            "start_us": 4_000_000,
            "duration_us": 1_000_000,
            "source_in_us": 4_000_000,
            "source_out_us": 5_000_000,
            "playback_rate": 1.0,
            "effects": [],
            "keyframes": [],
        })
        self.executor = ProjectToolExecutor(project)
        result = self.executor.execute("timeline.ripple_insert_clip", {
            "track_id": "main-video",
            "kind": "video",
            "media_id": "video-asset",
            "start_us": 0,
            "duration_us": 1_000_000,
            "source_in_us": 0,
            "source_out_us": 1_000_000,
        })
        payload = result["results"][0]["result"]
        self.assertEqual(payload["inserted_start_us"], 0)
        self.assertEqual(payload["inserted_duration_us"], 1_000_000)
        self.assertEqual(set(payload["shifted_clip_ids"]), {"main-clip", "later-video"})
        tracks = self.executor.get_project()["tracks"]
        main = tracks[0]
        self.assertEqual(next(c for c in main["clips"] if c["id"] == "main-clip")["start_us"], 1_000_000)
        self.assertEqual(next(c for c in main["clips"] if c["id"] == "later-video")["start_us"], 5_000_000)
        inserted = next(c for c in main["clips"] if c["id"] == payload["clip_id"])
        self.assertEqual(inserted["start_us"], 0)
        self.assertEqual(tracks[2]["clips"][0]["start_us"], 500_000)

    def test_ripple_insert_rejects_cutting_through_clip_or_locked_track_without_mutation(self):
        before = self.executor.get_project()
        with self.assertRaisesRegex(ProjectToolExecutionError, "cannot split through an existing clip"):
            self.executor.execute("timeline.ripple_insert_clip", {
                "track_id": "main-video",
                "kind": "video",
                "media_id": "video-asset",
                "start_us": 1_000_000,
                "duration_us": 1_000_000,
            })
        self.assertEqual(self.executor.get_project(), before)
        self.executor.execute("track.set_locked", {
            "track_id": "main-video", "locked": True,
        })
        before_locked = self.executor.get_project()
        with self.assertRaisesRegex(ProjectToolExecutionError, "locked"):
            self.executor.execute("timeline.ripple_insert_clip", {
                "track_id": "main-video",
                "kind": "video",
                "media_id": "video-asset",
                "start_us": 0,
                "duration_us": 1_000_000,
            })
        self.assertEqual(self.executor.get_project(), before_locked)

    def test_slip_clip_shifts_source_window_without_moving_timeline_clip(self):
        result = self.executor.execute("timeline.slip_clip", {
            "clip_id": "main-clip", "delta_us": 500_000,
        })
        clip = result["project"]["tracks"][0]["clips"][0]
        self.assertEqual(clip["source_in_us"], 500_000)
        self.assertEqual(clip["source_out_us"], 2_500_000)
        self.assertEqual(clip["start_us"], 0)
        self.assertEqual(clip["duration_us"], 2_000_000)
        self.assertEqual(result["results"][0]["result"]["preserved_duration_us"], 2_000_000)

    def test_slip_clip_rejects_source_underflow_overflow_and_zero_offset(self):
        with self.assertRaisesRegex(ProjectToolExecutionError, "before the beginning"):
            self.executor.execute("timeline.slip_clip", {
                "clip_id": "main-clip", "delta_us": -1,
            })
        with self.assertRaisesRegex(ProjectToolExecutionError, "beyond the media asset duration"):
            self.executor.execute("timeline.slip_clip", {
                "clip_id": "main-clip", "delta_us": 7_000_001,
            })
        with self.assertRaisesRegex(ProjectToolExecutionError, "non-zero"):
            self.executor.execute("timeline.slip_clip", {
                "clip_id": "main-clip", "delta_us": 0,
            })

    def test_slip_clip_rejects_locked_track_and_animated_speed_curve(self):
        self.run_tool("track.set_locked", {"track_id": "main-video", "locked": True})
        with self.assertRaisesRegex(ProjectToolExecutionError, "locked"):
            self.executor.execute("timeline.slip_clip", {
                "clip_id": "main-clip", "delta_us": 100_000,
            })
        project = self.executor.get_project()
        project["tracks"][0]["locked"] = False
        project["tracks"][0]["clips"][0]["keyframes"] = [{
            "property": "playback_rate", "time_us": 0, "value": 1.0,
        }, {
            "property": "playback_rate", "time_us": 1_000_000, "value": 1.5,
        }]
        executor = ProjectToolExecutor(project)
        with self.assertRaisesRegex(ProjectToolExecutionError, "animated speed curves"):
            executor.execute("timeline.slip_clip", {
                "clip_id": "main-clip", "delta_us": 100_000,
            })

    def test_clip_source_replace_preserves_timeline_and_clip_properties(self):
        project = self.executor.get_project()
        project["assets"].append({
            "id": "replacement-video",
            "media_type": "video",
            "file_name": "replacement.mp4",
            "storage_key": "private/replacement.mp4",
            "size_bytes": 2048,
            "duration_us": 8_000_000,
        })
        clip = project["tracks"][0]["clips"][0]
        clip["transform"] = {
            "position": {"x": 12, "y": -8},
            "scale": {"x": 1.2, "y": 0.9},
            "rotation_deg": 15,
            "opacity": 0.8,
            "anchor_x": 0.2,
            "anchor_y": 0.8,
            "flip_horizontal": True,
        }
        clip["crop"] = {"x": 0.1, "y": 0.1, "width": 0.8, "height": 0.8}
        executor = ProjectToolExecutor(project)
        before = executor.get_project()["tracks"][0]["clips"][0]
        result = executor.execute("timeline.replace_clip_media", {
            "clip_id": "main-clip", "media_id": "replacement-video",
        })
        after = result["project"]["tracks"][0]["clips"][0]
        self.assertEqual(after["media_id"], "replacement-video")
        self.assertEqual(after["start_us"], before["start_us"])
        self.assertEqual(after["duration_us"], before["duration_us"])
        self.assertEqual(after["playback_rate"], before["playback_rate"])
        self.assertEqual(after["effects"], before["effects"])
        self.assertEqual(after["transform"], before["transform"])
        self.assertEqual(after["crop"], before["crop"])
        self.assertEqual(after["source_in_us"], 0)
        self.assertEqual(after["source_out_us"], 2_000_000)

    def test_clip_source_replace_rejects_wrong_type_and_too_short_source(self):
        project = self.executor.get_project()
        project["assets"].extend([
            {
                "id": "replacement-audio", "media_type": "audio",
                "file_name": "music.mp3", "storage_key": "private/music.mp3",
                "size_bytes": 100, "duration_us": 8_000_000,
            },
            {
                "id": "replacement-short", "media_type": "video",
                "file_name": "short.mp4", "storage_key": "private/short.mp4",
                "size_bytes": 100, "duration_us": 1_000_000,
            },
        ])
        self.executor = ProjectToolExecutor(project)
        with self.assertRaisesRegex(ProjectToolExecutionError, "requires a video asset"):
            self.executor.execute("timeline.replace_clip_media", {
                "clip_id": "main-clip", "media_id": "replacement-audio",
            })
        with self.assertRaisesRegex(ProjectToolExecutionError, "too short"):
            self.executor.execute("timeline.replace_clip_media", {
                "clip_id": "main-clip", "media_id": "replacement-short",
            })

    def test_clip_source_replace_rejects_animated_speed_curve_until_remapping_is_supported(self):
        project = self.executor.get_project()
        project["assets"].append({
            "id": "replacement-video", "media_type": "video",
            "file_name": "replacement.mp4", "storage_key": "private/replacement.mp4",
            "size_bytes": 2048, "duration_us": 8_000_000,
        })
        clip = project["tracks"][0]["clips"][0]
        clip["keyframes"] = [{
            "property": "playback_rate", "time_us": 0, "value": 1.0,
        }, {
            "property": "playback_rate", "time_us": 1_000_000, "value": 1.5,
        }]
        executor = ProjectToolExecutor(project)
        with self.assertRaisesRegex(ProjectToolExecutionError, "animated speed curve"):
            executor.execute("timeline.replace_clip_media", {
                "clip_id": "main-clip", "media_id": "replacement-video",
            })

    def test_track_visual_visibility_is_independent_from_audio_mute(self):
        result = self.executor.execute("track.set_state", {
            "track_id": "main-video", "visible": False,
        })
        state = result["results"][0]["result"]
        self.assertFalse(state["visible"])
        self.assertFalse(state["muted"])
        self.assertFalse(result["project"]["tracks"][0]["visible"])
        self.executor.execute("track.set_state", {
            "track_id": "main-video", "visible": True,
        })
        self.assertTrue(self.executor.get_project()["tracks"][0]["visible"])

    def test_audio_track_rejects_visual_visibility_setting(self):
        self.add_audio_track()
        with self.assertRaisesRegex(ProjectToolExecutionError, "do not support visual visibility"):
            self.executor.execute("track.set_state", {
                "track_id": "music-track", "visible": False,
            })

    def test_track_solo_state_is_persisted_and_can_be_toggled(self):
        result = self.executor.execute(
            "track.set_state", {"track_id": "main-video", "solo": True}
        )
        self.assertTrue(result["project"]["tracks"][0]["solo"])
        self.assertTrue(result["results"][0]["result"]["solo"])
        self.executor.execute(
            "track.set_state", {"track_id": "main-video", "solo": False}
        )
        self.assertFalse(self.executor.get_project()["tracks"][0]["solo"])

    def test_track_reorder_moves_selected_track_and_normalizes_orders(self):
        self.run_tool("track.reorder", {"track_id": "title-track", "order": 0})
        tracks = sorted(self.executor.get_project()["tracks"], key=lambda item: item["order"])
        self.assertEqual(tracks[0]["id"], "title-track")
        self.assertEqual([item["order"] for item in tracks], list(range(len(tracks))))
        self.assertEqual(tracks[0]["clips"][0]["id"], "title-clip")

    def test_track_rename_and_lock_are_executable(self):
        self.run_tool("track.rename", {
            "track_id": "main-video", "name": "Primary footage",
        })
        self.run_tool("track.set_locked", {
            "track_id": "main-video", "locked": True,
        })
        project = self.executor.get_project()
        track = project["tracks"][0]
        self.assertEqual(track["name"], "Primary footage")
        self.assertTrue(track["locked"])
        with self.assertRaisesRegex(ProjectToolExecutionError, "locked"):
            self.run_tool("clip.set_speed", {
                "clip_id": "main-clip", "playback_rate": 1.25,
            })
        self.run_tool("track.set_locked", {
            "track_id": "main-video", "locked": False,
        })
        self.run_tool("clip.set_speed", {
            "clip_id": "main-clip", "playback_rate": 1.25,
        })
        self.assertEqual(
            self.executor.get_project()["tracks"][0]["clips"][0]["playback_rate"],
            1.25,
        )

    def test_effect_can_be_disabled_and_reenabled_without_deletion(self):
        self.run_tool("effect.set_enabled", {
            "clip_id": "main-clip",
            "effect_id": "brightness-1",
            "enabled": False,
        })
        effect = self.executor.get_project()["tracks"][0]["clips"][0]["effects"][0]
        self.assertFalse(effect["enabled"])
        self.run_tool("effect.set_enabled", {
            "clip_id": "main-clip",
            "effect_id": "brightness-1",
            "enabled": True,
        })
        effect = self.executor.get_project()["tracks"][0]["clips"][0]["effects"][0]
        self.assertTrue(effect["enabled"])

    def test_missing_effect_id_is_rejected(self):
        with self.assertRaisesRegex(ProjectToolExecutionError, "does not exist"):
            self.run_tool("effect.set_enabled", {
                "clip_id": "main-clip", "effect_id": "missing",
                "enabled": False,
            })

    def test_word_timed_captions_create_sequential_renderer_text_clips(self):
        result = self.run_tool("captions.add_word_timed", {
            "track_id": "title-track",
            "words": [
                {"text": "Hello", "start_us": 0, "end_us": 300_000},
                {"text": "world!", "start_us": 300_000, "end_us": 700_000},
            ],
            "text_style": {"size": 56, "fgcolour": "#FFFF00"},
        })
        payload = result["results"][0]["result"]
        self.assertEqual(payload["word_clip_count"], 2)
        self.assertFalse(payload["transcription_performed"])
        clips = self.executor.get_project()["tracks"][2]["clips"]
        created = [item for item in clips if item["id"].startswith("caption-")]
        self.assertEqual(len(created), 2)
        self.assertEqual(created[0]["text"]["content"], "Hello")
        self.assertEqual(created[0]["start_us"], 0)
        self.assertEqual(created[0]["duration_us"], 300_000)
        self.assertEqual(created[1]["text"]["content"], "world!")
        self.assertEqual(created[1]["text"]["size"], 56)
        self.assertEqual(self.executor.revision, 2)

    def test_word_timed_captions_reject_bad_order_and_locked_track(self):
        with self.assertRaisesRegex(ProjectToolExecutionError, "chronological"):
            self.run_tool("captions.add_word_timed", {
                "track_id": "title-track",
                "words": [
                    {"text": "one", "start_us": 0, "end_us": 500_000},
                    {"text": "two", "start_us": 400_000, "end_us": 700_000},
                ],
            })
        self.run_tool("track.set_locked", {"track_id": "title-track", "locked": True})
        with self.assertRaisesRegex(ProjectToolExecutionError, "unlocked text track"):
            self.run_tool("captions.add_word_timed", {
                "track_id": "title-track",
                "words": [{"text": "locked", "start_us": 0, "end_us": 200_000}],
            })

    def test_word_timed_caption_contract_bounds_word_count_and_fields(self):
        with self.assertRaisesRegex(ToolValidationError, "too many items"):
            validate_tool_call("captions.add_word_timed", {
                "track_id": "title-track",
                "words": [
                    {"text": "x", "start_us": index * 2, "end_us": index * 2 + 1}
                    for index in range(501)
                ],
            })
        with self.assertRaisesRegex(ToolValidationError, "unsupported field"):
            validate_tool_call("captions.add_word_timed", {
                "track_id": "title-track",
                "words": [{"text": "x", "start_us": 0, "end_us": 10, "html": "bad"}],
            })

    def test_text_content_and_supported_styling_can_be_updated(self):
        self.run_tool("text.update_clip", {
            "clip_id": "title-clip",
            "content": "Updated title",
            "text_style": {
                "family": "DejaVu Sans",
                "size": 64,
                "fgcolour": "#00FF00",
                "olcolour": "#000000",
                "outline": 2,
                "halign": "left",
                "y_percent": 20,
            },
        })
        text_spec = self.executor.get_project()["tracks"][2]["clips"][0]["text"]
        self.assertEqual(text_spec["content"], "Updated title")
        self.assertEqual(text_spec["size"], 64)
        self.assertEqual(text_spec["fgcolour"], "#00FF00")
        self.assertEqual(text_spec["halign"], "left")
        self.assertEqual(text_spec["y_percent"], 20)

    def test_text_update_rejects_non_text_clips(self):
        with self.assertRaisesRegex(ProjectToolExecutionError, "text/title clip"):
            self.run_tool("text.update_clip", {
                "clip_id": "main-clip", "content": "Not a title",
            })

    def test_text_update_requires_a_real_change_and_known_style_fields(self):
        with self.assertRaisesRegex(ToolValidationError, "must change"):
            validate_tool_call("text.update_clip", {"clip_id": "title-clip"})
        with self.assertRaisesRegex(ToolValidationError, "unsupported field"):
            validate_tool_call("text.update_clip", {
                "clip_id": "title-clip",
                "text_style": {"fake_option": True},
            })
        with self.assertRaisesRegex(ToolValidationError, "above the allowed maximum"):
            validate_tool_call("text.update_clip", {
                "clip_id": "title-clip",
                "text_style": {"size": 1000},
            })



    def _make_real_media_executor(self, directory, include_audio=True):
        from pathlib import Path
        import shutil
        import subprocess
        if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
            self.skipTest("FFmpeg/FFprobe are not installed.")
        root = Path(directory)
        root.mkdir(parents=True, exist_ok=True)
        source = root / "source-real.mp4"
        command = [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-f", "lavfi", "-i", "testsrc=size=160x120:rate=10",
        ]
        if include_audio:
            command += ["-f", "lavfi", "-i", "sine=frequency=440:sample_rate=44100"]
        command += ["-t", "2", "-c:v", "libx264", "-pix_fmt", "yuv420p"]
        if include_audio:
            command += ["-c:a", "aac", "-shortest"]
        else:
            command += ["-an"]
        command.append(str(source))
        subprocess.run(command, check=True, capture_output=True, text=True, timeout=120)
        project = make_project()
        project["assets"][0]["storage_key"] = source.name
        project["assets"][0]["size_bytes"] = source.stat().st_size
        project["assets"][0]["duration_us"] = 2_000_000
        return ProjectToolExecutor(project, asset_root=root), source

    def test_audio_extraction_creates_verified_audio_asset_and_is_undoable(self):
        import json
        import subprocess
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as directory:
            executor, source = self._make_real_media_executor(directory)
            result = executor.execute(
                "media.extract_audio", {"media_id": "video-asset", "format": "m4a"}
            )
            created = result["results"][0]["result"]
            audio = next(item for item in executor.get_project()["assets"] if item["id"] == created["media_id"])
            audio_path = Path(directory) / audio["storage_key"]
            self.assertTrue(audio_path.is_file())
            self.assertGreater(audio_path.stat().st_size, 0)
            probe = subprocess.run(
                ["ffprobe", "-v", "error", "-show_entries", "format=duration:stream=codec_type",
                 "-of", "json", str(audio_path)],
                check=True, capture_output=True, text=True,
            )
            metadata = json.loads(probe.stdout)
            self.assertTrue(any(item["codec_type"] == "audio" for item in metadata["streams"]))
            self.assertGreater(audio["duration_us"], 0)
            executor.execute("history.undo", {})
            self.assertFalse(any(item["id"] == audio["id"] for item in executor.get_project()["assets"]))
            executor.execute("history.redo", {})
            restored = next(item for item in executor.get_project()["assets"] if item["id"] == audio["id"])
            self.assertEqual(restored["storage_key"], audio["storage_key"])
            self.assertTrue(audio_path.is_file())

    def test_audio_extraction_rejects_video_without_audio_and_leaves_project_unchanged(self):
        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            executor, _ = self._make_real_media_executor(directory, include_audio=False)
            before = executor.get_project()
            with self.assertRaisesRegex(ProjectToolExecutionError, "contains no audio stream"):
                executor.execute("media.extract_audio", {"media_id": "video-asset"})
            self.assertEqual(executor.get_project(), before)
            self.assertEqual(executor.revision, 1)

    def test_freeze_frame_creates_real_image_and_hold_clip_with_undo_redo(self):
        import subprocess
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as directory:
            executor, _ = self._make_real_media_executor(directory)
            result = executor.execute("timeline.create_freeze_frame", {
                "media_id": "video-asset", "track_id": "overlay-track",
                "timestamp_us": 500_000, "start_us": 1_000_000,
                "duration_us": 3_000_000,
            })
            created = result["results"][0]["result"]
            project = executor.get_project()
            image_asset = next(item for item in project["assets"] if item["id"] == created["media_id"])
            image_path = Path(directory) / image_asset["storage_key"]
            self.assertTrue(image_path.is_file())
            self.assertGreater(image_path.stat().st_size, 0)
            image_probe = subprocess.run(
                ["ffprobe", "-v", "error", "-select_streams", "v:0",
                 "-show_entries", "stream=width,height", "-of", "json", str(image_path)],
                check=True, capture_output=True, text=True,
            )
            image_stream = __import__("json").loads(image_probe.stdout)["streams"][0]
            self.assertEqual((image_stream["width"], image_stream["height"]), (160, 120))
            clip = next(item for item in project["tracks"][1]["clips"] if item["id"] == created["clip_id"])
            self.assertEqual(clip["duration_us"], 3_000_000)
            self.assertEqual(clip["kind"], "image")
            executor.execute("history.undo", {})
            self.assertFalse(any(item["id"] == image_asset["id"] for item in executor.get_project()["assets"]))
            executor.execute("history.redo", {})
            self.assertTrue(any(item["id"] == image_asset["id"] for item in executor.get_project()["assets"]))
            self.assertTrue(image_path.is_file())

    def test_freeze_frame_rejects_out_of_range_timestamp_without_mutation(self):
        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            executor, _ = self._make_real_media_executor(directory)
            before = executor.get_project()
            with self.assertRaisesRegex(ProjectToolExecutionError, "inside the source video duration"):
                executor.execute("timeline.create_freeze_frame", {
                    "media_id": "video-asset", "track_id": "overlay-track",
                    "timestamp_us": 2_000_000, "start_us": 0, "duration_us": 1_000_000,
                })
            self.assertEqual(executor.get_project(), before)
            self.assertEqual(executor.revision, 1)

    def test_generated_asset_release_id_is_attached_to_current_project_and_redo_history(self):
        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            executor, _ = self._make_real_media_executor(directory)
            result = executor.execute("media.extract_audio", {"media_id": "video-asset"})
            media_id = result["results"][0]["result"]["media_id"]
            executor.set_persisted_asset_id(media_id, 987654)
            asset = next(item for item in executor.get_project()["assets"] if item["id"] == media_id)
            self.assertEqual(asset["release_asset_id"], 987654)
            executor.execute("history.undo", {})
            executor.execute("history.redo", {})
            restored = next(item for item in executor.get_project()["assets"] if item["id"] == media_id)
            self.assertEqual(restored["release_asset_id"], 987654)

    def test_audio_extraction_ffmpeg_partial_output_is_removed_on_failure(self):
        import json
        import subprocess
        import tempfile
        from pathlib import Path
        from types import SimpleNamespace
        from unittest.mock import patch

        with tempfile.TemporaryDirectory() as directory:
            executor, _ = self._make_real_media_executor(directory)
            before = executor.get_project()
            partial_paths = []

            def fake_run(command, **kwargs):
                if command[0] == "ffprobe":
                    return SimpleNamespace(stdout=json.dumps({
                        "format": {"duration": "2.0"},
                        "streams": [{"codec_type": "audio"}],
                    }), stderr="")
                if command[0] == "ffmpeg":
                    partial = Path(command[-1])
                    partial.write_bytes(b"partial-audio")
                    partial_paths.append(partial)
                    raise subprocess.CalledProcessError(
                        1, command, stderr="simulated FFmpeg failure"
                    )
                raise AssertionError("Unexpected process: " + command[0])

            with patch("project_tool_executor.subprocess.run", side_effect=fake_run):
                with self.assertRaisesRegex(ProjectToolExecutionError, "Audio extraction failed"):
                    executor.execute("media.extract_audio", {"media_id": "video-asset"})
            self.assertEqual(executor.get_project(), before)
            self.assertEqual(executor.revision, 1)
            self.assertEqual(len(partial_paths), 1)
            self.assertFalse(partial_paths[0].exists())

    def test_audio_extraction_does_not_overwrite_existing_generated_filename(self):
        import tempfile
        from pathlib import Path
        from unittest.mock import patch

        with tempfile.TemporaryDirectory() as directory:
            executor, _ = self._make_real_media_executor(directory)
            existing = Path(directory) / "audio-fixed.m4a"
            existing.write_bytes(b"keep-this-file")
            before = executor.get_project()
            with patch("project_tool_executor._new_id", return_value="audio-fixed"):
                with self.assertRaisesRegex(ProjectToolExecutionError, "already exists"):
                    executor.execute("media.extract_audio", {"media_id": "video-asset"})
            self.assertEqual(existing.read_bytes(), b"keep-this-file")
            self.assertEqual(executor.get_project(), before)

    def test_audio_extraction_missing_source_leaves_project_unchanged(self):
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as directory:
            executor, source = self._make_real_media_executor(directory)
            source.unlink()
            before = executor.get_project()
            with self.assertRaisesRegex(ProjectToolExecutionError, "not available"):
                executor.execute("media.extract_audio", {"media_id": "video-asset"})
            self.assertEqual(executor.get_project(), before)
            self.assertEqual(executor.revision, 1)

    def test_proxy_generation_creates_verified_low_resolution_asset_and_supports_undo_redo(self):
        import json
        import subprocess
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as directory:
            executor, source = self._make_real_media_executor(directory)
            result = executor.execute("media.create_proxy", {"media_id": "video-asset"})
            created = result["results"][0]["result"]
            proxy = next(item for item in executor.get_project()["assets"] if item["id"] == created["proxy_media_id"])
            proxy_path = Path(directory) / proxy["storage_key"]
            self.assertTrue(proxy_path.is_file())
            self.assertGreater(proxy_path.stat().st_size, 0)
            self.assertEqual(proxy["proxy_for_media_id"], "video-asset")
            self.assertEqual(proxy["generated_from_media_id"], "video-asset")
            probe = subprocess.run(
                ["ffprobe", "-v", "error", "-show_entries",
                 "format=duration:stream=codec_type,width,height",
                 "-of", "json", str(proxy_path)],
                check=True, capture_output=True, text=True,
            )
            metadata = json.loads(probe.stdout)
            video = next(item for item in metadata["streams"] if item["codec_type"] == "video")
            self.assertLessEqual(video["width"], 640)
            self.assertLessEqual(video["height"], 360)
            self.assertAlmostEqual(float(metadata["format"]["duration"]), 2.0, delta=0.25)
            self.assertEqual(created["width"], video["width"])
            executor.execute("history.undo", {})
            self.assertFalse(any(item["id"] == proxy["id"] for item in executor.get_project()["assets"]))
            executor.execute("history.redo", {})
            restored = next(item for item in executor.get_project()["assets"] if item["id"] == proxy["id"])
            self.assertEqual(restored["storage_key"], proxy["storage_key"])
            self.assertTrue(proxy_path.is_file())

    def test_proxy_generation_rejects_duplicates_without_mutation(self):
        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            executor, _ = self._make_real_media_executor(directory)
            executor.execute("media.create_proxy", {"media_id": "video-asset"})
            before = executor.get_project()
            with self.assertRaisesRegex(ProjectToolExecutionError, "proxy already exists"):
                executor.execute("media.create_proxy", {"media_id": "video-asset"})
            self.assertEqual(executor.get_project(), before)

    def test_proxy_generation_rejects_missing_source_without_mutation(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as directory:
            executor, source = self._make_real_media_executor(directory)
            source.unlink()
            before = executor.get_project()
            with self.assertRaisesRegex(ProjectToolExecutionError, "not available"):
                executor.execute("media.create_proxy", {"media_id": "video-asset"})
            self.assertEqual(executor.get_project(), before)




    def test_proxy_generation_removes_partial_output_after_ffmpeg_failure(self):
        import json
        import subprocess
        import tempfile
        from pathlib import Path
        from types import SimpleNamespace
        from unittest.mock import patch

        with tempfile.TemporaryDirectory() as directory:
            executor, _ = self._make_real_media_executor(directory)
            before = executor.get_project()
            partial_paths = []

            def fake_run(command, **kwargs):
                if command[0] == "ffprobe":
                    return SimpleNamespace(stdout=json.dumps({
                        "format": {"duration": "2.0"},
                        "streams": [{"codec_type": "video", "width": 160, "height": 120}],
                    }), stderr="")
                if command[0] == "ffmpeg":
                    partial = Path(command[-1])
                    partial.write_bytes(b"partial-proxy")
                    partial_paths.append(partial)
                    raise subprocess.CalledProcessError(1, command, stderr="simulated proxy failure")
                raise AssertionError("Unexpected process: " + command[0])

            with patch("project_tool_executor.subprocess.run", side_effect=fake_run):
                with self.assertRaisesRegex(ProjectToolExecutionError, "Proxy generation failed"):
                    executor.execute("media.create_proxy", {"media_id": "video-asset"})
            self.assertEqual(executor.get_project(), before)
            self.assertEqual(executor.revision, 1)
            self.assertEqual(len(partial_paths), 1)
            self.assertFalse(partial_paths[0].exists())

    def test_proxy_generation_never_overwrites_an_existing_file(self):
        import tempfile
        from pathlib import Path
        from unittest.mock import patch

        with tempfile.TemporaryDirectory() as directory:
            executor, _ = self._make_real_media_executor(directory)
            existing = Path(directory) / "proxy-fixed.mp4"
            existing.write_bytes(b"keep-existing-proxy")
            before = executor.get_project()
            with patch("project_tool_executor._new_id", return_value="proxy-fixed"):
                with self.assertRaisesRegex(ProjectToolExecutionError, "already exists"):
                    executor.execute("media.create_proxy", {"media_id": "video-asset"})
            self.assertEqual(existing.read_bytes(), b"keep-existing-proxy")
            self.assertEqual(executor.get_project(), before)


if __name__ == "__main__":
    unittest.main()


class TimedTranscriptTests(unittest.TestCase):
    def setUp(self):
        self.executor = ProjectToolExecutor(make_project())

    def sample_words(self):
        return [
            {"text": "The", "start_us": 100_000, "end_us": 250_000},
            {"text": "red,", "start_us": 300_000, "end_us": 500_000},
            {"text": "fox", "start_us": 500_000, "end_us": 800_000},
            {"text": "there", "start_us": 1_000_000, "end_us": 1_250_000},
            {"text": "red.", "start_us": 1_500_000, "end_us": 1_800_000},
        ]

    def import_words(self, words=None, **extra):
        return self.executor.execute(
            "transcript.import_words",
            {
                "media_id": "video-asset",
                "language": "en-US",
                "words": self.sample_words() if words is None else words,
                **extra,
            },
        )

    def test_transcript_tools_are_in_the_catalogue(self):
        names = {item["name"] for item in get_tool_catalog()}
        self.assertTrue({"transcript.import_words", "transcript.search"}.issubset(names))
        self.assertTrue(validate_tool_call("transcript.search", {
            "transcript_id": "transcript-1", "query": "hello",
        })["query"] == "hello")

    def test_import_is_revisioned_and_restored_by_undo_redo(self):
        result = self.import_words(name="Test transcript")
        created = result["results"][0]["result"]
        transcript_id = created["transcript_id"]
        self.assertEqual(result["revision"], 2)
        self.assertEqual(created["word_count"], 5)
        self.assertFalse(created["transcription_performed"])
        project = self.executor.get_project()
        self.assertEqual(project["transcripts"][0]["id"], transcript_id)
        self.assertEqual(project["transcripts"][0]["source_media_id"], "video-asset")
        self.assertEqual(project["transcripts"][0]["language"], "en-US")
        self.executor.execute("history.undo", {})
        self.assertEqual(self.executor.get_project().get("transcripts", []), [])
        self.executor.execute("history.redo", {})
        self.assertEqual(len(self.executor.get_project()["transcripts"][0]["words"]), 5)

    def test_search_matches_exact_phrase_and_maps_source_time_to_timeline(self):
        imported = self.import_words()
        transcript_id = imported["results"][0]["result"]["transcript_id"]
        revision = self.executor.revision
        result = self.executor.execute("transcript.search", {
            "transcript_id": transcript_id, "query": "RED fox",
        })
        payload = result["results"][0]["result"]
        self.assertFalse(result["changed"])
        self.assertEqual(self.executor.revision, revision)
        self.assertEqual(payload["match_count"], 1)
        match = payload["matches"][0]
        self.assertEqual((match["text"], match["start_us"], match["end_us"]),
                         ("red, fox", 300_000, 800_000))
        self.assertEqual((match["word_start_index"], match["word_end_index"]), (1, 2))
        self.assertEqual(match["timeline_locations"], [{
            "clip_id": "main-clip", "track_id": "main-video",
            "partial_source_match": False, "mapping_supported": True,
            "timeline_start_us": 300_000, "timeline_end_us": 800_000,
        }])

    def test_search_uses_exact_word_boundaries_not_substring_matches(self):
        imported = self.import_words()
        transcript_id = imported["results"][0]["result"]["transcript_id"]
        exact = self.executor.execute("transcript.search", {
            "transcript_id": transcript_id, "query": "red",
        })["results"][0]["result"]
        partial = self.executor.execute("transcript.search", {
            "transcript_id": transcript_id, "query": "he",
        })["results"][0]["result"]
        self.assertEqual(exact["match_count"], 2)
        self.assertEqual(exact["matches"][0]["text"], "red,")
        self.assertEqual(partial["match_count"], 0)

    def test_search_respects_case_sensitive_option_and_limit(self):
        imported = self.import_words()
        transcript_id = imported["results"][0]["result"]["transcript_id"]
        case_sensitive = self.executor.execute("transcript.search", {
            "transcript_id": transcript_id, "query": "Red", "case_sensitive": True,
        })["results"][0]["result"]
        limited = self.executor.execute("transcript.search", {
            "transcript_id": transcript_id, "query": "red", "limit": 1,
        })["results"][0]["result"]
        self.assertEqual(case_sensitive["match_count"], 0)
        self.assertTrue(limited["truncated"])
        self.assertEqual(len(limited["matches"]), 1)

    def test_search_maps_source_time_through_constant_playback_speed(self):
        project = make_project()
        project["tracks"][0]["clips"][0].update({
            "playback_rate": 2.0, "source_out_us": 4_000_000,
        })
        self.executor = ProjectToolExecutor(project)
        imported = self.import_words([
            {"text": "hello", "start_us": 1_000_000, "end_us": 1_200_000},
        ])
        transcript_id = imported["results"][0]["result"]["transcript_id"]
        match = self.executor.execute("transcript.search", {
            "transcript_id": transcript_id, "query": "hello",
        })["results"][0]["result"]["matches"][0]
        location = match["timeline_locations"][0]
        self.assertEqual((location["timeline_start_us"], location["timeline_end_us"]),
                         (500_000, 600_000))

    def test_search_marks_animated_speed_mapping_as_unsupported(self):
        project = make_project()
        project["tracks"][0]["clips"][0].update({
            "source_out_us": 3_000_000,
            "keyframes": [
                {"property": "playback_rate", "time_us": 0, "value": 1.0},
                {"property": "playback_rate", "time_us": 1_000_000, "value": 1.5},
            ],
        })
        self.executor = ProjectToolExecutor(project)
        imported = self.import_words([
            {"text": "hello", "start_us": 500_000, "end_us": 700_000},
        ])
        transcript_id = imported["results"][0]["result"]["transcript_id"]
        match = self.executor.execute("transcript.search", {
            "transcript_id": transcript_id, "query": "hello",
        })["results"][0]["result"]["matches"][0]
        self.assertFalse(match["timeline_locations"][0]["mapping_supported"])
        self.assertEqual(match["timeline_locations"][0]["reason"], "animated_speed_curve")

    def test_search_reports_partial_source_window_matches(self):
        project = make_project()
        project["tracks"][0]["clips"][0].update({
            "source_in_us": 500_000, "source_out_us": 2_500_000,
        })
        self.executor = ProjectToolExecutor(project)
        imported = self.import_words([
            {"text": "hello", "start_us": 300_000, "end_us": 700_000},
        ])
        transcript_id = imported["results"][0]["result"]["transcript_id"]
        match = self.executor.execute("transcript.search", {
            "transcript_id": transcript_id, "query": "hello",
        })["results"][0]["result"]["matches"][0]
        location = match["timeline_locations"][0]
        self.assertTrue(location["partial_source_match"])
        self.assertEqual((location["timeline_start_us"], location["timeline_end_us"]),
                         (0, 200_000))

    def test_search_rejects_missing_id_empty_terms_and_excessive_phrase(self):
        with self.assertRaises(ProjectToolExecutionError):
            self.executor.execute("transcript.search", {"transcript_id": "missing", "query": "hello"})
        imported = self.import_words()
        transcript_id = imported["results"][0]["result"]["transcript_id"]
        with self.assertRaises(ProjectToolExecutionError):
            self.executor.execute("transcript.search", {"transcript_id": transcript_id, "query": " !!! "})
        with self.assertRaises(ProjectToolExecutionError):
            self.executor.execute("transcript.search", {
                "transcript_id": transcript_id,
                "query": "one two three four five six seven eight nine ten eleven",
            })

    def test_transcript_import_rejects_wrong_asset_type_and_unsorted_words_atomically(self):
        project = make_project()
        project["assets"].append({
            "id": "font-asset", "media_type": "font", "file_name": "font.ttf",
            "storage_key": "font.ttf", "size_bytes": 10,
        })
        self.executor = ProjectToolExecutor(project)
        with self.assertRaises(ProjectToolExecutionError):
            self.executor.execute("transcript.import_words", {
                "media_id": "font-asset",
                "words": [{"text": "x", "start_us": 0, "end_us": 100_000}],
            })
        before_revision = self.executor.revision
        with self.assertRaises(ProjectValidationError):
            self.import_words([
                {"text": "later", "start_us": 500_000, "end_us": 700_000},
                {"text": "earlier", "start_us": 100_000, "end_us": 300_000},
            ])
        self.assertEqual(self.executor.revision, before_revision)
        self.assertEqual(self.executor.get_project().get("transcripts", []), [])

    def test_transcript_import_rejects_stale_revision_without_mutating(self):
        with self.assertRaises(ProjectRevisionConflict):
            self.executor.execute(
                "transcript.import_words",
                {"media_id": "video-asset", "words": self.sample_words()},
                expected_revision=99,
            )
        self.assertEqual(self.executor.revision, 1)
        self.assertEqual(self.executor.get_project().get("transcripts", []), [])



class TranscriptCutProposalTests(unittest.TestCase):
    def setUp(self):
        project = make_project()
        project["tracks"][0]["clips"].append({
            "id": "next-clip", "kind": "video", "media_id": "video-asset",
            "start_us": 2_000_000, "duration_us": 1_000_000,
            "source_in_us": 2_000_000, "source_out_us": 3_000_000,
            "playback_rate": 1.0, "effects": [], "keyframes": [],
        })
        self.executor = ProjectToolExecutor(project)
        imported = self.executor.execute("transcript.import_words", {
            "media_id": "video-asset", "language": "en",
            "words": [
                {"text": "This", "start_us": 100_000, "end_us": 250_000},
                {"text": "part", "start_us": 300_000, "end_us": 500_000},
                {"text": "goes", "start_us": 500_000, "end_us": 700_000},
                {"text": "away", "start_us": 700_000, "end_us": 2_000_000},
            ],
        })
        self.transcript_id = imported["results"][0]["result"]["transcript_id"]

    def proposal(self, start=1, end=2, clip_id="main-clip"):
        return self.executor.execute("transcript.propose_cut", {
            "transcript_id": self.transcript_id,
            "word_start_index": start,
            "word_end_index": end,
            "clip_id": clip_id,
        })

    def apply(self, start=1, end=2, clip_id="main-clip", confirmed=False):
        return self.executor.execute("transcript.apply_cut", {
            "transcript_id": self.transcript_id,
            "word_start_index": start,
            "word_end_index": end,
            "clip_id": clip_id,
        }, confirmed=confirmed)

    def test_proposal_previews_exact_range_without_mutation(self):
        before = self.executor.get_project()
        revision = self.executor.revision
        result = self.proposal()
        plan = result["results"][0]["result"]
        self.assertFalse(result["changed"])
        self.assertEqual(self.executor.revision, revision)
        self.assertEqual(self.executor.get_project(), before)
        self.assertEqual(plan["selected_text"], "part goes")
        self.assertEqual((plan["source_start_us"], plan["source_end_us"]), (300_000, 700_000))
        self.assertEqual((plan["timeline_cut_start_us"], plan["timeline_cut_end_us"]), (300_000, 700_000))
        self.assertEqual(plan["removed_duration_us"], 400_000)
        self.assertTrue(plan["can_apply"])

    def test_apply_requires_confirmation_and_leaves_project_untouched_before_approval(self):
        before = self.executor.get_project()
        with self.assertRaises(ToolConfirmationRequired):
            self.apply()
        self.assertEqual(self.executor.get_project(), before)
        self.assertEqual(self.executor.revision, 2)

    def test_apply_is_atomic_and_undoable_and_preserves_transcript(self):
        result = self.apply(confirmed=True)
        self.assertEqual(result["revision"], 3)
        outcome = result["results"][0]["result"]
        self.assertTrue(outcome["applied"])
        self.assertTrue(outcome["source_transcript_preserved"])
        project = self.executor.get_project()
        clips = {clip["id"]: clip for clip in project["tracks"][0]["clips"]}
        left = clips["main-clip"]
        right_id = outcome["after_clip_id"]
        self.assertIsNotNone(right_id)
        right = clips[right_id]
        self.assertEqual((left["source_in_us"], left["source_out_us"], left["duration_us"]),
                         (0, 300_000, 300_000))
        self.assertEqual((right["source_in_us"], right["source_out_us"], right["duration_us"]),
                         (700_000, 2_000_000, 1_300_000))
        self.assertEqual(right["start_us"], 300_000)
        self.assertEqual(clips["next-clip"]["start_us"], 1_600_000)
        self.assertEqual(len(project["transcripts"][0]["words"]), 4)
        self.executor.execute("history.undo", {})
        undone = {clip["id"]: clip for clip in self.executor.get_project()["tracks"][0]["clips"]}
        self.assertEqual(undone["main-clip"]["duration_us"], 2_000_000)
        self.assertEqual(undone["next-clip"]["start_us"], 2_000_000)
        self.executor.execute("history.redo", {})
        redone = {clip["id"]: clip for clip in self.executor.get_project()["tracks"][0]["clips"]}
        self.assertEqual(redone["next-clip"]["start_us"], 1_600_000)

    def test_apply_supports_cut_from_early_in_clip(self):
        result = self.apply(start=0, end=0, confirmed=True)
        project = self.executor.get_project()
        clips = {clip["id"]: clip for clip in project["tracks"][0]["clips"]}
        self.assertEqual(clips["main-clip"]["duration_us"], 100_000)
        remaining = clips[result["results"][0]["result"]["after_clip_id"]]
        self.assertEqual(remaining["source_in_us"], 250_000)
        self.assertEqual(remaining["start_us"], 100_000)
        self.assertEqual(clips["next-clip"]["start_us"], 1_850_000)

    def test_apply_supports_cut_to_clip_end(self):
        self.apply(start=3, end=3, confirmed=True)
        project = self.executor.get_project()
        clips = {clip["id"]: clip for clip in project["tracks"][0]["clips"]}
        self.assertEqual(clips["main-clip"]["source_out_us"], 700_000)
        self.assertEqual(clips["main-clip"]["duration_us"], 700_000)
        self.assertEqual(clips["next-clip"]["start_us"], 700_000)

    def test_proposal_blocks_keyframes_linked_groups_and_locked_tracks(self):
        project = self.executor.get_project()
        project["tracks"][0]["clips"][0]["keyframes"] = [
            {"property": "opacity", "time_us": 0, "value": 1.0}
        ]
        self.executor = ProjectToolExecutor(project)
        self.assertIn("clip_has_keyframes", self.proposal()["results"][0]["result"]["blockers"])

        project = self.executor.get_project()
        project["tracks"][0]["clips"][0]["keyframes"] = []
        project["tracks"][0]["clips"][0]["group_id"] = "group-1"
        project["clip_groups"] = [{"id": "group-1", "name": "Linked", "clip_ids": ["main-clip", "next-clip"]}]
        project["tracks"][0]["clips"][1]["group_id"] = "group-1"
        self.executor = ProjectToolExecutor(project)
        self.assertIn("clip_belongs_to_linked_group", self.proposal()["results"][0]["result"]["blockers"])

        project = self.executor.get_project()
        project["tracks"][0]["clips"][0].pop("group_id", None)
        project["tracks"][0]["clips"][1].pop("group_id", None)
        project.pop("clip_groups", None)
        project["transitions"] = [{
            "id": "transition-1", "type": "dissolve",
            "from_clip_id": "main-clip", "to_clip_id": "next-clip",
            "duration_us": 100_000, "parameters": {},
        }]
        self.executor = ProjectToolExecutor(project)
        self.assertIn("clip_has_transition", self.proposal()["results"][0]["result"]["blockers"])

        project = make_project()
        project["tracks"][0]["locked"] = True
        project["tracks"][0]["clips"].append({
            "id": "next-clip", "kind": "video", "media_id": "video-asset",
            "start_us": 2_000_000, "duration_us": 1_000_000,
            "source_in_us": 2_000_000, "source_out_us": 3_000_000,
            "playback_rate": 1.0, "effects": [], "keyframes": [],
        })
        self.executor = ProjectToolExecutor(project)
        imported = self.executor.execute("transcript.import_words", {
            "media_id": "video-asset", "words": [
                {"text": "This", "start_us": 100_000, "end_us": 250_000},
                {"text": "part", "start_us": 300_000, "end_us": 500_000},
            ],
        })
        self.transcript_id = imported["results"][0]["result"]["transcript_id"]
        self.assertIn("selected_track_locked", self.proposal(start=0, end=1)["results"][0]["result"]["blockers"])

    def test_proposal_blocks_out_of_clip_ranges_and_overlapping_siblings(self):
        project = self.executor.get_project()
        project["tracks"][0]["clips"][0]["source_out_us"] = 600_000
        project["tracks"][0]["clips"][0]["duration_us"] = 600_000
        self.executor = ProjectToolExecutor(project)
        self.assertIn("selected_range_outside_clip_source", self.proposal()["results"][0]["result"]["blockers"])

        project = make_project()
        project["tracks"][0]["clips"].append({
            "id": "overlap-clip", "kind": "video", "media_id": "video-asset",
            "start_us": 400_000, "duration_us": 500_000,
            "source_in_us": 2_000_000, "source_out_us": 2_500_000,
            "playback_rate": 1.0, "effects": [], "keyframes": [],
        })
        self.executor = ProjectToolExecutor(project)
        imported = self.executor.execute("transcript.import_words", {
            "media_id": "video-asset", "words": [
                {"text": "This", "start_us": 100_000, "end_us": 250_000},
                {"text": "part", "start_us": 300_000, "end_us": 500_000},
                {"text": "goes", "start_us": 500_000, "end_us": 700_000},
            ],
        })
        self.transcript_id = imported["results"][0]["result"]["transcript_id"]
        self.assertIn(
            "another_clip_overlaps_cut_range_on_selected_track",
            self.proposal()["results"][0]["result"]["blockers"],
        )

    def test_apply_refuses_unsafe_ranges_without_partial_mutation(self):
        project = self.executor.get_project()
        project["tracks"][0]["clips"][0]["source_out_us"] = 600_000
        project["tracks"][0]["clips"][0]["duration_us"] = 600_000
        self.executor = ProjectToolExecutor(project)
        before = self.executor.get_project()
        plan = self.proposal(start=0, end=3)["results"][0]["result"]
        with self.assertRaises(ToolConfirmationRequired):
            self.apply()
        self.assertEqual(self.executor.get_project(), before)
        self.assertFalse(plan["can_apply"])
        with self.assertRaises(ProjectToolExecutionError):
            self.apply(start=0, end=3, confirmed=True)
        self.assertEqual(self.executor.get_project(), before)


class MeasuredSilenceReviewTests(unittest.TestCase):
    def setUp(self):
        self.executor = ProjectToolExecutor(make_project(), asset_root="/tmp/video-editor-test-assets")
        imported = self.executor.execute("transcript.import_words", {
            "media_id": "video-asset",
            "language": "en",
            "words": [
                {"text": "Hello", "start_us": 100_000, "end_us": 300_000},
                {"text": "world", "start_us": 800_000, "end_us": 1_000_000},
            ],
        })
        self.transcript_id = imported["results"][0]["result"]["transcript_id"]

    def measured(self, *, coverage=8.0, full=True, intervals=None, status="measured"):
        return {
            "media_id": "video-asset",
            "duration_seconds": 8.0,
            "analysis_coverage_seconds": coverage,
            "full_duration_scanned": full,
            "measurement_status": status,
            "silence_intervals": intervals if intervals is not None else [
                {"start_seconds": 0.35, "end_seconds": 0.75, "duration_seconds": 0.4},
            ],
            "limitations": [],
        }

    def review(self, **overrides):
        arguments = {
            "transcript_id": self.transcript_id,
            "clip_id": "main-clip",
            "analysis_seconds": 600,
            "silence_threshold_db": -50,
            "minimum_silence_us": 100_000,
        }
        arguments.update(overrides)
        return self.executor.execute("transcript.review_silence", arguments)

    def apply(self, *, confirmed=False, **overrides):
        arguments = {
            "transcript_id": self.transcript_id,
            "clip_id": "main-clip",
            "source_start_us": 350_000,
            "source_end_us": 750_000,
        }
        arguments.update(overrides)
        return self.executor.execute(
            "transcript.apply_silence_cut", arguments,
            expected_revision=self.executor.revision, confirmed=confirmed,
        )

    def test_review_tool_is_registered_read_only_and_validates_scan_bounds(self):
        definition = next(
            item for item in get_tool_catalog()
            if item["name"] == "transcript.review_silence"
        )
        self.assertTrue(definition["read_only"])
        self.assertFalse(definition["requires_confirmation"])
        accepted = validate_tool_call("transcript.review_silence", {
            "transcript_id": self.transcript_id,
            "clip_id": "main-clip",
            "analysis_seconds": 60,
            "silence_threshold_db": -45,
            "minimum_silence_us": 100_000,
        })
        self.assertEqual(accepted["analysis_seconds"], 60)
        with self.assertRaises(ToolValidationError):
            validate_tool_call("transcript.review_silence", {
                "transcript_id": self.transcript_id, "clip_id": "main-clip",
                "analysis_seconds": 0, "silence_threshold_db": -50,
                "minimum_silence_us": 100_000,
            })

    def test_review_returns_only_measured_gaps_and_never_mutates(self):
        from unittest.mock import patch
        before = self.executor.get_project()
        revision = self.executor.revision
        with patch.object(ProjectToolExecutor, "_analyze_audio_media", return_value=self.measured()):
            result = self.review()
        payload = result["results"][0]["result"]
        self.assertFalse(result["changed"])
        self.assertEqual(self.executor.revision, revision)
        self.assertEqual(self.executor.get_project(), before)
        self.assertEqual(len(payload["candidates"]), 1)
        candidate = payload["candidates"][0]
        self.assertEqual((candidate["source_start_us"], candidate["source_end_us"]),
                         (350_000, 750_000))
        self.assertEqual(candidate["adjacent_words"], {"before": "Hello", "after": "world"})
        self.assertTrue(candidate["can_apply"])
        self.assertTrue(payload["full_duration_scanned"])
        self.assertEqual(payload["measurement_status"], "measured")

    def test_review_reports_partial_scan_and_no_audio_without_inventing_candidates(self):
        from unittest.mock import patch
        with patch.object(ProjectToolExecutor, "_analyze_audio_media",
                          return_value=self.measured(coverage=1.0, full=False)):
            partial = self.review(analysis_seconds=1)["results"][0]["result"]
        self.assertFalse(partial["full_duration_scanned"])
        self.assertEqual(partial["analysis_coverage_seconds"], 1.0)
        with patch.object(ProjectToolExecutor, "_analyze_audio_media",
                          return_value=self.measured(
                              intervals=[], status="no_audio_stream")):
            no_audio = self.review()["results"][0]["result"]
        self.assertEqual(no_audio["measurement_status"], "no_audio_stream")
        self.assertEqual(no_audio["candidates"], [])

    def test_apply_requires_confirmation_remeasures_and_is_undoable(self):
        from unittest.mock import patch
        measured = self.measured()
        before = self.executor.get_project()
        with patch.object(ProjectToolExecutor, "_analyze_audio_media", return_value=measured):
            with self.assertRaises(ToolConfirmationRequired):
                self.apply()
            self.assertEqual(self.executor.get_project(), before)
            result = self.apply(confirmed=True)
        outcome = result["results"][0]["result"]
        self.assertTrue(outcome["applied"])
        self.assertEqual((outcome["source_start_us"], outcome["source_end_us"]),
                         (350_000, 750_000))
        project = self.executor.get_project()
        self.assertEqual(len(project["transcripts"][0]["words"]), 2)
        clips = {clip["id"]: clip for track in project["tracks"] for clip in track["clips"]}
        self.assertEqual(clips["main-clip"]["source_out_us"], 350_000)
        after_id = outcome["after_clip_id"]
        self.assertEqual(clips[after_id]["source_in_us"], 750_000)
        self.executor.execute("history.undo", {})
        self.assertEqual(self.executor.get_project(), before)
        self.executor.execute("history.redo", {})
        self.assertEqual(
            {clip["id"]: clip for track in self.executor.get_project()["tracks"]
             for clip in track["clips"]}[after_id]["source_in_us"],
            750_000,
        )

    def test_apply_rejects_interval_when_fresh_measurement_no_longer_confirms_it(self):
        from unittest.mock import patch
        before = self.executor.get_project()
        with patch.object(ProjectToolExecutor, "_analyze_audio_media",
                          return_value=self.measured(intervals=[])):
            with self.assertRaises(ProjectToolExecutionError):
                self.apply(confirmed=True)
        self.assertEqual(self.executor.get_project(), before)
        self.assertEqual(self.executor.revision, 2)


