"""Check portable Cloth Lab samples against their original recorded vertices."""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from urllib.parse import parse_qsl

from .cloth import CASES, FPS, FREE_EDGE, PINS, VERTICES, floats, vertex

SCHEMA = "robot-reel-cloth-sample-1"
MAX_BYTES = 64 * 1024
LIMITS = [
    "Recorded simulation; no collisions or self-contact.",
    "Bending coefficients are solver settings, not calibrated fabric properties.",
    "Colors identify cases, not stress. Metrics exclude display spacing.",
]


def read_sample(path):
    """Read bounded UTF-8 JSON, rejecting ambiguous keys and non-finite numbers."""
    with Path(path).open("rb") as stream:
        content = stream.read(MAX_BYTES + 1)
    if len(content) > MAX_BYTES:
        raise ValueError("Sample JSON exceeds 64 KiB")

    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError(f"Duplicate sample JSON key: {key}")
            result[key] = value
        return result

    def constant(_):
        raise ValueError("Sample JSON must contain finite numbers")

    try:
        document = json.loads(content.decode("utf-8-sig"), object_pairs_hook=pairs, parse_constant=constant)
    except (UnicodeError, RecursionError) as exc:
        raise ValueError("Invalid sample JSON encoding or nesting") from exc
    pending = [(document, 0)]
    while pending:
        value, depth = pending.pop()
        if depth >= 32 and isinstance(value, (dict, list)):
            raise ValueError("Sample JSON nesting exceeds 32 levels")
        if type(value) in (int, float) and not _number(value):
            raise ValueError("Sample JSON must contain finite numbers")
        if isinstance(value, dict):
            pending.extend((v, depth + 1) for v in value.values())
        elif isinstance(value, list):
            pending.extend((v, depth + 1) for v in value)
    return document


def _number(value):
    if type(value) not in (int, float):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


def _same(actual, expected, path=""):
    if type(expected) in (int, float):
        if not _number(actual):
            return False
        # JavaScript and Python can differ in their final floating-point bits.
        return (math.isclose(actual, expected, rel_tol=1e-12, abs_tol=1e-12)
                if path.startswith("metrics.") else actual == expected)
    if type(actual) is not type(expected):
        return False
    if isinstance(expected, dict):
        return actual.keys() == expected.keys() and all(
            _same(actual[k], v, f"{path}.{k}" if path else k) for k, v in expected.items())
    if isinstance(expected, list):
        return len(actual) == len(expected) and all(_same(a, e, path) for a, e in zip(actual, expected))
    return actual == expected


def _fragment_matches(fragment, sample, case, mode, yaw):
    if not isinstance(fragment, str) or not fragment.startswith("#") or len(fragment) > 512:
        return False
    pairs = parse_qsl(fragment[1:], keep_blank_values=True)
    params = dict(pairs)
    if len(pairs) != 4 or set(params) != {"frame", "case", "view", "yaw"}:
        return False
    try:
        angle = json.loads(params["yaw"])
    except (ValueError, RecursionError):
        return False
    return (params["frame"] == str(sample) and params["case"] == str(case)
            and params["view"] == mode and _number(angle) and angle == yaw)


def verify_record(trace, positions, document):
    """Check a record against a validated cloth bundle; never mutate either input."""
    if not isinstance(document, dict):
        raise ValueError("Expected a sample JSON object")
    case, presentation = document.get("case"), document.get("presentation")
    if not isinstance(case, dict) or not isinstance(presentation, dict):
        raise ValueError("Invalid sample case or presentation")
    sample, index = document.get("sample"), case.get("index")
    if any(not _number(v) or int(v) != v for v in (sample, index)):
        raise ValueError("Sample and case must be integers")
    sample, index = int(sample), int(index)
    if not 0 <= sample < trace["frame_count"] or not 0 <= index < len(CASES):
        raise ValueError("Sample or case lies outside this recording")
    mode, yaw, pitch = (presentation.get(k) for k in ("mode", "yaw_rad", "pitch_rad"))
    if mode not in ("separate", "overlay") or not _number(yaw) or abs(yaw) > math.pi or pitch != .65:
        raise ValueError("Invalid sample camera or presentation")
    if not _fragment_matches(document.get("replay_fragment"), sample, index, mode, yaw):
        raise ValueError("Sample replay fragment differs from its selection")

    q = floats(positions, trace["frame_count"] * len(CASES) * VERTICES * 3)
    points = [vertex(q, sample, index, i) for i in range(VERTICES)]
    rms = math.sqrt(sum(sum((a-b)**2 for a, b in zip(p, vertex(q, sample, 0, i)))
                        for i, p in enumerate(points)) / VERTICES)
    drop = 1.5 - sum(points[i][2] for i in FREE_EDGE) / len(FREE_EDGE)
    pin = max(math.dist(points[i], vertex(q, 0, index, i)) for i in PINS)
    fingerprint = hashlib.sha256(positions).hexdigest()
    expected = {
        "schema": SCHEMA, "sample": sample, "time_s": sample / FPS, "blender_frame": sample + 1, "fps": FPS,
        "case": {"index": index, "id": CASES[index]["id"], "edge_ke": CASES[index]["edge_ke"]},
        "reference": {"index": 0, "id": CASES[0]["id"], "edge_ke": CASES[0]["edge_ke"]},
        "presentation": {"mode": mode, "yaw_rad": yaw, "pitch_rad": .65,
                         "display_offsets_x_m": [(i-1)*1.35 if mode == "separate" else 0 for i in range(len(CASES))]},
        "metrics": {"rms_separation_m": rms, "mean_free_edge_drop_m": drop, "max_pin_displacement_m": pin},
        "source": {**trace["source"], "positions_sha256": fingerprint,
                   "vertex_count": VERTICES, "frame_count": trace["frame_count"]},
        "replay_fragment": document["replay_fragment"], "limits": LIMITS,
    }
    if not _same(document, expected):
        raise ValueError("Sample facts differ from this recording")
    return {"schema": SCHEMA, "sample": sample, "case_index": index, "recorded_facts_match": True,
            "positions_sha256": fingerprint, "replay_fragment": document["replay_fragment"]}
