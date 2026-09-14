import copy
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from scripts.build_microduck_lab import ROOT, poses, seal, validate_trace, verify_showcase

SITE = ROOT/"docs/microduck-lab"


class MicroduckMotionTests(unittest.TestCase):
    def test_original_recordings_and_every_derived_transform_are_reproducible(self):
        self.assertEqual(verify_showcase(SITE, check_sources=True)["joint_samples"], 8400)
        data = json.loads((SITE/"data.json").read_text())
        check = json.loads((SITE/"kinematics-check.json").read_text())
        self.assertLess(check["max_position_error_m"], 1e-9)
        self.assertLess(check["max_rotation_matrix_error"], 1e-9)
        self.assertEqual(check["checked_body_transforms"], 18000)
        for run in data["runs"]:
            trace = json.loads((SITE/f'{run["id"]}-trace.json').read_text())
            for actual, original in zip(run["frames"], trace["frames"]):
                for key in original:
                    self.assertEqual(actual[key], original[key])
            active = [f for f in trace["frames"] if f["commanded_forward_speed_mps"] > 0]
            self.assertEqual(len(active), 210)
            self.assertAlmostEqual(run["mean_walking_speed_mps"],
                                   sum(f["measured_forward_speed_mps"] for f in active)/len(active))
            worst = run["peak_error"]
            selected = trace["frames"][worst["frame"]]
            self.assertEqual(worst["radians"], abs(selected["qpos"][worst["joint"]]-selected["target"][worst["joint"]]))
        self.assertTrue((ROOT/"scripts/microduck_lab.html").read_bytes().isascii())

    def test_hinge_rotation_about_an_offset_keeps_its_anchor_fixed(self):
        # Independent geometric fixture: rotating 180 degrees around (1,0,0)
        # moves a body's origin to (2,0,0), not the anchor.
        kin = {"bodies": [
            {"parent": -1},
            {"parent": 0, "position": [0, 0, 0], "quaternion": [1, 0, 0, 0],
             "joint": 0, "reference": 0, "axis": [0, 0, 1], "offset": [1, 0, 0]},
        ]}
        import math
        p = poses(kin, [math.pi])[1]
        self.assertAlmostEqual(p[0], 2)
        self.assertAlmostEqual(p[1], 0)
        self.assertAlmostEqual(p[3], 0)
        self.assertAlmostEqual(p[6], 1)

    def test_malformed_clocks_joint_order_and_changed_policy_targets_are_rejected(self):
        original = json.loads((SITE/"left-trace.json").read_text())
        cases = []
        changed = copy.deepcopy(original)
        changed["joints"].reverse()
        cases.append(changed)
        changed = copy.deepcopy(original)
        changed["frames"][1]["sim_time"] = changed["frames"][0]["sim_time"]
        cases.append(changed)
        changed = copy.deepcopy(original)
        changed["frames"][2]["target"][3] += .01
        cases.append(changed)
        changed = copy.deepcopy(original)
        changed["frames"][3]["qpos"][4] = float("nan")
        cases.append(changed)
        for trace in cases:
            with self.assertRaises(ValueError):
                validate_trace(trace, .3)

    def test_changed_derived_pose_is_rejected_even_when_repacked_and_rehashed(self):
        with tempfile.TemporaryDirectory() as temporary:
            site = Path(temporary)/"lab"
            shutil.copytree(SITE, site)
            data = json.loads((site/"data.json").read_text())
            template = (ROOT/"scripts/microduck_lab.html").read_text()
            def write():
                payload = json.dumps(data, separators=(",", ":"))
                (site/"data.json").write_text(payload+"\n")
                (site/"index.html").write_text(template.replace("__LAB_DATA__", payload))
            # Platform math roundoff is allowed in FK, never in recorded angles.
            data["runs"][1]["frames"][120]["measured_pose"][4][0] += 1e-15
            write()
            self.assertEqual(seal(site)["frames"], 600)
            data["runs"][1]["frames"][120]["measured_pose"][4][0] += .01
            write()
            with self.assertRaisesRegex(ValueError, "poses or metrics"):
                seal(site)
            data = json.loads((SITE/"data.json").read_text())
            data["runs"][0]["frames"][0]["commanded_forward_speed_mps"] = False
            write()
            with self.assertRaisesRegex(ValueError, "poses or metrics"):
                seal(site)


if __name__ == "__main__":
    unittest.main()
