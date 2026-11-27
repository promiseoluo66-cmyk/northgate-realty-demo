"""Keep the master feature catalogue aligned with the implemented tool registry."""

import json
import unittest
from pathlib import Path

from tool_registry import get_tool_catalog


CATALOGUE_PATH = (
    Path(__file__).resolve().parents[1]
    / "architecture"
    / "CAPCUT_PARITY_CAPABILITIES.json"
)


class CapabilityCatalogueTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalogue = json.loads(CATALOGUE_PATH.read_text(encoding="utf-8"))
        cls.features = [
            feature
            for category in cls.catalogue["categories"]
            for feature in category["features"]
        ]

    def test_capability_ids_are_unique_and_count_matches_audit(self):
        ids = [feature[0] for feature in self.features]
        self.assertTrue(ids)
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(
            len(ids),
            self.catalogue["audit"]["capability_entry_count"],
        )

    def test_every_feature_uses_a_known_status(self):
        allowed = set(self.catalogue["status_vocabulary"])
        for feature_id, description, status in self.features:
            with self.subTest(feature_id=feature_id):
                self.assertTrue(feature_id)
                self.assertTrue(description)
                self.assertIn(status, allowed)

    def test_status_totals_match_the_feature_rows(self):
        actual = {}
        for _, _, status in self.features:
            actual[status] = actual.get(status, 0) + 1
        self.assertEqual(actual, self.catalogue["audit"]["status_counts"])

    def test_registered_tool_count_matches_the_real_registry(self):
        registry = get_tool_catalog()
        names = [tool["name"] for tool in registry]
        self.assertEqual(len(names), len(set(names)))
        self.assertEqual(self.catalogue["audit"]["registered_tool_count"], 34)
        self.assertEqual(self.catalogue["audit"]["stage1_registered_tool_count"], 52)
        self.assertEqual(self.catalogue["audit"]["stage2_registered_tool_count"], 54)
        self.assertEqual(len(names), 54)
        self.assertTrue(self.catalogue["audit"]["registered_tool_names_are_unique"])
        self.assertTrue(self.catalogue["audit"]["stage1_registered_tool_names_are_unique"])

    def test_stage1_registry_additions_are_present(self):
        names = {tool["name"] for tool in get_tool_catalog()}
        self.assertTrue({
            "track.reorder", "animation.remove_keyframe",
            "animation.clear_keyframes", "media.organize_asset",
            "clip.set_crop", "timeline.replace_clip_media",
            "timeline.slip_clip", "timeline.ripple_insert_clip",
            "captions.import_subtitles",
            "timeline.ripple_overwrite_clip",
            "timeline.group_clips",
            "timeline.ungroup_clips",
            "timeline.add_marker",
            "timeline.move_marker",
            "timeline.remove_marker", "media.create_proxy",
        }.issubset(names))

    def test_six_reference_derived_capabilities_are_present(self):
        ids = {feature[0] for feature in self.features}
        self.assertTrue({
            "transcript_driven_editing",
            "audio_sync",
            "technical_quality_inspection",
            "visual_review_evidence",
            "reference_matching",
            "workflow_quality_receipts",
        }.issubset(ids))


if __name__ == "__main__":
    unittest.main()
