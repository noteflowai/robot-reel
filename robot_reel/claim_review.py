"""Check a model's structured claims against a recorded VLA trace, offline."""
import argparse
import hashlib
import json
import sys
from pathlib import Path

SCOPE = (
    "Checks agreement with the supplied recorded outcome and action count, and "
    "whether cited frame labels exist. It does not authenticate the trace, judge "
    "visual explanations, establish causality, or rerun a physical success test."
)


def review_claims(trace, claims):
    """Return individual matched, contradicted and unassessed claims."""
    if not isinstance(trace, dict) or trace.get("schema") != "robot-reel-vla-1":
        raise ValueError("Expected a robot-reel-vla-1 trace")
    result = trace.get("result", {})
    if not isinstance(result, dict) or result.get("outcome") not in ("success", "step_limit"):
        raise ValueError("Trace must record success or step_limit")
    if type(result.get("actions")) is not int or result["actions"] < 0:
        raise ValueError("Trace actions must be a nonnegative integer")
    frames = trace.get("frames")
    if not isinstance(frames, list) or not frames:
        raise ValueError("Trace frames are missing")
    labels = [frame.get("frame") for frame in frames if isinstance(frame, dict)]
    if len(labels) != len(frames) or any(type(n) is not int or n < 0 for n in labels):
        raise ValueError("Trace frame labels must be nonnegative integers")
    if len(set(labels)) != len(labels):
        raise ValueError("Trace frame labels must be unique")
    if not isinstance(claims, dict) or set(claims) != {
        "outcome", "action_count", "cited_frames", "explanation"
    }:
        raise ValueError("Claims require only outcome, action_count, cited_frames and explanation")
    if claims["outcome"] not in ("success", "step_limit", "unknown"):
        raise ValueError("Claim outcome must be success, step_limit or unknown")
    count = claims["action_count"]
    if count is not None and (type(count) is not int or count < 0):
        raise ValueError("Claim action_count must be a nonnegative integer or null")
    cited = claims["cited_frames"]
    if not isinstance(cited, list) or any(type(n) is not int or n < 0 for n in cited):
        raise ValueError("cited_frames must contain nonnegative integers")
    if not isinstance(claims["explanation"], str):
        raise ValueError("explanation must be text")
    checks = []
    for name, observed, recorded in (
        ("outcome", claims["outcome"], result["outcome"]),
        ("action_count", count, result["actions"]),
    ):
        status = "unassessed" if observed in (None, "unknown") else (
            "matched" if observed == recorded else "contradicted"
        )
        checks.append({"claim": name, "claimed": observed, "recorded": recorded, "status": status})
    missing = sorted(set(cited) - set(labels))
    checks.append({
        "claim": "cited_frame_labels_exist", "claimed": cited, "missing": missing,
        "status": "contradicted" if missing else ("matched" if cited else "unassessed"),
    })
    return {
        "schema": "robot-reel-claim-review-1", "checks": checks,
        "facts_match": all(check["status"] == "matched" for check in checks),
        "explanation": claims["explanation"], "explanation_status": "not_assessed",
        "scope": SCOPE,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("trace", type=Path)
    parser.add_argument("claims", type=Path, help="JSON with outcome, action_count, cited_frames, explanation")
    parser.add_argument("--output", type=Path, help="Write a new report; existing files are not replaced")
    args = parser.parse_args(argv)
    try:
        raw = []
        for path in (args.trace, args.claims):
            if path.stat().st_size > 32 * 1024 * 1024:
                raise ValueError("Each input must be at most 32 MiB")
            raw.append(path.read_bytes())
        report = review_claims(*(json.loads(data) for data in raw))
        report["inputs"] = {
            label: {"name": path.name, "sha256": hashlib.sha256(data).hexdigest()}
            for label, path, data in zip(("trace", "claims"), (args.trace, args.claims), raw)
        }
        text = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
        if args.output:
            with args.output.open("x", encoding="utf-8") as handle:
                handle.write(text)
        print(text, end="")
        return 0 if report["facts_match"] else 1
    except (OSError, ValueError, TypeError) as error:
        print(f"claim-review: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
