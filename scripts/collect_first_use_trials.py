"""Collect external first-use trial reports (roadmap RR-01) into docs/validation/external-trials.json.

    python3 scripts/collect_first_use_trials.py            # fetch public issues and rewrite the record
    python3 scripts/collect_first_use_trials.py --check    # fail if the committed record is stale

Reads GitHub issues labelled ``first-use-trial`` (the issue form in
.github/ISSUE_TEMPLATE/first_use_trial.yml). A report counts only if its author
is not an owner, member or collaborator of the repository and ticked both
confirmations. Nothing is inferred: missing or unparseable answers stay null.
Standard library only; set GITHUB_TOKEN to avoid the anonymous rate limit.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import sys
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
RECORD = ROOT / "docs/validation/external-trials.json"
REPO = "noteflowai/robot-reel"
LABEL = "first-use-trial"
MAINTAINER_ROLES = {"OWNER", "MEMBER", "COLLABORATOR"}
TARGETS = {"independent_attempts": 3, "first_useful_replay_minutes": 15, "returning_participants": 2}
FIELDS = {
    "Dataset source": "source_kind", "Dataset and episode": "dataset", "Robot Reel version and OS": "version",
    "Install time (seconds)": "install_seconds", "Export time (seconds)": "export_seconds",
    "Did the replay open?": "opened", "What were you trying to find out?": "question", "Did you find it?": "found",
    "Minutes from starting the install to your first useful replay": "minutes_to_first_replay",
    "What would you normally use for this?": "baseline", "Compared with that, what was better or worse?": "comparison",
    "Where did you get stuck, confused or slowed down?": "stuck", "Would you use it again on another episode?": "reuse",
    "Confirmation": "confirmation",
}


def parse(body):
    """Parse a rendered GitHub issue form ("### Label" sections) into named answers."""
    answers = {}
    for block in re.split(r"^### ", body or "", flags=re.M)[1:]:
        label, _, value = block.partition("\n")
        key = FIELDS.get(label.strip())
        if key:
            value = value.strip()
            answers[key] = None if value in ("", "_No response_") else value
    return answers


def number(text):
    match = re.search(r"\d+(?:\.\d+)?", text or "")
    return float(match.group()) if match else None


def exclusion(issue, answers):
    """Why a report does not count, or None if it counts."""
    confirmed = answers.get("confirmation") or ""
    if "pull_request" in issue:
        return "pull request, not a report"
    if issue.get("author_association") in MAINTAINER_ROLES:
        return f"filed by a repository {issue['author_association'].lower()}"
    if confirmed.count("- [X]") + confirmed.count("- [x]") < 2:
        return "both confirmations were not ticked"
    if answers.get("opened") is None:
        return "the form's answers could not be read"
    return None


def explain(issue):
    """Markdown acknowledgment for a single report: what was read and whether it counts."""
    answers = parse(issue.get("body"))
    reason = exclusion(issue, answers)
    status = ("**Counted** as an independent first-use attempt." if reason is None
              else f"**Not counted:** {reason}.")
    read = [("Replay opened", answers.get("opened")), ("Found the answer", answers.get("found")),
            ("Minutes to first useful replay", number(answers.get("minutes_to_first_replay"))),
            ("Compared with", answers.get("baseline")), ("Would reuse", answers.get("reuse"))]
    lines = ["<!-- first-use-trial-receipt -->", "Thank you for reporting this attempt. " + status, "",
             "| Read from the form | Value |", "| --- | --- |",
             *(f"| {k} | {'—' if v is None else v} |" for k, v in read), "",
             "Nothing is inferred beyond these answers. Edit the issue to correct them; this note updates. "
             "Maintainers fold counted reports into "
             "[docs/validation/external-trials.json](https://github.com/noteflowai/robot-reel/blob/main/docs/validation/external-trials.json)."]
    return "\n".join(lines)


def summarize(issues):
    trials, excluded = [], []
    for issue in sorted(issues, key=lambda i: i["number"]):
        answers = parse(issue.get("body"))
        reason = exclusion(issue, answers)
        if reason:
            excluded.append({"issue": issue["number"], "reason": reason})
            continue
        trials.append({
            "issue": issue["number"], "url": issue["html_url"], "participant": issue["user"]["login"],
            "reported_at": issue["created_at"][:10], "source_kind": answers.get("source_kind"),
            "dataset": answers.get("dataset"), "version": answers.get("version"),
            "install_seconds": number(answers.get("install_seconds")),
            "export_seconds": number(answers.get("export_seconds")), "opened": answers.get("opened"),
            "minutes_to_first_replay": number(answers.get("minutes_to_first_replay")),
            "found_answer": answers.get("found"), "baseline": answers.get("baseline"),
            "stuck": answers.get("stuck"), "reuse": answers.get("reuse"),
        })
    participants = {}
    for t in trials:
        participants.setdefault(t["participant"], []).append(t["reported_at"])
    minutes = [t["minutes_to_first_replay"] for t in trials if t["minutes_to_first_replay"] is not None]
    progress = {
        "independent_attempts": len(trials),
        "independent_participants": len(participants),
        "opened": sum((t["opened"] or "").startswith("Yes") for t in trials),
        "answered_question": sum(t["found_answer"] == "Yes" for t in trials),
        "within_target_minutes": sum(m <= TARGETS["first_useful_replay_minutes"] for m in minutes),
        "median_minutes_to_first_replay": sorted(minutes)[len(minutes) // 2] if minutes else None,
        "returning_participants": sum(len(dates) > 1 for dates in participants.values()),
    }
    met = (progress["independent_participants"] >= TARGETS["independent_attempts"]
           and progress["within_target_minutes"] >= TARGETS["independent_attempts"]
           and progress["returning_participants"] >= TARGETS["returning_participants"])
    return {
        "schema_version": 1, "roadmap": "RR-01", "source": f"https://github.com/{REPO}/issues?q=label%3A{LABEL}",
        "rules": "Counts issues labelled first-use-trial from non-maintainers who ticked both confirmations. "
                 "Answers are copied as reported; nothing is inferred or verified beyond that.",
        "targets": TARGETS, "progress": progress, "targets_met": met, "trials": trials, "excluded": excluded,
    }


def fetch(opener=urllib.request.urlopen):
    issues, page = [], 1
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "robot-reel-trials"}
    if os.environ.get("GITHUB_TOKEN"):
        headers["Authorization"] = f"Bearer {os.environ['GITHUB_TOKEN']}"
    while True:
        url = f"https://api.github.com/repos/{REPO}/issues?labels={LABEL}&state=all&per_page=100&page={page}"
        with opener(urllib.request.Request(url, headers=headers), timeout=30) as response:
            batch = json.loads(response.read())
        issues += batch
        if len(batch) < 100:
            return issues
        page += 1


def render(record):
    return json.dumps(record, indent=2, ensure_ascii=False) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--explain", type=Path, help="Print the receipt for one issue (a GitHub event payload)")
    args = parser.parse_args(argv)
    if args.explain:
        print(explain(json.loads(args.explain.read_text())["issue"]))
        return 0
    text = render(summarize(fetch()))
    if args.check:
        if RECORD.read_text() != text:
            print("docs/validation/external-trials.json is stale; run scripts/collect_first_use_trials.py")
            return 1
    else:
        RECORD.write_text(text)
    print(json.dumps(json.loads(text)["progress"], indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
