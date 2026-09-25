import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from robot_reel.claim_review import main, review_claims


class ClaimReviewTests(unittest.TestCase):
    def setUp(self):
        self.trace = {"schema": "robot-reel-vla-1", "result": {"outcome": "step_limit", "actions": 2},
                      "frames": [{"frame": n} for n in range(3)]}
        self.claims = {"outcome": "step_limit", "action_count": 2, "cited_frames": [0, 2],
                       "explanation": "An interpretation that is not graded."}

    def test_agreement_never_grades_explanation(self):
        report = review_claims(self.trace, self.claims)
        self.assertTrue(report["facts_match"])
        self.assertEqual(report["explanation_status"], "not_assessed")

    def test_wrong_outcome_and_nonexistent_citations(self):
        claims = {**self.claims, "outcome": "success", "cited_frames": [3]}
        report = review_claims(self.trace, claims)
        self.assertFalse(report["facts_match"])
        self.assertEqual([c["status"] for c in report["checks"]],
                         ["contradicted", "matched", "contradicted"])

    def test_unknown_is_unassessed_not_a_pass(self):
        report = review_claims(self.trace, {**self.claims, "outcome": "unknown", "action_count": None})
        self.assertFalse(report["facts_match"])
        self.assertEqual(report["checks"][0]["status"], "unassessed")

    def test_boolean_counts_and_duplicate_labels_are_rejected(self):
        with self.assertRaises(ValueError):
            review_claims(self.trace, {**self.claims, "action_count": True})
        with self.assertRaises(ValueError):
            review_claims({**self.trace, "frames": [{"frame": 0}, {"frame": 0}]}, self.claims)

    def test_cli_hashes_inputs_and_refuses_to_overwrite(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for name, data in (("trace", self.trace), ("claims", self.claims)):
                (root/f"{name}.json").write_text(json.dumps(data))
            output = root/"review.json"
            args = [str(root/"trace.json"), str(root/"claims.json"), "--output", str(output)]
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(main(args), 0)
                original = output.read_bytes()
                self.assertEqual(main(args), 2)
            self.assertEqual(output.read_bytes(), original)
            self.assertEqual(len(json.loads(original)["inputs"]["trace"]["sha256"]), 64)


if __name__ == "__main__":
    unittest.main()
