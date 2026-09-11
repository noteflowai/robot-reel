"""Check capture consistency; this does not certify autonomy or task success."""
import argparse
import hashlib
import json
import math
from pathlib import Path

REQUIRED_FILES = {"so100-trace.json", "unitree_g1-trace.json", "so100-raw.mp4",
                  "unitree_g1-raw.mp4", "robot-reel.mp4", "robot-reel-vertical.mp4"}


def finite(values):
    return all(type(v) in (int, float) and math.isfinite(v) for v in values)


def verify_trace(trace, director):
    name = trace["robot"]
    joints, frames = trace["joints"], trace["frames"]
    if not joints or len(set(joints)) != len(joints) or not frames:
        raise ValueError(f"{name}: empty or duplicate joint list, or no frames")
    if trace["fps"] != 30:
        raise ValueError(f"{name}: unsupported frame rate")
    if len(trace["home"]) != len(joints) or not finite(trace["home"]):
        raise ValueError(f"{name}: invalid home pose")
    last_time = -1
    for i, frame in enumerate(frames):
        if type(frame["frame"]) is not int or frame["frame"] != i:
            raise ValueError(f"{name}: nonsequential frame")
        for field in ("qpos", "target"):
            if len(frame[field]) != len(joints) or not finite(frame[field]):
                raise ValueError(f"{name}: invalid {field} values")
        if not finite([frame["sim_time"]]) or frame["sim_time"] < 0:
            raise ValueError(f"{name}: invalid simulation time")
        if name == "so100":
            if frame["mode"] != "physics" or frame["source"] != director:
                raise ValueError("Arm frame provenance mismatch")
            if frame["sim_time"] <= last_time:
                raise ValueError("Arm simulation time must increase")
        elif name == "microduck":
            if frame["mode"] != "physics" or frame["source"] != "policy" or frame["sim_time"] <= last_time:
                raise ValueError("Microduck policy frame provenance mismatch")
        elif name.startswith("braking_"):
            if frame["mode"] != "physics" or frame["source"] != "scripted" or frame["sim_time"] <= last_time:
                raise ValueError("Driving controller frame provenance mismatch")
        elif frame["mode"] != "kinematic" or frame["source"] != "scripted":
            raise ValueError("G1 showcase provenance mismatch")
        last_time = frame["sim_time"]
    if name == "microduck":
        steps = trace.get("policy_steps", [])
        if len(steps) != round(len(frames)/trace["fps"]*50):
            raise ValueError("Microduck capture must include every 50 Hz policy step")
        for i, step in enumerate(steps):
            if step["step"] != i or not finite(step["action"]) or not finite(step["target"]):
                raise ValueError("Invalid policy step")
            if len(step["action"]) != len(joints) or len(step["target"]) != len(joints):
                raise ValueError("Policy action dimension mismatch")
        for frame in frames:
            index = frame.get("policy_step")
            if type(index) is not int or not 0 <= index < len(steps):
                raise ValueError("Frame references a missing policy step")
            step = steps[index]
            if frame["target"] != step["target"]:
                raise ValueError("Frame target disagrees with its policy step")
            if not 0 <= frame["sim_time"]-step["sim_time"] <= .020001:
                raise ValueError("Frame and policy timestamps disagree")
        if trace["outcome"]["final_position_m"] != frames[-1]["base_position_m"]:
            raise ValueError("Microduck endpoint disagrees with recorded frame")
    if name.startswith("braking_"):
        outcome = trace["outcome"]
        if outcome["collision"] != any(f["collision"] for f in frames):
            raise ValueError("Collision summary disagrees with recorded contact flags")
        if abs(outcome["minimum_gap_m"]-min(f["qpos"][1] for f in frames)) > 1e-8:
            raise ValueError("Minimum gap disagrees with recorded telemetry")
    if name != "so100":
        return {"frames": len(frames), "channels" if name.startswith("braking_") else "actuated_joints": len(joints)}
    if len(trace["actions"]) != 4:
        raise ValueError("Expected four arm motions")
    cursor = 0
    for action in trace["actions"]:
        start, end = action["start_frame"], action["end_frame"]
        if type(start) is not int or type(end) is not int or start != cursor or not start <= end < len(frames):
            raise ValueError("Actions must cover every arm frame exactly once, in order")
        if action["source"] != director:
            raise ValueError("Director provenance mismatch")
        for field in ("measured", "target"):
            if set(action[field]) != set(joints) or not finite(action[field].values()):
                raise ValueError(f"Invalid action {field}")
        for j, joint in enumerate(joints):
            if abs(action["measured"][joint] - frames[end]["qpos"][j]) > 1e-9:
                raise ValueError("Action measurement does not match its recorded endpoint")
        target = [action["target"][j] for j in joints]
        for frame in frames[start:end+1]:
            if frame["target"] != target or frame["label"] != action["label"]:
                raise ValueError("Action target or label does not match its recorded frames")
        actual = max(abs(action["measured"][j]-action["target"][j]) for j in joints)
        if not finite([action["max_error_rad"]]) or abs(actual-action["max_error_rad"]) > 1e-8:
            raise ValueError("Reported tracking error does not match measurements")
        if actual > .05:
            raise ValueError(f"Tracking error {actual:.4f} exceeds demo tolerance .05 rad")
        cursor = end+1
    if cursor != len(frames):
        raise ValueError("Actions leave trailing frames uncovered")
    home_error = max(abs(a-b) for a, b in zip(frames[-1]["qpos"], trace["home"]))
    if home_error > .05:
        raise ValueError(f"Home error {home_error:.4f} exceeds .05 rad")
    return {"frames": len(frames), "actuated_joints": len(joints), "home_error_rad": home_error}


def verify(output: Path):
    manifest = json.loads((output / "manifest.json").read_text())
    if manifest.get("schema") not in (1, 2) or manifest.get("arm_director") not in ("agent", "scripted"):
        raise ValueError("Unsupported manifest schema or director")
    hashes = manifest.get("sha256", {})
    names = manifest.get("scenes", ["so100", "unitree_g1"])
    allowed = {"so100", "unitree_g1", "microduck", "braking_late", "braking_early"}
    if not isinstance(names, list) or not names or len(set(names)) != len(names) or not set(names) <= allowed:
        raise ValueError("Invalid scene list")
    required = {"robot-reel.mp4", "robot-reel-vertical.mp4"}
    for name in names:
        required.update({f"{name}-raw.mp4", f"{name}-trace.json"})
    if not required <= hashes.keys():
        raise ValueError("Manifest must hash all required video and trace files")
    for name, expected in hashes.items():
        if Path(name).name != name:
            raise ValueError("Manifest filenames must be local basenames")
        actual = hashlib.sha256((output / name).read_bytes()).hexdigest()
        if actual != expected:
            raise ValueError(f"Hash mismatch: {name}")
    summary = {}
    for name in names:
        trace = json.loads((output / f"{name}-trace.json").read_text())
        if trace["robot"] != name:
            raise ValueError("Trace robot does not match its filename")
        summary[name] = verify_trace(trace, manifest["arm_director"])
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    print(json.dumps(verify(args.directory), indent=2))


if __name__ == "__main__":
    main()
