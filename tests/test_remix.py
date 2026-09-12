import json
from pathlib import Path
import shutil
import tempfile
import unittest

from robot_reel.compare import digest
from scripts.build_remix_site import checked_scene, verify_site

DOCS = Path(__file__).resolve().parents[1]/"docs"


class RemixTest(unittest.TestCase):
    def test_published_views_share_all_source_samples_and_contact_outcomes(self):
        self.assertEqual(verify_site(), {"frames": 180, "fps": 30, "checked_vehicle_samples": 360})
        scene = checked_scene()
        for side, run in zip(("left", "right"), scene["runs"]):
            original = json.loads((DOCS/f"compare/braking/{side}-trace.json").read_text())
            self.assertEqual(run["frames"], original["frames"])
            self.assertEqual(run["outcome"], original["outcome"])
        self.assertFalse(scene["runs"][0]["outcome"]["collision"])
        self.assertTrue(scene["runs"][1]["frames"][107]["collision"])

    def test_rehashed_viewer_cannot_disagree_with_its_original_recording(self):
        with tempfile.TemporaryDirectory() as temporary:
            docs = Path(temporary)
            for folder in ("compare/braking", "blender", "remix"):
                shutil.copytree(DOCS/folder, docs/folder)
            path = docs/"remix/index.html"
            html = path.read_text()
            marker = '<script id="scene-data" type="application/json">'
            prefix, rest = html.split(marker, 1)
            payload, suffix = rest.split("</script>", 1)
            scene = json.loads(payload)
            scene["runs"][0]["frames"][0]["qpos"][0] += 1
            path.write_text(prefix+marker+json.dumps(scene)+"</script>"+suffix)
            manifest_path = docs/"remix/manifest.json"
            manifest = json.loads(manifest_path.read_text())
            manifest["sha256"]["index.html"] = digest(path)
            manifest_path.write_text(json.dumps(manifest))
            with self.assertRaisesRegex(ValueError, "viewer differs"):
                verify_site(docs)
