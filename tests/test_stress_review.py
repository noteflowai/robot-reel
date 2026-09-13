import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from robot_reel.stress_review import MAX_BYTES, read_review, record, verify_record
from robot_reel.stress_site import load_collection, payload

SITE = Path(__file__).resolve().parents[1] / "docs/stress"


class StressReviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = payload(*load_collection(SITE))

    def review(self, frame=61, condition="dim", note="Inspect the contact."):
        return record(self.data, {"seed": 9, "condition": condition, "frame": frame, "camera": "wrist"}, note)

    def test_recorded_action_terminal_and_held_clocks(self):
        for frame in (0, 61, 82, 100, 160):
            with self.subTest(frame=frame):
                review = self.review(frame)
                self.assertTrue(verify_record(self.data, review)["recorded_facts_match"])
                self.assertEqual(review["scope"]["planned_trials"], 30)
                self.assertEqual([c["successes"] for c in review["scope"]["conditions"]], [5, 4, 7])
                left, right = review["recorded"]
                self.assertEqual(left["source_frame"], min(frame, 82))
                self.assertEqual(right["source_frame"], frame)
                self.assertEqual(left["held_final"], frame > 82)
                for entry in review["recorded"]:
                    if entry["observation"]["terminal"]:
                        self.assertIsNone(entry["observation"]["action"])
                        self.assertIsNone(entry["active_inference"])
                    else:
                        self.assertEqual(entry["active_inference"]["frame"], entry["observation"]["inference_frame"])
        same = self.review(61, "reference")
        self.assertEqual(same["recorded"][0], same["recorded"][1])
        # Some JSON writers spell integer-valued numbers as 9.0 / 61.0. The
        # browser accepts these as integers; the CLI must make the same decision.
        review = self.review()
        review["selection"].update(seed=9.0, frame=61.0)
        self.assertTrue(verify_record(self.data, review)["recorded_facts_match"])

    def test_mutated_facts_and_unknown_fields_are_rejected(self):
        mutations = [
            ("schema", lambda r: r.update(schema="unknown")),
            ("denominator", lambda r: r["scope"].update(planned_trials=2)),
            ("outcome", lambda r: r["recorded"][1]["result"].update(outcome="success")),
            ("held", lambda r: r["recorded"][0].update(held_final=False)),
            ("source clock", lambda r: r["recorded"][0].update(source_frame=100)),
            ("terminal action", lambda r: r["recorded"][0]["observation"].update(action=[0]*7)),
            ("stale inference", lambda r: r["recorded"][0].update(active_inference=r["recorded"][1]["active_inference"])),
            ("checkpoint", lambda r: r["recorded"][0]["source"].update(checkpoint_sha256="0"*64)),
            ("pixels", lambda r: r["recorded"][1]["observation"]["raw_camera_sha256"].update(wrist="0"*64)),
            ("note masquerading as evidence", lambda r: r.update(verified_note=True)),
            ("boolean as number", lambda r: r["scope"].update(execution_errors=False)),
            ("non-finite", lambda r: r["recorded"][1]["observation"].update(episode_time=float("nan"))),
            ("extra selection", lambda r: r["selection"].update(url="file:///private")),
        ]
        for name, mutate in mutations:
            with self.subTest(name=name):
                review = copy.deepcopy(self.review(100))
                mutate(review)
                with self.assertRaises(ValueError):
                    verify_record(self.data, review)

    def test_invalid_selections_are_not_silently_clamped(self):
        for selection in (
            None, [], {}, {"seed": 9, "condition": "dim", "frame": 161, "camera": "main"},
            {"seed": True, "condition": "dim", "frame": 1, "camera": "main"},
            {"seed": 9, "condition": "dim", "frame": -1, "camera": "main"},
            {"seed": 9, "condition": "dim", "frame": 1.5, "camera": "main"},
            {"seed": 9.1, "condition": "dim", "frame": 1, "camera": "main"},
            {"seed": 9, "condition": "other", "frame": 1, "camera": "main"},
            {"seed": 9, "condition": "reference", "frame": 83, "camera": "main"},
            {"seed": 9, "condition": "dim", "frame": 1, "camera": "unknown"},
        ):
            with self.subTest(selection=selection), self.assertRaises(ValueError):
                record(self.data, selection)

    def test_note_is_bounded_user_text_and_cannot_claim_verification(self):
        for note in ("", "检查接触点 🔎\n```html\n<script>alert(1)</script>\n```", "😀"*4000):
            review = self.review(note=note)
            self.assertEqual(review["user_note"], note)
            self.assertFalse(verify_record(self.data, review)["user_note_verified"])
        for note in (None, [], "a"*4001, "\0", "\ud800"):
            with self.subTest(note=repr(note)[:50]), self.assertRaises(ValueError):
                self.review(note=note)

    def test_reader_rejects_duplicate_keys_nonfinite_oversize_and_encoding(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/"review.json"
            for content in (b'{"seed":9,"seed":8}', b'{"x":NaN}', b'{"x":Infinity}', b'{"x":1e999}',
                            b" "*MAX_BYTES+b"{}", b"\xff", b"["*2000+b"]"*2000):
                with self.subTest(content=content[:30]):
                    path.write_bytes(content)
                    with self.assertRaises(ValueError):
                        read_review(path)

    def test_stdlib_cli_checks_collection_and_review_then_rejects_changed_scope(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/"review.json"
            review = self.review()
            path.write_text(json.dumps(review))
            command = [sys.executable, "-S", "-m", "robot_reel.cli", "stress", str(SITE), "--review", str(path)]
            result = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            check = json.loads(result.stdout)["review"]
            self.assertTrue(check["recorded_facts_match"])
            self.assertFalse(check["user_note_verified"])
            review["scope"]["planned_trials"] = 2
            path.write_text(json.dumps(review))
            result = subprocess.run(command, capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Review facts differ", result.stderr)


if __name__ == "__main__":
    unittest.main()
