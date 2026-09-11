import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from robot_reel.microduck import MODEL_COMMIT, POLICY_REVISION, ensure_assets
from robot_reel.verify import verify_trace


def driving_trace():
    return {
        "robot": "braking_early", "fps": 30, "joints": ["speed", "gap", "position"],
        "home": [8, 28.5, 0], "actions": [],
        "frames": [{"frame": 0, "sim_time": 1/30, "source": "scripted", "mode": "physics",
                    "qpos": [8, 28, .5], "target": [0, 8, 20], "collision": False}],
        "outcome": {"collision": False, "minimum_gap_m": 28},
    }


class PackEvidenceTest(unittest.TestCase):
    def test_driving_channels_are_not_reported_as_actuators(self):
        result = verify_trace(driving_trace(), "scripted")
        self.assertEqual(result["channels"], 3)
        self.assertNotIn("actuated_joints", result)

    def test_collision_and_gap_summaries_must_match_frames(self):
        for key, wrong in [("collision", True), ("minimum_gap_m", 30)]:
            trace = driving_trace()
            trace["outcome"][key] = wrong
            with self.subTest(key=key), self.assertRaises(ValueError):
                verify_trace(trace, "scripted")

    def test_cached_policy_checksum_is_checked_before_inference(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            model = root/f"microduck-{MODEL_COMMIT}"
            model.mkdir()
            (model/"scene.xml").write_text("placeholder; not loaded by this test")
            (root/f"microduck-walk-{POLICY_REVISION}.onnx").write_bytes(b"changed")
            with patch.dict("os.environ", {"ROBOT_REEL_CACHE": directory}):
                with self.assertRaisesRegex(ValueError, "Cached policy has changed"):
                    ensure_assets()

    def test_frame_must_reference_the_actual_policy_target(self):
        trace = {
            "robot": "microduck", "fps": 30, "joints": ["joint"], "home": [0],
            "frames": [{"frame": 0, "sim_time": .035, "source": "policy", "mode": "physics",
                        "qpos": [0], "target": [1], "policy_step": 1, "base_position_m": [0,0,.12]}],
            "policy_steps": [
                {"step": 0, "sim_time": 0, "action": [0], "target": [0]},
                {"step": 1, "sim_time": .02, "action": [0], "target": [0]},
            ],
            "outcome": {"final_position_m": [0,0,.12]},
        }
        with self.assertRaisesRegex(ValueError, "Frame target disagrees"):
            verify_trace(trace, "scripted")
