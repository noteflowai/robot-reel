import csv
import json
from pathlib import Path
import tempfile
import unittest

from robot_reel import factory_twin as ft
from scripts.build_hf_factory_twin import decision_rows, pair_rows, sample_rows, seed_rows

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "docs/factory-twin"


class FactoryTwinDatasetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lab = ft.decode((SITE / "lab.json").read_bytes())
        cls.seeds = ft.decode((SITE / "seeds.json").read_bytes())

    def test_pair_rows_reproduce_the_published_summary(self):
        rows = pair_rows(self.seeds)
        s = self.seeds["summary"]
        self.assertEqual(len(rows), 12)
        self.assertEqual(sum(r["shadow_cnc2_failures"] for r in rows), s["shadow_failures"])
        self.assertEqual(sum(r["closed_cnc2_failures"] for r in rows), s["closed_failures"])
        self.assertEqual(sum(r["closed_intervals_over_limit"] for r in rows), s["closed_intervals_over_limit"])
        self.assertEqual(sum(r["good_units_gain"] > 0 for r in rows), s["good_units_gain"]["pairs_improved"])
        self.assertEqual(len(seed_rows(self.seeds)), 24)

    def test_sample_and_decision_rows_follow_the_lab(self):
        rows = sample_rows(self.lab)
        self.assertEqual(len(rows), 2 * ft.SAMPLES)
        closed = [r for r in rows if r["mode"] == "closed"]
        self.assertEqual([r["good"] for r in closed], self.lab["runs"]["closed"]["plant"]["good"])
        self.assertEqual(closed[-1]["clock"], "13:00:00")
        decisions = decision_rows(self.lab)
        self.assertEqual(len(decisions), sum(len(self.lab["runs"][m]["decisions"]) for m in ft.MODES))
        self.assertFalse(any(d["actuated"] is True for d in decisions if d["mode"] == "shadow"))

    def test_csv_round_trip(self):
        from scripts.build_hf_factory_twin import SAMPLE_FIELDS, table
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "samples.csv"
            path.write_text(table(SAMPLE_FIELDS, sample_rows(self.lab)))
            with path.open(newline="") as stream:
                back = list(csv.DictReader(stream))
        self.assertEqual(len(back), 2 * ft.SAMPLES)
        self.assertEqual(json.loads(back[400]["buffers"]), self.lab["runs"]["shadow"]["plant"]["buffers"][400]
                         if back[400]["mode"] == "shadow" else self.lab["runs"]["closed"]["plant"]["buffers"][400])


if __name__ == "__main__":
    unittest.main()
