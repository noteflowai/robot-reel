"""Compare browser scene readback with fresh native MuJoCo transforms."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from robot_reel.scene_motion import checked_file, identity, validate_trace, write_json


def check(base, browser_readback):
    import mujoco
    import numpy as np

    base, browser_readback = Path(base), Path(browser_readback)
    browser = json.loads(browser_readback.read_text())
    if browser.get("schema") != "robot-reel.scene-browser-readback.v1":
        raise ValueError("unsupported browser readback")
    conversion = np.array([[1., 0, 0, 0], [0, 0, 1, 0], [0, -1, 0, 0], [0, 0, 0, 1]])
    results = {}

    def matrix(rotation, position):
        value = np.eye(4)
        value[:3, :3], value[:3, 3] = rotation.reshape(3, 3), position
        return conversion @ value

    def maximum_difference(actual, expected):
        array = np.asarray(actual, dtype=np.float64)
        if array.shape != expected.shape or not np.isfinite(array).all():
            raise ValueError("browser readback dimensions or values differ")
        return float(np.max(np.abs(array - expected))) if array.size else 0.

    for case in ("baseline", "edited"):
        source = base / case
        trace = json.loads((source / "trace.json").read_text())
        validate_trace(trace)
        for name, expected in trace["files"].items():
            checked_file(source, name, expected)
        actual = browser["cases"][case]
        if actual["source_trace"] != identity(source / "trace.json"):
            raise ValueError("browser identifies a different source trace")
        model = mujoco.MjModel.from_xml_path(str(source / "model/captured-scene.xml"))
        data = mujoco.MjData(model)
        bodies = [model.body(name).id for name in trace["bodies"]]
        visual_ids = [i for i in range(model.ngeom) if model.geom_group[i] == 2]
        visual_names = [f"geom_{i:03}" for i in visual_ids]
        if actual["body_names"] != trace["bodies"] or actual["visual_names"] != visual_names:
            raise ValueError("browser model node inventory differs")
        if len(actual["frames"]) != len(trace["frames"]):
            raise ValueError("browser did not read every source frame")
        cam = model.camera("RecordedCamera").id
        matrix_error = pixel_error = contact_error = 0.
        count_contacts = 0
        for row, frame in zip(actual["frames"], trace["frames"], strict=True):
            if row["frame"] != frame["frame"]:
                raise ValueError("browser frame order differs")
            data.qpos[:], data.qvel[:] = frame["qpos"], frame["qvel"]
            mujoco.mj_forward(model, data)
            expected_body = np.array([matrix(data.xmat[i], data.xpos[i]).T.ravel() for i in bodies])
            expected_visual = np.array([matrix(data.geom_xmat[i], data.geom_xpos[i]).T.ravel() for i in visual_ids])
            matrix_error = max(matrix_error,
                               maximum_difference(row["bodies"], expected_body),
                               maximum_difference(row["visuals"], expected_visual))
            rotation, position = data.cam_xmat[cam].reshape(3, 3), data.cam_xpos[cam]
            camera_matrix = matrix(data.cam_xmat[cam], position).T.ravel()
            matrix_error = max(matrix_error, maximum_difference(row["camera"], camera_matrix))
            width, height = trace["camera"]["width"], trace["camera"]["height"]
            focal = height / (2 * math.tan(math.radians(model.cam_fovy[cam]) / 2))
            points = []
            for body in bodies:
                local = rotation.T @ (data.xpos[body] - position)
                depth = -local[2]
                if depth <= 0:
                    raise ValueError("source body is behind the recorded camera")
                points.append([width/2+focal*local[0]/depth,
                               height/2-focal*local[1]/depth, depth])
            pixel_error = max(pixel_error, maximum_difference(row["projections"], np.asarray(points)))
            expected_contacts = np.asarray([
                conversion[:3, :3] @ np.asarray(contact["position_m"])
                for contact in frame["terrain_contacts"]
            ]).reshape(-1, 3)
            contact_error = max(contact_error, maximum_difference(
                np.asarray(row["contacts"]).reshape(-1, 3), expected_contacts))
            count_contacts += len(expected_contacts)
        checked_vertices = 0
        for item, geom in zip(actual["geometry"], visual_ids, strict=True):
            mesh = int(model.geom_dataid[geom])
            first, count = model.mesh_vertadr[mesh], model.mesh_vertnum[mesh]
            start, faces = model.mesh_faceadr[mesh], model.mesh_facenum[mesh]
            vertices = model.mesh_vert[first:first+count].astype("<f4").tobytes()
            indices = model.mesh_face[start:start+faces].astype("<u4").ravel().tobytes()
            expected = {"name": f"geom_{geom:03}", "vertices": int(count),
                        "indices": int(faces*3),
                        "positions_sha256": hashlib.sha256(vertices).hexdigest(),
                        "indices_sha256": hashlib.sha256(indices).hexdigest()}
            if item != expected:
                raise ValueError(f"browser visual buffer differs from native geometry: {geom}")
            checked_vertices += int(count)
        if matrix_error > 3e-6 or pixel_error > .002 or contact_error > 3e-7:
            raise ValueError("browser transform, projection or contact readback exceeds tolerance")
        results[case] = {
            "frames": len(trace["frames"]), "body_transforms": len(bodies)*len(trace["frames"]),
            "visual_transforms": len(visual_ids)*len(trace["frames"]),
            "camera_projections": len(bodies)*len(trace["frames"]),
            "checked_visual_vertices": checked_vertices, "checked_contacts": count_contacts,
            "max_world_matrix_error": matrix_error, "max_projection_error_px": pixel_error,
            "max_contact_position_error_m": contact_error, "source_trace": identity(source / "trace.json"),
        }
    return {
        "schema": "robot-reel.scene-browser-native-check.v1", "passed": True,
        "mujoco": mujoco.__version__, "browser_readback": identity(browser_readback),
        "browser": browser["browser"], "cases": results,
        "scope": "Native MuJoCo transforms and camera versus browser scene matrices and projections; original visual buffers and recorded contacts. This is not raster pixel equality or a physical-camera calibration.",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--recordings", type=Path, required=True)
    parser.add_argument("--browser-readback", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = check(args.recordings, args.browser_readback)
    write_json(args.output, result)
    print(json.dumps(result, indent=2))
