"""Record Cosmos predictions against the same executed action chunk in LIBERO-Plus.

Run in the upstream Cosmos Policy Python environment. The public plan is created
by robot_reel.libero_plus on the host. Model weights have a noncommercial license;
this recorder is for the explicitly identified research experiment.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import random
import subprocess
import sys
import time
import traceback
from pathlib import Path

COSMOS_REVISION = "18a2accadf4e7a3531e56754102af5a24d2316da"
MODEL_REVISION = "cb689ec0e3347c13667d70a78a3447388f5c3bb8"


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path, payload):
    Path(path).write_text(json.dumps(payload, indent=2, allow_nan=False) + "\n")


def check_revision(path, revision):
    actual = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=path, text=True, timeout=10
    ).strip()
    if actual != revision:
        raise ValueError(f"expected reviewed source revision {revision}, got {actual}")
    if subprocess.run(["git", "diff", "--quiet", "HEAD", "--"], cwd=path, check=False).returncode:
        raise ValueError("tracked upstream source differs from its reviewed revision")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cosmos-repo", type=Path, required=True)
    parser.add_argument("--libero-repo", type=Path, required=True)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--condition", action="append")
    args = parser.parse_args()
    for name in ("cosmos_repo", "libero_repo", "checkpoint", "plan", "cache", "output"):
        setattr(args, name, getattr(args, name).resolve())
    plan = json.loads(args.plan.read_text())
    if plan.get("schema") != "robot-reel.libero-plus-plan.v1":
        raise ValueError("expected a reviewed LIBERO-Plus plan")
    check_revision(args.cosmos_repo, COSMOS_REVISION)
    check_revision(args.libero_repo, plan["source"]["revision"])
    model_manifest = json.loads(
        (Path(__file__).resolve().parents[1] / "requirements/cosmos-model.json").read_text()
    )
    if model_manifest["revision"] != MODEL_REVISION:
        raise ValueError("model manifest revision differs from the recorder")
    model_hashes = {}
    for name, identity in model_manifest["files"].items():
        path = args.checkpoint / name
        if path.stat().st_size != identity["bytes"] or sha(path) != identity["sha256"]:
            raise ValueError(f"checkpoint file differs from the pinned model: {name}")
        model_hashes[name] = identity["sha256"]
    libroot = args.libero_repo.resolve() / "libero/libero"
    for name, expected in plan["source"]["source_files"].items():
        if sha(args.libero_repo / name) != expected:
            raise ValueError(f"reviewed upstream source changed: {name}")
    state_path = libroot / plan["source"]["initial_state_file"]
    if sha(state_path) != plan["source"]["initial_state_sha256"]:
        raise ValueError("original initial state changed")
    for condition in plan["conditions"]:
        if sha(libroot / condition["bddl_file"]) != condition["bddl_sha256"]:
            raise ValueError("task definition changed after planning")
    if args.condition and any(
        name not in {row["name"] for row in plan["conditions"]} for name in args.condition
    ):
        raise ValueError("requested condition is absent from the plan")
    args.output.mkdir(parents=True, exist_ok=False)
    args.cache.mkdir(parents=True, exist_ok=True)
    # Keep an existing Hub login available when placing large model caches in a
    # separate directory. Never persist or print the credential in experiment files.
    from huggingface_hub import get_token
    cached_token = get_token()
    if cached_token:
        os.environ.setdefault("HF_TOKEN", cached_token)
    config_dir = args.cache / "libero"
    config_dir.mkdir(exist_ok=True)
    paths = {
        "benchmark_root": str(libroot), "bddl_files": str(libroot / "bddl_files"),
        "init_states": str(libroot / "init_files"), "assets": str(libroot / "assets"),
        "datasets": str(args.cache / "datasets"),
    }
    # JSON scalars are also valid YAML, without importing the upstream package
    # before its noninteractive configuration exists.
    (config_dir / "config.yaml").write_text(
        "\n".join(key + ": " + json.dumps(value) for key, value in paths.items()) + "\n"
    )
    os.environ["LIBERO_CONFIG_PATH"] = str(config_dir.resolve())
    os.environ.setdefault("MUJOCO_GL", "egl")
    os.environ.setdefault("HF_HOME", str((args.cache / "huggingface").resolve()))
    os.environ.setdefault("MPLCONFIGDIR", str((args.cache / "matplotlib").resolve()))
    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
    sys.path[:0] = [str(args.cosmos_repo.resolve()), str(args.libero_repo.resolve())]
    # The upstream config imports other configs using repository-relative paths.
    os.chdir(args.cosmos_repo)
    from importlib.metadata import version

    import imageio.v2 as imageio
    import numpy as np
    import torch
    from PIL import Image
    from libero.libero.envs import OffScreenRenderEnv
    from libero.libero.benchmark import grab_language_from_filename
    from cosmos_policy.experiments.robot.libero.run_libero_eval import (
        PolicyEvalConfig, prepare_observation,
    )
    from cosmos_policy.experiments.robot.cosmos_utils import (
        get_action, get_model, init_t5_text_embeddings_cache, load_dataset_stats,
        prepare_images_for_model, t5_text_embeddings_cache,
    )
    from skimage.metrics import structural_similarity

    if not torch.cuda.is_available():
        raise ValueError("this recording requires the declared CUDA device")
    torch.set_num_threads(4)
    torch.backends.cuda.matmul.allow_tf32 = False
    torch.backends.cudnn.allow_tf32 = False
    checkpoint = args.checkpoint.resolve()
    cfg = PolicyEvalConfig(
        config="cosmos_predict2_2b_480p_libero__inference_only",
        ckpt_path=str(checkpoint / "Cosmos-Policy-LIBERO-Predict2-2B.pt"),
        # Upstream converts this repository-relative filename to a module name.
        config_file="cosmos_policy/config/config.py",
        dataset_stats_path=str(checkpoint / "libero_dataset_statistics.json"),
        t5_text_embeddings_path=str(checkpoint / "libero_t5_embeddings.pkl"),
        seed=plan["seed"], available_gpus="0", use_wandb=False,
        chunk_size=16, num_open_loop_steps=16, flip_images=True,
        use_jpeg_compression=True, trained_with_image_aug=True,
        num_denoising_steps_action=5, deterministic=True,
    )
    source = {
        "kind": "closed-loop-policy-and-world-prediction",
        "model": "nvidia/Cosmos-Policy-LIBERO-Predict2-2B",
        "model_revision": MODEL_REVISION,
        "model_license": "NVIDIA One-Way Noncommercial License (NSCLv1)",
        "use_scope": "noncommercial research experiment",
        "cosmos_repository": "https://github.com/NVlabs/cosmos-policy",
        "cosmos_revision": COSMOS_REVISION,
        "model_files": model_hashes,
        "gpu": torch.cuda.get_device_name(), "precision": "bfloat16",
        "tf32": False, "threads": 4, "python": platform.python_version(),
        "versions": {
            name: version(name)
            for name in ("torch", "transformers", "libero", "mujoco", "robosuite", "numpy")
        },
        "recorder_sha256": sha(__file__), "plan_sha256": sha(args.plan),
    }
    write_json(args.output / "source.json", source)
    write_json(args.output / "plan.json", plan)
    stats = load_dataset_stats(cfg.dataset_stats_path)
    init_t5_text_embeddings_cache(cfg.t5_text_embeddings_path)
    language = grab_language_from_filename(plan["suite"], plan["base_task"] + ".bddl")
    if language not in t5_text_embeddings_cache:
        raise ValueError("the original benchmark instruction is absent from the pinned T5 cache")
    print("Loading the pinned Cosmos Policy checkpoint...", flush=True)
    model, _ = get_model(cfg)
    # Upstream's loader enables TF32 internally. Restore the declared experiment
    # setting after loading, before any measured policy inference.
    torch.backends.cuda.matmul.allow_tf32 = False
    torch.backends.cudnn.allow_tf32 = False
    # Only load the checked upstream initial-state file, never a caller-supplied pickle.
    initial_states = torch.load(state_path, map_location="cpu", weights_only=False)
    initial = np.asarray(initial_states[plan["initial_state_index"]])
    summaries = []
    for condition in plan["conditions"]:
        if args.condition and condition["name"] not in args.condition:
            continue
        destination = args.output / condition["name"]
        destination.mkdir()
        random.seed(plan["seed"])
        np.random.seed(plan["seed"])
        torch.manual_seed(plan["seed"])
        env = None
        writer = None
        frames, chunks = [], []
        status, error, success = "step_limit", None, False
        native_language = None
        started = time.monotonic()
        try:
            # Keep the virtual camera suffix: the official wrapper interprets it
            # and loads the physical BDDL named in the reviewed manifest.
            native_bddl = (
                libroot / "bddl_files" / plan["suite"] / (condition["task_name"] + ".bddl")
            )
            env = OffScreenRenderEnv(
                bddl_file_name=str(native_bddl), camera_heights=256, camera_widths=256
            )
            env.seed(0)  # Same placement convention as upstream Cosmos evaluation.
            env.reset()
            obs = env.set_init_state(initial)
            for _ in range(plan["settle_steps"]):
                obs, _, _, _ = env.step([0, 0, 0, 0, 0, 0, -1])
            # Use the original benchmark's canonical instruction, exactly as in
            # Cosmos evaluation. Preserve BDDL wording separately; camera/light
            # parameters are not language perturbations.
            native_language = env.language_instruction
            sim = env.env.sim
            native = {
                "camera_pos": np.asarray(sim.model.cam_pos).tolist(),
                "camera_quat": np.asarray(sim.model.cam_quat).tolist(),
                "camera_fovy": np.asarray(sim.model.cam_fovy).tolist(),
                "light_pos": np.asarray(sim.model.light_pos).tolist(),
                "light_diffuse": np.asarray(sim.model.light_diffuse).tolist(),
            }
            write_json(destination / "native-scene.json", native)
            writer = imageio.get_writer(
                str(destination / "rollout.mp4"), fps=20, codec="libx264",
                quality=7, macro_block_size=1,
            )
            controlled_steps = 0
            while controlled_steps < plan["max_steps"] and not success:
                current = prepare_observation(obs, 224, cfg.flip_images)
                before_time = float(sim.data.time)
                torch.cuda.synchronize()
                inference_started = time.monotonic()
                prediction = get_action(
                    cfg, model, stats, current, language, seed=plan["seed"],
                    randomize_seed=False, num_denoising_steps_action=5,
                    generate_future_state_and_value_in_parallel=True,
                )
                torch.cuda.synchronize()
                inference_seconds = time.monotonic() - inference_started
                actions = np.asarray(prediction["actions"], dtype=np.float32)
                if actions.shape != (16, 7) or not np.isfinite(actions).all():
                    raise ValueError("policy did not return a finite 16x7 action chunk")
                chunk_index = len(chunks)
                image_dir = destination / f"chunk-{chunk_index:03d}"
                image_dir.mkdir()
                processed_current = prepare_images_for_model(
                    [current["wrist_image"], current["primary_image"]], cfg
                )
                for camera, image in zip(("wrist", "primary"), processed_current):
                    Image.fromarray(image).save(image_dir / f"{camera}-current.png")
                for key, image in prediction["future_image_predictions"].items():
                    Image.fromarray(image).save(image_dir / f"{key}-predicted.png")
                executed = []
                for action in actions:
                    if controlled_steps >= plan["max_steps"] or success:
                        break
                    obs, reward, done, _ = env.step(action.tolist())
                    controlled_steps += 1
                    executed.append(action.tolist())
                    success = bool(done)
                    processed = prepare_observation(obs, 224, cfg.flip_images)
                    writer.append_data(np.concatenate(
                        [processed["primary_image"], processed["wrist_image"]], axis=1
                    ))
                    frames.append({
                        "step": controlled_steps, "time_s": float(sim.data.time),
                        "qpos": np.asarray(sim.data.qpos).tolist(),
                        "qvel": np.asarray(sim.data.qvel).tolist(),
                        "proprio": processed["proprio"].tolist(),
                        "action": action.tolist(), "reward": float(reward),
                        "task_success": success,
                    })
                observed = prepare_observation(obs, 224, cfg.flip_images)
                processed_observed = prepare_images_for_model(
                    [observed["wrist_image"], observed["primary_image"]], cfg
                )
                metrics = {}
                aligned = len(executed) == 16
                for camera, key, image in zip(
                    ("wrist", "primary"), ("future_wrist_image", "future_image"),
                    processed_observed,
                ):
                    Image.fromarray(image).save(image_dir / f"{camera}-observed.png")
                    predicted_image = prediction["future_image_predictions"][key]
                    if predicted_image.shape != image.shape:
                        raise ValueError("predicted and observed image shapes differ")
                    delta = np.abs(predicted_image.astype(float) - image.astype(float))
                    Image.fromarray(delta.astype(np.uint8)).save(
                        image_dir / f"{camera}-difference.png"
                    )
                    if aligned:
                        metrics[camera] = {
                            "rgb_mae_0_255": float(delta.mean()),
                            "ssim": float(structural_similarity(
                                predicted_image, image, channel_axis=2, data_range=255
                            )),
                        }
                chunk = {
                    "chunk": chunk_index, "start_step": controlled_steps - len(executed),
                    "target_step": controlled_steps - len(executed) + 16,
                    "observed_step": controlled_steps, "horizon_aligned": aligned,
                    "start_time_s": before_time, "observed_time_s": float(sim.data.time),
                    "predicted_actions": actions.tolist(), "executed_actions": executed,
                    "value_estimate": float(prediction["value_prediction"]),
                    "observed_proprio": observed["proprio"].tolist(),
                    "inference_seconds": inference_seconds,
                    "metrics": metrics,
                    "images": {
                        path.name: {"sha256": sha(path), "bytes": path.stat().st_size}
                        for path in sorted(image_dir.glob("*.png"))
                    },
                }
                chunks.append(chunk)
                write_json(destination / "progress.json", {
                    "condition": condition, "language": language,
                    "bddl_language": native_language, "frames": frames,
                    "chunks": chunks, "source": source,
                })
                print(condition["name"], "step", controlled_steps, "success", success, flush=True)
                del prediction
            status = "success" if success else "step_limit"
        except Exception as problem:
            status = "runtime_error"
            error = f"{type(problem).__name__}: {problem}"
            (destination / "error.txt").write_text(traceback.format_exc())
        finally:
            if writer:
                writer.close()
            if env:
                env.close()
        record = {
            "schema": "robot-reel.cosmos-plus-run.v1", "source": source,
            "condition": condition, "plan_sha256": sha(args.plan),
            "language": language, "bddl_language": native_language,
            "status": status, "error": error, "task_success": success,
            "elapsed_seconds": time.monotonic() - started, "frames": frames, "chunks": chunks,
            "interpretation": (
                "Predictions target t+16; metrics exist only after all 16 predicted actions "
                "were executed. Both observations use the policy's fixed image preparation. "
                "RGB error and SSIM measure appearance, not task success. Value is the model's "
                "estimate, not a calibrated probability. This preselected subset is not "
                "a full LIBERO-Plus benchmark or a production deployment claim."
            ),
        }
        write_json(destination / "run.json", record)
        summaries.append({
            "condition": condition["name"], "status": status, "error": error,
            "task_success": success, "steps": len(frames), "chunks": len(chunks),
            "aligned_chunks": sum(row["horizon_aligned"] for row in chunks),
        })
        write_json(args.output / "summary.json", {"runs": summaries})
    if any(row["status"] == "runtime_error" for row in summaries):
        raise SystemExit(2)


if __name__ == "__main__":
    main()
