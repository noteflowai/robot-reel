from pathlib import Path
import tempfile
import unittest
from unittest import mock

from scripts import claims_inventory as inventory

ROOT = Path(__file__).resolve().parents[1]


class ClaimsInventoryTests(unittest.TestCase):
    def test_every_readme_claim_matches_its_evidence_and_the_table_is_current(self):
        with mock.patch("builtins.print"):
            self.assertEqual(inventory.main([]), 0)
        rows, problems = inventory.check()
        self.assertEqual(problems, [])
        self.assertIn("Factory Twin Lab", {r[0] for r in rows})
        self.assertTrue(all(r[1] in inventory.KINDS for r in rows))

    def test_edited_readme_or_changed_evidence_is_reported(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "docs").symlink_to(ROOT / "docs")
            (root / "README.md").write_text((ROOT / "README.md").read_text().replace(
                "0 spindle failures (shadow: 11)", "0 spindle failures (shadow: 12)"))
            with mock.patch.object(inventory, "ROOT", root):
                problems = inventory.check()[1]
        self.assertEqual(len(problems), 1)
        self.assertIn("README no longer contains", problems[0])
        real = inventory.load
        def changed(name):
            data = real(name)
            if name == "factory-twin/seeds.json":
                data["summary"]["shadow_failures"] = 10
            return data
        with mock.patch.object(inventory, "load", changed):
            problems = inventory.check()[1]
        self.assertEqual(len(problems), 1)
        self.assertIn("evidence gives", problems[0])


if __name__ == "__main__":
    unittest.main()
