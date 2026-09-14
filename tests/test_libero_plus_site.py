import json
from pathlib import Path
import shutil
import tempfile
import unittest

from robot_reel.libero_plus_site import inspect, verify

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "docs/libero-plus"


class LiberoPlusSiteTests(unittest.TestCase):
    def test_recorded_case_and_external_script_match(self):
        result = verify(SITE)
        self.assertTrue(result["valid"])
        self.assertTrue(all(result["checks"].values()))
        self.assertEqual(
            (SITE / "libero_plus.js").read_bytes(),
            (ROOT / "robot_reel/libero_plus.js").read_bytes(),
        )

    def test_initial_physics_and_early_terminal_claims_are_checked(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "case"
            shutil.copytree(SITE, root)
            target = root / "camera-viewpoints/initial-state.json"
            original = target.read_text()
            document = json.loads(original)
            document["qpos"][0] += 0.01
            target.write_text(json.dumps(document))
            with self.assertRaisesRegex(ValueError, "initial physical states differ"):
                inspect(root)
            target.write_text(original)
            target = root / "camera-viewpoints/run.json"
            document = json.loads(target.read_text())
            document["frames"][0]["success"] = True
            target.write_text(json.dumps(document))
            with self.assertRaisesRegex(ValueError, "terminal state"):
                inspect(root)
