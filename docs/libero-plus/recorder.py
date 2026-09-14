"""Execute a preselected official LIBERO-Plus plan with the local SmolVLA bridge."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import platform
import subprocess
import sys
import time
import traceback
import urllib.request
from pathlib import Path


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write(path, body):
    Path(path).write_text(json.dumps(body, indent=2, allow_nan=False) + "\n")


def request(endpoint, body=None):
    req = urllib.request.Request(
        endpoint, data=None if body is None else json.dumps(body, allow_nan=False).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=120) as reply:
        return json.load(reply)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--libero-repo", type=Path, required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    for name in ("libero_repo", "plan", "cache", "output"):
        setattr(args, name, getattr(args, name).resolve())
    plan = json.loads(args.plan.read_text())
    if plan.get("schema") != "robot-reel.libero-plus-plan.v1":
        raise ValueError("expected official reviewed plan")
    revision = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=args.libero_repo, text=True
    ).strip()
    if revision != plan["source"]["revision"]:
        raise ValueError("upstream revision changed")
    for path, expected in plan["source"]["source_files"].items():
        if sha(args.libero_repo / path) != expected:
            raise ValueError("reviewed source changed")
    libroot = args.libero_repo / "libero/libero"
    init = libroot / plan["source"]["initial_state_file"]
    if sha(init) != plan["source"]["initial_state_sha256"]:
        raise ValueError("initial state changed")
    for condition in plan["conditions"]:
        if sha(libroot / condition["bddl_file"]) != condition["bddl_sha256"]:
            raise ValueError("native task changed")
    endpoint = "http://127.0.0.1:47866"
    policy = request(endpoint + "/health")
    args.output.mkdir(parents=True, exist_ok=False)
    config = args.cache / "libero"
    config.mkdir(parents=True, exist_ok=True)
    (config / "config.yaml").write_text("\n".join(
        key + ": " + json.dumps(str(value)) for key, value in {
            "benchmark_root": libroot, "bddl_files": libroot / "bddl_files",
            "init_states": libroot / "init_files", "assets": libroot / "assets",
            "datasets": args.cache / "datasets",
        }.items()
    ) + "\n")
    os.environ["LIBERO_CONFIG_PATH"] = str(config)
    os.environ.setdefault("MUJOCO_GL", "egl")
    sys.path.insert(0, str(args.libero_repo))
    from importlib.metadata import version

    import imageio.v2 as imageio
    import numpy as np
    import torch
    from PIL import Image
    from libero.libero.envs import OffScreenRenderEnv
    from libero.libero.benchmark import grab_language_from_filename

    language = grab_language_from_filename(plan["suite"], plan["base_task"] + ".bddl")
    initial_states = torch.load(init, map_location="cpu", weights_only=False)
    initial = np.asarray(initial_states[plan["initial_state_index"]])
    source = {
        "policy": policy, "recorder_sha256": sha(__file__), "plan_sha256": sha(args.plan),
        "python": platform.python_version(),
        "versions": {name: version(name) for name in ("libero", "robosuite", "mujoco", "numpy")},
        "runtime": "official LIBERO-Plus source; separate local LeRobot policy process",
    }
    write(args.output / "source.json", source)
    write(args.output / "plan.json", plan)
    summary = []
    for condition in plan["conditions"]:
        destination = args.output / condition["name"]
        destination.mkdir()
        request(endpoint + "/reset", {"seed": plan["seed"], "language": language})
        env, writer = None, None
        frames, status, error, success = [], "step_limit", None, False
        started = time.monotonic()
        try:
            env = OffScreenRenderEnv(
                bddl_file_name=str(libroot / "bddl_files" / plan["suite"] / (condition["task_name"] + ".bddl")),
                camera_heights=256, camera_widths=256,
            )
            env.seed(0)
            env.reset()
            obs = env.set_init_state(initial)
            for _ in range(plan["settle_steps"]):
                obs, _, _, _ = env.step([0, 0, 0, 0, 0, 0, -1])
            sim = env.env.sim
            write(destination / "native-scene.json", {
                key: np.asarray(getattr(sim.model, key)).tolist() for key in (
                    "cam_pos", "cam_quat", "cam_fovy", "light_pos", "light_diffuse",
                )
            })
            write(destination / "initial-state.json", {
                "qpos": sim.data.qpos.tolist(), "qvel": sim.data.qvel.tolist(),
                "time_s": float(sim.data.time), "bddl_language": env.language_instruction,
            })
            writer = imageio.get_writer(
                str(destination / "rollout.mp4"), fps=20, codec="libx264",
                quality=7, macro_block_size=1,
            )
            for step in range(plan["max_steps"]):
                images = [obs[key] for key in ("agentview_image", "robot0_eye_in_hand_image")]
                visible = np.concatenate([image[::-1, ::-1] for image in images], axis=1)
                writer.append_data(visible)
                if step == 0:
                    Image.fromarray(visible).save(destination / "poster.png")
                reply = request(endpoint + "/action", {
                    **{name: base64.b64encode(image.tobytes()).decode()
                       for name, image in zip(("primary", "wrist"), images)},
                    **{name: obs["robot0_" + name].tolist()
                       for name in ("eef_pos", "eef_quat", "gripper_qpos")},
                })
                if reply["step"] != step:
                    raise ValueError("policy action stream is out of order")
                before = float(sim.data.time)
                obs, reward, done, _ = env.step(reply["action"])
                success = bool(done)
                frames.append({
                    "step": step, "time_s": before, "next_time_s": float(sim.data.time),
                    "observation_sha256": [hashlib.sha256(image.tobytes()).hexdigest() for image in images],
                    "policy": reply, "reward": float(reward), "success": success,
                    "next_qpos": sim.data.qpos.tolist(), "next_qvel": sim.data.qvel.tolist(),
                })
                if step % 10 == 0:
                    print(condition["name"], "step", step, "success", success, flush=True)
                    write(destination / "progress.json", {"frames": frames})
                if success:
                    status = "success"
                    break
            writer.append_data(np.concatenate([
                obs[key][::-1, ::-1] for key in ("agentview_image", "robot0_eye_in_hand_image")
            ], axis=1))
        except Exception as problem:
            status, error = "runtime_error", f"{type(problem).__name__}: {problem}"
            (destination / "error.txt").write_text(traceback.format_exc())
        finally:
            if writer:
                writer.close()
            if env:
                env.close()
        record = {
            "schema": "robot-reel.libero-plus-run.v1", "source": source,
            "condition": condition, "language": language, "status": status,
            "error": error, "task_success": success, "steps": len(frames),
            "elapsed_seconds": time.monotonic() - started, "frames": frames,
            "scope": plan["scope"],
        }
        write(destination / "run.json", record)
        summary.append({key: record[key] for key in (
            "condition", "status", "task_success", "steps", "elapsed_seconds", "error",
        )})
        write(args.output / "summary.json", {"runs": summary})
    if any(row["status"] == "runtime_error" for row in summary):
        raise SystemExit(2)


if __name__ == "__main__":
    main()
