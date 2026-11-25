"""Unit tests for registered project-tool contracts and execution."""

import unittest

from tool_registry import (
    ToolValidationError,
    get_tool_catalog,
    tool_requires_confirmation,
    validate_tool_call,
)


class ToolRegistryTests(unittest.TestCase):
    def test_catalog_contains_only_engine_backed_tools(self):
        names = {item["name"] for item in get_tool_catalog()}
        self.assertTrue({
            "project.inspect", "media.list", "timeline.add_track",
            "timeline.add_clip", "timeline.add_text_clip",
            "timeline.split_clip", "timeline.trim_clip",
            "clip.set_transform", "clip.set_framing", "animation.set_keyframe",
            "effect.add", "timeline.add_transition",
            "audio.set_gain", "audio.set_fade", "render.export",
        }.issubset(names))
        self.assertNotIn("system.run_shell", names)

    def test_quality_inspection_is_registered_as_read_only(self):
        catalog = {item["name"]: item for item in get_tool_catalog()}
        self.assertIn("quality.inspect_media", catalog)
        self.assertIn("audio.analyze_media", catalog)
        self.assertTrue(catalog["audio.analyze_media"]["read_only"])
        self.assertTrue(catalog["quality.inspect_media"]["read_only"])
        self.assertIn("media.detect_scenes", catalog)
        self.assertTrue(catalog["media.detect_scenes"]["read_only"])
        self.assertEqual(
            validate_tool_call("quality.inspect_media", {"media_id": "source-video"}),
            {"media_id": "source-video"},
        )

    def test_clip_framing_contract_accepts_supported_modes_and_rejects_unknown_modes(self):
        clean = validate_tool_call("clip.set_framing", {
            "clip_id": "clip-1",
            "mode": "fill",
            "horizontal_alignment": "right",
            "vertical_alignment": "top",
        })
        self.assertEqual(clean["mode"], "fill")
        with self.assertRaisesRegex(ToolValidationError, "allowed choices"):
            validate_tool_call("clip.set_framing", {
                "clip_id": "clip-1", "mode": "smart_crop",
            })

    def test_unknown_tool_is_rejected(self):
        with self.assertRaisesRegex(ToolValidationError, "not registered"):
            validate_tool_call("system.run_shell", {"command": "ffmpeg"})

    def test_required_and_unknown_arguments_are_rejected(self):
        with self.assertRaisesRegex(ToolValidationError, "missing required"):
            validate_tool_call("timeline.add_track", {"track_type": "video"})
        with self.assertRaisesRegex(ToolValidationError, "unsupported field"):
            validate_tool_call("timeline.move_clip", {
                "clip_id": "clip-1", "start_us": 10, "run_code": "anything",
            })

    def test_numeric_ranges_and_choices_are_enforced(self):
        with self.assertRaisesRegex(ToolValidationError, "above the allowed maximum"):
            validate_tool_call("clip.set_transform", {"clip_id": "clip-1", "opacity": 4})
        with self.assertRaisesRegex(ToolValidationError, "allowed choices"):
            validate_tool_call("timeline.add_transition", {
                "from_clip_id": "a", "to_clip_id": "b",
                "transition_type": "invented", "duration_us": 1000,
            })

    def test_keyframe_property_and_bezier_are_checked(self):
        args = {
            "clip_id": "clip-1", "property": "scale_x",
            "time_us": 100, "value": 1.5,
            "interpolation": "bezier",
            "bezier": {"x1": 0.2, "y1": 0.1, "x2": 0.8, "y2": 1},
        }
        self.assertEqual(validate_tool_call("animation.set_keyframe", args), args)
        with self.assertRaisesRegex(ToolValidationError, "requires control points"):
            validate_tool_call("animation.set_keyframe", {
                "clip_id": "clip-1", "property": "scale_x",
                "time_us": 100, "value": 1.5, "interpolation": "bezier",
            })

    def test_animation_clear_keyframes_contract_accepts_optional_property(self):
        self.assertEqual(
            validate_tool_call("animation.clear_keyframes", {"clip_id": "clip-1"}),
            {"clip_id": "clip-1"},
        )
        self.assertEqual(
            validate_tool_call("animation.clear_keyframes", {
                "clip_id": "clip-1", "property": "opacity",
            }),
            {"clip_id": "clip-1", "property": "opacity"},
        )

    def test_media_organization_tool_has_bounded_folder_and_tag_contract(self):
        self.assertEqual(
            validate_tool_call("media.organize_asset", {
                "media_id": "asset-1", "folder": "B-roll",
                "tags": ["wildlife", "forest"],
            }),
            {"media_id": "asset-1", "folder": "B-roll", "tags": ["wildlife", "forest"]},
        )
        with self.assertRaises(ToolValidationError):
            validate_tool_call("media.organize_asset", {
                "media_id": "asset-1", "folder": "B-roll",
                "tags": ["tag-" + str(index) for index in range(13)],
            })

    def test_transform_contract_accepts_normalized_pivot_coordinates(self):
        self.assertEqual(
            validate_tool_call("clip.set_transform", {
                "clip_id": "clip-1", "anchor_x": 0.2, "anchor_y": 0.8,
            }),
            {"clip_id": "clip-1", "anchor_x": 0.2, "anchor_y": 0.8},
        )
        with self.assertRaises(ToolValidationError):
            validate_tool_call("clip.set_transform", {
                "clip_id": "clip-1", "anchor_x": 1.2,
            })

    def test_transform_contract_accepts_boolean_flip_flags(self):
        self.assertEqual(
            validate_tool_call("clip.set_transform", {
                "clip_id": "clip-1",
                "flip_horizontal": True,
                "flip_vertical": False,
            }),
            {
                "clip_id": "clip-1",
                "flip_horizontal": True,
                "flip_vertical": False,
            },
        )
        with self.assertRaises(ToolValidationError):
            validate_tool_call("clip.set_transform", {
                "clip_id": "clip-1", "flip_horizontal": "yes",
            })

    def test_ripple_insert_clip_contract_requires_compatible_insert_fields(self):
        self.assertEqual(
            validate_tool_call("timeline.ripple_insert_clip", {
                "track_id": "video-track",
                "kind": "video",
                "media_id": "asset-1",
                "start_us": 2_000_000,
                "duration_us": 1_000_000,
            }),
            {
                "track_id": "video-track",
                "kind": "video",
                "media_id": "asset-1",
                "start_us": 2_000_000,
                "duration_us": 1_000_000,
            },
        )

    def test_slip_clip_contract_accepts_bounded_signed_offsets(self):
        self.assertEqual(
            validate_tool_call("timeline.slip_clip", {
                "clip_id": "clip-1", "delta_us": -250_000,
            }),
            {"clip_id": "clip-1", "delta_us": -250_000},
        )
        with self.assertRaises(ToolValidationError):
            validate_tool_call("timeline.slip_clip", {
                "clip_id": "clip-1", "delta_us": -90_000_000_000,
            })

    def test_clip_source_replace_has_a_strict_registered_contract(self):
        self.assertEqual(
            validate_tool_call("timeline.replace_clip_media", {
                "clip_id": "clip-1", "media_id": "asset-2",
            }),
            {"clip_id": "clip-1", "media_id": "asset-2"},
        )
        with self.assertRaises(ToolValidationError):
            validate_tool_call("timeline.replace_clip_media", {
                "clip_id": "clip-1", "media_id": "../asset",
            })

    def test_manual_crop_tool_contract_accepts_normalized_rectangles(self):
        self.assertEqual(
            validate_tool_call("clip.set_crop", {
                "clip_id": "clip-1", "mode": "custom",
                "x": 0.1, "y": 0.2, "width": 0.7, "height": 0.6,
            }),
            {
                "clip_id": "clip-1", "mode": "custom",
                "x": 0.1, "y": 0.2, "width": 0.7, "height": 0.6,
            },
        )
        self.assertEqual(
            validate_tool_call("clip.set_crop", {
                "clip_id": "clip-1", "mode": "none",
            }),
            {"clip_id": "clip-1", "mode": "none"},
        )
        with self.assertRaises(ToolValidationError):
            validate_tool_call("clip.set_crop", {
                "clip_id": "clip-1", "mode": "custom",
                "x": 0, "y": 0, "width": 0, "height": 1,
            })

    def test_track_set_state_accepts_separate_visual_visibility_flag(self):
        self.assertEqual(
            validate_tool_call("track.set_state", {
                "track_id": "track-1", "visible": False,
            }),
            {"track_id": "track-1", "visible": False},
        )
        with self.assertRaises(ToolValidationError):
            validate_tool_call("track.set_state", {
                "track_id": "track-1", "visible": "hidden",
            })

    def test_track_set_state_accepts_optional_solo_flag(self):
        self.assertEqual(
            validate_tool_call("track.set_state", {"track_id": "track-1", "solo": True}),
            {"track_id": "track-1", "solo": True},
        )

    def test_track_reorder_and_keyframe_remove_have_strict_contracts(self):
        self.assertEqual(
            validate_tool_call("track.reorder", {"track_id": "track-1", "order": 2}),
            {"track_id": "track-1", "order": 2},
        )
        self.assertEqual(
            validate_tool_call("animation.remove_keyframe", {
                "clip_id": "clip-1", "property": "opacity", "time_us": 250000,
            }),
            {"clip_id": "clip-1", "property": "opacity", "time_us": 250000},
        )
        with self.assertRaisesRegex(ToolValidationError, "allowed maximum"):
            validate_tool_call("track.reorder", {"track_id": "track-1", "order": 1000})

    def test_only_destructive_and_export_tools_require_confirmation(self):
        self.assertTrue(tool_requires_confirmation("timeline.delete_clip"))
        self.assertTrue(tool_requires_confirmation("timeline.remove_track"))
        self.assertTrue(tool_requires_confirmation("render.export"))
        self.assertFalse(tool_requires_confirmation("animation.set_keyframe"))


if __name__ == "__main__":
    unittest.main()
