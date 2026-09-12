"""Record an actual SmolVLA policy in LIBERO using the isolated VLA environment."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import random
import sys
import time

POLICY = ("HuggingFaceVLA/smolvla_libero", "6721902bc4d61e50a3bfdb11dfb4cb626f05d102")
VLM = ("HuggingFaceTB/SmolVLM2-500M-Instruct", "7b375e1b73b11138ff12fe22c8f2822d8fe03467")
ASSETS = ("lerobot/libero-assets", "0b3ea86be5fe169d0fd036ae63d1070ec09e90f6")


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cache", type=Path, default=Path("artifacts/vla-cache"))
    parser.add_argument("--max-steps", type=int, default=280)
    parser.add_argument("--action-steps", type=int, default=10)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--task-id", type=int, default=0)
    parser.add_argument("--threads", type=int, default=2)
    args = parser.parse_args()
    if not 1 <= args.max_steps <= 280 or not 1 <= args.action_steps <= 50 or not 1 <= args.threads <= 16:
        parser.error("Expected max-steps 1–280, action-steps 1–50, threads 1–16")
    if not 0 <= args.task_id < 10:
        parser.error("Choose a libero_spatial task index from 0 to 9")
    if args.output.exists() and any(args.output.iterdir()):
        parser.error("Choose an empty recording directory")
    cache = args.cache.resolve()
    cache.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("HF_HOME", str(cache/"huggingface"))
    os.environ["LIBERO_CONFIG_PATH"] = str(cache/"libero")
    os.environ.setdefault("MPLCONFIGDIR", str(cache/"matplotlib"))
    os.environ.setdefault("MUJOCO_GL", "egl")
    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
    os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
    from importlib.metadata import version
    import gymnasium as gym
    import imageio_ffmpeg
    import numpy as np
    from PIL import Image
    import torch
    import yaml
    from huggingface_hub import snapshot_download

    for name, expected in (("lerobot", "0.6.1"), ("hf-libero", "0.1.4"), ("mujoco", "3.8.1")):
        if version(name) != expected:
            raise ValueError(f"Expected {name}=={expected}; use requirements/vla.txt in an isolated environment")
    torch.set_num_threads(args.threads)
    torch.manual_seed(args.seed)
    np.random.seed(args.seed)
    random.seed(args.seed)
    print("Loading pinned policy and simulation assets...", flush=True)
    model_dir = Path(snapshot_download(POLICY[0], revision=POLICY[1], allow_patterns=["*.json", "*.safetensors", "README.md"]))
    vlm_dir = Path(snapshot_download(VLM[0], revision=VLM[1], allow_patterns=["*.json", "*.txt", "*.model"]))
    asset_dir = Path(snapshot_download(ASSETS[0], revision=ASSETS[1], repo_type="dataset"))
    package = Path(importlib.util.find_spec("libero").origin).parent/"libero"
    config = {
        "benchmark_root": str(package), "bddl_files": str(package/"bddl_files"),
        "init_states": str(package/"init_files"), "datasets": str(cache/"datasets"),
        "assets": str(asset_dir),
    }
    (cache/"libero").mkdir(exist_ok=True)
    (cache/"libero/config.yaml").write_text(yaml.safe_dump(config))
    import libero.libero as libero_runtime
    # hf-libero 0.1.4 ignores config.yaml in get_assets_path(). Resolve its cache
    # explicitly to the pinned snapshot, avoiding its unpinned ~/.cache download.
    libero_runtime._assets_path_cache = str(asset_dir)
    from libero.libero import benchmark
    from lerobot.envs.configs import LiberoEnv as LiberoConfig
    from lerobot.envs.libero import LiberoEnv
    from lerobot.envs.utils import preprocess_observation
    from lerobot.policies.factory import make_pre_post_processors
    from lerobot.policies.smolvla.configuration_smolvla import SmolVLAConfig
    from lerobot.policies.smolvla.modeling_smolvla import SmolVLAPolicy

    cfg = SmolVLAConfig.from_pretrained(str(model_dir))
    cfg.device = "cpu"
    cfg.n_action_steps = args.action_steps
    cfg.load_vlm_weights = False  # Full policy checkpoint includes the VLM weights.
    cfg.vlm_model_name = str(vlm_dir)
    print("Loading SmolVLA on CPU...", flush=True)
    policy = SmolVLAPolicy.from_pretrained(model_dir, config=cfg, local_files_only=True, strict=True)
    pre, post = make_pre_post_processors(
        cfg, pretrained_path=str(model_dir),
        preprocessor_overrides={
            "device_processor": {"device": "cpu"},
            "tokenizer_processor": {"tokenizer_name": str(vlm_dir)},
        },
        postprocessor_overrides={"device_processor": {"device": "cpu"}},
    )
    env_cfg = LiberoConfig(task="libero_spatial", task_ids=[args.task_id], observation_height=256, observation_width=256)
    env_pre, env_post = env_cfg.get_env_processors()
    suite = benchmark.get_benchmark_dict()["libero_spatial"]()
    raw_env = LiberoEnv(
        task_suite=suite, task_id=args.task_id, task_suite_name="libero_spatial",
        obs_type="pixels_agent_pos", observation_height=256, observation_width=256,
        control_freq=20, init_states=True, episode_index=0, hard_reset=True,
    )
    env = gym.vector.SyncVectorEnv([lambda: raw_env])
    print("Starting task:", raw_env.task_description, flush=True)
    obs, _ = env.reset(seed=args.seed)
    policy.reset()
    args.output.mkdir(parents=True, exist_ok=True)
    writers = {}
    for name in ("main", "wrist"):
        writer = imageio_ffmpeg.write_frames(
            str(args.output/f"{name}.mp4"), (256, 256), fps=20,
            codec="libx264", pix_fmt_out="yuv420p", quality=8, ffmpeg_log_level="error",
        )
        writer.send(None)
        writers[name] = writer
    frames = []
    start_time = float(raw_env._env.env.sim.data.time)
    clock = time.monotonic()
    outcome = "step_limit"
    inference_calls = []

    def observation_frame(observation, step):
        batch = preprocess_observation(observation)
        batch["task"] = [raw_env.task_description]
        batch = env_pre(batch)
        state = batch["observation.state"][0].tolist()
        for name, key in (("main", "image"), ("wrist", "image2")):
            # Save exactly the orientation used by the policy, before resizing.
            pixels = observation["pixels"][key][0][::-1, ::-1].copy()
            writers[name].send(pixels)
            if step == 0:
                Image.fromarray(pixels).save(args.output/f"{name}-poster.png")
        return batch, {
            "frame": step, "episode_time": step/20,
            "sim_time": float(raw_env._env.env.sim.data.time), "state": state,
            "joint_position": observation["robot_state"]["joints"]["pos"][0].tolist(),
        }

    try:
        for step in range(args.max_steps):
            batch, row = observation_frame(obs, step)
            is_inference = step % args.action_steps == 0
            begin = time.monotonic()
            with torch.inference_mode():
                normalized = policy.select_action(pre(batch))
                action = env_post({"action": post(normalized)})["action"].cpu().numpy()
            if not np.isfinite(action).all():
                raise ValueError("Policy produced a non-finite action")
            # LIBERO/robosuite clips normalized controls internally. Record both.
            applied = np.clip(action, -1, 1)
            obs, reward, terminated, truncated, info = env.step(applied)
            success = bool(np.asarray(info.get("is_success", [False]))[0])
            row.update(
                action=applied[0].tolist(), proposed_action=action[0].tolist(),
                inference_frame=step-step % args.action_steps,
                next_success=success, reward=float(reward[0]), terminal=False,
            )
            frames.append(row)
            if is_inference:
                inference_calls.append({"frame": step, "wall_seconds": time.monotonic()-begin})
                print(f"Step {step:03d}: inference + step {inference_calls[-1]['wall_seconds']:.2f}s; success={success}", flush=True)
            if success or bool(terminated[0]) or bool(truncated[0]):
                outcome = "success" if success else "terminated"
                break
        _, terminal = observation_frame(obs, len(frames))
        terminal.update(action=None, proposed_action=None, inference_frame=None, next_success=None, reward=None, terminal=True)
        frames.append(terminal)
    finally:
        for writer in writers.values():
            writer.close()
        env.close()
    document = {
        "schema": "robot-reel-vla-1", "fps": 20, "task": raw_env.task_description,
        "suite": "libero_spatial", "task_id": args.task_id, "seed": args.seed, "initial_state_id": 0,
        "source": {
            "kind": "policy_rollout", "policy": POLICY[0], "policy_revision": POLICY[1],
            "vlm": VLM[0], "vlm_revision": VLM[1], "assets": ASSETS[0], "assets_revision": ASSETS[1],
            "checkpoint_sha256": sha(model_dir/"model.safetensors"), "device": "cpu",
            "n_action_steps": args.action_steps, "denoising_steps": cfg.num_steps,
            "control_mode": "relative", "observation_orientation": "both image axes flipped, matching LeRobot LIBERO preprocessing",
            "settle_steps": 10, "hard_reset": True,
            "versions": {name: version(name) for name in ("lerobot", "hf-libero", "robosuite", "mujoco", "torch", "transformers", "numpy")},
        },
        "channels": ["delta_x", "delta_y", "delta_z", "delta_rx", "delta_ry", "delta_rz", "gripper"],
        "action_units": "normalized controls in [-1, 1]; not joint angles or physical distances",
        "state_units": ["m", "m", "m", "rad", "rad", "rad", "m", "m"],
        "frames": frames, "inference_calls": inference_calls,
        "result": {
            "outcome": outcome, "actions": len(frames)-1, "simulation_seconds": (len(frames)-1)/20,
            "start_sim_time": start_time, "max_steps": args.max_steps,
            "wall_seconds": time.monotonic()-clock,
        },
    }
    (args.output/"trace.json").write_text(json.dumps(document, indent=2, allow_nan=False)+"\n")
    print(json.dumps(document["result"], indent=2), flush=True)
    print("Recorded:", args.output.resolve(), flush=True)


if __name__ == "__main__":
    main()
