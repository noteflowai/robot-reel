"""Check capture consistency; this does not certify autonomy or task success."""
import argparse
import hashlib
import json
import math
from pathlib import Path


def verify(output: Path):
    manifest = json.loads((output / "manifest.json").read_text())
    for name, expected in manifest["sha256"].items():
        if Path(name).name != name:
            raise ValueError("Manifest filenames must be local basenames")
        actual = hashlib.sha256((output / name).read_bytes()).hexdigest()
        if actual != expected:
            raise ValueError(f"Hash mismatch: {name}")
    summary = {}
    for name in ["so100", "unitree_g1"]:
        trace = json.loads((output / f"{name}-trace.json").read_text())
        if not trace["frames"]:
            raise ValueError(f"{name}: no frames")
        for i, frame in enumerate(trace["frames"]):
            if frame["frame"] != i:
                raise ValueError(f"{name}: nonsequential frame")
            if len(frame["qpos"]) != len(trace["joints"]):
                raise ValueError(f"{name}: mismatched joint count")
            if not all(math.isfinite(v) for v in frame["qpos"]):
                raise ValueError(f"{name}: nonfinite state")
        if name == "so100":
            if len(trace["actions"]) != 4:
                raise ValueError("Expected four arm motions")
            if any(frame["mode"] != "physics" for frame in trace["frames"]):
                raise ValueError("Arm must use physics stepping")
            if {a["source"] for a in trace["actions"]} != {manifest["arm_director"]}:
                raise ValueError("Director provenance mismatch")
            for action in trace["actions"]:
                actual = max(abs(action["measured"][j]-action["target"][j]) for j in trace["joints"])
                if abs(actual-action["max_error_rad"]) > 1e-8:
                    raise ValueError("Reported tracking error does not match measurements")
                if actual > .05:
                    raise ValueError(f"Tracking error {actual:.4f} exceeds demo tolerance .05 rad")
            home_error = max(abs(a-b) for a, b in zip(trace["frames"][-1]["qpos"], trace["home"]))
            if home_error > .05:
                raise ValueError(f"Home error {home_error:.4f} exceeds .05 rad")
            summary["home_error_rad"] = home_error
        elif any(f["mode"] != "kinematic" or f["source"] != "scripted" for f in trace["frames"]):
            raise ValueError("G1 showcase provenance mismatch")
        summary[name] = {"frames": len(trace["frames"]), "actuated_joints": len(trace["joints"])}
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    print(json.dumps(verify(args.directory), indent=2))


if __name__ == "__main__":
    main()
