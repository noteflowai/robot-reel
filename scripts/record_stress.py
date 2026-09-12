"""Record paired native rendering perturbations with new SmolVLA inference."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import platform
import random
import sys
import time
import traceback

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from robot_reel.stress import (
    CONDITIONS, MEDIA, SCHEMA, canonical_hash, file_hash, plan, trial_id,
    validate_plan, validate_run, verify_run, write_json,
)
from scripts.record_smolvla import POLICY, VLM, ASSETS, sha


def load_runtime(args):
    cache = args.cache.resolve()
    cache.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("HF_HOME", str(cache/"huggingface"))
    os.environ["LIBERO_CONFIG_PATH"] = str(cache/"libero")
    os.environ.setdefault("MPLCONFIGDIR", str(cache/"matplotlib"))
    os.environ.setdefault("MUJOCO_GL", "egl")
    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
    os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
    from importlib.metadata import version
    import torch
    import yaml
    from huggingface_hub import snapshot_download
    if args.device == "cuda" and not torch.cuda.is_available():
        raise ValueError("CUDA is unavailable. Run scripts/check_vla_gpu.py in the execution environment; check device exposure and use requirements/vla-gpu.txt.")
    if args.device == "cuda":
        torch.backends.cuda.matmul.allow_tf32 = False
        torch.backends.cudnn.allow_tf32 = False

    for name, expected in (("lerobot", "0.6.1"), ("hf-libero", "0.1.4"), ("mujoco", "3.8.1")):
        if version(name) != expected:
            raise ValueError(f"Expected {name}=={expected}; use requirements/vla.txt")
    torch.set_num_threads(args.threads)
    print("Resolving the pinned policy, tokenizer and simulation assets...", flush=True)
    model_dir = Path(snapshot_download(POLICY[0], revision=POLICY[1], allow_patterns=["*.json", "*.safetensors", "README.md"]))
    vlm_dir = Path(snapshot_download(VLM[0], revision=VLM[1], allow_patterns=["*.json", "*.txt", "*.model"]))
    asset_dir = Path(snapshot_download(ASSETS[0], revision=ASSETS[1], repo_type="dataset"))
    package = Path(importlib.util.find_spec("libero").origin).parent/"libero"
    (cache/"libero").mkdir(exist_ok=True)
    (cache/"libero/config.yaml").write_text(yaml.safe_dump({
        "benchmark_root": str(package), "bddl_files": str(package/"bddl_files"),
        "init_states": str(package/"init_files"), "datasets": str(cache/"datasets"),
        "assets": str(asset_dir),
    }))
    import libero.libero as libero_runtime
    libero_runtime._assets_path_cache = str(asset_dir)
    from libero.libero import benchmark
    from lerobot.envs.configs import LiberoEnv as LiberoConfig
    from lerobot.policies.factory import make_pre_post_processors
    from lerobot.policies.smolvla.configuration_smolvla import SmolVLAConfig
    from lerobot.policies.smolvla.modeling_smolvla import SmolVLAPolicy

    cfg = SmolVLAConfig.from_pretrained(str(model_dir))
    cfg.device = args.device
    cfg.n_action_steps = args.action_steps
    cfg.load_vlm_weights = False
    cfg.vlm_model_name = str(vlm_dir)
    print(f"Loading strict checkpoint on {args.device}, with float32 inference...", flush=True)
    policy = SmolVLAPolicy.from_pretrained(model_dir, config=cfg, local_files_only=True, strict=True)
    policy.float().to(args.device).eval()
    pre, post = make_pre_post_processors(
        cfg, pretrained_path=str(model_dir),
        preprocessor_overrides={
            "device_processor": {"device": args.device},
            "tokenizer_processor": {"tokenizer_name": str(vlm_dir)},
        },
        postprocessor_overrides={"device_processor": {"device": args.device}},
    )
    env_cfg = LiberoConfig(task="libero_spatial", task_ids=[0], observation_height=256, observation_width=256)
    env_pre, env_post = env_cfg.get_env_processors()
    suite = benchmark.get_benchmark_dict()["libero_spatial"]()
    versions = {name: version(name) for name in ("lerobot", "hf-libero", "robosuite", "mujoco", "torch", "transformers", "numpy")}
    cpu_name = platform.machine()
    if Path("/proc/cpuinfo").exists():
        cpu_name = next((line.split(":", 1)[1].strip() for line in Path("/proc/cpuinfo").read_text().splitlines() if line.startswith("model name")), cpu_name)
    source = {
        "kind": "policy_rollout", "policy": POLICY[0], "policy_revision": POLICY[1],
        "vlm": VLM[0], "vlm_revision": VLM[1], "assets": ASSETS[0], "assets_revision": ASSETS[1],
        "checkpoint_sha256": sha(model_dir/"model.safetensors"), "device": args.device, "precision": "float32",
        "threads": args.threads, "cpu": cpu_name, "platform": platform.system()+" "+platform.machine(),
        "n_action_steps": args.action_steps, "denoising_steps": cfg.num_steps,
        "control_mode": "relative",
        "observation_orientation": "both image axes flipped, matching LeRobot LIBERO preprocessing",
        "settle_steps": 10, "hard_reset": True, "versions": versions,
    }
    if args.device == "cuda":
        source.update(gpu=torch.cuda.get_device_name(), tf32=False)
    print(f"Ready: {cpu_name}; {args.threads} threads; {cfg.num_steps} denoising steps", flush=True)
    return policy, cfg, pre, post, env_pre, env_post, suite, source


def collect(runtime, document, seed, condition, output):
    import imageio_ffmpeg
    import numpy as np
    from PIL import Image
    import torch
    from lerobot.envs.libero import LiberoEnv
    from lerobot.envs.utils import preprocess_observation
    from gymnasium.vector.utils import concatenate, create_empty_array

    policy, cfg, pre, post, env_pre, env_post, suite, source = runtime
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    generator = torch.Generator(device="cpu").manual_seed(seed)
    raw = LiberoEnv(
        task_suite=suite, task_id=0, task_suite_name="libero_spatial",
        obs_type="pixels_agent_pos", observation_height=256, observation_width=256,
        control_freq=20, init_states=True, episode_index=seed, hard_reset=True,
    )
    writers = {}
    output.mkdir(parents=True)
    try:
        observation, _ = raw.reset(seed=seed)
        if len(raw._init_states) <= seed:
            raise ValueError("Requested initial state is not present")
        sim = raw._env.env.sim
        model = sim.model
        camera_id = model.camera_name2id("agentview")
        if int(model.cam_bodyid[camera_id]) != 0:
            raise ValueError("Expected a world-fixed agentview camera")

        def physics():
            return {"qpos": sim.data.qpos.tolist(), "qvel": sim.data.qvel.tolist(), "time": float(sim.data.time)}

        def render_settings():
            return {
                "camera_pos": model.cam_pos[camera_id].tolist(), "camera_quat": model.cam_quat[camera_id].tolist(),
                "camera_fovy": float(model.cam_fovy[camera_id]),
                **{key: getattr(model, key).tolist() for key in ("light_ambient", "light_diffuse", "light_specular")},
            }

        initial = physics()
        before = render_settings()
        for key in ("light_ambient", "light_diffuse", "light_specular"):
            getattr(model, key)[:] *= condition["light_scale"]
        model.cam_pos[camera_id] += np.asarray(condition["camera_offset_m"])
        sim.forward()
        after = render_settings()
        unchanged = initial == physics()
        if not unchanged:
            raise ValueError("Rendering perturbation changed physical state")
        # Refresh both cameras after changing native scene settings and BEFORE
        # the first policy call. Every later env.step returns new observations.
        observation = raw._format_raw_obs(raw._env.env._get_observations(force_update=True))
        policy.reset()
        for name in ("main", "wrist"):
            writer = imageio_ffmpeg.write_frames(
                str(output/f"{name}.mp4"), (256, 256), fps=20,
                codec="libx264", pix_fmt_out="yuv420p", quality=8, ffmpeg_log_level="error",
            )
            writer.send(None)
            writers[name] = writer
        frames, calls = [], []
        clock = time.monotonic()
        outcome = "step_limit"

        def observe(obs, step):
            batch_obs = concatenate(raw.observation_space, [obs], create_empty_array(raw.observation_space, n=1))
            batch = preprocess_observation(batch_obs)
            batch["task"] = [raw.task_description]
            batch = env_pre(batch)
            image_hashes = {}
            for name, key in (("main", "image"), ("wrist", "image2")):
                pixels = obs["pixels"][key][::-1, ::-1].copy()
                writers[name].send(pixels)
                image_hashes[name] = hashlib.sha256(pixels.tobytes()).hexdigest()
                if step == 0:
                    Image.fromarray(pixels).save(output/f"{name}-poster.png")
            return batch, {
                "frame": step, "episode_time": step/20, "sim_time": float(sim.data.time),
                "state": batch["observation.state"][0].tolist(),
                "joint_position": obs["robot_state"]["joints"]["pos"].tolist(),
                "raw_camera_sha256": image_hashes,
            }

        for step in range(document["max_steps"]):
            batch, row = observe(observation, step)
            inference = step % document["action_steps"] == 0
            noise = torch.randn((1, cfg.chunk_size, cfg.max_action_dim), generator=generator) if inference else None
            policy_noise = noise.to(cfg.device) if noise is not None else None
            if cfg.device == "cuda":
                torch.cuda.synchronize()
            begin = time.monotonic()
            with torch.inference_mode():
                normalized = policy.select_action(pre(batch), noise=policy_noise)
                proposed = env_post({"action": post(normalized)})["action"].cpu().numpy()[0]
            if cfg.device == "cuda":
                torch.cuda.synchronize()
            policy_end = time.monotonic()
            if not np.isfinite(proposed).all():
                raise ValueError("Policy produced non-finite actions")
            applied = np.clip(proposed, -1, 1)
            env_begin = time.monotonic()
            observation, reward, terminated, truncated, info = raw.step(applied)
            env_end = time.monotonic()
            success = bool(info["is_success"])
            row.update(
                action=applied.tolist(), proposed_action=proposed.tolist(),
                inference_frame=step-step % document["action_steps"],
                next_success=success, reward=float(reward), terminal=False,
                env_step_seconds=env_end-env_begin,
            )
            frames.append(row)
            if inference:
                call = {
                    "frame": step, "policy_seconds": policy_end-begin, "env_step_seconds": env_end-env_begin,
                    "wall_seconds": policy_end-begin+env_end-env_begin,
                    "started_seconds": begin-clock, "finished_seconds": env_end-clock,
                    "noise_sha256": hashlib.sha256(noise.numpy().tobytes()).hexdigest(),
                }
                calls.append(call)
                print(f"{trial_id(seed, condition['id'])} sample {step:03d}: policy {call['policy_seconds']:.2f}s, sim {call['env_step_seconds']:.3f}s, success={success}", flush=True)
            if success or terminated or truncated:
                outcome = "success" if success else "terminated"
                break
        _, terminal = observe(observation, len(frames))
        terminal.update(action=None, proposed_action=None, inference_frame=None, next_success=None, reward=None, terminal=True)
        frames.append(terminal)
        result = {
            "outcome": outcome, "actions": len(frames)-1, "simulation_seconds": (len(frames)-1)/20,
            "start_sim_time": initial["time"], "max_steps": document["max_steps"],
            "wall_seconds": time.monotonic()-clock,
        }
        trace = {
            "schema": "robot-reel-vla-1", "fps": 20, "task": raw.task_description,
            "suite": "libero_spatial", "task_id": 0, "seed": seed, "initial_state_id": seed,
            "source": source, "channels": ["delta_x", "delta_y", "delta_z", "delta_rx", "delta_ry", "delta_rz", "gripper"],
            "action_units": "normalized controls in [-1, 1]; not joint angles or physical distances",
            "state_units": ["m", "m", "m", "rad", "rad", "rad", "m", "m"],
            "frames": frames, "inference_calls": calls, "result": result,
            "stress": {
                "trial_id": trial_id(seed, condition["id"]), "condition": condition["id"],
                "plan_sha256": canonical_hash(document), "nq": len(initial["qpos"]), "nv": len(initial["qvel"]),
                "initial_physics": initial, "initial_physics_sha256": canonical_hash(initial),
                "render_before": before, "render_after": after, "physics_unchanged_by_condition": unchanged,
                "task_bddl_sha256": file_hash(raw._task_bddl_file),
                "camera_name": "agentview", "noise_seed": seed,
            },
        }
        validate_run(trace, document)
    finally:
        for writer in writers.values():
            writer.close()
        raw.close()
    write_json(output/"trace.json", trace)
    write_json(output/"run-manifest.json", {
        "schema": SCHEMA, "files": {name: file_hash(output/name) for name in ("trace.json", *MEDIA)},
    })
    verify_run(output, document)
    print(f"COMPLETED {trial_id(seed, condition['id'])}: {result}", flush=True)
    return trace


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cache", type=Path, default=ROOT/"artifacts/vla-cache")
    parser.add_argument("--seeds", type=int, default=10)
    parser.add_argument("--max-steps", type=int, default=160)
    parser.add_argument("--action-steps", type=int, default=10)
    parser.add_argument("--threads", type=int, default=2)
    parser.add_argument("--device", choices=("cpu", "cuda"), default="cpu")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--stop-after", type=int, help="Seal this many pending trials, then exit for bounded job runners")
    args = parser.parse_args()
    if args.stop_after is not None and args.stop_after < 1:
        parser.error("--stop-after must be positive")
    document = plan(args.seeds, args.max_steps, args.action_steps, args.threads, args.device)
    validate_plan(document)
    if args.output.exists() and any(args.output.iterdir()):
        if not args.resume or json.loads((args.output/"experiment.json").read_text()) != document:
            parser.error("Choose an empty output directory, or resume its unchanged experiment plan")
    args.output.mkdir(parents=True, exist_ok=True)
    write_json(args.output/"experiment.json", document)
    ledger_file = args.output/"attempts.json"
    attempts = json.loads(ledger_file.read_text()) if ledger_file.exists() else []
    # Preserve an interrupted attempt before starting a new one.
    for attempt in attempts:
        if attempt["status"] == "running":
            attempt.update(status="error", error="Collector interrupted before producing a sealed trace",
                           interruption_detected_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    write_json(ledger_file, attempts)
    runtime = None
    recorded = 0
    for seed in document["seeds"]:
        for condition in CONDITIONS:
            key = trial_id(seed, condition["id"])
            previous = [a for a in attempts if a["trial_id"] == key]
            complete = [a for a in previous if a["status"] == "completed"]
            if complete:
                verify_run(args.output/complete[-1]["directory"], document)
                print("RESUMED", key, flush=True)
                continue
            if runtime is None:
                runtime = load_runtime(args)
            relative = f"runs/{key}/attempt-{len(previous)+1:03d}"
            attempt = {
                "trial_id": key, "attempt": len(previous)+1, "directory": relative,
                "status": "running", "started_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            }
            attempts.append(attempt)
            write_json(ledger_file, attempts)
            try:
                trace = collect(runtime, document, seed, condition, args.output/relative)
                attempt.update(status="completed", outcome=trace["result"]["outcome"])
            except Exception as exc:
                attempt.update(status="error", error=f"{type(exc).__name__}: {exc}")
                traceback.print_exc()
                raise
            finally:
                attempt["finished_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                write_json(ledger_file, attempts)
            recorded += 1
            if args.stop_after is not None and recorded >= args.stop_after:
                print("Requested number of pending trials sealed; resume the unchanged plan to continue.", flush=True)
                return
    print("All planned paired trials are sealed.", flush=True)


if __name__ == "__main__":
    main()
