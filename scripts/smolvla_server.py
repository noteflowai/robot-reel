"""Local-only SmolVLA inference bridge for an isolated official LIBERO-Plus runtime.

Keep the reviewed simulator and LeRobot dependency stacks in separate processes.
Only fixed-size RGB observations and robot state cross this HTTP boundary.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--port", type=int, default=47866)
    args = parser.parse_args()
    os.environ["HF_HOME"] = str(args.cache.resolve() / "huggingface")
    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
    from importlib.metadata import version

    import numpy as np
    import torch
    from huggingface_hub import snapshot_download
    from lerobot.policies.factory import make_pre_post_processors
    from lerobot.policies.smolvla.configuration_smolvla import SmolVLAConfig
    from lerobot.policies.smolvla.modeling_smolvla import SmolVLAPolicy
    from lerobot.processor.env_processor import LiberoProcessorStep
    from record_smolvla import POLICY, VLM, sha

    if not torch.cuda.is_available() or version("lerobot") != "0.6.1":
        raise ValueError("requires the reviewed LeRobot 0.6.1 CUDA environment")
    torch.set_num_threads(4)
    torch.backends.cuda.matmul.allow_tf32 = False
    torch.backends.cudnn.allow_tf32 = False
    model_dir = Path(snapshot_download(
        POLICY[0], revision=POLICY[1], local_files_only=True,
        allow_patterns=["*.json", "*.safetensors", "README.md"],
    ))
    vlm_dir = Path(snapshot_download(
        VLM[0], revision=VLM[1], local_files_only=True,
        allow_patterns=["*.json", "*.txt", "*.model"],
    ))
    cfg = SmolVLAConfig.from_pretrained(str(model_dir))
    cfg.device, cfg.n_action_steps = "cuda", 10
    cfg.load_vlm_weights, cfg.vlm_model_name = False, str(vlm_dir)
    policy = SmolVLAPolicy.from_pretrained(
        model_dir, config=cfg, local_files_only=True, strict=True
    ).float().cuda().eval()
    pre, post = make_pre_post_processors(
        cfg, pretrained_path=str(model_dir),
        preprocessor_overrides={
            "device_processor": {"device": "cuda"},
            "tokenizer_processor": {"tokenizer_name": str(vlm_dir)},
        },
        postprocessor_overrides={"device_processor": {"device": "cuda"}},
    )
    env_pre = LiberoProcessorStep()
    identity = {
        "policy": POLICY[0], "policy_revision": POLICY[1],
        "vlm": VLM[0], "vlm_revision": VLM[1],
        "checkpoint_sha256": sha(model_dir / "model.safetensors"),
        "gpu": torch.cuda.get_device_name(), "device": "cuda", "precision": "float32",
        "tf32": False, "threads": 4, "action_steps": 10,
        "versions": {name: version(name) for name in ("lerobot", "torch", "transformers")},
        "server_sha256": sha(__file__),
        "preprocessing": "LeRobot LiberoProcessorStep: 180-degree RGB rotation, axis-angle + gripper state",
    }
    state = {"step": 0, "language": None, "generator": None}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def reply(self, status, payload):
            data = json.dumps(payload, allow_nan=False).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            self.reply(200 if self.path == "/health" else 404, identity)

        def do_POST(self):
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 600_000:
                    raise ValueError("request exceeds the observation bound")
                body = json.loads(self.rfile.read(length))
                if self.path == "/reset":
                    seed, language = body["seed"], body["language"]
                    if type(seed) is not int or not isinstance(language, str) or len(language) > 2000:
                        raise ValueError("invalid reset")
                    policy.reset()
                    torch.manual_seed(seed)
                    state.update(
                        step=0, language=language,
                        generator=torch.Generator(device="cpu").manual_seed(seed),
                    )
                    self.reply(200, {"reset": True})
                    return
                if self.path != "/action" or state["language"] is None:
                    raise ValueError("reset before requesting actions")
                batch = {"task": [state["language"]]}
                for key, name in (("image", "primary"), ("image2", "wrist")):
                    pixels = base64.b64decode(body[name], validate=True)
                    if len(pixels) != 256 * 256 * 3:
                        raise ValueError("expected raw 256x256 RGB")
                    image = np.frombuffer(pixels, dtype=np.uint8).reshape(256, 256, 3).copy()
                    batch[f"observation.images.{key}"] = (
                        torch.from_numpy(image).permute(2, 0, 1).unsqueeze(0).float() / 255
                    )
                vectors = {}
                for name, size in (("eef_pos", 3), ("eef_quat", 4), ("gripper_qpos", 2)):
                    vector = np.asarray(body[name], dtype=np.float32)
                    if vector.shape != (size,) or not np.isfinite(vector).all():
                        raise ValueError("invalid robot observation")
                    vectors[name] = torch.from_numpy(vector).unsqueeze(0)
                batch["observation.robot_state"] = {
                    "eef": {"pos": vectors["eef_pos"], "quat": vectors["eef_quat"]},
                    "gripper": {"qpos": vectors["gripper_qpos"]},
                }
                batch = env_pre.observation(batch)
                inference = state["step"] % 10 == 0
                noise = torch.randn(
                    (1, cfg.chunk_size, cfg.max_action_dim), generator=state["generator"]
                ) if inference else None
                torch.cuda.synchronize()
                started = time.monotonic()
                with torch.inference_mode():
                    normalized = policy.select_action(
                        pre(batch), noise=noise.cuda() if inference else None
                    )
                    action = post(normalized).cpu().numpy()[0]
                torch.cuda.synchronize()
                if action.shape != (7,) or not np.isfinite(action).all():
                    raise ValueError("policy returned invalid actions")
                result = {
                    "step": state["step"], "action": np.clip(action, -1, 1).tolist(),
                    "proposed_action": action.tolist(), "inference": inference,
                    "seconds": time.monotonic() - started,
                    "state": batch["observation.state"][0].tolist(),
                    "noise_sha256": (
                        hashlib.sha256(noise.numpy().tobytes()).hexdigest() if inference else None
                    ),
                }
                state["step"] += 1
                self.reply(200, result)
            except (ValueError, KeyError, TypeError) as error:
                self.reply(400, {"error": str(error)})

    print(json.dumps({"ready": True, **identity}), flush=True)
    HTTPServer(("127.0.0.1", args.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
