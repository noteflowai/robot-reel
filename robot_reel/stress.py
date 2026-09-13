"""Validate paired, closed-loop SmolVLA trials using the standard library."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import re

from .vla import validate_trace as validate_vla

SCHEMA = "robot-reel-stress-1"
CONDITIONS = [
    {"id": "reference", "label": "Reference", "light_scale": 1., "camera_offset_m": [0., 0., 0.]},
    {"id": "dim", "label": "25% light", "light_scale": .25, "camera_offset_m": [0., 0., 0.]},
    {"id": "camera", "label": "Camera +12 cm", "light_scale": 1., "camera_offset_m": [.12, 0., 0.]},
]
MEDIA = ("main.mp4", "wrist.mp4", "main-poster.png", "wrist-poster.png")


def canonical_hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, value):
    path = Path(path)
    temporary = path.with_suffix(path.suffix+".tmp")
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False)+"\n")
    temporary.replace(path)


def plan(seeds=10, max_steps=160, action_steps=10, threads=2, device="cpu"):
    document = {
        "schema": SCHEMA, "suite": "libero_spatial", "task_id": 0,
        "seeds": list(range(seeds)), "initial_state_ids": list(range(seeds)),
        "conditions": CONDITIONS, "max_steps": max_steps, "action_steps": action_steps,
        "fps": 20, "precision": "float32", "threads": threads,
        "policy": "HuggingFaceVLA/smolvla_libero",
        "policy_revision": "6721902bc4d61e50a3bfdb11dfb4cb626f05d102",
        "noise": "independent torch.Generator per seed; identical noise sequence across paired conditions",
        "measurement": "new closed-loop policy rollout in every condition",
    }
    # Preserve the already-locked CPU plan and its hashes exactly.
    if device != "cpu":
        document["device"] = device
    return document


def validate_plan(document):
    if not isinstance(document, dict):
        raise ValueError("Expected an experiment plan")
    seeds = document.get("seeds", [])
    if not isinstance(seeds, list) or not 1 <= len(seeds) <= 10:
        raise ValueError("Expected one to ten paired seeds")
    for key, low, high in (("max_steps", 1, 280), ("action_steps", 1, 50), ("threads", 1, 16)):
        if type(document.get(key)) is not int or not low <= document[key] <= high:
            raise ValueError(f"Invalid experiment {key}")
    device = document.get("device", "cpu")
    if device not in ("cpu", "cuda"):
        raise ValueError("Unsupported experiment device")
    if canonical_hash(document) != canonical_hash(plan(len(seeds), document["max_steps"], document["action_steps"], document["threads"], device)):
        raise ValueError("Experiment definition or condition mismatch")


def trial_id(seed, condition):
    return f"seed-{seed:02d}-{condition}"


def _finite(values, length=None):
    return isinstance(values, list) and (length is None or len(values) == length) and all(
        type(v) in (int, float) and math.isfinite(v) for v in values
    )


def validate_run(trace, document):
    validate_plan(document)
    result = validate_vla(trace)
    meta = trace.get("stress", {})
    seed = trace["seed"]
    if seed not in document["seeds"] or trace["initial_state_id"] != seed:
        raise ValueError("Trial does not use the declared paired initial state")
    condition = next((c for c in CONDITIONS if c["id"] == meta.get("condition")), None)
    if (
        condition is None or meta.get("plan_sha256") != canonical_hash(document)
        or meta.get("trial_id") != trial_id(seed, condition["id"])
        or trace["source"].get("precision") != document["precision"]
        or trace["source"]["policy_revision"] != document["policy_revision"]
        or trace["source"]["n_action_steps"] != document["action_steps"]
        or trace["result"]["max_steps"] != document["max_steps"]
        or trace["source"].get("threads") != document["threads"]
        or trace["source"].get("device") != document.get("device", "cpu")
        or trace["task_id"] != document["task_id"] or trace["suite"] != document["suite"]
        or meta.get("noise_seed") != seed or meta.get("camera_name") != "agentview"
        or not re.fullmatch("[a-f0-9]{64}", meta.get("task_bddl_sha256", ""))
    ):
        raise ValueError("Trial differs from the locked experiment")
    source = trace["source"]
    if source["device"] == "cuda" and (
        not isinstance(source.get("gpu"), str) or not source["gpu"]
        or source.get("tf32") is not False
    ):
        raise ValueError("Missing GPU hardware or precision evidence")
    if (
        source.get("vlm_revision") != "7b375e1b73b11138ff12fe22c8f2822d8fe03467"
        or source.get("assets_revision") != "0b3ea86be5fe169d0fd036ae63d1070ec09e90f6"
        or source.get("denoising_steps") != 10 or source.get("settle_steps") != 10
        or source.get("hard_reset") is not True
        or any(source["versions"].get(k) != v for k, v in (
            ("lerobot", "0.6.1"), ("hf-libero", "0.1.4"), ("robosuite", "1.4.0"), ("mujoco", "3.8.1"),
        ))
    ):
        raise ValueError("Trial differs from the pinned policy or simulator configuration")
    physics = meta.get("initial_physics", {})
    if (
        not isinstance(physics, dict)
        or not _finite(physics.get("qpos"), meta.get("nq"))
        or not _finite(physics.get("qvel"), meta.get("nv"))
        or type(meta.get("nq")) is not int or meta["nq"] < 1
        or type(meta.get("nv")) is not int or meta["nv"] < 1
        or not _finite([physics.get("time")])
        or abs(physics["time"]-trace["result"]["start_sim_time"]) > 1e-9
        or meta.get("initial_physics_sha256") != canonical_hash(physics)
    ):
        raise ValueError("Invalid initial physics evidence")
    before, after = meta.get("render_before", {}), meta.get("render_after", {})
    for state in (before, after):
        if not isinstance(state, dict) or not _finite(state.get("camera_pos"), 3) or not _finite(state.get("camera_quat"), 4):
            raise ValueError("Missing camera configuration")
        if not _finite([state.get("camera_fovy")]):
            raise ValueError("Invalid camera field of view")
        for key in ("light_ambient", "light_diffuse", "light_specular"):
            if not isinstance(state.get(key), list) or not state[key] or not all(_finite(row, 3) for row in state[key]):
                raise ValueError("Missing scene light configuration")
    if after["camera_quat"] != before["camera_quat"] or after["camera_fovy"] != before["camera_fovy"]:
        raise ValueError("Undeclared camera change")
    for axis in range(3):
        if abs(after["camera_pos"][axis]-before["camera_pos"][axis]-condition["camera_offset_m"][axis]) > 1e-8:
            raise ValueError("Camera perturbation does not match the plan")
    for key in ("light_ambient", "light_diffuse", "light_specular"):
        if len(before[key]) != len(after[key]):
            raise ValueError("Scene light count changed")
        for a, b in zip(before[key], after[key]):
            if any(abs(y-x*condition["light_scale"]) > 1e-6 for x, y in zip(a, b)):
                raise ValueError("Light perturbation does not match the plan")
    if meta.get("physics_unchanged_by_condition") is not True:
        raise ValueError("Rendering perturbation modified physical state")
    for call in trace["inference_calls"]:
        if (
            not _finite([call.get("policy_seconds"), call.get("env_step_seconds"), call.get("started_seconds"), call.get("finished_seconds")])
            or min(call["policy_seconds"], call["env_step_seconds"], call["started_seconds"]) < 0
            or call["finished_seconds"] < call["started_seconds"]
            or abs(call["wall_seconds"]-call["policy_seconds"]-call["env_step_seconds"]) > 1e-8
            or not re.fullmatch("[a-f0-9]{64}", call.get("noise_sha256", ""))
        ):
            raise ValueError("Invalid separate inference and simulation timing")
    for frame in trace["frames"]:
        if not frame["terminal"] and (not _finite([frame.get("env_step_seconds")]) or frame["env_step_seconds"] < 0):
            raise ValueError("Missing simulation step timing")
        hashes = frame.get("raw_camera_sha256", {})
        if not isinstance(hashes, dict) or set(hashes) != {"main", "wrist"} or any(
            not isinstance(h, str) or not re.fullmatch("[a-f0-9]{64}", h) for h in hashes.values()
        ):
            raise ValueError("Missing raw policy observation hashes")
    previous_end = 0.
    for call in trace["inference_calls"]:
        if (
            call["started_seconds"] < previous_end or call["finished_seconds"] > trace["result"]["wall_seconds"]
            or abs(call["env_step_seconds"]-trace["frames"][call["frame"]]["env_step_seconds"]) > 1e-9
            or call["finished_seconds"]-call["started_seconds"]+1e-6 < call["wall_seconds"]
        ):
            raise ValueError("Inference timing does not match its recorded step")
        previous_end = call["finished_seconds"]
    return result


def verify_run(directory, document):
    directory = Path(directory)
    manifest = json.loads((directory/"run-manifest.json").read_text())
    if manifest.get("schema") != SCHEMA or set(manifest.get("files", {})) != {"trace.json", *MEDIA}:
        raise ValueError("Incomplete stress run manifest")
    for name, expected in manifest["files"].items():
        if file_hash(directory/name) != expected:
            raise ValueError(f"Stress run hash mismatch: {name}")
    trace = json.loads((directory/"trace.json").read_text())
    validate_run(trace, document)
    return trace


def wilson(successes, count):
    """95% Wilson score interval for a displayed small-sample proportion."""
    if count == 0:
        return None
    z = 1.959963984540054
    p = successes/count
    denominator = 1+z*z/count
    center = (p+z*z/(2*count))/denominator
    half = z*math.sqrt(p*(1-p)/count+z*z/(4*count*count))/denominator
    return [max(0., center-half), min(1., center+half)]


def divergence(reference, other):
    """Measured EEF separation on the shared observation prefix, in meters."""
    distances = [
        math.dist(a["state"][:3], b["state"][:3])
        for a, b in zip(reference["frames"], other["frames"])
    ]
    peak = max(range(len(distances)), key=distances.__getitem__)
    return {
        "shared_observations": len(distances), "max_eef_distance_m": distances[peak],
        "max_eef_frame": peak, "first_action_l2": math.dist(reference["frames"][0]["action"], other["frames"][0]["action"]),
    }


def summarize(document, traces, attempts):
    expected = {trial_id(seed, c["id"]) for seed in document["seeds"] for c in CONDITIONS}
    by_id = {}
    for trace in traces:
        validate_run(trace, document)
        key = trace["stress"]["trial_id"]
        if key in by_id:
            raise ValueError("Duplicate trial would change the denominator")
        by_id[key] = trace
    if set(by_id) != expected:
        raise ValueError("Experiment must retain every planned trial")
    first = traces[0]
    for trace in traces:
        if trace["source"] != first["source"] or trace["task"] != first["task"] or trace["stress"]["task_bddl_sha256"] != first["stress"]["task_bddl_sha256"]:
            raise ValueError("Experiment changed the policy, runtime or task")
    pairs = []
    for seed in document["seeds"]:
        runs = [by_id[trial_id(seed, c["id"])] for c in CONDITIONS]
        reference = runs[0]
        for other in runs[1:]:
            if other["stress"]["initial_physics"] != reference["stress"]["initial_physics"]:
                raise ValueError("Paired trials start from different physical states")
            if other["stress"]["render_before"] != reference["stress"]["render_before"]:
                raise ValueError("Paired trials have different baseline scene settings")
            images = other["frames"][0]["raw_camera_sha256"]
            baseline = reference["frames"][0]["raw_camera_sha256"]
            if images["main"] == baseline["main"] or (
                other["stress"]["condition"] == "camera" and images["wrist"] != baseline["wrist"]
            ):
                raise ValueError("Initial policy views do not reflect the declared condition")
            a, b = reference["inference_calls"], other["inference_calls"]
            if [x["noise_sha256"] for x in a[:len(b)]] != [x["noise_sha256"] for x in b[:len(a)]]:
                raise ValueError("Paired trials do not share the same policy noise sequence")
            pairs.append({
                "seed": seed, "condition": other["stress"]["condition"],
                "reference_success": reference["result"]["outcome"] == "success",
                "condition_success": other["result"]["outcome"] == "success",
                **divergence(reference, other),
            })
    conditions = []
    for condition in CONDITIONS:
        runs = [by_id[trial_id(seed, condition["id"])] for seed in document["seeds"]]
        successes = sum(t["result"]["outcome"] == "success" for t in runs)
        times = [call["policy_seconds"] for t in runs for call in t["inference_calls"]]
        conditions.append({
            "id": condition["id"], "trials": len(runs), "successes": successes,
            "step_limits": sum(t["result"]["outcome"] == "step_limit" for t in runs),
            "terminated": sum(t["result"]["outcome"] == "terminated" for t in runs),
            "wilson95": wilson(successes, len(runs)),
            "inference_calls": len(times), "mean_policy_seconds": sum(times)/len(times),
            "simulation_seconds": sum(t["result"]["simulation_seconds"] for t in runs),
        })
    return {
        "planned_trials": len(expected), "completed_trials": len(traces),
        "attempts": len(attempts), "execution_errors": sum(a["status"] == "error" for a in attempts),
        "conditions": conditions, "pairs": pairs,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--check-media", action="store_true", help="Decode both policy cameras in every completed trial")
    parser.add_argument("--check-mcap", action="store_true", help="Read back and compare every MCAP telemetry message")
    parser.add_argument("--review", type=Path, help="Compare an exported review JSON with this complete collection")
    args = parser.parse_args(argv)
    from .stress_site import check_media, load_collection, verify_site
    try:
        result = verify_site(args.source)
        if args.review:
            from .stress_review import read_review, verify_record
            from .stress_site import payload
            result["review"] = verify_record(payload(*load_collection(args.source)), read_review(args.review))
        if args.check_media:
            result["media_trials_checked"] = len(check_media(args.source))
        if args.check_mcap:
            from .stress_mcap import check_mcap
            _, _, traces = load_collection(args.source)
            result["mcap"] = check_mcap(traces, args.source/"telemetry.mcap")
        print(json.dumps(result, indent=2))
    except ImportError as exc:
        parser.error(f"{exc}. Install robot-reel[inspect] for the optional media/MCAP checks.")
    except (ValueError, OSError, TypeError, KeyError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
