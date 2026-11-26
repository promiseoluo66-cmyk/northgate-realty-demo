"""Unit tests for the safe MLT adapter compiler (no MLT runtime required)."""
from __future__ import annotations

import importlib.util
import shutil
import tempfile
import unittest
from pathlib import Path

from mlt_engine.renderer import (
    MltRenderError,
    _apply_clip_transform,
    _frame_at_us,
    compile_render_plan,
)


def make_project(asset_root: Path) -> dict:
    source = asset_root / "source.mp4"
    source.write_bytes(b"generated-placeholder-for-plan-tests")
    return {
        "schema_version": 1,
        "id": "mlt-test-project",
        "name": "MLT adapter test",
        "revision": 3,
        "timeline_timebase": "microseconds",
        "video_profile": {
            "width": 320,
            "height": 240,
            "frame_rate": {"numerator": 25, "denominator": 1},
        },
        "assets": [{
            "id": "asset-video",
            "media_type": "video",
            "file_name": "source.mp4",
            "storage_key": "source.mp4",
            "size_bytes": source.stat().st_size,
            "duration_us": 4_000_000,
        }],
        "tracks": [{
            "id": "track-main",
            "type": "video",
            "name": "Main",
            "order": 0,
            "clips": [{
                "id": "clip-main",
                "kind": "video",
                "media_id": "asset-video",
                "start_us": 0,
                "duration_us": 2_000_000,
                "source_in_us": 0,
                "source_out_us": 2_000_000,
                "playback_rate": 1,
                "effects": [],
                "keyframes": [],
            }],
        }],
        "transitions": [],
    }


class FrameConversionTests(unittest.TestCase):
    def test_exact_frame_boundary(self):
        self.assertEqual(_frame_at_us(400_000, 25, 1), 10)

    def test_half_frame_rounds_up(self):
        self.assertEqual(_frame_at_us(20_000, 25, 1), 1)

    def test_fractional_frame_rate(self):
        # At 30000/1001 fps, one second is approximately 29.97 frames.
        self.assertEqual(_frame_at_us(1_000_000, 30_000, 1_001), 30)


class CompilePlanTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.project = make_project(self.root)

    def tearDown(self):
        self.temp.cleanup()

    def compile(self):
        return compile_render_plan(self.project, self.root)

    def test_compiles_basic_video_project(self):
        plan = self.compile()
        self.assertEqual(plan["project_id"], "mlt-test-project")
        self.assertEqual(plan["revision"], 3)
        self.assertEqual(plan["total_frames"], 50)
        self.assertEqual(len(plan["tracks"]), 1)
        self.assertEqual(plan["tracks"][0]["clips"][0]["duration_frames"], 50)

    def test_compiles_text_caption_track(self):
        self.project["tracks"].append({
            "id": "captions", "type": "text", "name": "Captions", "order": 1,
            "clips": [{
                "id": "caption-one", "kind": "text", "start_us": 400_000,
                "duration_us": 800_000,
                "text": {
                    "content": "AI EDITED TITLE", "size": 42, "weight": 700,
                    "fgcolour": "#FFFF00", "x_percent": 5, "y_percent": 35,
                    "width_percent": 90, "height_percent": 30,
                },
                "effects": [], "keyframes": [],
            }],
        })
        plan = self.compile()
        text_track = plan["tracks"][1]
        self.assertEqual(text_track["type"], "text")
        self.assertEqual(text_track["clips"][0]["kind"], "text")
        self.assertIsNone(text_track["clips"][0]["path"])
        self.assertEqual(text_track["clips"][0]["text"]["content"], "AI EDITED TITLE")
        self.assertEqual(plan["total_frames"], 50)

    def test_compiles_still_image_overlay(self):
        image = self.root / "overlay.png"
        image.write_bytes(b"generated-image-placeholder")
        self.project["assets"].append({
            "id": "asset-image", "media_type": "image",
            "file_name": image.name, "storage_key": image.name,
            "size_bytes": image.stat().st_size, "duration_us": 2_000_000,
        })
        self.project["tracks"].append({
            "id": "track-overlay", "type": "overlay", "name": "Image overlay",
            "order": 1, "clips": [{
                "id": "image-overlay", "kind": "image", "media_id": "asset-image",
                "start_us": 400_000, "duration_us": 800_000,
                "source_in_us": 0, "source_out_us": 800_000,
                "playback_rate": 1, "effects": [], "keyframes": [],
            }],
        })
        plan = self.compile()
        image_clip = plan["tracks"][1]["clips"][0]
        self.assertEqual(image_clip["kind"], "image")
        self.assertEqual(image_clip["path"], image.resolve())

    def test_rejects_text_outside_canvas(self):
        self.project["tracks"].append({
            "id": "captions", "type": "text", "name": "Captions", "order": 1,
            "clips": [{
                "id": "caption-invalid", "kind": "text", "start_us": 0,
                "duration_us": 500_000,
                "text": {"content": "BAD", "x_percent": 90, "width_percent": 20},
                "effects": [], "keyframes": [],
            }],
        })
        with self.assertRaisesRegex(ValueError, "geometry must stay inside"):
            self.compile()

    def test_track_order_is_sorted(self):
        overlay = dict(self.project["tracks"][0])
        overlay.update({"id": "track-overlay", "type": "overlay",
                        "name": "Overlay", "order": 5})
        overlay["clips"] = [dict(self.project["tracks"][0]["clips"][0],
                                  id="clip-overlay", start_us=2_000_000)]
        overlay["clips"][0]["source_in_us"] = 0
        overlay["clips"][0]["source_out_us"] = 2_000_000
        self.project["tracks"].append(overlay)
        self.project["tracks"][0]["order"] = 10
        plan = self.compile()
        self.assertEqual([track["id"] for track in plan["tracks"]],
                         ["track-overlay", "track-main"])

    def test_compiles_brightness_and_chroma_allowlisted_effects(self):
        self.project["tracks"][0]["clips"][0]["effects"] = [
            {"id": "bright-1", "type": "brightness",
             "parameters": {"level": 1.2}},
            {"id": "key-1", "type": "chroma",
             "parameters": {"key": "#00ff00", "variance": 0.2}},
        ]
        effects = self.compile()["tracks"][0]["clips"][0]["effects"]
        self.assertEqual([effect["type"] for effect in effects],
                         ["brightness", "chroma"])

    def test_compiles_contrast_and_saturation_allowlisted_effects(self):
        self.project["tracks"][0]["clips"][0]["effects"] = [
            {"id": "contrast-1", "type": "contrast", "parameters": {"value": 1.5}},
            {"id": "saturation-1", "type": "saturation", "parameters": {"value": 1.8}},
        ]
        effects = self.compile()["tracks"][0]["clips"][0]["effects"]
        self.assertEqual([item["type"] for item in effects], ["avfilter.eq", "avfilter.eq"])
        self.assertEqual(effects[0]["contrast"], 1.5)
        self.assertEqual(effects[0]["saturation"], 1.0)
        self.assertEqual(effects[1]["contrast"], 1.0)
        self.assertEqual(effects[1]["saturation"], 1.8)

    def test_rejects_out_of_range_contrast_and_saturation(self):
        for effect_type, value in (("contrast", 5.0), ("saturation", 4.0)):
            with self.subTest(effect_type=effect_type):
                self.project["tracks"][0]["clips"][0]["effects"] = [
                    {"id": "bad-effect", "type": effect_type, "parameters": {"value": value}},
                ]
                with self.assertRaisesRegex(MltRenderError, "must be between"):
                    self.compile()

    def test_disabled_effect_is_not_rendered(self):
        self.project["tracks"][0]["clips"][0]["effects"] = [
            {"id": "bright-1", "type": "brightness", "enabled": False,
             "parameters": {"level": 1.2}},
        ]
        self.assertEqual(self.compile()["tracks"][0]["clips"][0]["effects"], [])

    def test_rejects_non_allowlisted_effect(self):
        self.project["tracks"][0]["clips"][0]["effects"] = [
            {"id": "volume-1", "type": "volume",
             "parameters": {"level": 0.5}},
        ]
        with self.assertRaisesRegex(MltRenderError, "allowlist"):
            self.compile()

    def test_rejects_invalid_brightness_value(self):
        self.project["tracks"][0]["clips"][0]["effects"] = [
            {"id": "bright-1", "type": "brightness",
             "parameters": {"level": 99}},
        ]
        with self.assertRaisesRegex(MltRenderError, "between 0 and 15"):
            self.compile()

    def test_compiles_static_transform_to_affine_rectangle(self):
        self.project["tracks"][0]["clips"][0]["transform"] = {
            "position": {"x": 10, "y": -5},
            "scale": {"x": 0.5, "y": 0.5},
            "rotation_deg": 15,
            "opacity": 0.75,
        }
        transform = self.compile()["tracks"][0]["clips"][0]["transform"]
        self.assertEqual(transform["rect"], "90.000/55.000:160.000x120.000:1.000")
        self.assertEqual(transform["opacity_alpha"], "0.750")
        self.assertTrue(transform["opacity_enabled"])
        self.assertEqual(transform["rotation"], 15.0)
        self.assertFalse(transform["animated"])

    def test_compiles_linear_zoom_keyframes(self):
        self.project["tracks"][0]["clips"][0]["keyframes"] = [
            {"property": "scale_x", "time_us": 0, "value": 0.5},
            {"property": "scale_y", "time_us": 0, "value": 0.5},
            {"property": "scale_x", "time_us": 1_600_000, "value": 1.0},
            {"property": "scale_y", "time_us": 1_600_000, "value": 1.0},
        ]
        transform = self.compile()["tracks"][0]["clips"][0]["transform"]
        self.assertTrue(transform["animated"])
        self.assertIn("40=0.000/0.000:320.000x240.000:1.000", transform["rect"])
        self.assertTrue(transform["rect"].startswith("0=80.000/60.000:160.000x120.000:1.000"))

    def test_compiles_position_rotation_and_opacity_keyframes(self):
        self.project["tracks"][0]["clips"][0]["keyframes"] = [
            {"property": "position_x", "time_us": 0, "value": -80},
            {"property": "position_x", "time_us": 1_600_000, "value": 80},
            {"property": "rotation_deg", "time_us": 0, "value": 0},
            {"property": "rotation_deg", "time_us": 1_600_000, "value": 45},
            {"property": "opacity", "time_us": 0, "value": 1},
            {"property": "opacity", "time_us": 1_600_000, "value": 0.2},
        ]
        transform = self.compile()["tracks"][0]["clips"][0]["transform"]
        self.assertTrue(transform["animated"])
        self.assertTrue(transform["rect"].startswith("0=-80.000/0.000:320.000x240.000:1.000"))
        self.assertIn("40=80.000/0.000:320.000x240.000:1.000", transform["rect"])
        self.assertTrue(transform["opacity_alpha"].startswith("0=1.000;"))
        self.assertIn("40=0.200", transform["opacity_alpha"])
        self.assertTrue(transform["opacity_enabled"])
        self.assertIn("0=0.000000", transform["rotation"])
        self.assertIn("40=45.000000", transform["rotation"])
        self.assertTrue(transform["rotation_animated"])

    def test_compiles_static_opacity_as_normalized_mlt_mix(self):
        self.project["tracks"][0]["clips"][0]["transform"] = {
            "position": {"x": 0, "y": 0},
            "scale": {"x": 1, "y": 1},
            "rotation_deg": 0,
            "opacity": 0.25,
        }
        transform = self.compile()["tracks"][0]["clips"][0]["transform"]
        self.assertTrue(transform["rect"].endswith(":1.000"))
        self.assertEqual(transform["opacity_alpha"], "0.250")
        self.assertTrue(transform["opacity_enabled"])

    def test_compiles_eased_keyframes(self):
        self.project["tracks"][0]["clips"][0]["keyframes"] = [
            {"property": "scale_x", "time_us": 0, "value": 0.5,
             "interpolation": "ease_in"},
            {"property": "scale_x", "time_us": 1_600_000, "value": 1.0},
        ]
        transform = self.compile()["tracks"][0]["clips"][0]["transform"]
        # At half time, cubic ease-in is 0.125 progress, not linear 0.5.
        self.assertIn("20=70.000/0.000:180.000x240.000:1.000", transform["rect"])

    def test_compiles_custom_bezier_keyframes(self):
        self.project["tracks"][0]["clips"][0]["keyframes"] = [
            {"property": "scale_x", "time_us": 0, "value": 0.5,
             "interpolation": "bezier",
             "bezier": {"x1": 0.42, "y1": 0.0, "x2": 0.58, "y2": 1.0}},
            {"property": "scale_x", "time_us": 1_600_000, "value": 1.0},
        ]
        transform = self.compile()["tracks"][0]["clips"][0]["transform"]
        self.assertTrue(transform["animated"])
        self.assertIn("20=", transform["rect"])


    def test_compiles_audio_volume_keyframes(self):
        self.add_audio_track()
        self.project["tracks"][-1]["clips"][0]["keyframes"] = [
            {"property": "volume_db", "time_us": 0, "value": 0.0},
            {"property": "volume_db", "time_us": 1_000_000, "value": -24.0},
        ]
        planned = self.compile()["tracks"][1]["clips"][0]
        self.assertTrue(planned["audio_keyframes"].startswith("0=1.000000000;"))
        self.assertIn("25=0.063095734", planned["audio_keyframes"])
        self.assertTrue(planned["audio_keyframes"].endswith("49=0.063095734"))

    def test_rejects_visual_keyframes_on_audio_track(self):
        self.add_audio_track()
        self.project["tracks"][-1]["clips"][0]["keyframes"] = [
            {"property": "position_x", "time_us": 0, "value": 10.0}
        ]
        with self.assertRaisesRegex(MltRenderError, "volume_db keyframes only"):
            self.compile()

    def test_compiles_constant_double_speed_clip(self):
        clip = self.project["tracks"][0]["clips"][0]
        clip["playback_rate"] = 2.0
        clip["source_out_us"] = 4_000_000
        planned = self.compile()["tracks"][0]["clips"][0]
        self.assertEqual(planned["playback_rate"], 2.0)
        self.assertEqual(planned["source_in_frame"], 0)
        self.assertEqual(planned["source_out_frame"], 99)
        self.assertEqual(planned["render_in_frame"], 0)
        self.assertEqual(planned["render_out_frame"], 49)

    def test_compiles_constant_half_speed_clip(self):
        clip = self.project["tracks"][0]["clips"][0]
        clip["playback_rate"] = 0.5
        clip["source_out_us"] = 1_000_000
        planned = self.compile()["tracks"][0]["clips"][0]
        self.assertEqual(planned["playback_rate"], 0.5)
        self.assertEqual(planned["render_in_frame"], 0)
        self.assertEqual(planned["render_out_frame"], 49)

    def test_compiles_keyframed_speed_curve_into_contiguous_segments(self):
        clip = self.project["tracks"][0]["clips"][0]
        clip["source_out_us"] = 3_000_000
        clip["keyframes"] = [
            {"property": "playback_rate", "time_us": 0, "value": 1.0},
            {"property": "playback_rate", "time_us": 1_999_999, "value": 2.0},
        ]
        planned = self.compile()["tracks"][0]["clips"][0]
        segments = planned["speed_segments"]
        self.assertEqual(len(segments), 50)
        self.assertEqual(sum(item["duration_frames"] for item in segments), 50)
        self.assertAlmostEqual(
            sum(item["playback_rate"] * item["duration_frames"] for item in segments),
            75.0,
            delta=0.1,
        )
        self.assertAlmostEqual(segments[0]["playback_rate"], 1.01, delta=0.02)
        self.assertGreater(segments[-1]["playback_rate"], 1.98)
        self.assertEqual(segments[0]["output_start_frame"], 0)
        self.assertEqual(segments[-1]["output_start_frame"], 49)

    def test_rejects_speed_curve_combined_with_animated_visual_transform(self):
        clip = self.project["tracks"][0]["clips"][0]
        clip["keyframes"] = [
            {"property": "playback_rate", "time_us": 0, "value": 1.0},
            {"property": "playback_rate", "time_us": 1_000_000, "value": 2.0},
            {"property": "scale_x", "time_us": 0, "value": 1.0},
            {"property": "scale_x", "time_us": 1_000_000, "value": 1.5},
        ]
        clip["source_out_us"] = 3_000_000
        with self.assertRaisesRegex(MltRenderError, "cannot yet be combined"):
            self.compile()

    def test_rejects_invalid_source_range_for_playback_speed(self):
        clip = self.project["tracks"][0]["clips"][0]
        clip["playback_rate"] = 2.0
        clip["source_out_us"] = 2_000_000
        with self.assertRaisesRegex(MltRenderError, "does not match the integrated playback speed curve"):
            self.compile()

    def test_rejects_overlapping_clips_on_same_track(self):
        second = dict(self.project["tracks"][0]["clips"][0])
        second["id"] = "clip-overlap"
        second["start_us"] = 1_000_000
        self.project["tracks"][0]["clips"].append(second)
        with self.assertRaisesRegex(MltRenderError, "overlap"):
            self.compile()

    def add_audio_track(self, *, muted=False, solo=False):
        self.project["assets"].append({
            "id": "asset-audio", "media_type": "audio", "file_name": "music.wav",
            "storage_key": "music.wav", "size_bytes": 8, "duration_us": 2_000_000,
        })
        (self.root / "music.wav").write_bytes(b"12345678")
        self.project["tracks"].append({
            "id": "track-audio", "type": "audio", "name": "Music", "order": 1,
            "muted": muted,
            "solo": solo,
            "clips": [{
                "id": "clip-audio", "kind": "audio", "media_id": "asset-audio",
                "start_us": 0, "duration_us": 2_000_000, "source_in_us": 0,
                "source_out_us": 2_000_000, "playback_rate": 1, "effects": [],
                "keyframes": [],
            }],
        })

    def test_compiles_an_independent_audio_track(self):
        self.add_audio_track()
        plan = self.compile()
        audio = [track for track in plan["tracks"] if track["type"] == "audio"]
        self.assertEqual(len(audio), 1)
        self.assertEqual(audio[0]["clips"][0]["duration_frames"], 50)

    def test_muted_audio_track_is_skipped(self):
        self.add_audio_track(muted=True)
        plan = self.compile()
        self.assertEqual([track["type"] for track in plan["tracks"]], ["video"])

    def test_muted_video_track_remains_visible_but_is_marked_muted(self):
        self.project["tracks"][0]["muted"] = True
        plan = self.compile()
        self.assertTrue(plan["tracks"][0]["muted"])

    def test_solo_audio_track_keeps_picture_and_suppresses_other_audio(self):
        self.add_audio_track(solo=True)
        plan = self.compile()
        video = next(track for track in plan["tracks"] if track["type"] == "video")
        audio = next(track for track in plan["tracks"] if track["type"] == "audio")
        self.assertTrue(video["muted"])
        self.assertTrue(audio["solo"])
        self.assertEqual([track["id"] for track in plan["tracks"]],
                         ["track-main", "track-audio"])

    def test_solo_visual_track_hides_other_visuals_but_keeps_music(self):
        self.add_audio_track()
        overlay = {
            "id": "track-overlay", "type": "overlay", "name": "Overlay",
            "order": 2, "solo": False,
            "clips": [{
                "id": "clip-overlay", "kind": "video", "media_id": "asset-video",
                "start_us": 0, "duration_us": 1_000_000,
                "source_in_us": 0, "source_out_us": 1_000_000,
                "playback_rate": 1, "effects": [], "keyframes": [],
            }],
        }
        self.project["tracks"].append(overlay)
        self.project["tracks"][0]["solo"] = True
        plan = self.compile()
        self.assertEqual(
            [track["id"] for track in plan["tracks"]],
            ["track-main", "track-audio"],
        )
        self.assertFalse(next(track for track in plan["tracks"]
                              if track["type"] == "video")["muted"])

    def test_solo_disabled_audio_track_does_not_activate_audio_solo(self):
        self.add_audio_track(solo=True)
        self.project["tracks"][1]["enabled"] = False
        plan = self.compile()
        self.assertEqual([track["id"] for track in plan["tracks"]], ["track-main"])
        self.assertFalse(plan["tracks"][0]["muted"])

    def test_compiles_audio_gain_and_fade_allowlisted_effects(self):
        self.add_audio_track()
        self.project["tracks"][1]["clips"][0]["effects"] = [
            {"id": "gain-1", "type": "gain", "parameters": {"gain_db": -6}},
            {"id": "fade-1", "type": "fade", "parameters": {
                "fade_in_us": 300_000, "fade_out_us": 400_000,
            }},
        ]
        plan = self.compile()
        effects = plan["tracks"][1]["clips"][0]["effects"]
        self.assertEqual(effects, [
            {"type": "avfilter.volume", "volume": "0.501187234"},
            {"type": "avfilter.afade", "direction": "in", "start_time": "0.000000",
             "duration": "0.300000", "curve": "qsin"},
            {"type": "avfilter.afade", "direction": "out", "start_time": "1.600000",
             "duration": "0.400000", "curve": "qsin"},
        ])

    def test_rejects_audio_gain_outside_safe_range(self):
        self.add_audio_track()
        self.project["tracks"][1]["clips"][0]["effects"] = [{
            "id": "gain-1", "type": "gain", "parameters": {"gain_db": 30},
        }]
        with self.assertRaisesRegex(MltRenderError, "between -96 and 24"):
            self.compile()

    def test_rejects_audio_fades_longer_than_clip(self):
        self.add_audio_track()
        self.project["tracks"][1]["clips"][0]["effects"] = [{
            "id": "fade-1", "type": "fade", "parameters": {
                "fade_in_us": 1_500_000, "fade_out_us": 600_000,
            },
        }]
        with self.assertRaisesRegex(MltRenderError, "cannot exceed"):
            self.compile()

    def add_dissolve_pair(self):
        second = dict(self.project["tracks"][0]["clips"][0])
        second.update({
            "id": "clip-next", "start_us": 1_600_000,
            "duration_us": 1_200_000, "source_in_us": 2_000_000,
            "source_out_us": 3_200_000,
        })
        self.project["tracks"][0]["clips"].append(second)
        self.project["transitions"] = [{
            "id": "transition-1", "type": "dissolve",
            "from_clip_id": "clip-main", "to_clip_id": "clip-next",
            "duration_us": 400_000, "parameters": {},
        }]

    def test_compiles_adjacent_clip_dissolve(self):
        self.add_dissolve_pair()
        plan = self.compile()
        transition = plan["tracks"][0]["transitions"][0]
        self.assertEqual(transition["from_clip_id"], "clip-main")
        self.assertEqual(transition["to_clip_id"], "clip-next")
        self.assertEqual(transition["duration_frames"], 10)
        self.assertEqual(plan["total_frames"], 70)

    def test_compiles_horizontal_wipe(self):
        self.add_dissolve_pair()
        self.project["transitions"][0]["type"] = "wipe"
        self.project["transitions"][0]["parameters"] = {"direction": "left_to_right", "softness": 0.12}
        transition = self.compile()["tracks"][0]["transitions"][0]
        self.assertEqual(transition["type"], "wipe")
        self.assertEqual(transition["parameters"], {"direction": "left_to_right", "softness": 0.12})

    def test_compiles_left_to_right_wipe_parameters(self):
        self.add_dissolve_pair()
        self.project["transitions"][0]["type"] = "wipe"
        self.project["transitions"][0]["parameters"] = {
            "direction": "left_to_right", "softness": 0.12
        }
        parameters = self.compile()["tracks"][0]["transitions"][0]["parameters"]
        self.assertEqual(parameters, {"direction": "left_to_right", "softness": 0.12})

    def test_compiles_reverse_horizontal_wipe_defaults(self):
        self.add_dissolve_pair()
        self.project["transitions"][0]["type"] = "wipe"
        self.project["transitions"][0]["parameters"] = {"direction": "right_to_left"}
        parameters = self.compile()["tracks"][0]["transitions"][0]["parameters"]
        self.assertEqual(parameters["direction"], "right_to_left")
        self.assertEqual(parameters["softness"], 0.08)

    def test_rejects_invalid_wipe_direction(self):
        self.add_dissolve_pair()
        self.project["transitions"][0]["type"] = "wipe"
        self.project["transitions"][0]["parameters"] = {"direction": "diagonal"}
        with self.assertRaisesRegex(MltRenderError, "wipe.direction"):
            self.compile()

    def test_rejects_invalid_wipe_softness(self):
        self.add_dissolve_pair()
        self.project["transitions"][0]["type"] = "wipe"
        self.project["transitions"][0]["parameters"] = {"softness": 1.5}
        with self.assertRaisesRegex(MltRenderError, "wipe.softness"):
            self.compile()

    def test_rejects_unknown_wipe_parameter(self):
        self.add_dissolve_pair()
        self.project["transitions"][0]["type"] = "wipe"
        self.project["transitions"][0]["parameters"] = {"custom_resource": "/tmp/other.pgm"}
        with self.assertRaisesRegex(MltRenderError, "Unsupported wipe parameter"):
            self.compile()

    def test_rejects_unsupported_transition_type(self):
        self.add_dissolve_pair()
        self.project["transitions"][0]["type"] = "fade"
        with self.assertRaisesRegex(MltRenderError, "Only dissolve and wipe"):
            self.compile()

    def test_rejects_dissolve_duration_that_does_not_match_overlap(self):
        self.add_dissolve_pair()
        self.project["transitions"][0]["duration_us"] = 200_000
        with self.assertRaisesRegex(MltRenderError, "exactly match"):
            self.compile()

    def test_rejects_cross_track_dissolve(self):
        second = dict(self.project["tracks"][0]["clips"][0])
        second.update({
            "id": "clip-other", "start_us": 1_600_000,
            "duration_us": 1_200_000, "source_in_us": 2_000_000,
            "source_out_us": 3_200_000,
        })
        self.project["tracks"].append({
            "id": "track-overlay", "type": "overlay", "name": "Overlay",
            "order": 1, "clips": [second],
        })
        self.project["transitions"] = [{
            "id": "transition-1", "type": "dissolve",
            "from_clip_id": "clip-main", "to_clip_id": "clip-other",
            "duration_us": 400_000, "parameters": {},
        }]
        with self.assertRaisesRegex(MltRenderError, "same visual track"):
            self.compile()


    def test_rejects_missing_asset_file(self):
        (self.root / "source.mp4").unlink()
        with self.assertRaises((FileNotFoundError, MltRenderError)):
            self.compile()

    def test_rejects_absolute_storage_path(self):
        self.project["assets"][0]["storage_key"] = "/etc/passwd"
        with self.assertRaises(Exception):
            self.compile()

if __name__ == "__main__":
    unittest.main()



class FramingRenderPlanTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.project = make_project(self.root)

    def tearDown(self):
        self.temp.cleanup()

    def test_compiles_framing_without_a_manual_transform(self):
        self.project["tracks"][0]["clips"][0]["framing"] = {
            "mode": "fit",
            "horizontal_alignment": "right",
            "vertical_alignment": "top",
        }
        from unittest.mock import patch

        with patch("mlt_engine.renderer._probe_media_dimensions", return_value=(320, 240)):
            transform = compile_render_plan(self.project, self.root)["tracks"][0]["clips"][0]["transform"]
        self.assertIsNotNone(transform)
        self.assertEqual(transform["framing"], {
            "mode": "fit",
            "horizontal_alignment": "right",
            "vertical_alignment": "top",
        })

    def test_fill_framing_computes_cover_rectangle_from_source_dimensions(self):
        from mlt_engine.renderer import _compile_clip_transform

        clip = {
            "framing": {
                "mode": "fill",
                "horizontal_alignment": "center",
                "vertical_alignment": "middle",
            },
            "keyframes": [],
        }
        transform = _compile_clip_transform(
            clip, 320, 180, 25, 1, 25,
            source_dimensions=(320, 240),
        )
        self.assertEqual(transform["rect"], "0.000/-30.000:320.000x240.000:1.000")

    def test_fit_framing_computes_contain_rectangle_from_source_dimensions(self):
        from mlt_engine.renderer import _compile_clip_transform

        transform = _compile_clip_transform(
            {
                "framing": {
                    "mode": "fit",
                    "horizontal_alignment": "center",
                    "vertical_alignment": "middle",
                },
                "keyframes": [],
            },
            320, 180, 25, 1, 25,
            source_dimensions=(320, 240),
        )
        self.assertEqual(transform["rect"], "40.000/0.000:240.000x180.000:1.000")

    def test_fit_framing_fails_closed_without_source_dimensions(self):
        from mlt_engine.renderer import _compile_clip_transform

        with self.assertRaisesRegex(MltRenderError, "Fit framing requires readable source"):
            _compile_clip_transform(
                {"framing": {"mode": "fit"}, "keyframes": []},
                320, 180, 25, 1, 25,
            )

    def test_fill_framing_fails_closed_without_source_dimensions(self):
        from mlt_engine.renderer import _compile_clip_transform

        with self.assertRaisesRegex(MltRenderError, "source width and height"):
            _compile_clip_transform(
                {"framing": {"mode": "fill"}, "keyframes": []},
                320, 180, 25, 1, 25,
            )

    def test_project_model_rejects_malformed_framing_alignment(self):
        for key, value in (("horizontal_alignment", []), ("vertical_alignment", {})):
            with self.subTest(key=key):
                self.project["tracks"][0]["clips"][0]["framing"] = {
                    "mode": "fit", key: value,
                }
                with self.assertRaisesRegex(ValueError, f"framing.{key}"):
                    compile_render_plan(self.project, self.root)

    def test_project_model_rejects_unknown_framing_mode(self):
        self.project["tracks"][0]["clips"][0]["framing"] = {"mode": "smart_crop"}
        with self.assertRaisesRegex(ValueError, "framing.mode is unsupported"):
            compile_render_plan(self.project, self.root)


class FramingFilterTests(unittest.TestCase):
    class RecordingFilter:
        def __init__(self):
            self.settings = {}

        def is_valid(self):
            return True

        def set(self, name, value):
            self.settings[name] = value

    class RecordingMlt:
        def __init__(self):
            self.filter = FramingFilterTests.RecordingFilter()

        def Filter(self, profile, service):
            if service != "affine":
                raise AssertionError(f"Unexpected filter service: {service}")
            return self.filter

    class RecordingProducer:
        def __init__(self):
            self.filters = []

        def attach(self, filter_instance):
            self.filters.append(filter_instance)

    def test_fit_fill_and_stretch_compile_to_documented_affine_flags(self):
        expected = {
            "fit": (1, 0),
            "fill": (1, 0),
            "stretch": (1, 1),
        }
        for mode, (fill, distort) in expected.items():
            with self.subTest(mode=mode):
                mlt = self.RecordingMlt()
                producer = self.RecordingProducer()
                _apply_clip_transform(
                    mlt, object(), producer, {
                        "rect": "0.000/0.000:320.000x180.000:1.000",
                        "rotation": 0.0,
                        "opacity_enabled": False,
                        "framing": {
                            "mode": mode,
                            "horizontal_alignment": "center",
                            "vertical_alignment": "middle",
                        },
                    },
                )
                settings = mlt.filter.settings
                self.assertEqual(settings["transition.fill"], fill)
                self.assertEqual(settings["transition.distort"], distort)
                self.assertEqual(settings["transition.halign"], "center")
                self.assertEqual(settings["transition.valign"], "middle")


class ManualCropRenderPlanTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.project = make_project(self.root)

    def tearDown(self):
        self.temp.cleanup()

    def test_compiles_normalized_manual_crop_to_source_space_affine_rect(self):
        from unittest.mock import patch

        self.project["tracks"][0]["clips"][0]["crop"] = {
            "x": 0.25, "y": 0.25, "width": 0.5, "height": 0.5,
        }
        with patch("mlt_engine.renderer._probe_media_dimensions", return_value=(320, 240)):
            clip = compile_render_plan(self.project, self.root)["tracks"][0]["clips"][0]
        self.assertEqual(clip["transform"]["rect"], "-160.000/-120.000:640.000x480.000:1.000")
        self.assertEqual(clip["transform"]["crop"], {
            "x": 0.25, "y": 0.25, "width": 0.5, "height": 0.5,
        })

    def test_manual_crop_fails_closed_without_readable_source_dimensions(self):
        from mlt_engine.renderer import _compile_clip_transform

        with self.assertRaisesRegex(MltRenderError, "Manual crop requires readable source"):
            _compile_clip_transform(
                {
                    "crop": {"x": 0.1, "y": 0.1, "width": 0.8, "height": 0.8},
                    "keyframes": [],
                },
                320, 240, 25, 1, 50,
            )

    def test_manual_crop_compiles_to_centered_cover_affine_filter(self):
        mlt = FramingFilterTests.RecordingMlt()
        producer = FramingFilterTests.RecordingProducer()
        _apply_clip_transform(
            mlt, object(), producer, {
                "rect": "-160.000/-120.000:640.000x480.000:1.000",
                "rotation": 0.0,
                "opacity_enabled": False,
                "crop": {"x": 0.25, "y": 0.25, "width": 0.5, "height": 0.5},
            },
        )
        settings = mlt.filter.settings
        self.assertEqual(settings["transition.fill"], 1)
        self.assertEqual(settings["transition.distort"], 0)
        self.assertEqual(settings["transition.halign"], "center")
        self.assertEqual(settings["transition.valign"], "middle")


class TransformFlipTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.project = make_project(self.root)

    def tearDown(self):
        self.temp.cleanup()

    def test_render_plan_retains_horizontal_and_vertical_flip_flags(self):
        self.project["tracks"][0]["clips"][0]["transform"] = {
            "position": {"x": 0, "y": 0},
            "scale": {"x": 1, "y": 1},
            "rotation_deg": 0,
            "opacity": 1,
            "flip_horizontal": True,
            "flip_vertical": True,
        }
        transform = compile_render_plan(self.project, self.root)["tracks"][0]["clips"][0]["transform"]
        self.assertTrue(transform["flip_horizontal"])
        self.assertTrue(transform["flip_vertical"])

    def test_horizontal_flip_preserves_the_original_manual_crop_selection(self):
        from unittest.mock import patch

        clip = self.project["tracks"][0]["clips"][0]
        clip["crop"] = {"x": 0.1, "y": 0.1, "width": 0.2, "height": 0.8}
        clip["transform"] = {
            "position": {"x": 0, "y": 0},
            "scale": {"x": 1, "y": 1},
            "rotation_deg": 0,
            "opacity": 1,
            "flip_horizontal": True,
            "flip_vertical": False,
        }
        with patch("mlt_engine.renderer._probe_media_dimensions", return_value=(320, 240)):
            transform = compile_render_plan(self.project, self.root)["tracks"][0]["clips"][0]["transform"]
        self.assertEqual(transform["rect"], "-1120.000/-480.000:1600.000x1200.000:1.000")
        self.assertTrue(transform["flip_horizontal"])

    def test_mlt_flip_filters_are_attached_before_the_affine_transform(self):
        class Filter:
            def __init__(self, service):
                self.service = service
                self.settings = {}

            def is_valid(self):
                return True

            def set(self, key, value):
                self.settings[key] = value

        class Mlt:
            def __init__(self):
                self.filters = []

            def Filter(self, profile, service):
                item = Filter(service)
                self.filters.append(item)
                return item

        class Producer:
            def __init__(self):
                self.filters = []

            def attach(self, item):
                self.filters.append(item)

        mlt = Mlt()
        producer = Producer()
        _apply_clip_transform(mlt, object(), producer, {
            "rect": "0.000/0.000:320.000x240.000:1.000",
            "rotation": 0.0,
            "opacity_enabled": False,
            "flip_horizontal": True,
            "flip_vertical": True,
        })
        self.assertEqual(
            [item.service for item in producer.filters],
            ["avfilter.hflip", "avfilter.vflip", "affine"],
        )

    def test_missing_mlt_flip_filter_is_rejected(self):
        class Filter:
            def __init__(self, service):
                self.service = service

            def is_valid(self):
                return self.service != "avfilter.hflip"

        class Mlt:
            def Filter(self, profile, service):
                return Filter(service)

        class Producer:
            def attach(self, item):
                raise AssertionError("Invalid filter must not be attached.")

        with self.assertRaisesRegex(MltRenderError, "avfilter.hflip"):
            _apply_clip_transform(mlt=Mlt(), profile=object(), producer=Producer(), transform={
                "rect": "0.000/0.000:320.000x240.000:1.000",
                "rotation": 0.0,
                "opacity_enabled": False,
                "flip_horizontal": True,
                "flip_vertical": False,
            })


class RotationPivotRenderTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.project = make_project(self.root)

    def tearDown(self):
        self.temp.cleanup()

    def test_non_centre_pivot_compensates_affine_rect_before_rotation(self):
        self.project["tracks"][0]["clips"][0]["transform"] = {
            "position": {"x": 0, "y": 0},
            "scale": {"x": 1, "y": 1},
            "rotation_deg": 90,
            "opacity": 1,
            "anchor_x": 0,
            "anchor_y": 0.5,
        }
        transform = compile_render_plan(self.project, self.root)["tracks"][0]["clips"][0]["transform"]
        self.assertEqual(transform["rect"], "-160.000/160.000:320.000x240.000:1.000")

    def test_default_centre_pivot_keeps_existing_rotation_geometry(self):
        self.project["tracks"][0]["clips"][0]["transform"] = {
            "position": {"x": 0, "y": 0},
            "scale": {"x": 1, "y": 1},
            "rotation_deg": 90,
            "opacity": 1,
            "anchor_x": 0.5,
            "anchor_y": 0.5,
        }
        transform = compile_render_plan(self.project, self.root)["tracks"][0]["clips"][0]["transform"]
        self.assertEqual(transform["rect"], "0.000/0.000:320.000x240.000:1.000")


class RippleInsertRenderPlanTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.project = make_project(self.root)

    def tearDown(self):
        self.temp.cleanup()

    def test_ripple_inserted_clip_renders_before_shifted_clips_on_its_track(self):
        track = self.project["tracks"][0]
        existing = track["clips"][0]
        existing["start_us"] = 1_000_000
        track["clips"].append({
            "id": "inserted-clip",
            "kind": "video",
            "media_id": "asset-video",
            "start_us": 0,
            "duration_us": 1_000_000,
            "source_in_us": 0,
            "source_out_us": 1_000_000,
            "playback_rate": 1.0,
            "effects": [],
            "keyframes": [],
        })
        planned = compile_render_plan(self.project, self.root)["tracks"][0]["clips"]
        self.assertEqual([item["id"] for item in planned], ["inserted-clip", existing["id"]])
        self.assertEqual([item["start_frame"] for item in planned], [0, 25])
        self.assertEqual([item["duration_frames"] for item in planned], [25, 50])


class SlipEditRenderPlanTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.project = make_project(self.root)

    def tearDown(self):
        self.temp.cleanup()

    def test_slipped_clip_renders_the_new_source_window_without_timeline_change(self):
        clip = self.project["tracks"][0]["clips"][0]
        clip["source_in_us"] = 500_000
        clip["source_out_us"] = 2_500_000
        plan_clip = compile_render_plan(self.project, self.root)["tracks"][0]["clips"][0]
        self.assertEqual(plan_clip["source_in_frame"], 13)
        self.assertEqual(plan_clip["source_out_frame"], 62)
        self.assertEqual(plan_clip["start_frame"], 0)
        self.assertEqual(plan_clip["duration_frames"], 50)


class ClipSourceReplacementRenderPlanTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.project = make_project(self.root)

    def tearDown(self):
        self.temp.cleanup()

    def test_replaced_clip_render_plan_points_to_the_new_media_asset(self):
        replacement = self.root / "replacement.mp4"
        replacement.write_bytes(b"replacement video source")
        self.project["assets"].append({
            "id": "asset-replacement",
            "media_type": "video",
            "file_name": "replacement.mp4",
            "storage_key": "replacement.mp4",
            "size_bytes": replacement.stat().st_size,
            "duration_us": 8_000_000,
        })
        clip = self.project["tracks"][0]["clips"][0]
        clip["media_id"] = "asset-replacement"
        plan_clip = compile_render_plan(self.project, self.root)["tracks"][0]["clips"][0]
        self.assertEqual(plan_clip["media_id"], "asset-replacement")
        self.assertEqual(plan_clip["path"], replacement.resolve())


class TrackVisibilityRenderTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.project = make_project(self.root)

    def tearDown(self):
        self.temp.cleanup()

    def test_render_plan_keeps_invisible_visual_track_audio_unmuted(self):
        self.project["tracks"][0]["visible"] = False
        track = compile_render_plan(self.project, self.root)["tracks"][0]
        self.assertFalse(track["visible"])
        self.assertFalse(track["muted"])

    def test_mlt_hide_flags_keep_visual_visibility_and_audio_mute_independent(self):
        from mlt_engine.renderer import _playlist_hide_flags

        self.assertEqual(_playlist_hide_flags({
            "type": "video", "visible": True, "muted": False,
        }), 0)
        self.assertEqual(_playlist_hide_flags({
            "type": "video", "visible": False, "muted": False,
        }), 1)
        self.assertEqual(_playlist_hide_flags({
            "type": "video", "visible": True, "muted": True,
        }), 2)
        self.assertEqual(_playlist_hide_flags({
            "type": "video", "visible": False, "muted": True,
        }), 3)
        self.assertEqual(_playlist_hide_flags({
            "type": "audio", "visible": True, "muted": False,
        }), 1)
        self.assertEqual(_playlist_hide_flags({
            "type": "audio", "visible": True, "muted": True,
        }), 3)


class GeneratedFreezeFrameMltRenderTests(unittest.TestCase):
    """Exercise extraction -> timeline hold -> real MLT render -> decoded pixels."""
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.project = make_project(self.root)

    def tearDown(self):
        self.temp.cleanup()


    @unittest.skipUnless(
        importlib.util.find_spec("mlt7") is not None
        and shutil.which("ffmpeg")
        and shutil.which("ffprobe"),
        "The real MLT/FFmpeg runtime is not installed.",
    )
    def test_generated_freeze_frame_is_visible_for_the_full_hold_duration(self):
        import json
        import subprocess
        from project_tool_executor import ProjectToolExecutor
        from mlt_engine.renderer import render_project

        root = self.root
        base = root / "source.mp4"
        freeze_source = root / "freeze-source.mp4"
        output = root / "freeze-frame-hold-render.mp4"

        def make_colour_video(path, colour, duration):
            subprocess.run([
                "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                "-f", "lavfi", "-i",
                f"color=c={colour}:s=320x240:r=25:d={duration}",
                "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(path),
            ], check=True, capture_output=True, text=True, timeout=120)

        make_colour_video(base, "blue", 3)
        make_colour_video(freeze_source, "red", 2)
        self.project["assets"][0].update({
            "size_bytes": base.stat().st_size, "duration_us": 3_000_000,
        })
        main_clip = self.project["tracks"][0]["clips"][0]
        main_clip.update({"duration_us": 3_000_000, "source_out_us": 3_000_000})
        self.project["assets"].append({
            "id": "freeze-source", "media_type": "video",
            "file_name": freeze_source.name, "storage_key": freeze_source.name,
            "size_bytes": freeze_source.stat().st_size, "duration_us": 2_000_000,
        })
        self.project["tracks"].append({
            "id": "track-overlay", "type": "overlay", "name": "Freeze holds",
            "order": 1, "locked": False, "clips": [],
        })

        executor = ProjectToolExecutor(self.project, asset_root=root)
        result = executor.execute("timeline.create_freeze_frame", {
            "media_id": "freeze-source", "track_id": "track-overlay",
            "timestamp_us": 500_000, "start_us": 1_000_000,
            "duration_us": 1_500_000,
        })
        generated = result["results"][0]["result"]
        generated_asset = next(
            item for item in executor.get_project()["assets"]
            if item["id"] == generated["media_id"]
        )
        still_path = root / generated_asset["storage_key"]
        self.assertTrue(still_path.is_file())
        self.assertGreater(still_path.stat().st_size, 0)

        receipt = render_project(executor.get_project(), root, output, timeout_seconds=120)
        self.assertTrue(receipt["ok"])
        self.assertTrue(output.is_file())
        self.assertGreater(output.stat().st_size, 0)

        def centre_rgb(timestamp):
            decoded = subprocess.run([
                "ffmpeg", "-hide_banner", "-loglevel", "error",
                "-i", str(output), "-ss", f"{timestamp:.3f}",
                "-vf", "crop=20:20:150:110,scale=1:1:flags=area,format=rgb24",
                "-frames:v", "1", "-f", "rawvideo", "-",
            ], check=True, capture_output=True, timeout=60)
            self.assertEqual(len(decoded.stdout), 3)
            return tuple(decoded.stdout)

        before_hold = centre_rgb(0.5)
        during_hold = centre_rgb(1.25)
        near_hold_end = centre_rgb(2.4)
        after_hold = centre_rgb(2.7)
        self.assertGreater(before_hold[2], 150, f"Expected blue before hold, got {before_hold}")
        for timestamp, pixel in ((1.25, during_hold), (2.4, near_hold_end)):
            self.assertGreater(pixel[0], 150, f"Expected red freeze at {timestamp}s, got {pixel}")
            self.assertLess(pixel[1], 90, f"Unexpected green at {timestamp}s: {pixel}")
            self.assertLess(pixel[2], 90, f"Unexpected blue at {timestamp}s: {pixel}")
        self.assertGreater(after_hold[2], 150, f"Expected blue after hold, got {after_hold}")
