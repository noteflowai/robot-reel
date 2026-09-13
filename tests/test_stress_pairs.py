import copy
import json
from pathlib import Path
import tempfile
import unittest

from robot_reel.stress import canonical_hash
from robot_reel.stress_pairs import paired_report, verify_report
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
