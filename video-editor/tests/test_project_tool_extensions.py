"""Regression tests for the first editor-tool expansion batch."""

import unittest

from project_tool_executor import (
    ProjectToolExecutionError,
    ProjectToolExecutor,
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


if __name__ == "__main__":
    unittest.main()
