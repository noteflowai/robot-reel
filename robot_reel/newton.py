"""Record a CPU Newton double pendulum, then share its measured rigid poses."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

FPS = 30
SUBSTEPS = 10
SCHEMA = "robot-reel-newton-1"
FILES = ("trace.json", "scene.usda", "index.html")
BODIES = [
    {"name": "upper", "size": [1.6, .18, .18], "color": "#65dcc5"},
    {"name": "lower", "size": [1.6, .18, .18], "color": "#ffba75"},
]


def point(pose, local):
    """Transform a point by [x, y, z, qx, qy, qz, qw]."""
    x, y, z, w = pose[3:]
    u, v, t = local
    tx, ty, tz = 2 * (y*t-z*v), 2 * (z*u-x*t), 2 * (x*v-y*u)
    return [
        pose[0] + u + w*tx + y*tz - z*ty,
        pose[1] + v + w*ty + z*tx - x*tz,
        pose[2] + t + w*tz + x*ty - y*tx,
    ]


def summary(trace):
    anchor_error = joint_error = 0.
    heights = []
    for frame in trace["frames"]:
        upper, lower = frame["poses"]
        anchor_error = max(anchor_error, math.dist(point(upper, [-.8, 0, 0]), [0, 0, 3.8]))
        joint_error = max(joint_error, math.dist(point(upper, [.8, 0, 0]), point(lower, [-.8, 0, 0])))
        heights.append(point(lower, [.8, 0, 0])[2])
    return {
        "max_anchor_error_m": anchor_error,
        "max_joint_error_m": joint_error,
        "min_tip_height_m": min(heights),
        "max_tip_height_m": max(heights),
    }


def validate_trace(trace):
    """Validate this bounded demo schema without importing Newton or NumPy."""
    if not isinstance(trace, dict) or trace.get("schema") != SCHEMA:
        raise ValueError("Unsupported Newton trace schema")
    if trace.get("bodies") != BODIES:
        raise ValueError("This demo supports its two recorded box links only")
    expected = {
        "engine": "newton", "engine_version": "1.6.0", "solver": "SolverXPBD",
        "device": "cpu", "mode": "physics", "scene": "double_pendulum",
        "substeps": SUBSTEPS, "timestep": 1 / (FPS * SUBSTEPS),
        "gravity_m_s2": [0, 0, -9.81],
    }
    source = trace.get("source", {})
    if not isinstance(source, dict) or any(source.get(k) != v for k, v in expected.items()):
        raise ValueError("Newton scene provenance mismatch")
    for key in ("warp_version", "usd_version"):
        if not isinstance(source.get(key), str) or not source[key]:
            raise ValueError(f"Missing {key}")
    if trace.get("fps") != FPS or trace.get("units") != {
        "position": "m", "time": "s", "quaternion": "xyzw", "up_axis": "Z",
    }:
        raise ValueError("Unsupported time base, units or quaternion convention")
    frames = trace.get("frames")
    if not isinstance(frames, list) or not 2 <= len(frames) <= 30*FPS+1:
        raise ValueError("Expected 2–901 recorded samples")
    for i, frame in enumerate(frames):
        if not isinstance(frame, dict) or type(frame.get("frame")) is not int or frame["frame"] != i:
            raise ValueError("Nonsequential frame")
        time = frame.get("sim_time")
        if type(time) not in (int, float) or not math.isfinite(time) or abs(time - i/FPS) > 1e-9:
            raise ValueError("Frame timestamp does not match the simulation clock")
        poses = frame.get("poses")
        if not isinstance(poses, list) or len(poses) != len(BODIES):
            raise ValueError("Missing body poses")
        for pose in poses:
            if not isinstance(pose, list) or len(pose) != 7 or not all(
                type(v) in (int, float) and math.isfinite(v) for v in pose
            ):
                raise ValueError("Invalid position or quaternion")
            if abs(sum(v*v for v in pose[3:]) - 1) > 1e-5:
                raise ValueError("Quaternion is not normalized")
    measured = summary(trace)
    if trace.get("summary") != measured:
        raise ValueError("Summary does not agree with the recorded poses")
    return measured


def export_viewer(trace, destination):
    validate_trace(trace)
    template = Path(__file__).with_name("newton.html").read_text()
    # Keep the inline JSON inert, including for future string metadata.
    data = json.dumps(trace, separators=(",", ":"), allow_nan=False).replace("<", "\\u003c")
    Path(destination).write_text(template.replace("__TRACE__", data))


def write_manifest(output):
    output = Path(output)
    document = {
        "schema": SCHEMA,
        "files": {name: hashlib.sha256((output/name).read_bytes()).hexdigest() for name in FILES},
    }
    (output/"manifest.json").write_text(json.dumps(document, indent=2) + "\n")


def verify(output):
    output = Path(output)
    manifest = json.loads((output/"manifest.json").read_text())
    if manifest.get("schema") != SCHEMA or set(manifest.get("files", {})) != set(FILES):
        raise ValueError("Incomplete Newton bundle manifest")
    for name in FILES:
        if hashlib.sha256((output/name).read_bytes()).hexdigest() != manifest["files"][name]:
            raise ValueError(f"Hash mismatch: {name}")
    trace = json.loads((output/"trace.json").read_text())
    result = validate_trace(trace)
    # Check the actual browser payload too, even if someone refreshed its hash.
    html = (output/"index.html").read_text()
    marker = '<script id="trace-data" type="application/json">'
    if html.count(marker) != 1:
        raise ValueError("Missing browser trace")
    embedded = json.loads(html.split(marker, 1)[1].split("</script>", 1)[0])
    if embedded != trace:
        raise ValueError("Browser poses differ from the source trace")
    return result


def record(output, seconds=6):
    if type(seconds) not in (int, float) or not math.isfinite(seconds) or not 1/FPS <= seconds <= 30:
        raise ValueError("Duration must be between 1/30 and 30 seconds")
    steps = round(seconds * FPS)
    if abs(seconds * FPS - steps) > 1e-8:
        raise ValueError("Duration must contain a whole number of 30 Hz intervals")
    output = Path(output)
    if output.exists() and any(output.iterdir()):
        raise ValueError("Output is not empty; choose a fresh directory")

    from importlib.metadata import version
    import newton
    import warp as wp
    from .newton_usd import export_usd, check_usd

    if version("newton") != "1.6.0":
        raise ValueError("This adapter is tested with newton==1.6.0")
    output.mkdir(parents=True, exist_ok=True)
    wp.init()
    with wp.ScopedDevice("cpu"):
        builder = newton.ModelBuilder(gravity=-9.81)
        links = [builder.add_link(label=body["name"]) for body in BODIES]
        for link in links:
            builder.add_shape_box(link, hx=.8, hy=.09, hz=.09)
        joints = [
            builder.add_joint_revolute(
                -1, links[0], axis=(0, 1, 0),
                parent_xform=wp.transform(p=(0, 0, 3.8), q=wp.quat_from_axis_angle(wp.vec3(0, 1, 0), .55)),
                child_xform=wp.transform(p=(-.8, 0, 0), q=wp.quat_identity()),
                target_ke=0, target_kd=0, damping=0,
            ),
            builder.add_joint_revolute(
                links[0], links[1], axis=(0, 1, 0),
                parent_xform=wp.transform(p=(.8, 0, 0), q=wp.quat_identity()),
                child_xform=wp.transform(p=(-.8, 0, 0), q=wp.quat_identity()),
                target_ke=0, target_kd=0, damping=0,
            ),
        ]
        builder.add_articulation(joints, label="pendulum")
        builder.add_ground_plane()
        model = builder.finalize()
        current, next_state = model.state(), model.state()
        control = model.control()
        solver = newton.solvers.SolverXPBD(model)
        pipeline = newton.CollisionPipeline(model)
        contacts = pipeline.contacts()
        newton.eval_fk(model, model.joint_q, model.joint_qd, current)
        frames = []
        for i in range(steps+1):
            # Frame 0 is the initialized state, before the first physics step.
            frames.append({"frame": i, "sim_time": i/FPS, "poses": current.body_q.numpy().tolist()})
            if i == steps:
                break
            for _ in range(SUBSTEPS):
                current.clear_forces()
                pipeline.collide(current, contacts)
                solver.step(current, next_state, control, contacts, 1/(FPS*SUBSTEPS))
                current, next_state = next_state, current
    trace = {
        "schema": SCHEMA, "fps": FPS,
        "units": {"position": "m", "time": "s", "quaternion": "xyzw", "up_axis": "Z"},
        "source": {
            "engine": "newton", "engine_version": version("newton"), "warp_version": version("warp-lang"),
            "usd_version": version("usd-core"), "solver": "SolverXPBD", "device": "cpu",
            "mode": "physics", "scene": "double_pendulum", "substeps": SUBSTEPS,
            "timestep": 1/(FPS*SUBSTEPS), "gravity_m_s2": [0, 0, -9.81],
        },
        "bodies": BODIES, "frames": frames,
    }
    trace["summary"] = summary(trace)
    validate_trace(trace)
    (output/"trace.json").write_text(json.dumps(trace, indent=2, allow_nan=False) + "\n")
    export_usd(trace, output/"scene.usda")
    check_usd(trace, output/"scene.usda")
    export_viewer(trace, output/"index.html")
    write_manifest(output)
    return verify(output)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("artifacts/newton"))
    parser.add_argument("--seconds", type=float, default=6, help="Recording duration, up to 30 s (default: 6)")
    parser.add_argument("--verify", action="store_true", help="Check an existing bundle using only the standard library")
    parser.add_argument("--check-usd", action="store_true", help="Also compare every USD transform (requires usd-core)")
    args = parser.parse_args(argv)
    if args.check_usd and not args.verify:
        parser.error("--check-usd applies to --verify")
    try:
        result = verify(args.output) if args.verify else record(args.output, args.seconds)
        if args.check_usd:
            from .newton_usd import check_usd
            result["usd"] = check_usd(json.loads((args.output/"trace.json").read_text()), args.output/"scene.usda")
        print(json.dumps(result, indent=2))
        print(f"Verified: {args.output.resolve()}")
    except ImportError as exc:
        parser.exit(1, f"Missing recording/export dependency: {exc}. Install: pip install -e '.[newton]'\n")
    except (ValueError, OSError, KeyError, TypeError) as exc:
        parser.exit(1, f"Newton bundle error: {exc}\n")


if __name__ == "__main__":
    main()
