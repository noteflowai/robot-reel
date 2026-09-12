"""Validate and package a recorded VLA rollout without importing ML libraries."""
import argparse
import json
import math
from pathlib import Path
import re

from .compare import digest

SCHEMA = "robot-reel-vla-1"
REQUIRED = {"trace.json", "main.mp4", "wrist.mp4", "main-poster.png", "wrist-poster.png", "index.html", "NOTICE.txt", "LICENSE"}
CHANNELS = ["delta_x", "delta_y", "delta_z", "delta_rx", "delta_ry", "delta_rz", "gripper"]


def numbers(values, count):
    return isinstance(values, list) and len(values) == count and all(type(v) in (int, float) and math.isfinite(v) for v in values)


def validate_trace(trace):
    if not isinstance(trace, dict) or trace.get("schema") != SCHEMA or type(trace.get("fps")) is not int or trace["fps"] != 20:
        raise ValueError("Unsupported VLA schema or frame rate")
    if not isinstance(trace.get("task"), str) or not trace["task"].strip():
        raise ValueError("Missing language task")
    if trace.get("suite") != "libero_spatial" or type(trace.get("task_id")) is not int or not 0 <= trace["task_id"] < 10:
        raise ValueError("Unsupported task suite")
    if trace.get("channels") != CHANNELS or trace.get("state_units") != ["m", "m", "m", "rad", "rad", "rad", "m", "m"]:
        raise ValueError("VLA channel convention mismatch")
    source = trace.get("source", {})
    if not isinstance(source, dict) or source.get("kind") != "policy_rollout" or source.get("device") != "cpu" or source.get("control_mode") != "relative":
        raise ValueError("Unsupported VLA provenance")
    if source.get("policy") != "HuggingFaceVLA/smolvla_libero" or source.get("versions", {}).get("lerobot") != "0.6.1":
        raise ValueError("Unsupported policy adapter")
    for key, length in (("policy_revision", 40), ("vlm_revision", 40), ("assets_revision", 40), ("checkpoint_sha256", 64)):
        if not isinstance(source.get(key), str) or not re.fullmatch(f"[a-f0-9]{{{length}}}", source[key]):
            raise ValueError(f"Invalid {key}")
    chunk = source.get("n_action_steps")
    if type(chunk) is not int or not 1 <= chunk <= 50:
        raise ValueError("Invalid action chunk length")
    frames = trace.get("frames")
    if not isinstance(frames, list) or not 2 <= len(frames) <= 281:
        raise ValueError("Expected action frames and one terminal observation")
    result = trace.get("result", {})
    if (
        not isinstance(result, dict) or type(result.get("max_steps")) is not int
        or not 1 <= result["max_steps"] <= 280
        or not numbers([result.get("wall_seconds")], 1) or result["wall_seconds"] < 0
        or type(trace.get("seed")) is not int or trace.get("initial_state_id") != 0
    ):
        raise ValueError("Invalid VLA run metadata")
    start = result.get("start_sim_time")
    if type(start) not in (int, float) or not math.isfinite(start) or start < 0:
        raise ValueError("Invalid initial simulator time")
    success = False
    for i, frame in enumerate(frames):
        terminal = i == len(frames)-1
        if not isinstance(frame, dict) or type(frame.get("frame")) is not int or frame["frame"] != i or frame.get("terminal") is not terminal:
            raise ValueError("Nonsequential VLA frame or terminal observation")
        if not numbers([frame.get("episode_time"), frame.get("sim_time")], 2):
            raise ValueError("Invalid VLA timestamp")
        if abs(frame["episode_time"]-i/20) > 1e-9 or abs(frame["sim_time"]-(start+i/20)) > 1e-6:
            raise ValueError("VLA observation/action clock mismatch")
        if not numbers(frame.get("state"), 8) or not numbers(frame.get("joint_position"), 7):
            raise ValueError("Invalid measured robot state")
        if terminal:
            if any(frame.get(k) is not None for k in ("action", "proposed_action", "inference_frame", "next_success", "reward")):
                raise ValueError("Terminal observation must not contain a fabricated action")
            continue
        if not numbers(frame.get("action"), 7) or not numbers(frame.get("proposed_action"), 7):
            raise ValueError("Invalid policy action")
        if frame["action"] != [min(1., max(-1., v)) for v in frame["proposed_action"]]:
            raise ValueError("Applied action does not match the recorded clipping rule")
        if type(frame.get("inference_frame")) is not int or frame["inference_frame"] != i-i % chunk:
            raise ValueError("Action does not reference its inference observation")
        if type(frame.get("next_success")) is not bool or not numbers([frame.get("reward")], 1):
            raise ValueError("Invalid action result")
        if success:
            raise ValueError("Recording continued after task success")
        success = success or frame["next_success"]
    count = len(frames)-1
    calls = trace.get("inference_calls")
    expected = list(range(0, count, chunk))
    if not isinstance(calls, list) or not all(isinstance(call, dict) for call in calls) or [call.get("frame") for call in calls] != expected:
        raise ValueError("Missing inference calls")
    if any(not numbers([call.get("wall_seconds")], 1) or call["wall_seconds"] < 0 for call in calls):
        raise ValueError("Invalid inference timing")
    if type(result.get("actions")) is not int or result["actions"] != count or count > result["max_steps"] or result.get("simulation_seconds") != count/20:
        raise ValueError("VLA result length mismatch")
    if result.get("outcome") not in ("success", "step_limit", "terminated") or (result["outcome"] == "success") != success:
        raise ValueError("VLA outcome disagrees with action results")
    if result["outcome"] == "step_limit" and result.get("max_steps") != count:
        raise ValueError("Step-limit outcome does not match the recording")
    return {"actions": count, "frames": len(frames), "fps": 20, "outcome": result["outcome"], "inference_calls": len(calls)}


def export_viewer(trace, path):
    validate_trace(trace)
    payload = json.dumps(trace, separators=(",", ":"), allow_nan=False).replace("<", "\\u003c")
    template = Path(__file__).with_name("vla.html").read_text()
    Path(path).write_text(template.replace("__VLA_DATA__", payload))


def seal(directory):
    directory = Path(directory)
    trace = json.loads((directory/"trace.json").read_text())
    validate_trace(trace)
    export_viewer(trace, directory/"index.html")
    (directory/"manifest.json").write_text(json.dumps({
        "schema": SCHEMA, "sha256": {name: digest(directory/name) for name in sorted(REQUIRED)},
    }, indent=2)+"\n")
    return verify(directory)


def verify(directory):
    directory = Path(directory)
    manifest = json.loads((directory/"manifest.json").read_text())
    if manifest.get("schema") != SCHEMA or set(manifest.get("sha256", {})) != REQUIRED:
        raise ValueError("Incomplete VLA manifest")
    for filename, expected in manifest["sha256"].items():
        if digest(directory/filename) != expected:
            raise ValueError(f"VLA hash mismatch: {filename}")
    trace = json.loads((directory/"trace.json").read_text())
    result = validate_trace(trace)
    html = (directory/"index.html").read_text()
    marker = '<script id="vla-data" type="application/json">'
    if html.count(marker) != 1 or json.loads(html.split(marker)[1].split("</script>", 1)[0]) != trace:
        raise ValueError("VLA viewer differs from the recording")
    return result


def check_media(directory):
    import imageio_ffmpeg
    directory = Path(directory)
    result = verify(directory)
    for name in ("main", "wrist"):
        path = directory/f"{name}.mp4"
        count, duration = imageio_ffmpeg.count_frames_and_secs(str(path))
        reader = imageio_ffmpeg.read_frames(str(path))
        try:
            metadata = next(reader)
        finally:
            reader.close()
        if count != result["frames"] or abs(metadata["fps"]-result["fps"]) > .01 or abs(duration-count/result["fps"]) > .01:
            raise ValueError(f"{name} camera video and action timeline differ")
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--check-media", action="store_true")
    args = parser.parse_args(argv)
    try:
        print(json.dumps(check_media(args.source) if args.check_media else verify(args.source), indent=2))
    except (ValueError, OSError, TypeError, KeyError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
