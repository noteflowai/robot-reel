import json
from pathlib import Path
import shutil
import tempfile
import unittest

from robot_reel.scene_lab import checked_scene, verify

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "docs/scene-lab"


class SceneLabTests(unittest.TestCase):
    def test_published_evidence_and_external_script_match(self):
        self.assertTrue(verify(SITE)["valid"])
        self.assertEqual(
            (SITE / "scene_lab.js").read_bytes(),
            (ROOT / "robot_reel/scene_lab.js").read_bytes(),
        )

    def test_changed_splat_and_false_native_readback_are_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "baseline"
            shutil.copytree(SITE / "baseline", root)
            path = root / "terrain.splat"
            original = path.read_bytes()
            path.write_bytes(bytes([original[0] ^ 1]) + original[1:])
            with self.assertRaisesRegex(ValueError, "identity differs"):
                checked_scene(root, native=False)
            path.write_bytes(original)
            native = json.loads((root / "native-check.json").read_text())
            native["scene_sha256"] = "0" * 64
            (root / "native-check.json").write_text(json.dumps(native))
            with self.assertRaisesRegex(ValueError, "readback is inconsistent"):
                checked_scene(root, native=False)
