"""Sanity checks for the registered editor-operation inventory."""

import inspect
import unittest

from project_tool_executor import ProjectRevisionConflict, ProjectToolExecutionError, ProjectToolExecutor
from tool_registry import (
    ToolValidationError,
    _validate_value,
    get_tool_catalog,
    tool_requires_confirmation,
    validate_tool_call,
)


class OperationInventoryAuditTests(unittest.TestCase):
    def test_registry_has_58_unique_operations(self):
        names = [item["name"] for item in get_tool_catalog()]
        self.assertEqual(len(names), 58)
        self.assertEqual(len(set(names)), 58)

    def test_each_registered_tool_has_an_executor_dispatch_reference(self):
        source = inspect.getsource(ProjectToolExecutor)
        missing = [
            name for name in (item["name"] for item in get_tool_catalog())
            if f'"{name}"' not in source
        ]
        self.assertEqual(missing, [], f"Missing executor dispatch reference(s): {missing}")

    def test_every_registered_tool_rejects_unrecognised_arguments(self):
        for item in get_tool_catalog():
            with self.subTest(operation=item["name"]):
                with self.assertRaises(ToolValidationError):
                    validate_tool_call(item["name"], {"unexpected_audit_field": True})

    def test_every_operation_schema_is_closed_and_has_valid_required_fields(self):
        for item in get_tool_catalog():
            with self.subTest(operation=item["name"]):
                schema = item["input_schema"]
                self.assertEqual(schema.get("type"), "object")
                self.assertIs(schema.get("additionalProperties"), False)
                properties = schema.get("properties", {})
                self.assertTrue(set(schema.get("required", [])).issubset(properties))

                # Every required top-level field is independently enforced.
                required = schema.get("required", [])
                for missing in required:
                    arguments = {key: None for key in required if key != missing}
                    with self.assertRaises(ToolValidationError):
                        validate_tool_call(item["name"], arguments)

    def test_all_declared_numeric_bounds_reject_values_outside_the_contract(self):
        def walk(schema, path):
            if not isinstance(schema, dict):
                return
            kind = schema.get("type")
            if kind in {"integer", "number"}:
                if "minimum" in schema:
                    value = schema["minimum"] - 1
                    with self.subTest(path=path, boundary="minimum"):
                        with self.assertRaises(ToolValidationError):
                            _validate_value(value, schema, path)
                if "maximum" in schema:
                    value = schema["maximum"] + 1
                    with self.subTest(path=path, boundary="maximum"):
                        with self.assertRaises(ToolValidationError):
                            _validate_value(value, schema, path)
            for key, child in schema.get("properties", {}).items():
                walk(child, path + "." + key)
            items = schema.get("items")
            if isinstance(items, dict):
                walk(items, path + "[]")

        for item in get_tool_catalog():
            walk(item["input_schema"], item["name"])

    def test_identifier_arrays_reject_path_like_and_malformed_track_ids(self):
        with self.assertRaisesRegex(ToolValidationError, "valid project identifier"):
            validate_tool_call("timeline.ripple_insert_clip", {
                "track_id": "track-main",
                "ripple_track_ids": ["track-safe", "../outside"],
                "kind": "video",
                "media_id": "media-source",
                "start_us": 0,
                "duration_us": 1,
            })
        accepted = validate_tool_call("timeline.ripple_insert_clip", {
            "track_id": "track-main",
            "ripple_track_ids": ["track-safe", "track-secondary"],
            "kind": "video",
            "media_id": "media-source",
            "start_us": 0,
            "duration_us": 1,
        })
        self.assertEqual(accepted["ripple_track_ids"], ["track-safe", "track-secondary"])

    def test_every_registered_operation_is_blocked_by_stale_revision_without_mutation(self):
        project = {
            "schema_version": 1,
            "id": "operation-audit-project",
            "name": "Operation audit",
            "revision": 1,
            "timeline_timebase": "microseconds",
            "video_profile": {
                "width": 320, "height": 240,
                "frame_rate": {"numerator": 25, "denominator": 1},
            },
            "assets": [],
            "tracks": [{
                "id": "track-main", "type": "video", "name": "Main",
                "order": 0, "locked": False, "clips": [],
            }],
            "transitions": [],
        }
        for item in get_tool_catalog():
            with self.subTest(operation=item["name"]):
                executor = ProjectToolExecutor(project)
                before = executor.get_project()
                with self.assertRaises(ProjectRevisionConflict):
                    executor.execute(
                        item["name"], {}, expected_revision=0, confirmed=True
                    )
                self.assertEqual(executor.get_project(), before)
                self.assertEqual(executor.revision, 1)

    def test_failed_multi_operation_batch_rolls_back_earlier_valid_mutation(self):
        project = {
            "schema_version": 1,
            "id": "operation-atomicity-audit",
            "name": "Atomicity audit",
            "revision": 1,
            "timeline_timebase": "microseconds",
            "video_profile": {
                "width": 320, "height": 240,
                "frame_rate": {"numerator": 25, "denominator": 1},
            },
            "assets": [],
            "tracks": [{
                "id": "track-main", "type": "video", "name": "Main",
                "order": 0, "locked": False, "clips": [],
            }],
            "transitions": [],
        }
        executor = ProjectToolExecutor(project)
        before = executor.get_project()
        with self.assertRaises(ProjectToolExecutionError):
            executor.execute_batch([
                {"name": "timeline.add_track", "arguments": {
                    "track_type": "audio", "name": "Temporary audio"
                }},
                {"name": "timeline.move_clip", "arguments": {
                    "clip_id": "missing-clip", "start_us": 1000000
                }},
            ], expected_revision=1)
        self.assertEqual(executor.get_project(), before)
        self.assertEqual(executor.revision, 1)

    def test_undo_redo_restores_project_state_as_separate_revisioned_transactions(self):
        project = {
            "schema_version": 1,
            "id": "operation-history-audit",
            "name": "History audit",
            "revision": 1,
            "timeline_timebase": "microseconds",
            "video_profile": {
                "width": 320, "height": 240,
                "frame_rate": {"numerator": 25, "denominator": 1},
            },
            "assets": [],
            "tracks": [{
                "id": "track-main", "type": "video", "name": "Main",
                "order": 0, "locked": False, "clips": [],
            }],
            "transitions": [],
        }
        executor = ProjectToolExecutor(project)
        before = executor.get_project()
        executor.execute(
            "timeline.add_track",
            {"track_type": "audio", "name": "Audio"},
            expected_revision=1,
        )
        self.assertEqual(len(executor.get_project()["tracks"]), 2)
        executor.execute("history.undo", {}, expected_revision=2)
        self.assertEqual(executor.get_project()["tracks"], before["tracks"])
        executor.execute("history.redo", {}, expected_revision=3)
        self.assertEqual(len(executor.get_project()["tracks"]), 2)
        self.assertEqual(executor.revision, 4)

    def test_only_the_five_destructive_or_export_operations_require_confirmation(self):
        expected = {
            "timeline.remove_track",
            "timeline.delete_clip",
            "timeline.ripple_delete_clip",
            "render.export",
            "transcript.apply_cut",
            "transcript.apply_silence_cut",
        }
        actual = {
            item["name"] for item in get_tool_catalog()
            if item["requires_confirmation"]
        }
        self.assertEqual(actual, expected)
        for name in expected:
            self.assertTrue(tool_requires_confirmation(name))


if __name__ == "__main__":
    unittest.main()
