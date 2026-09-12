import copy
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from robot_reel.blender import export_blender, scene_document, verify_export
from robot_reel.compare import digest

SOURCE = Path(__file__).resolve().parents[1] / "docs/compare/braking"


class BlenderExportTest(unittest.TestCase):
    def test_export_preserves_all_samples_and_source_hashes(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "blender"
            document = export_blender(SOURCE, output)
            self.assertEqual(verify_export(output), {"kind": "braking", "frames": 180, "fps": 30})
            for side, run in zip(("left", "right"), document["runs"]):
                original = json.loads((SOURCE / f"{side}-trace.json").read_text())
                self.assertEqual(run["frames"], original["frames"])
                self.assertEqual(run["outcome"], original["outcome"])
                self.assertEqual(digest(output / f"{side}-trace.json"), digest(SOURCE / f"{side}-trace.json"))
            self.assertIn("CONSTANT", document["interpolation"])
            self.assertTrue((output / "build_scene.py").is_file())
            with self.assertRaisesRegex(ValueError, "empty"):
                export_blender(SOURCE, output)

    def test_tampering_and_rehashed_motion_changes_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "blender"
            export_blender(SOURCE, output)
            scene = json.loads((output / "scene.json").read_text())
            scene["runs"][0]["frames"][0]["qpos"][2] += 1
            (output / "scene.json").write_text(json.dumps(scene))
            with self.assertRaisesRegex(ValueError, "hash mismatch"):
                verify_export(output)
            manifest = json.loads((output / "blender-manifest.json").read_text())
            manifest["sha256"]["scene.json"] = digest(output / "scene.json")
            (output / "blender-manifest.json").write_text(json.dumps(manifest))
            with self.assertRaisesRegex(ValueError, "disagrees"):
                verify_export(output)

    def test_geometry_and_time_must_agree_with_the_recording(self):
        traces = [json.loads((SOURCE / f"{s}-trace.json").read_text()) for s in ("left", "right")]
        changed = copy.deepcopy(traces)
        changed[0]["frames"][0]["qpos"][2] += 1
        with self.assertRaisesRegex(ValueError, "geometry"):
            scene_document(changed, ["Left", "Right"])
        changed = copy.deepcopy(traces)
        changed[1]["frames"][0]["sim_time"] += .1
        with self.assertRaisesRegex(ValueError, "timestamps"):
            scene_document(changed, ["Left", "Right"])
        changed = copy.deepcopy(traces)
        for trace in changed:
            trace["units"] = ["mph", "m", "m"]
        with self.assertRaisesRegex(ValueError, "channels"):
            scene_document(changed, ["Left", "Right"])

    def test_unsupported_pack_is_rejected_before_output_creation(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "blender"
            with self.assertRaisesRegex(ValueError, "braking"):
                export_blender(SOURCE.parent / "microduck", output)
            self.assertFalse(output.exists())

    def test_export_cannot_modify_source_bundle(self):
        with self.assertRaisesRegex(ValueError, "outside"):
            export_blender(SOURCE, SOURCE / "blender")

    def test_published_demo_and_downloads_are_consistent(self):
        site = SOURCE.parents[1] / "blender"
        media = json.loads((site / "media-manifest.json").read_text())
        self.assertEqual((media["frames"], media["fps"]), (180, 30))
        for filename, expected in media["sha256"].items():
            self.assertEqual(Path(filename).name, filename)
            self.assertEqual(digest(site / filename), expected, filename)
        with tempfile.TemporaryDirectory() as directory:
            extracted = Path(directory)
            with zipfile.ZipFile(site / "robot-reel-blender.zip") as archive:
                self.assertTrue(all(Path(n).name == n for n in archive.namelist()))
                archive.extractall(extracted)
            self.assertEqual(verify_export(extracted)["frames"], 180)
            report = json.loads((extracted / "animation-check.json").read_text())
            self.assertEqual(report["checked_vehicle_samples"], 360)
            self.assertLess(report["maximum_position_error_m"], 1e-5)
            self.assertEqual(report["blend_sha256"], digest(site / "replay.blend"))
            self.assertEqual(report["scene_json_sha256"], digest(extracted / "scene.json"))
