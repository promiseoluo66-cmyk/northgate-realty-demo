"""Acceptance tests for Stage 1 Tasks 4 and 5."""
import unittest

from project_model import ProjectValidationError, validate_project
from project_tool_executor import ProjectToolExecutionError, ProjectToolExecutor
from tool_registry import ToolValidationError, validate_tool_call
from mlt_engine.renderer import (
    MltRenderError, _apply_track_audio_routing, _compile_clip_transform, _eased_ratio,
)


def make_project():
    return {
        "schema_version": 1, "id": "stage1-task45", "name": "Tasks 4 and 5",
        "revision": 1, "timeline_timebase": "microseconds",
        "video_profile": {"width": 720, "height": 1280, "frame_rate": {"numerator": 25, "denominator": 1}},
        "assets": [
            {"id": "video-a", "media_type": "video", "file_name": "a.mp4", "storage_key": "a.mp4", "size_bytes": 100, "duration_us": 4000000},
            {"id": "audio-a", "media_type": "audio", "file_name": "a.wav", "storage_key": "a.wav", "size_bytes": 100, "duration_us": 4000000},
        ],
        "tracks": [
            {"id": "v1", "type": "video", "name": "Video", "order": 0, "clips": [
                {"id": "c1", "kind": "video", "media_id": "video-a", "start_us": 0, "duration_us": 2000000, "source_in_us": 0, "source_out_us": 2000000, "playback_rate": 1, "effects": [], "keyframes": []}
            ]},
            {"id": "a1", "type": "audio", "name": "Audio", "order": 1, "clips": [
                {"id": "ac1", "kind": "audio", "media_id": "audio-a", "start_us": 0, "duration_us": 2000000, "source_in_us": 0, "source_out_us": 2000000, "playback_rate": 1, "effects": [], "keyframes": []}
            ]},
            {"id": "t1", "type": "text", "name": "Text", "order": 2, "clips": []},
        ],
        "transitions": [],
    }


class RecordingFilter:
    def __init__(self, service):
        self.service = service
        self.settings = {}

    def is_valid(self):
        return True

    def set(self, key, value):
        self.settings[key] = value


class RecordingMlt:
    def __init__(self):
        self.filters = []

    def Filter(self, profile, service):
        item = RecordingFilter(service)
        self.filters.append(item)
        return item


class RecordingProducer:
    def __init__(self):
        self.filters = []

    def attach(self, item):
        self.filters.append(item)


class Stage1Tasks45Tests(unittest.TestCase):
    def setUp(self):
        self.project = make_project()
        self.executor = ProjectToolExecutor(self.project)

    def test_track_level_gain_and_pan_are_saved_on_track(self):
        result = self.executor.execute("track.set_state", {
            "track_id": "a1", "audio_gain_db": -6, "audio_pan": 0.75,
        })
        track = next(item for item in result["project"]["tracks"] if item["id"] == "a1")
        self.assertEqual(track["audio_gain_db"], -6)
        self.assertEqual(track["audio_pan"], 0.75)

    def test_track_audio_mix_rejects_text_tracks_and_out_of_range_values(self):
        before = self.executor.get_project()
        with self.assertRaises(ProjectToolExecutionError):
            self.executor.execute("track.set_state", {"track_id": "t1", "audio_pan": 0.5})
        self.assertEqual(self.executor.get_project(), before)
        with self.assertRaises(ToolValidationError):
            validate_tool_call("track.set_state", {"track_id": "a1", "audio_pan": 1.1})
        with self.assertRaises(ToolValidationError):
            validate_tool_call("track.set_state", {"track_id": "a1", "audio_gain_db": -97})

    def test_project_model_rejects_invalid_track_audio_values(self):
        project = make_project()
        project["tracks"][1]["audio_pan"] = -1.2
        with self.assertRaises(ProjectValidationError):
            validate_project(project)
        project = make_project()
        project["tracks"][2]["audio_gain_db"] = -3
        with self.assertRaises(ProjectValidationError):
            validate_project(project)

    def test_track_audio_routing_compiles_gain_and_stereo_pan_filters(self):
        mlt, producer = RecordingMlt(), RecordingProducer()
        _apply_track_audio_routing(mlt, object(), producer, gain_db=-6, pan=-0.5)
        self.assertEqual([item.service for item in producer.filters], ["avfilter.volume", "panner"])
        self.assertAlmostEqual(float(producer.filters[0].settings["av.volume"]), 0.501187, places=5)
        self.assertEqual(producer.filters[1].settings["channel"], -1)
        self.assertEqual(producer.filters[1].settings["gang"], 1)
        self.assertEqual(producer.filters[1].settings["split"], 0.25)

    def test_center_pan_is_neutral_and_does_not_attach_panner(self):
        mlt, producer = RecordingMlt(), RecordingProducer()
        _apply_track_audio_routing(mlt, object(), producer, gain_db=0, pan=0)
        self.assertEqual(producer.filters, [])

    def test_track_audio_routing_fails_closed_for_unsupported_pan(self):
        with self.assertRaisesRegex(MltRenderError, "pan must be between"):
            _apply_track_audio_routing(RecordingMlt(), object(), RecordingProducer(), pan=1.5)

    def test_crop_keyframes_are_saved_and_eased(self):
        self.executor.execute("animation.set_keyframe", {
            "clip_id": "c1", "property": "crop_x", "time_us": 0,
            "value": 0.1, "interpolation": "smoothstep",
        })
        self.executor.execute("animation.set_keyframe", {
            "clip_id": "c1", "property": "crop_x", "time_us": 1000000,
            "value": 0.2, "interpolation": "linear",
        })
        clip = self.executor.get_project()["tracks"][0]["clips"][0]
        self.assertEqual([item["property"] for item in clip["keyframes"]], ["crop_x", "crop_x"])
        self.assertEqual(_eased_ratio(0.5, {"interpolation": "ease_in_quad"}), 0.25)
        self.assertEqual(_eased_ratio(0.5, {"interpolation": "smoothstep"}), 0.5)
        self.assertEqual(_eased_ratio(0.5, {"interpolation": "ease_out_quart"}), 0.9375)

    def test_animated_crop_compiles_a_time_varying_affine_rectangle(self):
        clip = {
            "kind": "video",
            "keyframes": [
                {"property": "crop_x", "time_us": 0, "value": 0.1, "interpolation": "linear"},
                {"property": "crop_x", "time_us": 1000000, "value": 0.2, "interpolation": "linear"},
                {"property": "crop_y", "time_us": 0, "value": 0.1},
                {"property": "crop_y", "time_us": 1000000, "value": 0.1},
                {"property": "crop_width", "time_us": 0, "value": 0.8},
                {"property": "crop_width", "time_us": 1000000, "value": 0.6},
                {"property": "crop_height", "time_us": 0, "value": 0.8},
                {"property": "crop_height", "time_us": 1000000, "value": 0.8},
            ],
        }
        compiled = _compile_clip_transform(clip, 720, 1280, 25, 1, 50, (1920, 1080))
        self.assertIn("0=", compiled["rect"])
        self.assertIn("25=", compiled["rect"])
        self.assertIn(";25=", compiled["rect"])
        self.assertTrue(compiled["crop"]["animated"])

    def test_animated_crop_rejects_geometry_outside_source_frame(self):
        clip = {
            "kind": "video",
            "keyframes": [
                {"property": "crop_x", "time_us": 0, "value": 0.8},
                {"property": "crop_width", "time_us": 0, "value": 0.4},
            ],
        }
        with self.assertRaisesRegex(MltRenderError, "stay inside"):
            _compile_clip_transform(clip, 720, 1280, 25, 1, 50, (1920, 1080))

    def test_animated_crop_requires_source_dimensions(self):
        clip = {
            "kind": "video",
            "keyframes": [{"property": "crop_x", "time_us": 0, "value": 0.1}],
        }
        with self.assertRaisesRegex(MltRenderError, "readable source width"):
            _compile_clip_transform(clip, 720, 1280, 25, 1, 50, None)

    def test_animated_crop_cannot_be_combined_with_auto_framing_or_speed_ramp(self):
        project = make_project()
        project["tracks"][0]["clips"][0]["framing"] = {"mode": "fill"}
        project["tracks"][0]["clips"][0]["keyframes"] = [
            {"property": "crop_x", "time_us": 0, "value": 0.1}
        ]
        with self.assertRaises(ProjectValidationError):
            validate_project(project)
        project = make_project()
        project["tracks"][0]["clips"][0]["keyframes"] = [
            {"property": "crop_x", "time_us": 0, "value": 0.1},
            {"property": "playback_rate", "time_us": 0, "value": 1.0},
        ]
        with self.assertRaises(ProjectValidationError):
            validate_project(project)

    def test_crop_keyframes_have_safe_schema_ranges(self):
        validate_tool_call("animation.set_keyframe", {
            "clip_id": "c1", "property": "crop_width", "time_us": 0, "value": 0.5,
        })
        with self.assertRaises(ToolValidationError):
            validate_tool_call("animation.set_keyframe", {
                "clip_id": "c1", "property": "crop_width", "time_us": 0, "value": 0,
            })


    def test_project_profile_update_is_executable(self):
        result = self.executor.execute("project.set_profile", {
            "width": 1080, "height": 1920, "fps_numerator": 30, "fps_denominator": 1,
        })
        profile = result["project"]["video_profile"]
        self.assertEqual(profile["width"], 1080)
        self.assertEqual(profile["height"], 1920)
        self.assertEqual(profile["frame_rate"], {"numerator": 30, "denominator": 1})

    def test_track_create_and_remove_are_executable(self):
        self.executor.execute("timeline.add_track", {
            "track_type": "audio", "name": "Effects", "order": 3,
        })
        project = self.executor.get_project()
        created = next(track for track in project["tracks"] if track["name"] == "Effects")
        self.executor.execute("timeline.remove_track", {"track_id": created["id"]}, confirmed=True)
        self.assertNotIn(created["id"], [track["id"] for track in self.executor.get_project()["tracks"]])

    def test_clip_trim_is_executable_and_updates_source_duration(self):
        result = self.executor.execute("timeline.trim_clip", {
            "clip_id": "c1", "source_in_us": 200000, "source_out_us": 1200000,
        })
        clip = self.executor.get_project()["tracks"][0]["clips"][0]
        self.assertEqual(clip["source_in_us"], 200000)
        self.assertEqual(clip["source_out_us"], 1200000)
        self.assertEqual(clip["duration_us"], 1000000)

    def test_effect_remove_is_executable(self):
        project = self.executor.get_project()
        project["tracks"][0]["clips"][0]["effects"].append({
            "id": "fx1", "type": "brightness", "parameters": {"level": 1.0},
        })
        self.executor = ProjectToolExecutor(project)
        result = self.executor.execute("effect.remove", {"clip_id": "c1", "effect_id": "fx1"})
        self.assertEqual(result["results"][0]["result"]["removed_effect_id"], "fx1")
        self.assertEqual(self.executor.get_project()["tracks"][0]["clips"][0]["effects"], [])


if __name__ == "__main__":
    unittest.main()
