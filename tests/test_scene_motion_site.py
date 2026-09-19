"""Reject changed source facts even when a received manifest has been resealed."""
import copy
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from robot_reel.scene_motion import identity
from robot_reel.scene_motion_site import verify, verify_frame

SITE = Path(__file__).resolve().parents[1] / "docs/scene-lab"
MOTION = SITE / "motion"


class SceneMotionSiteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.trace = json.loads((MOTION / "edited/trace.json").read_text())

    def frame_record(self):
        return {
            "schema": "robot-reel.scene-motion-frame.v1", "case": "edited",
            "source_trace": identity(MOTION / "edited/trace.json"),
            "frame": copy.deepcopy(self.trace["frames"][1]),
            "camera": copy.deepcopy(self.trace["camera"]),
            "world": copy.deepcopy(self.trace["world"]),
            "blender_frame": 2, "browser_view": "recorded",
        }

    def test_received_frame_retains_original_physics_clock_and_camera(self):
        record = self.frame_record()
        self.assertEqual(verify_frame(MOTION, record)["frame"], 1)
        for field, value in (
            ("frame", {**record["frame"], "sim_time_s": 1 / 30}),
            ("camera", {**record["camera"], "width": 1920}),
            ("source_trace", {"sha256": "0" * 64, "bytes": 1}),
            ("blender_frame", 1),
        ):
            with self.subTest(field=field), self.assertRaises(ValueError):
                verify_frame(MOTION, {**record, field: value})

    def test_malformed_received_records_are_reported_as_validation_errors(self):
        record = self.frame_record()
        for value in (None, [], "frame", 1, {**record, "frame": []},
                      {**record, "browser_view": []},
                      {**record, "frame": {"frame": True}}):
            with self.subTest(value=value), self.assertRaises(ValueError):
                verify_frame(MOTION, value)

    def test_case_summary_cannot_override_original_final_position(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "motion"
            shutil.copytree(MOTION, root)
            manifest = json.loads((root / "motion.json").read_text())
            manifest["cases"]["edited"]["final_root_m"][0] += 1
            (root / "motion.json").write_text(json.dumps(manifest))
            with self.assertRaisesRegex(ValueError, "case summary"):
                verify(root, SITE)

    def test_resealed_native_check_and_simplified_geometry_are_rejected(self):
        for name, mutate, message in (
            ("edited/native-check.json",
             lambda value: value["trace"].update(sha256="0" * 64), "native motion check"),
            ("body-bounds.json",
             lambda value: value["bodies"][0]["max_m"].__setitem__(0, 100), "geometry bounds"),
        ):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary) / "motion"
                shutil.copytree(MOTION, root)
                document = json.loads((root / name).read_text())
                mutate(document)
                (root / name).write_text(json.dumps(document))
                manifest = json.loads((root / "motion.json").read_text())
                manifest["files"][name] = identity(root / name)
                (root / "motion.json").write_text(json.dumps(manifest))
                with self.assertRaisesRegex(ValueError, message):
                    verify(root, SITE)
