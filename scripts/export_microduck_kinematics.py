"""Extract a bounded Microduck schematic and check FK against native MuJoCo.

Requires the pinned model in ROBOT_REEL_CACHE (robot-reel record --pack microduck
fetches it). Never fetches or runs the policy. No simulation or rendering needed.
"""
import argparse
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.build_microduck_lab import JOINTS, KINEMATICS, MODEL_COMMIT, SOURCE, digest, poses, rotate


def extract(model):
    import mujoco
    import numpy as np
    bodies = []
    for i in range(1, model.nbody):
        joint_id = int(model.body_jntadr[i])
        if int(model.body_jntnum[i]) != 1:
            raise ValueError("Expected one joint per body")
        joint_index = -1 if i == 1 else JOINTS.index(model.joint(joint_id).name)
        points = []
        for g in range(model.ngeom):
            if model.geom_bodyid[g] != i or model.geom_group[g] != 2:
                continue
            if model.geom_type[g] != mujoco.mjtGeom.mjGEOM_MESH:
                raise ValueError("Unexpected visual geometry")
            mesh = model.geom_dataid[g]
            start, count = model.mesh_vertadr[mesh], model.mesh_vertnum[mesh]
            matrix = np.zeros(9)
            mujoco.mju_quat2Mat(matrix, model.geom_quat[g])
            points.extend(model.mesh_vert[start:start+count] @ matrix.reshape(3, 3).T + model.geom_pos[g])
        if not points:
            raise ValueError("Expected visual vertices for body envelope")
        points = np.asarray(points)
        bodies.append({"name": model.body(i).name, "parent": int(model.body_parentid[i])-1,
                       "position": model.body_pos[i].tolist(), "quaternion": model.body_quat[i].tolist(),
                       "joint": joint_index, "axis": model.jnt_axis[joint_id].tolist(),
                       "offset": model.jnt_pos[joint_id].tolist(),
                       "reference": float(model.qpos0[model.jnt_qposadr[joint_id]]),
                       "bounds": [points.min(axis=0).tolist(), points.max(axis=0).tolist()]})
    return {"schema": "robot-reel-microduck-kinematics-1", "model_commit": MODEL_COMMIT,
            "joints": list(JOINTS), "bodies": bodies,
            "bounds_method": "body-local AABB of all group-2 visual mesh vertices",
            "license": "Upstream 3D model terms: Creative Commons BY-SA-NC (version unspecified)."}


def native_check(model, kin):
    import mujoco
    import numpy as np
    data = mujoco.MjData(model)
    data.qpos[:7] = [0, 0, 0, 1, 0, 0, 0]
    ids = [model.joint(name).id for name in JOINTS]
    position_error = rotation_error = 0.
    count = 0
    for name in ("left", "right"):
        trace = json.loads((SOURCE/f"{name}-trace.json").read_text())
        for frame in trace["frames"]:
            for field in ("qpos", "target"):
                data.qpos[model.jnt_qposadr[ids]] = frame[field]
                mujoco.mj_forward(model, data)
                for i, pose in enumerate(poses(kin, frame[field]), 1):
                    position_error = max(position_error, float(np.max(np.abs(data.xpos[i]-pose[:3]))))
                    matrix = np.array([rotate(pose[3:], axis) for axis in np.eye(3)]).T
                    rotation_error = max(rotation_error, float(np.max(np.abs(data.xmat[i].reshape(3, 3)-matrix))))
                    count += 1
    if position_error >= 1e-9 or rotation_error >= 1e-9:
        raise ValueError("Forward kinematics differs from MuJoCo")
    return {"mujoco": mujoco.__version__, "checked_body_transforms": count,
            "max_position_error_m": position_error, "max_rotation_matrix_error": rotation_error,
            "trace_sha256": {name: digest(SOURCE/f"{name}-trace.json") for name in ("left", "right")}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Verify committed extraction without writing")
    args = parser.parse_args()
    import mujoco
    cache = Path(os.environ.get("ROBOT_REEL_CACHE", Path.home()/".cache/robot-reel"))
    directory = cache/f"microduck-{MODEL_COMMIT}"
    model = mujoco.MjModel.from_xml_path(str(directory/"scene.xml"))
    kin = extract(model)
    # Include every XML/STL file in the pinned snapshot, not workspace paths.
    kin["model_files_sha256"] = {p.relative_to(directory).as_posix(): digest(p)
        for p in sorted(directory.rglob("*")) if p.suffix in (".xml", ".stl")}
    if args.check:
        if json.loads(KINEMATICS.read_text()) != kin:
            raise ValueError("Committed kinematics differs from pinned native model")
    else:
        KINEMATICS.parent.mkdir(parents=True, exist_ok=True)
        KINEMATICS.write_text(json.dumps(kin, indent=2)+"\n")
    report = {**native_check(model, kin), "kinematics_sha256": digest(KINEMATICS)}
    if not args.check:
        KINEMATICS.with_name("microduck-kinematics-check.json").write_text(json.dumps(report, indent=2)+"\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
