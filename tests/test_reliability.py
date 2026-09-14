"""Check the failure taxonomy and the reproducibility measurement.

Uses the published collection, so the numbers asserted here are the ones the
project reports, not synthetic ones.
"""

import copy
import json
import unittest
from pathlib import Path
from statistics import median

from robot_reel.reliability import (
    classify_run,
    compare_run,
    reproducibility,
    taxonomy,
)
from robot_reel.stress_site import load_collection

ROOT = Path(__file__).resolve().parent.parent


def frame(index, position, action=None):
    return {
        "frame": index,
        "state": [*position, 0.0, 0.0, 0.0, 0.02, -0.02],
        "action": action,
        "raw_camera_sha256": {"main": f"m{index}", "wrist": f"w{index}"},
    }


class Taxonomy(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _, _, traces = load_collection(ROOT / "docs/stress")
        cls.named = {t["stress"]["trial_id"]: t for t in traces}

    def test_every_recorded_failure_was_still_moving_when_the_budget_ran_out(self):
        report = taxonomy(self.named)
        self.assertEqual(report["trials"], 30)
        # The point of the split: none of the fourteen failures was a stall, so
        # the step limit is binding on the reported success rate rather than the
        # policy having given up.
        self.assertEqual(report["counts"], {"step_limit_in_motion": 14, "success": 16})
        self.assertNotIn("step_limit_stalled", report["counts"])

    def test_failures_wander_more_typically_but_the_ranges_overlap(self):
        runs = taxonomy(self.named)["runs"]
        failed = sorted(r["wander_ratio"] for r in runs.values() if r["kind"] != "success")
        passed = sorted(r["wander_ratio"] for r in runs.values() if r["kind"] == "success")
        self.assertGreater(median(failed), median(passed))
        # Asserted deliberately: the ranges overlap, so this is a description of
        # what failures look like and not a test that decides which is which.
        # Locking the overlap in stops the measure being read as a classifier.
        self.assertLess(min(failed), max(passed))

    def test_a_stalled_failure_is_distinguished_from_one_still_in_motion(self):
        moving = {
            "result": {"outcome": "step_limit", "actions": 3},
            "frames": [frame(i, [i * 0.05, 0.0, 0.0]) for i in range(20)],
        }
        stalled = copy.deepcopy(moving)
        # Same total travel, but the arm stops before the budget expires.
        stalled["frames"] = [
            frame(i, [min(i, 5) * 0.05, 0.0, 0.0]) for i in range(20)
        ]
        self.assertEqual(classify_run(moving)["kind"], "step_limit_in_motion")
        self.assertEqual(classify_run(stalled)["kind"], "step_limit_stalled")
        # An early termination is its own event, not a step-limit variety.
        terminated = copy.deepcopy(moving)
        terminated["result"]["outcome"] = "terminated"
        self.assertEqual(classify_run(terminated)["kind"], "terminated")


class Reproducibility(unittest.TestCase):
    def test_the_published_measurement_matches_a_recomputation(self):
        # The taxonomy is sealed inside the pack and recomputed on verification.
        sealed = json.loads((ROOT / "docs/stress/reliability.json").read_text())
        _, _, traces = load_collection(ROOT / "docs/stress")
        self.assertEqual(sealed, taxonomy({t["stress"]["trial_id"]: t for t in traces}))
        # Reproducibility spans two collections, so it sits beside the pack.
        recorded = json.loads((ROOT / "docs/stress-reproducibility.json").read_text())
        # A render difference on a frame no policy call consumed cannot change an
        # outcome, so the two render levels are reported apart. This is the whole
        # reason the measurement is worth more than one agreement rate.
        frames = recorded["frames"]
        self.assertEqual(frames["input_renders"]["identical"], frames["input_renders"]["compared"])
        self.assertLess(
            frames["recorded_renders"]["identical"], frames["recorded_renders"]["compared"]
        )
        self.assertEqual(recorded["differing_trials"], [])

    def test_a_difference_on_a_consumed_frame_is_reported_apart_from_one_that_is_not(self):
        reference = {
            "result": {"outcome": "success", "actions": 2},
            "frames": [frame(i, [i * 0.01, 0.0, 0.0], action=[0.0] * 7) for i in range(21)],
        }
        # Frame 3 is never handed to the policy when a call happens every ten.
        recorded_only = copy.deepcopy(reference)
        recorded_only["frames"][3]["raw_camera_sha256"]["wrist"] = "changed"
        result = compare_run(reference, recorded_only, 10)
        self.assertTrue(result["identical_input_renders"])
        self.assertEqual(result["recorded_renders"]["identical"], result["recorded_renders"]["compared"] - 1)

        # Frame 10 is a call boundary, so the same edit lands on policy input.
        consumed = copy.deepcopy(reference)
        consumed["frames"][10]["raw_camera_sha256"]["wrist"] = "changed"
        result = compare_run(reference, consumed, 10)
        self.assertFalse(result["identical_input_renders"])
        self.assertEqual(result["input_renders"]["identical"], result["input_renders"]["compared"] - 1)

    def test_a_repeat_missing_a_trial_cannot_report_agreement(self):
        one = {
            "result": {"outcome": "success", "actions": 1},
            "frames": [frame(i, [i * 0.01, 0.0, 0.0], action=[0.0] * 7) for i in range(11)],
        }
        with self.assertRaisesRegex(ValueError, "same trials"):
            reproducibility({"a": one, "b": one}, {"a": one}, 10)
        with self.assertRaisesRegex(ValueError, "at least one trial"):
            reproducibility({}, {}, 10)

    def test_missing_consumed_frames_or_hashes_cannot_report_identical_inputs(self):
        reference = {
            "result": {"outcome": "success", "actions": 20},
            "frames": [frame(i, [i * .01, 0, 0], action=[0.0] * 7) for i in range(21)],
        }
        truncated = copy.deepcopy(reference)
        truncated["frames"] = truncated["frames"][:10]
        self.assertFalse(compare_run(reference, truncated, 10)["identical_input_renders"])
        no_hashes = copy.deepcopy(reference)
        for row in no_hashes["frames"]:
            row.pop("raw_camera_sha256")
        self.assertFalse(compare_run(no_hashes, no_hashes, 10)["identical_input_renders"])
        no_inputs = copy.deepcopy(reference)
        for row in no_inputs["frames"]:
            row["action"] = None
        self.assertFalse(compare_run(no_inputs, no_inputs, 10)["identical_input_renders"])


if __name__ == "__main__":
    unittest.main()
