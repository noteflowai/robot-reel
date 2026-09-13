"""Portable review selections, checked against a complete Stress Lab collection."""
from __future__ import annotations

import json
import math
from pathlib import Path

from .stress import canonical_hash, trial_id

SCHEMA = "robot-reel-stress-review-1"
MAX_BYTES = 128 * 1024
MAX_NOTE = 4000
SCOPE_KEYS = ("planned_trials", "completed_trials", "attempts", "execution_errors", "conditions")


def validate_note(note):
    if not isinstance(note, str) or len(note) > MAX_NOTE or any(
        ord(c) < 32 and c not in "\t\n\r" or 0xD800 <= ord(c) <= 0xDFFF for c in note
    ):
        raise ValueError("Review note must be text of at most 4000 characters, without control characters")


def record(data, selection, note=""):
    """Derive facts from verified source data; notes remain unverified user text."""
    validate_note(note)
    if not isinstance(selection, dict) or set(selection) != {"seed", "condition", "frame", "camera"}:
        raise ValueError("Invalid review selection")
    seed, condition, frame, camera = (selection[k] for k in ("seed", "condition", "frame", "camera"))
    if (
        type(seed) is not int or seed not in data["experiment"]["seeds"]
        or condition not in [c["id"] for c in data["experiment"]["conditions"]]
        or camera not in ("main", "wrist") or type(frame) is not int
    ):
        raise ValueError("Invalid review seed, condition, camera or sample")
    traces = {t["stress"]["trial_id"]: t for t in data["traces"]}
    pair = [traces[trial_id(seed, c)] for c in ("reference", condition)]
    if not 0 <= frame <= max(len(t["frames"]) - 1 for t in pair):
        raise ValueError("Review sample lies outside this recorded pair")
    attempts = {a["trial_id"]: a for a in data["attempts"] if a["status"] == "completed"}
    selected = []
    for trace in pair:
        index = min(frame, len(trace["frames"]) - 1)
        sample = trace["frames"][index]
        selected.append({
            "trial_id": trace["stress"]["trial_id"],
            "attempt": attempts[trace["stress"]["trial_id"]],
            "source": trace["source"],
            "initial_physics_sha256": trace["stress"]["initial_physics_sha256"],
            "task_bddl_sha256": trace["stress"]["task_bddl_sha256"],
            "channels": trace["channels"],
            "action_units": trace["action_units"],
            "state_units": trace["state_units"],
            "result": trace["result"],
            "source_frame": index,
            "held_final": frame > index,
            "observation": sample,
            "active_inference": None if sample["terminal"] else next(
                c for c in trace["inference_calls"] if c["frame"] == sample["inference_frame"]
            ),
        })
    return {
        "schema": SCHEMA,
        "plan_sha256": canonical_hash(data["experiment"]),
        "experiment": data["experiment"],
        "scope": {key: data["summary"][key] for key in SCOPE_KEYS},
        "selection": dict(selection),
        "replay_fragment": f"#seed={seed}&condition={condition}&frame={frame}&camera={camera}",
        "recorded": selected,
        "user_note": note,
    }


def same_json(actual, expected):
    """Compare JSON values without accepting booleans as numbers or NaN."""
    if type(expected) in (int, float):
        return type(actual) in (int, float) and actual == expected
    if type(actual) is not type(expected):
        return False
    if isinstance(expected, dict):
        return actual.keys() == expected.keys() and all(same_json(actual[k], v) for k, v in expected.items())
    if isinstance(expected, list):
        return len(actual) == len(expected) and all(same_json(a, e) for a, e in zip(actual, expected))
    return actual == expected


def verify_record(data, review):
    if not isinstance(review, dict):
        raise ValueError("Expected a review JSON object")
    expected = record(data, review.get("selection"), review.get("user_note"))
    if not same_json(review, expected):
        raise ValueError("Review facts differ from this collection; no selection or notes were applied")
    return {
        "schema": SCHEMA, "selection": expected["selection"],
        "recorded_facts_match": True, "user_note_verified": False,
        "planned_trials": expected["scope"]["planned_trials"],
    }


def read_review(path):
    """Reject oversized, duplicate-key and non-finite JSON before comparison."""
    with Path(path).open("rb") as stream:
        content = stream.read(MAX_BYTES + 1)
    if len(content) > MAX_BYTES:
        raise ValueError("Review JSON exceeds 128 KiB")

    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError(f"Duplicate review JSON key: {key}")
            result[key] = value
        return result

    def constant(_):
        raise ValueError("Review JSON must contain finite numbers")

    try:
        document = json.loads(content.decode("utf-8"), object_pairs_hook=pairs, parse_constant=constant)
    except (UnicodeError, RecursionError) as exc:
        raise ValueError("Invalid review JSON encoding or nesting") from exc
    pending = [(document, 0)]
    while pending:
        value, depth = pending.pop()
        if depth > 32:
            raise ValueError("Review JSON nesting exceeds 32 levels")
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError("Review JSON must contain finite numbers")
        if isinstance(value, dict):
            pending.extend((v, depth + 1) for v in value.values())
        elif isinstance(value, list):
            pending.extend((v, depth + 1) for v in value)
    return document
