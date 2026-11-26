"""Sanity checks for the registered editor-operation inventory."""
import inspect
import unittest

from project_tool_executor import ProjectToolExecutor
from tool_registry import get_tool_catalog


class OperationInventoryAuditTests(unittest.TestCase):
    def test_registry_has_49_unique_operations(self):
        names = [item["name"] for item in get_tool_catalog()]
        self.assertEqual(len(names), 49)
        self.assertEqual(len(set(names)), 49)

    def test_each_registered_tool_has_an_executor_dispatch_reference(self):
        source = inspect.getsource(ProjectToolExecutor)
        missing = [name for name in (item["name"] for item in get_tool_catalog())
                   if f'"{name}"' not in source]
        self.assertEqual(missing, [], f"Missing executor dispatch reference(s): {missing}")


if __name__ == "__main__":
    unittest.main()
