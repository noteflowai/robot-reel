"""Record fresh Microduck physics on a reviewed captured-scene heightfield.

Uses the official ONNX observation/action convention and XML PD fallback.
Run with MUJOCO_GL=egl. Both terrain cases must be declared before inference.
"""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import math
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import time
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from robot_reel.microduck import DEFAULT_POSE, MODEL_COMMIT, POLICY_REVISION, POLICY_SHA256
from robot_reel.scene_motion import (
    JOINTS, PLAN_SCHEMA, SCHEMA, camera_axes, checked_file, checked_heightfield, height_at,
    identity, validate_trace, write_json,
)


def prepare_model(model_source, source_check, height_path, output, plan, case):
    import mujoco
    import numpy as np

    source = json.loads(source_check.read_text())
    if source.get("commit") != MODEL_COMMIT:
        raise ValueError("the model source check names another revision")
    copied = output / "model"
    copied.mkdir()
    for name, expected in source["files"].items():
        path = checked_file(model_source, name, expected)
        dest = copied / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, dest)
    terrain = checked_heightfield(height_path)
    n = terrain["resolution"]
    low, high = np.asarray(terrain["bounds"])
    span, center = high - low, (high + low) / 2
    heights = np.asarray(terrain["heights_m"])
    bottom, vertical_span = float(heights.min()), float(heights.max() - heights.min())
    # MuJoCo splits cells along their positive diagonal. The existing Blender
    # proxy uses the opposite diagonal. Rotate the local grid +90 degrees and
    # reindex its samples so both representations contain the same world triangles.
    normalized = np.rot90(((heights - bottom) / vertical_span).reshape(n, n)).astype("<f4")
    (copied / "assets/captured.hfield").write_bytes(struct.pack("<ii", n, n) + normalized.tobytes())
    root = ET.parse(copied / "scene.xml").getroot()
    world = root.find("worldbody")
    world.remove(world.find("geom[@name='floor']"))
    ET.SubElement(root.find("asset"), "hfield", name="CapturedHeightfield",
                  file="captured.hfield", size=f"{span[1]/2} {span[0]/2} {vertical_span} 0.1")
    ET.SubElement(world, "geom", name="CapturedTerrain", type="hfield",
                  hfield="CapturedHeightfield", pos=f"{center[0]} {center[1]} {bottom}",
                  quat=f"{math.sqrt(.5)} 0 0 {math.sqrt(.5)}",
                  rgba="0.22 0.43 0.38 1", friction="1 0.005 0.0001")
    # A declared 24 cm square bounds the initial stance footprint. Sample its
    # corners/edge centres/centre before inference; keep the same rule in both cases.
    surface = max(height_at(terrain, float(center[0]) + dx, float(center[1]) + dy)
                  for dx in (-.12, 0, .12) for dy in (-.12, 0, .12))
    spawn = [float(center[0]), float(center[1]),
             surface + plan["base_clearance_m"]]
    position = [spawn[i] + plan["camera"]["offset_m"][i] for i in range(3)]
    target = [spawn[i] + plan["camera"]["target_offset_m"][i] for i in range(3)]
    axes = camera_axes(position, target)
    ET.SubElement(world, "camera", name="RecordedCamera", mode="fixed",
                  pos=" ".join(map(str, position)),
                  xyaxes=" ".join(map(str, (*axes[0], *axes[1]))),
                  fovy=str(plan["camera"]["vertical_fov_degrees"]))
    ET.SubElement(world, "light", name="PatchLight",
                  pos=f"{spawn[0]} {spawn[1]} {spawn[2]+3}", dir="0 0 -1",
                  directional="true", diffuse="0.6 0.6 0.6")
    xml = copied / "captured-scene.xml"
    ET.ElementTree(root).write(xml, encoding="unicode")
    model = mujoco.MjModel.from_xml_path(str(xml))
    model.opt.timestep = plan["physics_timestep"]
    model.vis.global_.offwidth = plan["camera"]["width"]
    model.vis.global_.offheight = plan["camera"]["height"]
    model.vis.map.znear = .001
    data = mujoco.MjData(model)
    ids = model.actuator_trnid[:, 0]
    names = [model.joint(int(i)).name for i in ids]
    if names != list(JOINTS) or model.nq != 21 or model.nbody != 16:
        raise ValueError("compiled robot differs from the declared policy contract")
    qi, vi = model.jnt_qposadr[ids], model.jnt_dofadr[ids]
    data.qpos[:7] = [*spawn, 1, 0, 0, 0]
    data.qpos[qi] = DEFAULT_POSE
    data.ctrl[:] = DEFAULT_POSE
    mujoco.mj_forward(model, data)
    terrain_id = model.geom("CapturedTerrain").id
    contacts = [data.contact[i] for i in range(data.ncon)
                if terrain_id in data.contact[i].geom]
    if any(c.dist < -1e-6 for c in contacts):
        raise ValueError("declared initial placement penetrates the collision proxy")
    # MuJoCo normalizes height data on load. Check its actual compiled samples,
    # then ray-test both triangle interiors of every cell against the display proxy.
    native_heights = np.rot90(model.hfield_data.reshape(n, n), -1).ravel()
    native_heights = native_heights * model.hfield_size[0, 2] + bottom
    sample_error = float(np.max(np.abs(native_heights - heights)))
    if sample_error > 2e-5:
        raise ValueError(f"compiled height samples differ: {sample_error} m")
    mask = np.asarray([1, 0, 0, 0, 0, 0], dtype=np.uint8)
    geom_id = np.zeros(1, dtype=np.int32)
    largest = 0.
    for r in range(n - 1):
        for c in range(n - 1):
            for u, v in ((.2, .3), (.8, .7)):
                point = np.asarray([low[0] + span[0] * (c+u) / (n-1),
                                    low[1] + span[1] * (r+v) / (n-1), high[2] + 1])
                distance = mujoco.mj_ray(model, data, point, np.asarray([0., 0., -1.]),
                                         mask, 1, -1, geom_id)
                expected = height_at(terrain, float(point[0]), float(point[1]))
                if geom_id[0] != terrain_id or distance < 0:
                    raise ValueError("compiled terrain ray did not hit the captured proxy")
                largest = max(largest, abs(point[2] - distance - expected))
    if largest > 2e-5:
        raise ValueError(f"compiled heightfield differs from source: {largest} m")
    camera_id = model.camera("RecordedCamera").id
    native_axes = data.cam_xmat[camera_id].reshape(3, 3).T
    if not np.allclose(native_axes, axes, atol=1e-12, rtol=0):
        raise ValueError("compiled camera axes differ from the declared pose")
    height, width = plan["camera"]["height"], plan["camera"]["width"]
    focal = height / (2 * math.tan(math.radians(float(model.cam_fovy[camera_id])) / 2))
    camera = {
        "name": "RecordedCamera", "width": width, "height": height,
        "position_m": data.cam_xpos[camera_id].tolist(),
        "axes_world": native_axes.tolist(), "focal_px": [focal, focal],
        "principal_px": [width / 2, height / 2],
        "vertical_fov_degrees": float(model.cam_fovy[camera_id]),
        "convention": "camera right +X, up +Y, forward -Z; pixel origin top-left",
    }
    metadata = {"case": case, "spawn_position_m": spawn, "camera": camera,
                "source_heightfield": identity(height_path),
                "heightfield_local_to_world": "rotate +90 degrees around Z; swap X/Y extents; reindex samples",
                "compiled_vertical_span_m": vertical_span,
                "compiled_heightfield_vertices": n * n,
                "max_compiled_height_error_m": sample_error,
                "checked_triangle_interiors": 2 * (n - 1) ** 2,
                "max_heightfield_ray_error_m": largest,
                "initial_terrain_contacts": len(contacts)}
    shutil.copyfile(height_path, output / "collision-heightfield.json")
    shutil.copyfile(source_check, output / "model-source-check.json")
    write_json(output / "preflight.json", metadata)
    return model, data, qi, vi, metadata


def record(args):
    import imageio_ffmpeg
    import mujoco
    import numpy as np
    import onnxruntime as ort

    plan = json.loads(args.plan.read_text())
    if (plan.get("schema") != PLAN_SCHEMA or args.case not in plan["cases"]
            or plan["physics_timestep"] != .005 or plan["sample_hz"] != 30
            or plan["seconds"] != 6):
        raise ValueError("unsupported or incomplete recording plan")
    if identity(args.policy)["sha256"] != POLICY_SHA256:
        raise ValueError("official policy bytes differ")
    source = ROOT / "docs/scene-lab" / args.case
    for name, expected in plan["cases"][args.case]["files"].items():
        checked_file(source, name, expected)
    args.output.mkdir(parents=True, exist_ok=False)
    shutil.copyfile(args.plan, args.output / "plan.json")
    source_commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    dirty = bool(subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True))
    if dirty and not args.preflight_only:
        raise ValueError("commit recorder source before running the planned policy")
    recorder_files = {name: identity(ROOT / name) for name in (
        "scripts/record_scene_motion.py", "robot_reel/scene_motion.py", "robot_reel/microduck.py")}
    if identity(args.source_check) != plan["source_check"]:
        raise ValueError("model source check differs from the frozen plan")
    for name, expected in recorder_files.items():
        destination = args.output / "recorder" / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(checked_file(ROOT, name, expected), destination)
    model, data, qi, vi, prepared = prepare_model(
        args.model, args.source_check, source / "collision-heightfield.json",
        args.output, plan, args.case,
    )
    if args.preflight_only:
        return prepared
    options = ort.SessionOptions()
    options.intra_op_num_threads = options.inter_op_num_threads = 1
    policy = ort.InferenceSession(str(args.policy), sess_options=options, providers=["CPUExecutionProvider"])
    if policy.get_inputs()[0].shape != [1, 61] or policy.get_outputs()[0].shape != [1, 14]:
        raise ValueError("official ONNX policy has an unexpected interface")
    renderer = mujoco.Renderer(model, height=plan["camera"]["height"], width=plan["camera"]["width"])
    from OpenGL.GL import GL_RENDERER, GL_VENDOR, GL_VERSION, glGetString
    graphics = {name: glGetString(key).decode() for name, key in (
        ("renderer", GL_RENDERER), ("vendor", GL_VENDOR), ("version", GL_VERSION))}
    writer = imageio_ffmpeg.write_frames(
        str(args.output / "simulation.mp4"), (plan["camera"]["width"], plan["camera"]["height"]),
        fps=plan["sample_hz"], codec="libx264", pix_fmt_out="yuv420p",
        quality=8, macro_block_size=2, ffmpeg_log_level="error",
    )
    writer.send(None)
    frames, calls = [], []
    gyro = int(model.sensor("imu_ang_vel").adr[0])
    trunk, terrain_id = model.body("trunk_base").id, model.geom("CapturedTerrain").id
    pose = np.asarray(DEFAULT_POSE, dtype=np.float32)
    previous = np.zeros(14, dtype=np.float32)
    total_steps = round(plan["seconds"] / plan["physics_timestep"])
    sample_steps = {round(i / plan["sample_hz"] / plan["physics_timestep"]): i
                    for i in range(round(plan["seconds"] * plan["sample_hz"]) + 1)}
    started = time.perf_counter()
    failure = None
    try:
        for step in range(total_steps + 1):
            if not np.isfinite(data.qpos).all() or not np.isfinite(data.qvel).all():
                raise ValueError("non-finite simulator state")
            if step % 4 == 0 and step < total_steps:
                mujoco.mj_forward(model, data)
                command = np.zeros(13, dtype=np.float32)
                command[0] = plan["forward_command_mps"] if 200 <= step < 1000 else 0
                gravity = data.xmat[trunk].reshape(3, 3).T @ np.asarray([0., 0., -1.])
                observation = np.concatenate([
                    data.sensordata[gyro:gyro+3], gravity, data.qpos[qi]-pose,
                    data.qvel[vi], previous, command,
                ]).astype(np.float32)
                begin = time.perf_counter()
                action = policy.run(None, {policy.get_inputs()[0].name: observation[None]})[0][0]
                elapsed = time.perf_counter() - begin
                if action.shape != (14,) or not np.isfinite(action).all():
                    raise ValueError("non-finite or malformed policy output")
                previous = action.astype(np.float32)
                data.ctrl[:] = pose + previous
                calls.append({"call": len(calls), "physics_step": step, "sim_time_s": float(data.time),
                              "observation": observation.tolist(), "action": previous.tolist(),
                              "target_rad": data.ctrl.tolist(), "elapsed_seconds": elapsed})
            if step in sample_steps:
                # mj_step integrates qpos after computing transforms; refresh before
                # recording so poses and rendered pixels describe the stored qpos.
                mujoco.mj_forward(model, data)
                if not np.isfinite(data.xpos).all() or not np.isfinite(data.xquat).all():
                    raise ValueError("non-finite body transforms")
                contacts = []
                for i in range(data.ncon):
                    contact = data.contact[i]
                    if terrain_id not in contact.geom:
                        continue
                    force = np.zeros(6)
                    mujoco.mj_contactForce(model, data, i, force)
                    other = int(contact.geom[1] if contact.geom[0] == terrain_id else contact.geom[0])
                    contacts.append({"robot_body": model.body(int(model.geom_bodyid[other])).name,
                                     "position_m": contact.pos.tolist(), "distance_m": float(contact.dist),
                                     "contact_frame": contact.frame.tolist(),
                                     "force_torque_contact_frame": force.tolist()})
                frames.append({
                    "frame": len(frames), "physics_step": step, "sim_time_s": float(data.time),
                    "qpos": data.qpos.tolist(), "qvel": data.qvel.tolist(),
                    "target_rad": data.ctrl.tolist(), "policy_call": len(calls)-1,
                    "body_poses": [np.concatenate([data.xpos[i], data.xquat[i]]).tolist()
                                   for i in range(1, model.nbody)],
                    "terrain_contacts": contacts,
                })
                renderer.update_scene(data, camera="RecordedCamera")
                writer.send(renderer.render())
            if step < total_steps:
                mujoco.mj_step(model, data)
    except Exception as error:
        failure = {"type": type(error).__name__, "message": str(error)}
    finally:
        writer.close()
        renderer.close()
    trace = {
        "schema": SCHEMA, "case": args.case, "world": {"unit": "metre", "up": "Z"},
        "plan": plan, "plan_file": identity(args.plan),
        "recorder": {"commit": source_commit, "dirty": dirty, "files": recorder_files},
        "runtime": {name: importlib.metadata.version(name) for name in (
            "mujoco", "onnxruntime", "numpy", "imageio_ffmpeg")},
        "graphics": graphics, "elapsed_seconds": time.perf_counter() - started,
        "policy": {"revision": POLICY_REVISION, "sha256": POLICY_SHA256,
                   "model_commit": MODEL_COMMIT, "providers": policy.get_providers(),
                   "actuators": "XML position-actuator fallback; not BAM"},
        "joints": list(JOINTS), "bodies": [model.body(i).name for i in range(1, model.nbody)],
        "camera": prepared["camera"], "initial": prepared,
        "frames": frames, "policy_calls": calls,
        "error": failure,
        "simulator_warnings": [
            {"name": mujoco.mjtWarning(i).name, "count": int(warning.number),
             "last_info": int(warning.lastinfo)}
            for i, warning in enumerate(data.warning)
        ],
        "files": {str(p.relative_to(args.output)): identity(p) for p in sorted(args.output.rglob("*"))
                  if p.is_file()},
        "scope": "Fresh simulation on a captured-scene heightfield approximation; no real-hardware result.",
    }
    # Retain partial state and policy outputs before any validation can fail.
    write_json(args.output / "trace.json", trace)
    if failure:
        raise RuntimeError(f"recording failed; partial trace retained: {failure}")
    for name, expected in recorder_files.items():
        checked_file(ROOT, name, expected)
    if identity(args.policy)["sha256"] != POLICY_SHA256:
        raise ValueError("policy file changed during recording")
    result = validate_trace(trace)
    write_json(args.output / "validation.json", result)
    return {**result, "case": args.case, "graphics": graphics,
            "final_root_position_m": frames[-1]["qpos"][:3],
            "contact_samples": sum(bool(f["terrain_contacts"]) for f in frames)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--case", choices=("baseline", "edited"), required=True)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--source-check", type=Path, required=True)
    parser.add_argument("--policy", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--preflight-only", action="store_true")
    args = parser.parse_args()
    print(json.dumps(record(args), indent=2), flush=True)
