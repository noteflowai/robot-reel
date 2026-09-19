"""Recompute every recorded body pose and replay the saved control sequence."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from robot_reel.microduck import DEFAULT_POSE
from robot_reel.scene_motion import checked_file, identity, validate_trace, write_json


def check(root):
    import mujoco
    import numpy as np

    root = Path(root)
    trace = json.loads((root / "trace.json").read_text())
    result = validate_trace(trace)
    if trace["error"] is not None:
        raise ValueError("recording retained an execution error")
    for name, expected in trace["files"].items():
        checked_file(root, name, expected)
    if identity(root / "plan.json") != trace["plan_file"]:
        raise ValueError("copied plan differs from the recorded plan")
    model = mujoco.MjModel.from_xml_path(str(root / "model/captured-scene.xml"))
    if mujoco.__version__ != trace["runtime"]["mujoco"]:
        raise ValueError("use the recorded MuJoCo version for dynamics replay")
    model.opt.timestep = trace["plan"]["physics_timestep"]
    if [model.body(i).name for i in range(1, model.nbody)] != trace["bodies"]:
        raise ValueError("compiled body identities differ")
    data = mujoco.MjData(model)
    pose_error = 0.
    camera_error = 0.
    camera_id = model.camera("RecordedCamera").id
    # FK is recomputed independently from each full qpos, including the floating root.
    for frame in trace["frames"]:
        data.qpos[:] = frame["qpos"]
        data.qvel[:] = frame["qvel"]
        data.ctrl[:] = frame["target_rad"]
        mujoco.mj_forward(model, data)
        poses = np.column_stack([data.xpos[1:], data.xquat[1:]])
        pose_error = max(pose_error, float(np.max(np.abs(poses - frame["body_poses"]))))
        camera_error = max(camera_error,
                           float(np.max(np.abs(data.cam_xpos[camera_id] - trace["camera"]["position_m"]))),
                           float(np.max(np.abs(data.cam_xmat[camera_id].reshape(3, 3).T
                                               - trace["camera"]["axes_world"]))))
    if pose_error > 1e-11 or camera_error > 1e-11:
        raise ValueError(f"native transforms differ: poses={pose_error}, camera={camera_error}")

    mujoco.mj_resetData(model, data)
    data.qpos[:] = trace["frames"][0]["qpos"]
    data.qvel[:] = trace["frames"][0]["qvel"]
    data.ctrl[:] = DEFAULT_POSE
    mujoco.mj_forward(model, data)
    frames = {frame["physics_step"]: frame for frame in trace["frames"]}
    calls = {call["physics_step"]: call for call in trace["policy_calls"]}
    qi = model.jnt_qposadr[model.actuator_trnid[:, 0]]
    vi = model.jnt_dofadr[model.actuator_trnid[:, 0]]
    gyro, trunk = int(model.sensor("imu_ang_vel").adr[0]), model.body("trunk_base").id
    previous = np.zeros(14, dtype=np.float32)
    pose = np.asarray(DEFAULT_POSE, dtype=np.float32)
    state_error = observation_error = contact_error = 0.
    contact_count = 0
    for step in range(max(frames) + 1):
        if step in calls:
            mujoco.mj_forward(model, data)
            command = np.zeros(13, dtype=np.float32)
            command[0] = trace["plan"]["forward_command_mps"] if 200 <= step < 1000 else 0
            gravity = data.xmat[trunk].reshape(3, 3).T @ np.asarray([0., 0., -1.])
            observation = np.concatenate([
                data.sensordata[gyro:gyro+3], gravity, data.qpos[qi] - pose,
                data.qvel[vi], previous, command,
            ]).astype(np.float32)
            call = calls[step]
            observation_error = max(observation_error, float(np.max(np.abs(
                observation - call["observation"]))))
            previous = np.asarray(call["action"], dtype=np.float32)
            expected = pose + previous
            if not np.array_equal(expected, call["target_rad"]):
                raise ValueError("recorded action does not produce its target")
            data.ctrl[:] = call["target_rad"]
        if step in frames:
            mujoco.mj_forward(model, data)
            frame = frames[step]
            state_error = max(
                state_error, float(np.max(np.abs(data.qpos - frame["qpos"]))),
                float(np.max(np.abs(data.qvel - frame["qvel"]))),
            )
            native_contacts = [i for i in range(data.ncon)
                               if model.geom("CapturedTerrain").id in data.contact[i].geom]
            if len(native_contacts) != len(frame["terrain_contacts"]):
                raise ValueError("replayed terrain contact count differs")
            for i, expected in zip(native_contacts, frame["terrain_contacts"]):
                contact = data.contact[i]
                force = np.zeros(6)
                mujoco.mj_contactForce(model, data, i, force)
                contact_error = max(
                    contact_error, abs(float(contact.dist) - expected["distance_m"]),
                    float(np.max(np.abs(contact.pos - expected["position_m"]))),
                    float(np.max(np.abs(force - expected["force_torque_contact_frame"]))),
                )
                contact_count += 1
        if step < max(frames):
            mujoco.mj_step(model, data)
    if max(state_error, observation_error, contact_error) > 1e-8:
        raise ValueError(f"control replay differs: state={state_error}, "
                         f"observation={observation_error}, contacts={contact_error}")
    return {
        **result, "schema": "robot-reel.scene-motion-native-check.v1",
        "trace": identity(root / "trace.json"), "mujoco": mujoco.__version__,
        "max_body_pose_error": pose_error, "max_camera_transform_error": camera_error,
        "max_replayed_state_error": state_error, "max_policy_observation_error": observation_error,
        "checked_terrain_contacts": contact_count, "max_replayed_contact_error": contact_error,
        "scope": "Native FK and saved-control dynamics replay; policy inference is not repeated.",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("recording", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = check(args.recording)
    if args.output:
        if args.output.exists():
            raise ValueError("choose a new verification output")
        write_json(args.output, result)
    print(json.dumps(result, indent=2))
