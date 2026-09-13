"""Describe paired recorded outcomes without hiding gains behind net rates."""
from __future__ import annotations

import json
from pathlib import Path

from .stress import canonical_hash

SCHEMA = "robot-reel-paired-outcomes-1"
GROUPS = ("both_success", "lost_success", "gained_success", "neither_success")


def paired_report(summary, plan_sha256):
    """Consume the complete, validated experiment summary."""
    reference = next(c for c in summary["conditions"] if c["id"] == "reference")
    comparisons = []
    for condition in summary["conditions"]:
        if condition["id"] == "reference":
            continue
        rows = [p for p in summary["pairs"] if p["condition"] == condition["id"]]
        seeds = [p["seed"] for p in rows]
        if (len(rows) != reference["trials"] or len(rows) != condition["trials"]
                or len(set(seeds)) != len(seeds) or not rows):
            raise ValueError("Paired outcomes require every unique planned seed")
        groups = {name: [] for name in GROUPS}
        for row in rows:
            a, b = row["reference_success"], row["condition_success"]
            if type(a) is not bool or type(b) is not bool:
                raise ValueError("Recorded success flags must be booleans")
            key = ("both_success" if a and b else "lost_success" if a
                   else "gained_success" if b else "neither_success")
            groups[key].append(row["seed"])
        groups = {name: sorted(values) for name, values in groups.items()}
        reference_successes = len(groups["both_success"]) + len(groups["lost_success"])
        condition_successes = len(groups["both_success"]) + len(groups["gained_success"])
        if reference_successes != reference["successes"] or condition_successes != condition["successes"]:
            raise ValueError("Paired counts differ from full condition totals")
        comparisons.append({
            "condition": condition["id"], "paired_seeds": len(rows),
            "groups": groups,
            "reference_successes": reference_successes,
            "condition_successes": condition_successes,
            "net_success_difference": condition_successes - reference_successes,
        })
    return {
        "schema": SCHEMA, "plan_sha256": plan_sha256,
        "scope": {key: summary[key] for key in (
            "planned_trials", "completed_trials", "attempts", "execution_errors",
        )},
        "comparisons": comparisons,
    }


def verify_report(path, expected):
    raw = Path(path).read_bytes()
    if len(raw) > 131072:
        raise ValueError("Paired report exceeds 128 KiB")

    def unique_keys(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Duplicate JSON field in paired report")
            result[key] = value
        return result

    value = json.loads(raw, object_pairs_hook=unique_keys)
    if canonical_hash(value) != canonical_hash(expected):
        raise ValueError("Paired report differs from the complete source experiment")
    return True
