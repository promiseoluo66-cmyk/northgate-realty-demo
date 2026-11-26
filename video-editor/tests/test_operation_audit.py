"""Sanity checks for the registered editor-operation inventory."""

import inspect
import unittest

from project_tool_executor import ProjectToolExecutor
from tool_registry import (
    ToolValidationError,
    _validate_value,
    get_tool_catalog,
    validate_tool_call,
)


class OperationInventoryAuditTests(unittest.TestCase):
    def test_registry_has_51_unique_operations(self):
        names = [item["name"] for item in get_tool_catalog()]
        self.assertEqual(len(names), 51)
        self.assertEqual(len(set(names)), 51)

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


if __name__ == "__main__":
    unittest.main()
