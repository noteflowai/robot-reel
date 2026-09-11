"""Capture actual MuJoCo states. No synthetic video or hidden hardware mode."""
from __future__ import annotations

import gc
import hashlib
import json
import math
import queue
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path

import imageio_ffmpeg
import mujoco
import numpy as np
from strands_robots import Robot

FPS = 30
WIDTH, HEIGHT = 960, 900


def validate_targets(targets, names, limits):
    if not targets:
        raise ValueError("At least one joint target is required")
    for name, value in targets.items():
        if name not in names:
            raise ValueError(f"Unknown joint: {name}")
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError(f"Non-finite or non-numeric target for {name}")
        lo, hi = limits[names.index(name)]
        if not lo <= value <= hi:
            raise ValueError(f"{name} must be in [{lo}, {hi}] radians")


class Capture:
    def __init__(self, output: Path, name: str):
        self.name, self.output = name, output
        self.robot = Robot(name, mode="sim", backend="mujoco")
        # This adapter intentionally pins strands-robots: the backend access is private.
        self.model, self.data = self.robot._world._model, self.robot._world._data
        m = self.model
        self.ids = [int(m.actuator_trnid[i, 0]) for i in range(m.nu)]
        self.names = [m.joint(i).name.split("/")[-1] for i in self.ids]
        self.addresses = [int(m.jnt_qposadr[i]) for i in self.ids]
        self.limits = m.jnt_range[self.ids].copy()
        if m.nkey:
            mujoco.mj_resetDataKeyframe(m, self.data, 0)
        self.home = self.data.qpos[self.addresses].copy()
        self.data.ctrl[:] = self.home
        mujoco.mj_forward(m, self.data)
        m.vis.global_.offwidth, m.vis.global_.offheight = WIDTH, HEIGHT
        m.vis.headlight.ambient[:] = [0.35, 0.35, 0.4]
        for i in range(m.ngeom):
            if m.geom_type[i] == mujoco.mjtGeom.mjGEOM_PLANE:
                m.geom_rgba[i] = [0.075, 0.095, 0.13, 1]
        self.renderer = mujoco.Renderer(m, height=HEIGHT, width=WIDTH)
        self.camera = mujoco.MjvCamera()
        self.camera.lookat[:] = [0, 0, 0.19 if name == "so100" else 0.75]
        self.camera.distance = 0.82 if name == "so100" else 2.65
        self.camera.elevation = -20 if name == "so100" else -12
        self.writer = imageio_ffmpeg.write_frames(
            str(output / f"{name}-raw.mp4"), (WIDTH, HEIGHT), fps=FPS,
            codec="libx264", pix_fmt_out="yuv420p", quality=8,
            macro_block_size=2, ffmpeg_log_level="error",
        )
        self.writer.send(None)
        self.frames, self.actions = [], []
        self.closed = False

    def state(self):
        return dict(zip(self.names, self.data.qpos[self.addresses].tolist()))

    def frame(self, label, source, mode, target):
        i = len(self.frames)
        self.camera.azimuth = (135 if self.name == "so100" else 145) + 12 * math.sin(i / 160)
        self.renderer.update_scene(self.data, camera=self.camera)
        pixels = self.renderer.render()
        self.writer.send(pixels)
        self.frames.append({
            "frame": i, "sim_time": float(self.data.time), "label": label,
            "source": source, "mode": mode,
            "qpos": self.data.qpos[self.addresses].tolist(),
            "target": np.asarray(target).tolist(),
        })

    def move(self, targets: dict[str, float], label: str, source: str, seconds=4.0):
        validate_targets(targets, self.names, self.limits)
        if len(self.actions) >= 6:
            raise ValueError("Maximum six motions per recording")
        label = label[:64]
        target = self.data.ctrl.copy()
        for name, value in targets.items():
            target[self.names.index(name)] = value
        start = self.data.ctrl.copy()
        start_frame = len(self.frames)
        for i in range(round(seconds * FPS)):
            # Minimum-jerk target, followed by position actuators and mj_step.
            t = min(1., (i + 1) / (seconds * FPS * 0.7))
            blend = 10*t**3 - 15*t**4 + 6*t**5
            self.data.ctrl[:] = start + (target - start) * blend
            steps = round((i + 1) / FPS / self.model.opt.timestep) - round(i / FPS / self.model.opt.timestep)
            for _ in range(steps):
                mujoco.mj_step(self.model, self.data)
            if not np.isfinite(self.data.qpos).all():
                raise RuntimeError("Non-finite simulation state")
            self.frame(label, source, "physics", target)
        error = float(np.max(np.abs(self.data.qpos[self.addresses] - target)))
        result = {"label": label, "source": source, "start_frame": start_frame,
                  "end_frame": len(self.frames)-1, "target": dict(zip(self.names, target.tolist())),
                  "measured": self.state(), "max_error_rad": error}
        self.actions.append(result)
        self.flush()
        return {"measured_joints": self.state(), "max_error_rad": error, "recorded_frames": len(self.frames)}

    def showcase(self):
        """G1 joint-space pose animation, NOT a walking or balancing policy."""
        baseline = self.data.qpos.copy()
        for i in range(10 * FPS):
            t = i / FPS
            envelope = math.sin(math.pi * t / 10)**2
            self.data.qpos[:] = baseline
            poses = {
                "right_shoulder_pitch_joint": -1.05*envelope,
                "right_shoulder_roll_joint": -0.42*envelope,
                "right_elbow_joint": 1.1*envelope,
                "right_wrist_roll_joint": 0.55*math.sin(t*4)*envelope,
                "waist_yaw_joint": 0.18*math.sin(t*0.6)*envelope,
            }
            validate_targets(poses, self.names, self.limits)
            for name, value in poses.items():
                self.data.qpos[self.addresses[self.names.index(name)]] = value
            mujoco.mj_forward(self.model, self.data)
            self.frame("Hello, physical world.", "scripted", "kinematic", self.data.qpos[self.addresses])
        self.flush()

    def flush(self):
        document = {
            "robot": self.name, "fps": FPS, "joints": self.names,
            "limits": self.limits.tolist(), "home": self.home.tolist(),
            "model_dimensions": {"nq": self.model.nq, "nu": self.model.nu},
            "timestep": float(self.model.opt.timestep),
            "actions": self.actions, "frames": self.frames,
        }
        (self.output / f"{self.name}-trace.json").write_text(json.dumps(document, indent=2))

    def close(self):
        if self.closed:
            return
        self.closed = True
        self.flush()
        self.writer.close()
        self.renderer.close()
        self.robot.cleanup()
        del self.robot
        gc.collect()


def run_arm(output, agent=False, model_id=None, region="us-west-2", shot_plan=None):
    from .plans import DEFAULT_PLAN, validate_plan
    plan = validate_plan(shot_plan if shot_plan is not None else DEFAULT_PLAN)
    capture = Capture(output, "so100")
    try:
        if agent:
            from strands import Agent, tool
            from strands.models import BedrockModel

            jobs = queue.Queue()

            def on_render_thread(fn, *args):
                result = Future()
                jobs.put((fn, args, result))
                return result.result(timeout=120)

            @tool
            def inspect_arm() -> dict:
                """Read measured arm joints, legal radians, and asset-defined home pose."""
                return {"joints": capture.state(),
                        "limits": dict(zip(capture.names, capture.limits.tolist())),
                        "home": dict(zip(capture.names, capture.home.tolist()))}

            @tool
            def move_joints(targets: dict[str, float], label: str) -> dict:
                """Move named arm joints in radians over four simulated seconds and record the result.

                Args:
                    targets: Joint names and absolute target angles in radians.
                    label: Short descriptive English caption for the move.
                """
                return on_render_thread(capture.move, targets, label, "agent")

            prompt = (
                "Direct a four-shot SO-100 simulation film. First inspect the arm. "
                "Then use exactly four move_joints calls: rotate base to -0.8 radians; "
                "rotate base to +0.8 radians; turn Wrist_Roll to +0.6 radians and open Jaw to 0.5; "
                "finally restore EVERY joint to the asset-defined home returned by inspect_arm. "
                "Keep other joints at home for the first two moves. Use short cinematic English labels. "
                "Read measured errors in tool results and honestly summarize them. "
                "Do not call a zero pose home. These are simulation position actuators, not real hardware."
            )
            (output / "prompt.txt").write_text(prompt)
            director = Agent(model=BedrockModel(model_id=model_id, region_name=region),
                             tools=[inspect_arm, move_joints])
            # EGL contexts belong to their creating thread. Strands tool calls run
            # on workers, so marshal all simulation/render mutations to this thread.
            with ThreadPoolExecutor(max_workers=1) as executor:
                pending = executor.submit(director, prompt)
                while not pending.done():
                    try:
                        fn, args, reply = jobs.get(timeout=0.1)
                    except queue.Empty:
                        continue
                    try:
                        reply.set_result(fn(*args))
                    except Exception as exc:
                        reply.set_exception(exc)
                result = pending.result()
            (output / "agent-response.txt").write_text(str(result))
            if len(capture.actions) != 4:
                raise RuntimeError(f"Expected 4 recorded agent motions, got {len(capture.actions)}")
        else:
            home = dict(zip(capture.names, capture.home.tolist()))
            # Validate the entire plan against the loaded model before any motion.
            resolved = [(home if shot.get("home") else shot["targets"], shot["label"])
                        for shot in plan["shots"]]
            for targets, _ in resolved:
                validate_targets(targets, capture.names, capture.limits)
            (output / "shot-plan.json").write_text(json.dumps(plan, indent=2))
            for targets, label in resolved:
                capture.move(targets, label, "scripted")
    finally:
        capture.close()


def manifest(output, mode, model_id, region, scene_names=None, pack=None):
    from importlib.metadata import version
    files = sorted(p for p in output.iterdir() if p.is_file() and p.name != "manifest.json")
    document = {
        "schema": 1, "arm_director": mode, "model_id": model_id, "region": region if model_id else None,
        "simulation_only": True, "g1_mode": "scripted kinematic pose showcase; no locomotion or balance",
        "editing": "Inference pauses omitted. Simulation frames retained in order." if mode == "agent" else "Simulation frames sampled at 30 fps and retained in order.",
        "versions": {n: version(n) for n in ["strands-robots", "mujoco", "strands-agents"]},
        "sha256": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in files},
    }
    if scene_names:
        document.update(schema=2, scenes=scene_names, pack=pack)
        if "unitree_g1" not in scene_names:
            document.pop("g1_mode", None)
    (output / "manifest.json").write_text(json.dumps(document, indent=2))
