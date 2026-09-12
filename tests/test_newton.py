import copy
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from robot_reel.newton import export_viewer, point, record, validate_trace, verify, write_manifest

DEMO = Path(__file__).resolve().parents[1] / "docs/newton"


class NewtonEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.trace = json.loads((DEMO/"trace.json").read_text())

    def test_published_run_and_blender_check_agree(self):
        result = verify(DEMO)
        self.assertLess(result["max_anchor_error_m"], .001)
        self.assertLess(result["max_joint_error_m"], .001)
        self.assertGreater(result["max_tip_height_m"]-result["min_tip_height_m"], 1)
        report = json.loads((DEMO/"blender-check.json").read_text())
        for key, name in (("trace_sha256", "trace.json"), ("usd_sha256", "scene.usda")):
            self.assertEqual(report[key], hashlib.sha256((DEMO/name).read_bytes()).hexdigest())
        self.assertEqual(report["checked_body_samples"], 2*len(self.trace["frames"]))
        self.assertEqual(report["frame_start"], 1)
        self.assertEqual(report["frame_end"], len(self.trace["frames"]))
        self.assertEqual(report["fps"], 30)
        self.assertLess(report["maximum_transform_error_m"], 1e-5)

    def test_rejects_bad_timestamps_poses_units_and_summary(self):
        mutations = [
            lambda t: t["frames"][1].update(sim_time=0),
            lambda t: t["frames"][1].update(frame=True),
            lambda t: t["frames"][1]["poses"][0].__setitem__(0, float("nan")),
            lambda t: t["frames"][1]["poses"][0].__setitem__(0, True),
            lambda t: t["frames"][1]["poses"][0].__setitem__(6, 0),
            lambda t: t["frames"][1].update(poses=[]),
            lambda t: t["frames"][0]["poses"][0].__setitem__(0, 50),
            lambda t: t["units"].update(quaternion="wxyz"),
            lambda t: t["units"].update(position="cm"),
            lambda t: t["source"].update(mode="kinematic"),
            lambda t: t["summary"].update(max_anchor_error_m=0),
        ]
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                trace = copy.deepcopy(self.trace)
                mutation(trace)
                with self.assertRaises(ValueError):
                    validate_trace(trace)

    def test_browser_payload_cannot_diverge_after_rehash(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)/"run"
            shutil.copytree(DEMO, output)
            trace = copy.deepcopy(self.trace)
            trace["source"]["warp_version"] = "changed"
            export_viewer(trace, output/"index.html")
            write_manifest(output)
            with self.assertRaisesRegex(ValueError, "Browser poses differ"):
                verify(output)

    def test_changed_usd_and_missing_files_fail_hash_verification(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)/"run"
            shutil.copytree(DEMO, output)
            (output/"scene.usda").write_text("#usda 1.0\n")
            with self.assertRaisesRegex(ValueError, "Hash mismatch: scene.usda"):
                verify(output)
            manifest = json.loads((output/"manifest.json").read_text())
            del manifest["files"]["scene.usda"]
            (output/"manifest.json").write_text(json.dumps(manifest))
            with self.assertRaisesRegex(ValueError, "Incomplete"):
                verify(output)

    def test_duration_validation_needs_no_recording_dependencies(self):
        with tempfile.TemporaryDirectory() as output:
            for seconds in (0, -1, float("nan"), float("inf"), True, 30.1, .04):
                with self.subTest(seconds=seconds), self.assertRaises(ValueError):
                    record(output, seconds)

    def test_xyzw_rotation_and_safe_inline_metadata(self):
        rotated = point([2, 3, 4, 0, 0, 2**-.5, 2**-.5], [1, 0, 0])
        for actual, expected in zip(rotated, [2, 4, 4]):
            self.assertAlmostEqual(actual, expected)
        self.trace["source"]["warp_version"] = "</script><script>alert(1)</script>"
        with tempfile.TemporaryDirectory() as output:
            page = Path(output)/"index.html"
            export_viewer(self.trace, page)
            self.assertNotIn("</script><script>alert", page.read_text())


if __name__ == "__main__":
    unittest.main()
