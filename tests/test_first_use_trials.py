import json
from pathlib import Path
import unittest

from scripts.collect_first_use_trials import RECORD, parse, summarize

ROOT = Path(__file__).resolve().parents[1]


def form(**answers):
    defaults = {
        "Dataset source": "My own dataset (kept private)", "Dataset and episode": "private",
        "Robot Reel version and OS": "0.18.4 on macOS 15", "Install time (seconds)": "120",
        "Export time (seconds)": "about 40 s", "Did the replay open?": "Yes, on the first attempt",
        "What were you trying to find out?": "Where the gripper closes late", "Did you find it?": "Yes",
        "Minutes from starting the install to your first useful replay": "11",
        "What would you normally use for this?": "Rerun", "Compared with that, what was better or worse?": "_No response_",
        "Where did you get stuck, confused or slowed down?": "Needed huggingface-cli login",
        "Would you use it again on another episode?": "Yes",
        "Confirmation": "- [X] I am not a Robot Reel maintainer.\n- [X] The maintainers may summarize this report",
    }
    defaults.update(answers)
    return "\n\n".join(f"### {k}\n\n{v}" for k, v in defaults.items())


def issue(number, user="alice", role="NONE", date="2026-10-02T09:00:00Z", **answers):
    return {"number": number, "html_url": f"https://github.com/noteflowai/robot-reel/issues/{number}",
            "user": {"login": user}, "author_association": role, "created_at": date, "body": form(**answers)}


class FirstUseTrialTests(unittest.TestCase):
    def test_issue_form_and_template_agree(self):
        from scripts.collect_first_use_trials import FIELDS
        template = (ROOT / ".github/ISSUE_TEMPLATE/first_use_trial.yml").read_text()
        for label in FIELDS:  # the collector's labels must be exactly the form's labels
            self.assertIn(f"label: {label}\n", template)
        self.assertIn('labels: ["first-use-trial"]', template)

    def test_parses_answers_and_keeps_missing_values_null(self):
        answers = parse(form())
        self.assertEqual(answers["opened"], "Yes, on the first attempt")
        self.assertIsNone(answers["comparison"])
        record = summarize([issue(5)])
        self.assertEqual(record["trials"][0]["export_seconds"], 40.0)
        self.assertEqual(record["trials"][0]["minutes_to_first_replay"], 11.0)

    def test_only_confirmed_non_maintainer_reports_count(self):
        record = summarize([
            issue(1, user="owner", role="OWNER"),
            issue(2, user="bob", **{"Confirmation": "- [X] I am not a Robot Reel maintainer.\n- [ ] summarize"}),
            issue(3, user="carol"),
        ])
        self.assertEqual([t["issue"] for t in record["trials"]], [3])
        self.assertEqual(record["excluded"], [{"issue": 1, "reason": "filed by a repository owner"},
                                              {"issue": 2, "reason": "both confirmations were not ticked"}])

    def test_targets_need_three_participants_in_time_and_two_returning(self):
        reports = [issue(1, "a"), issue(2, "b"), issue(3, "c", **{
            "Minutes from starting the install to your first useful replay": "25"})]
        record = summarize(reports)
        self.assertEqual(record["progress"]["independent_participants"], 3)
        self.assertEqual(record["progress"]["within_target_minutes"], 2)
        self.assertFalse(record["targets_met"])
        reports[2] = issue(3, "c")
        reports += [issue(4, "a", date="2026-10-20T00:00:00Z"), issue(5, "b", date="2026-10-21T00:00:00Z")]
        record = summarize(reports)
        self.assertEqual(record["progress"]["returning_participants"], 2)
        self.assertTrue(record["targets_met"])

    def test_receipt_tells_the_participant_what_was_read(self):
        from scripts.collect_first_use_trials import explain
        receipt = explain(issue(7))
        self.assertIn("**Counted**", receipt)
        self.assertIn("| Minutes to first useful replay | 11.0 |", receipt)
        self.assertIn("filed by a repository owner", explain(issue(8, role="OWNER")))
        self.assertTrue(receipt.startswith("<!-- first-use-trial-receipt -->"))

    def test_committed_record_is_well_formed(self):
        record = json.loads(RECORD.read_text())
        self.assertEqual(record["roadmap"], "RR-01")
        self.assertEqual(record["progress"]["independent_attempts"], len(record["trials"]))
        self.assertIs(record["targets_met"], False if not record["trials"] else record["targets_met"])


if __name__ == "__main__":
    unittest.main()
