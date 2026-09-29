import copy
from contextlib import redirect_stderr, redirect_stdout
import csv
import io
import json
from pathlib import Path
import tempfile
import unittest

from robot_reel import stress
from robot_reel.stress import canonical_hash
from robot_reel.stress_pairs import exact_paired_test, paired_report, verify_report
from robot_reel.stress_site import verify_site

SITE = Path(__file__).resolve().parents[1] / "docs/stress"


class PairedOutcomesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.summary = verify_site(SITE)
        cls.plan_hash = canonical_hash(json.loads((SITE / "experiment.json").read_text()))
        cls.report = paired_report(cls.summary, cls.plan_hash)

    def test_all_seed_groups_reconcile_with_marginal_rates(self):
        for comparison in self.report["comparisons"]:
            groups = comparison["groups"]
            seeds = [s for values in groups.values() for s in values]
            self.assertEqual(sorted(seeds), list(range(10)))
            self.assertEqual(len(seeds), len(set(seeds)))
            self.assertEqual(comparison["net_success_difference"],
                             len(groups["gained_success"]) - len(groups["lost_success"]))
        dim, camera = self.report["comparisons"]
        self.assertEqual(dim["net_success_difference"], -1)
        self.assertEqual(camera["net_success_difference"], 2)
        self.assertIn(9, dim["groups"]["lost_success"])
        self.assertIn(9, camera["groups"]["lost_success"])
        self.assertGreater(len(camera["groups"]["gained_success"]), 2)

    def test_missing_duplicate_or_nonboolean_pair_cannot_change_counts(self):
        for kind in ("missing", "duplicate", "boolean", "marginal"):
            summary = copy.deepcopy(self.summary)
            if kind == "missing":
                summary["pairs"].pop()
            elif kind == "duplicate":
                summary["pairs"][0] = copy.deepcopy(summary["pairs"][2])
            elif kind == "boolean":
                summary["pairs"][0]["reference_success"] = 1
            else:
                summary["conditions"][1]["successes"] += 1
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                paired_report(summary, self.plan_hash)

    def test_export_is_verified_against_all_source_outcomes(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "report.json"
            path.write_text(json.dumps(self.report))
            self.assertTrue(verify_report(path, self.report))
            for kind in ("delta", "seed", "plan", "type"):
                changed = copy.deepcopy(self.report)
                if kind == "delta":
                    changed["comparisons"][0]["net_success_difference"] += 1
                elif kind == "seed":
                    changed["comparisons"][0]["groups"]["lost_success"].append(100)
                elif kind == "plan":
                    changed["plan_sha256"] = "0" * 64
                else:
                    changed["comparisons"][0]["paired_seeds"] = 10.0
                path.write_text(json.dumps(changed))
                with self.subTest(kind=kind), self.assertRaisesRegex(ValueError, "differs"):
                    verify_report(path, self.report)
            path.write_text('{"schema":1,"schema":2}')
            with self.assertRaisesRegex(ValueError, "Duplicate"):
                verify_report(path, self.report)
            path.write_bytes(b" " * 131073)
            with self.assertRaisesRegex(ValueError, "128 KiB"):
                verify_report(path, self.report)

    def test_dataset_rows_preserve_all_source_pairs_and_units(self):
        from scripts.build_hf_results import pairs_csv
        rows = list(csv.DictReader(io.StringIO(pairs_csv(self.summary["pairs"]))))
        self.assertEqual(len(rows), 20)
        self.assertEqual(len({(r["seed"], r["condition"]) for r in rows}), 20)
        camera = [r for r in rows if r["condition"] == "camera"]
        self.assertEqual(sum(r["outcome_group"] == "gained_success" for r in camera), 3)
        self.assertEqual(sum(r["outcome_group"] == "lost_success" for r in camera), 1)
        for row, source in zip(rows, self.summary["pairs"]):
            self.assertEqual(float(row["max_eef_distance_m"]), source["max_eef_distance_m"])
            self.assertEqual(int(row["max_eef_frame"]), source["max_eef_frame"])

    def test_exact_test_uses_recorded_pairs(self):
        exact = exact_paired_test(self.report)
        self.assertEqual(exact["schema"], "robot-reel-paired-exact-1")
        self.assertEqual(exact["plan_sha256"], self.plan_hash)
        dim, camera = exact["comparisons"]
        self.assertEqual([dim["condition"], camera["condition"]], ["dim", "camera"])
        for row, lost, gained, numerator, denominator in (
            (dim, 1, 0, 2, 2),
            (camera, 1, 3, 10, 16),
        ):
            self.assertEqual((row["lost_success"], row["gained_success"]), (lost, gained))
            self.assertEqual((row["p_numerator"], row["p_denominator"]), (numerator, denominator))
            self.assertEqual(row["exact_p_two_sided"], numerator / denominator)
            self.assertEqual(row["holm_adjusted_p"], 1.0)
            self.assertEqual(row["net_success_difference"], gained - lost)
        self.assertEqual(camera["min_attainable_p"], 0.125)
        self.assertFalse(camera["conventional_0_05_attainable"])
        self.assertEqual(camera["direction"], "gained")
        self.assertEqual(dim["min_attainable_p"], 1.0)
        self.assertEqual(dim["direction"], "lost")

    def test_exact_tail_matches_brute_force_sign_patterns(self):
        for n in range(13):
            for lost in range(n + 1):
                gained = n - lost
                report = {
                    "schema": "robot-reel-paired-outcomes-1", "plan_sha256": self.plan_hash,
                    "comparisons": [{
                        "condition": "synthetic", "paired_seeds": n + 2,
                        "groups": {
                            "both_success": [1000],
                            "lost_success": list(range(lost)),
                            "gained_success": list(range(lost, n)),
                            "neither_success": [1001],
                        },
                        "net_success_difference": gained - lost,
                    }],
                }
                row = exact_paired_test(report)["comparisons"][0]
                tail = sum(
                    min(bits.bit_count(), n - bits.bit_count()) <= min(lost, gained)
                    for bits in range(1 << n)
                )
                self.assertEqual(row["p_numerator"], tail)
                self.assertEqual(row["p_denominator"], 1 << n)
                self.assertEqual(row["exact_p_two_sided"], tail / (1 << n))
                self.assertEqual(row["holm_adjusted_p"], row["exact_p_two_sided"])

    def test_holm_is_monotone_and_never_below_raw_p(self):
        report = copy.deepcopy(self.report)
        report["comparisons"] = []
        for index, (lost, gained) in enumerate(((0, 10), (1, 4), (2, 2), (0, 0))):
            n = lost + gained
            report["comparisons"].append({
                "condition": str(index), "paired_seeds": n,
                "groups": {
                    "both_success": [], "lost_success": list(range(lost)),
                    "gained_success": list(range(lost, n)), "neither_success": [],
                },
                "net_success_difference": gained - lost,
            })
        rows = exact_paired_test(report)["comparisons"]
        ordered = sorted(rows, key=lambda row: row["exact_p_two_sided"])
        self.assertEqual(rows[0]["exact_p_two_sided"], 2 / 1024)
        self.assertEqual(
            [row["holm_adjusted_p"] for row in ordered],
            sorted(row["holm_adjusted_p"] for row in ordered),
        )
        for row in rows:
            self.assertGreaterEqual(row["holm_adjusted_p"], row["exact_p_two_sided"])
            self.assertLessEqual(row["holm_adjusted_p"], 1.0)

    def test_malformed_exact_report_is_rejected(self):
        for kind, message in (
            ("schema", "schema"), ("missing", "group"),
            ("boolean", "integer"), ("repeated", "repeats"),
            ("total", "paired_seeds"), ("empty", "nonempty"),
        ):
            report = copy.deepcopy(self.report)
            comparison = report["comparisons"][0]
            if kind == "schema":
                report["schema"] = "other"
            elif kind == "missing":
                del comparison["groups"]["lost_success"]
            elif kind == "boolean":
                comparison["groups"]["lost_success"][0] = True
            elif kind == "repeated":
                comparison["groups"]["gained_success"].append(
                    comparison["groups"]["lost_success"][0]
                )
                comparison["paired_seeds"] += 1
            elif kind == "total":
                comparison["paired_seeds"] -= 1
            else:
                report["comparisons"] = []
            with self.subTest(kind=kind), self.assertRaisesRegex(ValueError, message):
                exact_paired_test(report)

    def test_cli_adds_exact_result_and_keeps_paired_export_unchanged(self):
        output = io.StringIO()
        with redirect_stdout(output):
            stress.main([str(SITE), "--paired"])
        self.assertEqual(output.getvalue(), json.dumps(self.report, indent=2) + "\n")

        with tempfile.TemporaryDirectory() as directory:
            saved = Path(directory) / "paired.json"
            saved.write_text(output.getvalue())
            result = io.StringIO()
            with redirect_stdout(result):
                stress.main([str(SITE), "--paired-exact", "--paired-report", str(saved)])
            parsed = json.loads(result.getvalue())
            self.assertTrue(parsed["paired_report_verified"])
            self.assertEqual(parsed["paired_exact_test"], exact_paired_test(self.report))

        error = io.StringIO()
        with redirect_stderr(error), self.assertRaises(SystemExit) as stopped:
            stress.main([str(SITE), "--paired-exact", "--paired"])
        self.assertEqual(stopped.exception.code, 2)
        self.assertIn("run --paired-exact separately", error.getvalue())
        self.assertNotIn("Traceback", error.getvalue())
