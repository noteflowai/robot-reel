"""Claims inventory (roadmap RR-03): every headline number in README.md, recomputed from its evidence.

    python3 scripts/claims_inventory.py            # check and print a summary
    python3 scripts/claims_inventory.py --write    # also regenerate docs/claims.md

Each entry names the lab, how its evidence was produced, the exact README
wording, the evidence file and a small function that recomputes the displayed
value from that file. The check fails if a README sentence is edited away from
its evidence, if an evidence file changes the number, or if the generated table
is stale. Standard library only.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "docs/claims.md"

KINDS = {
    "real-recording": "Recorded run of a real simulator or policy in this project",
    "real-dataset": "Third-party dataset recorded on physical hardware",
    "model-output": "Recorded responses of a language/vision model",
    "procedural-simulation": "Deterministic model written for this project; not calibrated to a real system",
}


def load(name):
    return json.loads((ROOT / "docs" / name).read_text())


def stress_failures():
    runs = load("stress/reliability.json")["runs"].values()
    failed = [r for r in runs if r["outcome"] != "success"]
    assert all(r["outcome"] == "step_limit" for r in failed)
    return len(failed)


def stress_tail_mm():
    runs = [r for r in load("stress/reliability.json")["runs"].values() if r["outcome"] != "success"]
    return f"{min(r['tail_travel_m'] for r in runs) * 1000:.1f} mm to {max(r['tail_travel_m'] for r in runs) * 1000:.1f} mm"


def stress_camera():
    pairs = [p for p in load("stress/summary.json")["pairs"] if p["condition"] == "camera"]
    gains = sum(p["condition_success"] and not p["reference_success"] for p in pairs)
    losses = sum(p["reference_success"] and not p["condition_success"] for p in pairs)
    words = {1: "one", 2: "two", 3: "three", 4: "four"}
    return f"{words[gains]} gains and {words[losses]} loss"


def repeat():
    r = load("stress-reproducibility.json")
    return f"{r['levels']['same_outcome']} / {load('stress/summary.json')['completed_trials']} outcomes"


def solver():
    m = load("solver-lab/lab.json")["metrics"]
    return f"{m['genesis-1']['max_position_error_m'] * 100:.2f} cm to {m['genesis-16']['max_position_error_m'] * 100:.2f} cm"


def factory(key):
    s = load("factory-twin/seeds.json")["summary"]
    return {"failures": f"{s['closed_failures']} spindle failures (shadow: {s['shadow_failures']})",
            "limit": f"{s['closed_intervals_over_limit']} billing intervals over the demand limit "
                     f"(shadow: {s['shadow_intervals_over_limit']})",
            "pairs": f"{s['good_units_gain']['pairs_improved']} pairs and fell in {s['good_units_gain']['pairs_worse']}",
            }[key]


def factory_values():
    check = load("factory-twin/blender-check.json")["modes"]
    values = {m["channel_values_checked"] for m in check.values()}
    assert len(values) == 1 and all(m["verified"] for m in check.values())
    return f"{values.pop():,} animated values"


def microduck_samples():
    data = load("microduck-lab/data.json")
    return f"{sum(len(r['frames']) * len(data['joints']) for r in data['runs']):,} measured joint samples"


def scene_frames():
    total = sum(load(f"scene-lab/motion/{v}/native-check.json")["frames"] for v in ("baseline", "edited"))
    return f"{total} source frames"


# (lab, evidence kind, README wording to find, evidence file(s), recompute -> README wording)
CLAIMS = (
    ("Stress Lab", "real-recording", "30 real closed-loop trials", "stress/summary.json",
     lambda: f"{load('stress/summary.json')['completed_trials']} real closed-loop trials"),
    ("Stress Lab", "real-recording", "All 14 unsuccessful trials reached the action limit", "stress/reliability.json",
     lambda: f"All {stress_failures()} unsuccessful trials reached the action limit"),
    ("Stress Lab", "real-recording", "44.8 mm to 138.6 mm", "stress/reliability.json", stress_tail_mm),
    ("Stress Lab", "real-recording", "three gains and one loss", "stress/summary.json", stress_camera),
    ("Stress Lab", "real-recording", "30 / 30 outcomes", "stress-reproducibility.json", repeat),
    ("Stress Lab", "real-recording", "360 / 360 rendered frames", "stress-reproducibility.json",
     lambda: "{identical} / {compared} rendered frames".format(**load("stress-reproducibility.json")["frames"]["input_renders"])),
    ("Stress Lab", "real-recording", "One of 3,195", "stress-reproducibility.json",
     lambda: "One of {:,}".format(load("stress-reproducibility.json")["frames"]["recorded_renders"]["compared"])
     if load("stress-reproducibility.json")["frames"]["recorded_renders"]["compared"]
     - load("stress-reproducibility.json")["frames"]["recorded_renders"]["identical"] == 1 else "changed"),
    ("Solver Lab", "real-recording", "32.70 cm to 2.05 cm", "solver-lab/lab.json", solver),
    ("Solver Lab", "real-recording", "366 recorded position/velocity states", "solver-lab/lab.json",
     lambda: f"{sum(len(v['samples']) for v in load('solver-lab/lab.json')['metrics'].values())} recorded position/velocity states"),
    ("Cloth Lab", "real-recording", "42,471 vertex samples", "cloth/blender-check.json",
     lambda: f"{load('cloth/blender-check.json')['checked_vertex_samples']:,} vertex samples"),
    ("Butterfly Lab", "real-recording", "14,424 body poses", "chaos/blender-check.json",
     lambda: f"{load('chaos/blender-check.json')['checked_body_samples']:,} body poses"),
    ("Butterfly Lab", "real-recording", "6.26 m gap", "chaos/trace.json",
     lambda: f"{load('chaos/trace.json')['summary']['peak']['distance_m']:.2f} m gap"),
    ("Butterfly Lab", "real-recording", "at 12.5 s", "chaos/trace.json",
     lambda: f"at {load('chaos/trace.json')['summary']['peak']['frame'] / 30:.1f} s"),
    ("Factory Twin Lab", "procedural-simulation", "0 spindle failures (shadow: 11)", "factory-twin/seeds.json",
     lambda: factory("failures")),
    ("Factory Twin Lab", "procedural-simulation", "0 billing intervals over the demand limit (shadow: 8)",
     "factory-twin/seeds.json", lambda: factory("limit")),
    ("Factory Twin Lab", "procedural-simulation", "10 pairs and fell in 2", "factory-twin/seeds.json",
     lambda: factory("pairs")),
    ("Factory Twin Lab", "procedural-simulation", "676,393 animated values", "factory-twin/blender-check.json",
     factory_values),
    ("Newton", "real-recording", "362 checked body transforms", "newton/blender-check.json",
     lambda: f"{load('newton/blender-check.json')['checked_body_samples']} checked body transforms"),
    ("VLA", "real-recording", "76 actions · one completed simulation task", "vla/trace.json",
     lambda: f"{load('vla/trace.json')['result']['actions']} actions · one completed simulation task"
     if load("vla/trace.json")["result"]["outcome"] == "success" else "failed"),
    ("Microduck Motion Lab", "real-recording", "8,400 measured joint samples", "microduck-lab/data.json",
     microduck_samples),
    ("Microduck Motion Lab", "real-recording", "18,000 body transforms", "microduck-lab/kinematics-check.json",
     lambda: f"{load('microduck-lab/kinematics-check.json')['checked_body_transforms']:,} body transforms"),
    ("Scene Lab", "real-recording", "362 source frames", "scene-lab/motion/*/native-check.json", scene_frames),
    ("Director", "real-recording", "420 vehicle samples", "director/animation-check.json",
     lambda: f"{load('director/animation-check.json')['checked_vehicle_samples']} vehicle samples"),
)


def check():
    readme = " ".join((ROOT / "README.md").read_text().split())
    rows, problems = [], []
    for lab, kind, wording, evidence, compute in CLAIMS:
        try:
            value = compute()
        except (OSError, KeyError, AssertionError, ValueError) as exc:
            value = f"error: {exc}"
        if value != wording:
            problems.append(f"{lab}: evidence gives {value!r}, README says {wording!r}")
        if wording not in readme:
            problems.append(f"{lab}: README no longer contains {wording!r}")
        rows.append((lab, kind, wording, evidence))
    return rows, problems


def render(rows):
    lines = [
        "# Claims inventory",
        "",
        "Every headline number in the [README](../README.md), the evidence file it comes from and how",
        "that evidence was produced. `python3 scripts/claims_inventory.py` recomputes each value from",
        "its file and fails if the README, the evidence or this table drift apart (roadmap RR-03).",
        "Generated; edit `scripts/claims_inventory.py`, then run it with `--write`.",
        "",
        "| Evidence kind | Meaning |",
        "| --- | --- |",
        *(f"| `{k}` | {v} |" for k, v in KINDS.items() if any(r[1] == k for r in rows)),
        "",
        "| Lab | Evidence kind | README wording | Evidence |",
        "| --- | --- | --- | --- |",
    ]
    for lab, kind, wording, evidence in rows:
        link = evidence if "*" in evidence else f"[{evidence}]({evidence})"
        lines.append(f"| {lab} | `{kind}` | {wording} | {link} |")
    lines += [
        "",
        "Numbers establish what these recordings contain, not general performance. Each lab's",
        "methods page states its sample size and limits; the Factory Twin is a procedural",
        "simulation and none of its numbers are measurements of a real factory.",
        "",
    ]
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)
    rows, problems = check()
    text = render(rows)
    if args.write:
        OUTPUT.write_text(text)
    elif not OUTPUT.exists() or OUTPUT.read_text() != text:
        problems.append("docs/claims.md is stale; run with --write")
    print(json.dumps({"claims": len(rows), "labs": len({r[0] for r in rows}), "problems": problems}, indent=2))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
