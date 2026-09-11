"""Recorded inference of Pollen's official Microduck walking policy.

Observation/action conventions follow microduck_rl/scripts/infer_policy.py
(Apache-2.0). Uses the documented XML position-actuator fallback, not BAM.
"""
import hashlib
import json
import os
import shutil
import tempfile
import urllib.request
import zipfile
from pathlib import Path

import imageio_ffmpeg
import mujoco
import numpy as np

from .capture import FPS, HEIGHT, WIDTH

MODEL_COMMIT = "53b8971b61baf5b7f3c16d135dd7cac37623de4b"
POLICY_REVISION = "088524a64e2557dc453256b6071dbb9d23888802"
POLICY_SHA256 = "e36332d383997d51401897734cd3e79cf5038406feddb18b4d57ecfb141daa6c"
DEFAULT_POSE = np.array([0, -.0873, -.4579, -.0049, .453, .3491, .3491, 0, 0,
                         0, .0873, .4579, .0049, -.453], dtype=np.float32)


def ensure_assets():
    cache = Path(os.environ.get("ROBOT_REEL_CACHE", Path.home()/".cache/robot-reel"))
    cache.mkdir(parents=True, exist_ok=True)
    model_dir = cache/f"microduck-{MODEL_COMMIT}"
    if not (model_dir/"scene.xml").exists():
        print("Downloading pinned Microduck model assets (upstream BY-SA-NC terms)...", flush=True)
        with tempfile.TemporaryDirectory(dir=cache) as temporary:
            temp = Path(temporary)
            request = urllib.request.Request(
                f"https://codeload.github.com/pollen-robotics/microduck_rl/zip/{MODEL_COMMIT}",
                headers={"User-Agent": "robot-reel/0.2"})
            with urllib.request.urlopen(request, timeout=120) as response, (temp/"model.zip").open("wb") as out:
                shutil.copyfileobj(response, out)
            prefix = f"microduck_rl-{MODEL_COMMIT}/src/mjlab_microduck/robot/microduck/"
            extracted = temp/"model"
            extracted.mkdir()
            with zipfile.ZipFile(temp/"model.zip") as archive:
                for entry in archive.infolist():
                    if entry.is_dir() or not entry.filename.startswith(prefix):
                        continue
                    relative = Path(entry.filename[len(prefix):])
                    if relative.is_absolute() or ".." in relative.parts:
                        raise ValueError("Unexpected archive path")
                    target = extracted/relative
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(archive.read(entry))
            if not (extracted/"scene.xml").exists():
                raise ValueError("Pinned model archive is missing scene.xml")
            shutil.copytree(extracted, model_dir, dirs_exist_ok=True)
    policy = cache/f"microduck-walk-{POLICY_REVISION}.onnx"
    if not policy.exists():
        print("Downloading the pinned official walking policy...", flush=True)
        request = urllib.request.Request(
            f"https://huggingface.co/pollen-robotics/microduck-policies/resolve/{POLICY_REVISION}/alpha_walking.onnx",
            headers={"User-Agent": "robot-reel/0.2"})
        with urllib.request.urlopen(request, timeout=120) as response:
            payload = response.read()
        if hashlib.sha256(payload).hexdigest() != POLICY_SHA256:
            raise ValueError("Downloaded policy checksum does not match the pinned release")
        policy.write_bytes(payload)
    if hashlib.sha256(policy.read_bytes()).hexdigest() != POLICY_SHA256:
        raise ValueError("Cached policy has changed; remove it and retry")
    return model_dir, policy


def validate_speed(speed):
    if type(speed) not in (int, float) or not np.isfinite(speed) or not 0 <= speed <= .6:
        raise ValueError("Microduck speed must be a finite number between 0 and 0.6 m/s")
    return float(speed)


def record_microduck(output, speed=.5):
    speed = validate_speed(speed)
    try:
        import onnxruntime as ort
    except ImportError as exc:
        raise RuntimeError("Microduck requires: pip install -e '.[microduck]'") from exc
    model_dir, policy_path = ensure_assets()
    model = mujoco.MjModel.from_xml_path(str(model_dir/"scene.xml"))
    model.opt.timestep = .005
    model.vis.global_.offwidth, model.vis.global_.offheight = WIDTH, HEIGHT
    data = mujoco.MjData(model)
    ids = model.actuator_trnid[:, 0]
    qindices, vindices = model.jnt_qposadr[ids], model.jnt_dofadr[ids]
    names = [model.joint(i).name for i in ids]
    if model.nu != 14 or names != [
        "left_hip_yaw", "left_hip_roll", "left_hip_pitch", "left_knee", "left_ankle",
        "neck_pitch", "head_pitch", "head_yaw", "head_roll", "right_hip_yaw",
        "right_hip_roll", "right_hip_pitch", "right_knee", "right_ankle",
    ]:
        raise ValueError("Microduck actuator order does not match the official policy")
    data.qpos[:7] = [0, 0, .125, 1, 0, 0, 0]
    data.qpos[qindices], data.ctrl[:] = DEFAULT_POSE, DEFAULT_POSE
    mujoco.mj_forward(model, data)
    options = ort.SessionOptions()
    options.intra_op_num_threads = options.inter_op_num_threads = 1
    policy = ort.InferenceSession(str(policy_path), sess_options=options, providers=["CPUExecutionProvider"])
    if policy.get_inputs()[0].shape != [1, 61] or policy.get_outputs()[0].shape != [1, 14]:
        raise ValueError("Unsupported policy observation/action shape")
    gyro = int(model.sensor("imu_ang_vel").adr[0])
    trunk = model.body("trunk_base").id
    renderer = mujoco.Renderer(model, height=HEIGHT, width=WIDTH)
    camera = mujoco.MjvCamera()
    camera.distance, camera.elevation, camera.azimuth = .8, -16, 135
    writer = imageio_ffmpeg.write_frames(str(output/"microduck-raw.mp4"), (WIDTH, HEIGHT),
        fps=FPS, codec="libx264", pix_fmt_out="yuv420p", quality=8,
        macro_block_size=2, ffmpeg_log_level="error")
    writer.send(None)
    frames, policy_steps = [], []
    previous = np.zeros(14, dtype=np.float32)
    command = np.zeros(13, dtype=np.float32)
    label, minimum_height = "", float("inf")
    try:
        for step in range(2000):  # 10 simulated seconds; 200 Hz physics / 50 Hz policy.
            if step % 4 == 0:
                t = step*.005
                command[0] = speed if 1 <= t < 8 else 0
                label = "Find the balance." if t < 1 else ("A tiny duck. A real policy." if t < 8 else "Come to a stop.")
                gravity = data.xmat[trunk].reshape(3, 3).T @ np.array([0, 0, -1])
                observation = np.concatenate([
                    data.sensordata[gyro:gyro+3], gravity,
                    data.qpos[qindices]-DEFAULT_POSE, data.qvel[vindices], previous, command,
                ]).astype(np.float32)[None]
                action = policy.run(None, {policy.get_inputs()[0].name: observation})[0][0]
                if action.shape != (14,) or not np.isfinite(action).all():
                    raise RuntimeError("Policy returned an invalid action")
                previous = action.astype(np.float32)
                data.ctrl[:] = DEFAULT_POSE+previous
                policy_steps.append({"step": len(policy_steps), "sim_time": float(data.time),
                                     "command": command.tolist(), "action": previous.tolist(),
                                     "target": data.ctrl.tolist()})
            mujoco.mj_step(model, data)
            if not np.isfinite(data.qpos).all():
                raise RuntimeError("Non-finite simulation state")
            minimum_height = min(minimum_height, float(data.qpos[2]))
            if step+1 == round((len(frames)+1)/FPS/model.opt.timestep):
                frames.append({
                    "frame": len(frames), "sim_time": float(data.time), "label": label,
                    "source": "policy", "mode": "physics", "qpos": data.qpos[qindices].tolist(),
                    "target": data.ctrl.tolist(), "policy_step": len(policy_steps)-1,
                    "base_position_m": data.qpos[:3].tolist(),
                    "commanded_forward_speed_mps": float(command[0]),
                    "measured_forward_speed_mps": float((data.xmat[trunk].reshape(3, 3).T @ data.qvel[:3])[0]),
                })
                camera.lookat[:] = [float(data.qpos[0]), float(data.qpos[1]), .13]
                renderer.update_scene(data, camera=camera)
                writer.send(renderer.render())
    finally:
        writer.close()
        renderer.close()
    if len(frames) != 300:
        raise RuntimeError("Incomplete Microduck recording")
    outcome = {"minimum_base_height_m": minimum_height, "final_position_m": data.qpos[:3].tolist(),
               "base_below_7cm": minimum_height < .07}
    trace = {
        "robot": "microduck", "kind": "policy", "fps": FPS, "timestep": model.opt.timestep,
        "display_name": "MICRODUCK", "eyebrow": "OFFICIAL POLICY / LOCAL INFERENCE",
        "description": "50 Hz ONNX / MuJoCo physics",
        "disclaimer": "PD approximation / not real hardware",
        "joints": names, "units": ["rad"]*len(names),
        "display_joints": ["left_hip_pitch", "left_knee", "right_hip_pitch"],
        "limits": model.jnt_range[ids].tolist(), "home": DEFAULT_POSE.tolist(),
        "frames": frames, "actions": [
            {"label": "Stand", "start_frame": 0, "end_frame": 29, "source": "policy"},
            {"label": "Walk", "start_frame": 30, "end_frame": 239, "source": "policy"},
            {"label": "Stop", "start_frame": 240, "end_frame": 299, "source": "policy"},
        ], "policy_steps": policy_steps, "outcome": outcome,
        "policy": {"repo": "pollen-robotics/microduck-policies", "revision": POLICY_REVISION,
                   "file": "alpha_walking.onnx", "sha256": POLICY_SHA256,
                   "model_commit": MODEL_COMMIT, "control_hz": 50, "runtime": ort.__version__,
                   "actuators": "XML position-actuator fallback, not the official BAM motor model"},
        "requested_speed_mps": speed,
        "asset_license": "Upstream identifies 3D models as Creative Commons BY-SA-NC; see Microduck media notice.",
    }
    (output/"microduck-trace.json").write_text(json.dumps(trace, indent=2))
    (output/"MICRODUCK-MEDIA-NOTICE.txt").write_text(
        "Robot model: Pollen Robotics / Microduck RL.\n"
        f"Source: https://github.com/pollen-robotics/microduck_rl/tree/{MODEL_COMMIT}\n"
        "The source README identifies the 3D models as Creative Commons BY-SA-NC, without specifying a version.\n"
        "Microduck footage depicts those models; keep this attribution and the upstream noncommercial/share-alike terms with this footage.\n"
        "The Robot Reel recorder code is Apache-2.0; it does not relicense the downloaded robot assets.\n")
    print("Microduck outcome:", json.dumps(outcome), flush=True)
    return ["microduck"]
