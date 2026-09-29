"""Describe paired recorded outcomes without hiding gains behind net rates."""
from __future__ import annotations

import json
from fractions import Fraction
from math import comb
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


def exact_paired_test(report):
    """Exact two-sided sign tests on the recorded discordant pairs."""
    if not isinstance(report, dict) or report.get("schema") != SCHEMA:
        raise ValueError("Paired report schema differs from paired_report")
    if not isinstance(report.get("plan_sha256"), str):
        raise ValueError("Paired report plan_sha256 is missing")
    comparisons = report.get("comparisons")
    if not isinstance(comparisons, list) or not comparisons:
        raise ValueError("Paired report comparisons must be a nonempty list")

    rows = []
    raw_p = []
    for comparison in comparisons:
        if not isinstance(comparison, dict):
            raise ValueError("Paired comparison must be an object")
        if not isinstance(comparison.get("condition"), str):
            raise ValueError("Paired comparison condition is missing")
        groups = comparison.get("groups")
        if not isinstance(groups, dict):
            raise ValueError("Paired comparison groups are missing")
        seeds = []
        for name in GROUPS:
            values = groups.get(name)
            if not isinstance(values, list) or any(type(seed) is not int for seed in values):
                raise ValueError(f"Paired group {name} must be a list of integer seeds")
            seeds.extend(values)
        if len(seeds) != len(set(seeds)):
            raise ValueError("A paired seed repeats within or across groups")
        paired_seeds = comparison.get("paired_seeds")
        if type(paired_seeds) is not int or len(seeds) != paired_seeds:
            raise ValueError("Paired group sizes do not sum to paired_seeds")
        b, c = len(groups["lost_success"]), len(groups["gained_success"])
        if comparison.get("net_success_difference") != c - b:
            raise ValueError("Paired net_success_difference disagrees with the groups")
        n = b + c
        denominator = 2 ** n
        numerator = min(2 * sum(comb(n, k) for k in range(min(b, c) + 1)), denominator)
        p = Fraction(numerator, denominator)
        raw_p.append(p)
        rows.append({
            "condition": comparison["condition"],
            "paired_seeds": paired_seeds,
            "lost_success": b,
            "gained_success": c,
            "discordant": n,
            "net_success_difference": comparison["net_success_difference"],
            "p_numerator": numerator,
            "p_denominator": denominator,
            "exact_p_two_sided": float(p),
            "min_attainable_p": float(min(Fraction(2, denominator), 1)),
            "conventional_0_05_attainable": Fraction(2, denominator) < Fraction(1, 20),
            "direction": "gained" if c > b else "lost" if b > c else "none",
        })

    previous = Fraction(0)
    for rank, index in enumerate(sorted(range(len(rows)), key=lambda i: (raw_p[i], i))):
        previous = min(Fraction(1), max(previous, (len(rows) - rank) * raw_p[index]))
        rows[index]["holm_adjusted_p"] = float(previous)
    return {
        "schema": "robot-reel-paired-exact-1",
        "plan_sha256": report["plan_sha256"],
        "comparisons": rows,
        "method": "exact two-sided binomial sign test on discordant paired seeds (exact McNemar); Holm across listed conditions",
        "scope": "Recorded pairs in this locked plan only; no multi-level outcomes, sequential stopping, power analysis or causal attribution",
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
