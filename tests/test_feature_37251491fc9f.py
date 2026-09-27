"""Behavioral tests for python -m robot_reel.stress --stall-sweep.

Every trace built here is SYNTHETIC: hand-made end-effector paths that exercise
the labelling logic only and say nothing about policy behavior. One test reads
the published collection solely to confirm that the reference threshold in a
sweep reproduces its sealed taxonomy.
"""

import contextlib
import io
import json
import unittest
from pathlib import Path
from unittest.mock import patch

from robot_reel import stress
from robot_reel.reliability import classify_run, stall_sensitivity, taxonomy

ROOT = Path(__file__).resolve().parent.parent


def synthetic_trace(trial, outcome, tail_m, frames=20):
    """SYNTHETIC trace whose final tenth of frames travels exactly tail_m."""
    positions = [[i * 0.01, 0.0, 0.0] for i in range(frames - 1)]
    positions.append([positions[-1][0] + tail_m, 0.0, 0.0])
    return {
        "stress": {"trial_id": trial},
        "result": {"outcome": outcome, "actions": 2},
        "frames": [
            {"frame": i, "state": [*p, 0.0, 0.0, 0.0, 0.02, -0.02], "action": None}
            for i, p in enumerate(positions)
        ],
    }


SYNTHETIC = {
    trace["stress"]["trial_id"]: trace
    for trace in (
        synthetic_trace("syn-step-1p5mm", "step_limit", 0.0015),
        synthetic_trace("syn-step-0p7mm", "step_limit", 0.0007),
        synthetic_trace("syn-step-0p2mm", "step_limit", 0.0002),
        synthetic_trace("syn-step-50mm", "step_limit", 0.05),
        synthetic_trace("syn-success", "success", 0.0001),
        synthetic_trace("syn-terminated", "terminated", 0.0001),
    )
}


def run_cli(*extra, traces=None):
    """Run the real CLI over synthetic traces, standing in for a verified collection."""
    traces = SYNTHETIC if traces is None else traces
    out, err, code = io.StringIO(), io.StringIO(), 0
    with (
        patch("robot_reel.stress_site.verify_site", return_value={"completed_trials": len(traces)}),
        patch("robot_reel.stress_site.load_collection",
              return_value=({"action_steps": 10}, [], list(traces.values()))),
        contextlib.redirect_stdout(out),
        contextlib.redirect_stderr(err),
    ):
        try:
            stress.main(["synthetic-collection", *extra])
        except SystemExit as exc:
            code = exc.code
    return code, out.getvalue(), err.getvalue()


class StallSweepCli(unittest.TestCase):
    def sweep(self, *extra):
        code, out, err = run_cli("--stall-sweep", "0.0005,0.002", *extra)
        self.assertEqual(code, 0, err)
        return json.loads(out)

    def test_reports_sorted_thresholds_with_counts_matching_classify_run(self):
        report = self.sweep()["stall_sensitivity"]
        self.assertEqual(report["schema"], "robot-reel-stall-sensitivity-1")
        self.assertEqual(report["reference_threshold_m"], 0.001)
        self.assertEqual(report["thresholds"], [0.0005, 0.001, 0.002])
        self.assertEqual(report["trials"], len(SYNTHETIC))
        for threshold in report["thresholds"]:
            with self.subTest(threshold=threshold):
                kinds = {n: classify_run(t, stall_metres=threshold)["kind"] for n, t in SYNTHETIC.items()}
                expected = {}
                for kind in kinds.values():
                    expected[kind] = expected.get(kind, 0) + 1
                entry = report["by_threshold"][repr(threshold)]
                self.assertEqual(entry["counts"], expected)
                self.assertEqual(
                    entry["stalled_trials"],
                    sorted(n for n, k in kinds.items() if k == "step_limit_stalled"),
                )

    def test_a_trial_near_the_cutoff_changes_label_and_is_marked_threshold_dependent(self):
        report = self.sweep()["stall_sensitivity"]
        looser = {row["trial"]: row for row in report["changed"]["0.002"]}
        self.assertEqual(set(looser), {"syn-step-1p5mm"})
        row = looser["syn-step-1p5mm"]
        self.assertEqual(row["reference_kind"], "step_limit_in_motion")
        self.assertEqual(row["kind"], "step_limit_stalled")
        self.assertAlmostEqual(row["tail_travel_m"], 0.0015, places=9)
        stricter = {row["trial"]: row for row in report["changed"]["0.0005"]}
        self.assertEqual(set(stricter), {"syn-step-0p7mm"})
        self.assertEqual(stricter["syn-step-0p7mm"]["kind"], "step_limit_in_motion")
        self.assertNotIn("0.001", report["changed"])
        self.assertTrue(report["boundary"]["syn-step-1p5mm"]["depends_on_threshold"])
        self.assertTrue(report["boundary"]["syn-step-0p7mm"]["depends_on_threshold"])
        self.assertFalse(report["boundary"]["syn-step-0p2mm"]["depends_on_threshold"])
        self.assertFalse(report["boundary"]["syn-step-50mm"]["depends_on_threshold"])
        self.assertEqual(report["stable_step_limit_trials"], ["syn-step-0p2mm", "syn-step-50mm"])
        self.assertEqual(report["step_limit_trials"], 4)

    def test_success_and_terminated_trials_never_change(self):
        report = self.sweep()["stall_sensitivity"]
        changed = {row["trial"] for rows in report["changed"].values() for row in rows}
        for name in ("syn-success", "syn-terminated"):
            self.assertNotIn(name, changed)
            self.assertNotIn(name, report["boundary"])
        for entry in report["by_threshold"].values():
            self.assertEqual(entry["counts"]["success"], 1)
            self.assertEqual(entry["counts"]["terminated"], 1)

    def test_without_the_flag_output_and_default_taxonomy_are_unchanged(self):
        code, out, err = run_cli()
        self.assertEqual(code, 0, err)
        self.assertEqual(json.loads(out), {"completed_trials": len(SYNTHETIC)})
        before = json.dumps(taxonomy(SYNTHETIC), sort_keys=True)
        stall_sensitivity(SYNTHETIC, [0.0005, 0.002])
        self.assertEqual(json.dumps(taxonomy(SYNTHETIC), sort_keys=True), before)

    def test_combined_with_reliability_keeps_the_reference_taxonomy(self):
        result = self.sweep("--reliability")
        self.assertEqual(result["reliability"]["stall_threshold_m"], 0.001)
        self.assertEqual(result["reliability"], json.loads(json.dumps(taxonomy(SYNTHETIC))))
        self.assertEqual(
            result["reliability"]["counts"],
            result["stall_sensitivity"]["by_threshold"]["0.001"]["counts"],
        )

    def test_invalid_thresholds_exit_2_with_a_message_naming_the_problem(self):
        cases = {
            "": "one to eight",
            "0.001,,0.002": "no empty entries",
            "abc": "not a number",
            "nan": "not finite",
            "inf": "not finite",
            "0": "greater than zero",
            "-1": "greater than zero",
            "0.002,0.002": "duplicate",
            "0.002,2e-3": "duplicate",
            ",".join(str(0.0001 * (i + 1)) for i in range(9)): "at most 8",
            "2": "exceeds 1 m",
        }
        for value, message in cases.items():
            with self.subTest(value=value):
                code, out, err = run_cli(f"--stall-sweep={value}")
                self.assertEqual(code, 2)
                self.assertEqual(out, "")
                self.assertIn(message, err)
                self.assertNotIn("Traceback", err)

    def test_a_trial_with_one_frame_is_reported_as_an_error(self):
        short = synthetic_trace("syn-short", "step_limit", 0.001)
        short["frames"] = short["frames"][:1]
        code, out, err = run_cli("--stall-sweep", "0.002", traces={"syn-short": short})
        self.assertEqual(code, 2)
        self.assertIn("two recorded frames", err)


class PublishedReference(unittest.TestCase):
    def test_the_reference_threshold_reproduces_the_sealed_taxonomy(self):
        from robot_reel.stress_site import load_collection
        _, _, traces = load_collection(ROOT / "docs/stress")
        named = {t["stress"]["trial_id"]: t for t in traces}
        sealed = json.loads((ROOT / "docs/stress/reliability.json").read_text())
        report = stall_sensitivity(named, [0.0005, 0.002])
        reference = report["by_threshold"]["0.001"]
        self.assertEqual(reference["counts"], sealed["counts"])
        self.assertEqual(reference["stalled_trials"], sealed["kinds"].get("step_limit_stalled", []))
        self.assertEqual(report["trials"], sealed["trials"])


if __name__ == "__main__":
    unittest.main()
