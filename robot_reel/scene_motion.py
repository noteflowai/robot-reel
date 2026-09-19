"""Coordinate and file contracts for motion recorded on a captured heightfield."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

SCHEMA = "robot-reel.scene-motion.v1"
PLAN_SCHEMA = "robot-reel.scene-motion-plan.v1"
JOINTS = (
    "left_hip_yaw", "left_hip_roll", "left_hip_pitch", "left_knee", "left_ankle",
    "neck_pitch", "head_pitch", "head_yaw", "head_roll", "right_hip_yaw",
    "right_hip_roll", "right_hip_pitch", "right_knee", "right_ankle",
)


def identity(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"expected an ordinary file: {path.name}")
    with path.open("rb") as stream:
        return {"sha256": hashlib.file_digest(stream, "sha256").hexdigest(),
                "bytes": path.stat().st_size}


def checked_file(root, name, expected):
    root = Path(root).resolve()
    path = root / name
    if Path(name).is_absolute() or ".." in Path(name).parts:
        raise ValueError("source path must stay inside its reviewed directory")
    if not path.resolve().is_relative_to(root) or any(
        p.is_symlink() for p in (path, *path.parents) if p != root and p.is_relative_to(root)
    ):
        raise ValueError("source path contains a symlink")
    if identity(path) != expected:
        raise ValueError(f"source file changed: {name}")
    return path


def write_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")


def finite_vector(value, length):
    if not isinstance(value, list) or len(value) != length or any(
        type(x) not in (int, float) or not math.isfinite(x) for x in value
    ):
        raise ValueError(f"expected {length} finite numbers")
    return value


def dot(a, b):
    return sum(x * y for x, y in zip(a, b))


def cross(a, b):
    return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0]]


def normalized(a):
    size = math.sqrt(dot(a, a))
    if size < 1e-12:
        raise ValueError("camera axes must be nondegenerate")
    return [x / size for x in a]


def camera_axes(position, target):
    """Return camera-local right/up/back axes in the Z-up world."""
    back = normalized([p - t for p, t in zip(position, target)])
    right = normalized(cross([0, 0, 1], back))
    return right, cross(back, right), back


def project(camera, point):
    """Top-left image coordinates; positive depth is along camera -Z."""
    right, up, back = camera["axes_world"]
    offset = [x - p for x, p in zip(point, camera["position_m"])]
    depth = -dot(back, offset)
    if depth <= 0:
        return None
    fx, fy = camera["focal_px"]
    cx, cy = camera["principal_px"]
    return [cx + fx * dot(right, offset) / depth,
            cy - fy * dot(up, offset) / depth, depth]


def browser_point(point):
    """Metre-preserving Z-up to glTF/Three.js Y-up conversion."""
    x, y, z = finite_vector(list(point), 3)
    return [x, z, -y]


def checked_heightfield(path):
    record = json.loads(Path(path).read_text())
    n = record.get("resolution")
    if (record.get("schema") != "robot-reel.heightfield.v1"
            or record.get("unit") != "metre" or record.get("up_axis") != "Z"
            or type(n) is not int or not 3 <= n <= 1025):
        raise ValueError("unsupported captured heightfield")
    low, high = record["bounds"]
    finite_vector(low, 3)
    finite_vector(high, 3)
    finite_vector(record["heights_m"], n * n)
    if any(b <= a for a, b in zip(low, high)):
        raise ValueError("heightfield bounds must have positive spans")
    if any(z < low[2] - 1e-6 or z > high[2] + 1e-6 for z in record["heights_m"]):
        raise ValueError("heightfield sample outside recorded bounds")
    return record


def height_at(terrain, x, y):
    """Interpolate the existing CollisionHeightfield mesh's explicit triangles."""
    low, high = terrain["bounds"]
    n = terrain["resolution"]
    u = (x - low[0]) * (n - 1) / (high[0] - low[0])
    v = (y - low[1]) * (n - 1) / (high[1] - low[1])
    if not 0 <= u <= n - 1 or not 0 <= v <= n - 1:
        raise ValueError("point lies outside the captured proxy")
    col, row = min(int(u), n - 2), min(int(v), n - 2)
    u, v = u - col, v - row
    values = terrain["heights_m"]
    a, b = values[row*n+col:row*n+col+2]
    c, d = values[(row+1)*n+col:(row+1)*n+col+2]
    if u + v <= 1:
        return a + u * (b - a) + v * (c - a)
    return d + (1 - u) * (c - d) + (1 - v) * (b - d)


def validate_trace(trace):
    if trace.get("schema") != SCHEMA or trace.get("world") != {"unit": "metre", "up": "Z"}:
        raise ValueError("unsupported motion trace")
    if trace.get("joints") != list(JOINTS):
        raise ValueError("joint order differs from the pinned walking policy")
    frames, calls = trace["frames"], trace["policy_calls"]
    plan = trace["plan"]
    expected = round(plan["seconds"] * plan["sample_hz"]) + 1
    if len(frames) != expected or len(calls) != round(plan["seconds"] / .02):
        raise ValueError("incomplete recording")
    body_count = len(trace["bodies"])
    if body_count != 15 or len(set(trace["bodies"])) != body_count:
        raise ValueError("expected every non-world Microduck body")
    for i, frame in enumerate(frames):
        step = round(i / plan["sample_hz"] / plan["physics_timestep"])
        if frame["frame"] != i or frame["physics_step"] != step or not math.isclose(
            frame["sim_time_s"], step * plan["physics_timestep"], abs_tol=1e-9
        ):
            raise ValueError("frame clock differs from the recorded physics step")
        finite_vector(frame["qpos"], 21)
        finite_vector(frame["qvel"], 20)
        finite_vector(frame["target_rad"], 14)
        if len(frame["body_poses"]) != body_count:
            raise ValueError("body transforms are missing")
        for pose in frame["body_poses"]:
            finite_vector(pose, 7)
            if not math.isclose(dot(pose[3:], pose[3:]), 1, abs_tol=1e-9):
                raise ValueError("body quaternion is not normalized")
        if frame["policy_call"] != min(step // 4, len(calls) - 1):
            raise ValueError("frame does not identify its actual policy call")
        if frame["target_rad"] != calls[frame["policy_call"]]["target_rad"]:
            raise ValueError("frame targets differ from the applied policy output")
    for i, call in enumerate(calls):
        if call["call"] != i or call["physics_step"] != i * 4 or not math.isclose(
            call["sim_time_s"], i * .02, abs_tol=1e-9
        ):
            raise ValueError("policy clock differs from the fixed control rate")
        finite_vector(call["observation"], 61)
        finite_vector(call["action"], 14)
        finite_vector(call["target_rad"], 14)
        if type(call["elapsed_seconds"]) not in (int, float) or not (
            math.isfinite(call["elapsed_seconds"]) and call["elapsed_seconds"] >= 0
        ):
            raise ValueError("invalid inference time")
    return {"valid": True, "frames": len(frames), "policy_calls": len(calls),
            "body_transforms": len(frames) * body_count}
