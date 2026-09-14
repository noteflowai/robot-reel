import json
import unittest

from robot_reel.libero_plus import read_catalog


class LiberoPlusCatalogTests(unittest.TestCase):
    def test_official_ids_are_distinct_from_runtime_indices(self):
        rows = read_catalog(
            "libero_task_map = {'libero_spatial': ['task_view_0', 'task_light_1']}",
            json.dumps({"libero_spatial": [
                {"id": 1, "name": "task_view_0", "category": "Camera Viewpoints",
                 "difficulty_level": 1},
                {"id": 2, "name": "task_light_1", "category": "Light Conditions",
                 "difficulty_level": 1},
            ]}),
            "libero_spatial",
        )
        self.assertEqual([(row["id"], row["runtime_index"]) for row in rows], [(1, 0), (2, 1)])

    def test_reordered_classification_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "identity mismatch"):
            read_catalog(
                "libero_task_map = {'libero_spatial': ['task']}",
                json.dumps({"libero_spatial": [
                    {"id": 0, "name": "task", "category": "Camera Viewpoints",
                     "difficulty_level": 1},
                ]}),
                "libero_spatial",
            )

    def test_task_map_code_is_never_executed(self):
        with self.assertRaises(ValueError):
            read_catalog(
                "libero_task_map = __import__('os').system('touch /tmp/not-allowed')",
                "{}", "libero_spatial",
            )
