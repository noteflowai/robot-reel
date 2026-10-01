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
            (root / "README.zh-CN.md").write_text((ROOT / "README.zh-CN.md").read_text())
            with mock.patch.object(inventory, "ROOT", root):
                problems = inventory.check()[1]
        self.assertEqual(len(problems), 1)
        self.assertIn("README no longer contains", problems[0])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "docs").symlink_to(ROOT / "docs")
            (root / "README.md").write_text((ROOT / "README.md").read_text())
            (root / "README.zh-CN.md").write_text((ROOT / "README.zh-CN.md").read_text().replace(
                "影子模式 11 次", "影子模式 12 次"))
            with mock.patch.object(inventory, "ROOT", root):
                problems = inventory.check()[1]
        self.assertEqual(len(problems), 1)
        self.assertIn("README.zh-CN no longer contains", problems[0])
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



class NumberExtractionTests(unittest.TestCase):
    def test_english_and_chinese_numbers_compare_equal(self):
        self.assertEqual(inventory.numbers("three gains and one loss"),
                         inventory.numbers("三次从未完成变为成功、一次从成功变为未完成"))
        self.assertEqual(inventory.numbers("360 / 360 个渲染帧一致"), [360.0, 360.0])
        self.assertEqual(inventory.numbers("676,393 animated values"), [676393.0])
        self.assertNotEqual(inventory.numbers("32.70 cm to 2.05 cm"), inventory.numbers("32.70 厘米降至 2.50 厘米"))


if __name__ == "__main__":
    unittest.main()
