"""Record twelve isolated Newton pendulums with slightly different releases."""
from __future__ import annotations

import argparse
import colorsys
import hashlib
import json
import math
from pathlib import Path

from .newton import point

SCHEMA = "robot-reel-chaos-1"
FPS = 30
SUBSTEPS = 10
WORLD_COUNT = 12
ANGLE_STEP_DEG = .05
BASE_ANGLE_RAD = -1.3
SIZE = [1.6, .18, .18]
ANCHOR = [0, 0, 3.8]
FILES = ("trace.json", "index.html", "scene.usdc")


def worlds(count=WORLD_COUNT):
    result = []
    for i in range(count):
        rgb = colorsys.hsv_to_rgb(.46 + i * .039, .65, 1)
        result.append({
            "id": i, "angle_offset_deg": i * ANGLE_STEP_DEG,
            "release_angle_rad": BASE_ANGLE_RAD + math.radians(i * ANGLE_STEP_DEG),
            "color": "#" + "".join(f"{round(v*255):02x}" for v in rgb),
        })
    return result


def measure(trace):
    anchor_error = joint_error = 0.
    peak = {"distance_m": 0., "frame": 0, "world": 1}
    initial = []
    for frame in trace["frames"]:
        reference = point(frame["poses"][1], [.8, 0, 0])
        for w in range(trace["source"]["world_count"]):
            upper, lower = frame["poses"][w*2:w*2+2]
            anchor_error = max(anchor_error, math.dist(point(upper, [-.8, 0, 0]), ANCHOR))
            joint_error = max(joint_error, math.dist(point(upper, [.8, 0, 0]), point(lower, [-.8, 0, 0])))
            distance = math.dist(reference, point(lower, [.8, 0, 0]))
            if frame["frame"] == 0:
                initial.append(distance)
            if distance > peak["distance_m"]:
                peak = {"distance_m": distance, "frame": frame["frame"], "world": w}
    return {
        "body_samples": len(trace["frames"]) * trace["source"]["world_count"] * 2,
        "max_anchor_error_m": anchor_error, "max_joint_error_m": joint_error,
        "initial_tip_distances_m": initial, "peak": peak,
    }


def validate_trace(trace):
    """Validate provenance, initial conditions, constraints and derived metrics."""
    if not isinstance(trace, dict) or trace.get("schema") != SCHEMA:
        raise ValueError("Unsupported chaos trace")
    source = trace.get("source") or {}
    count, device = source.get("world_count"), source.get("device")
    if type(count) is not int or not 2 <= count <= 512:
        raise ValueError("Recorded world_count must be an integer in 2-512")
    if device not in ("cpu", "cuda:0"):
        raise ValueError("Unsupported recorded device")
    expected = {
        "engine": "newton", "engine_version": "1.6.0", "warp_version": "1.17.0",
        "solver": "SolverXPBD", "device": device, "world_count": count,
        "substeps": SUBSTEPS, "timestep": 1/(FPS*SUBSTEPS),
        "gravity_m_s2": [0, 0, -9.81], "initial_velocity": "zero",
        "world_isolation": "ModelBuilder.begin_world/end_world",
        "scene": "double_pendulum_release_sweep",
    }
    if {k: v for k, v in source.items() if k != "device_name"} != expected \
            or trace.get("worlds") != worlds(count):
        raise ValueError("Chaos release provenance mismatch")
    if trace.get("fps") != FPS or trace.get("link_size_m") != SIZE or trace.get("anchor_m") != ANCHOR:
        raise ValueError("Unsupported chaos geometry or clock")
    if trace.get("units") != {"position": "m", "time": "s", "quaternion": "xyzw", "up_axis": "Z"}:
        raise ValueError("Unsupported chaos units")
    frames = trace.get("frames")
    if not isinstance(frames, list) or not 2 <= len(frames) <= 601:
        raise ValueError("Expected 2–601 source samples")
    for i, frame in enumerate(frames):
        if not isinstance(frame, dict) or type(frame.get("frame")) is not int or frame["frame"] != i:
            raise ValueError("Nonsequential chaos sample")
        time = frame.get("sim_time")
        if type(time) not in (int, float) or not math.isfinite(time) or abs(time-i/FPS) > 1e-9:
            raise ValueError("Chaos timestamp mismatch")
        poses = frame.get("poses")
        if not isinstance(poses, list) or len(poses) != 2*count:
            raise ValueError("Missing chaos poses")
        for pose in poses:
            if not isinstance(pose, list) or len(pose) != 7 or not all(
                type(v) in (int, float) and math.isfinite(v) for v in pose
            ):
                raise ValueError("Invalid chaos pose")
            if abs(sum(v*v for v in pose[3:])-1) > 1e-5:
                raise ValueError("Unnormalized chaos quaternion")
    # Validate the declared perturbation against actual initial geometry.
    for world in trace["worlds"]:
        angle = world["release_angle_rad"]
        for link in range(2):
            pose = frames[0]["poses"][world["id"]*2+link]
            for local in ([-.8, 0, 0], [0, 0, 0], [.8, 0, 0]):
                length = .8 + 1.6*link + local[0]
                expected_point = [length*math.cos(angle), 0, 3.8-length*math.sin(angle)]
                if math.dist(point(pose, local), expected_point) > 2e-6:
                    raise ValueError("Initial poses differ from the declared release")
    result = measure(trace)
    if result["max_anchor_error_m"] > .01 or result["max_joint_error_m"] > .01:
        raise ValueError("Pendulum constraint drift exceeds 1 cm")
    if trace.get("summary") != result:
        raise ValueError("Chaos metrics differ from the recorded poses")
    return result


def export_viewer(trace, destination):
    validate_trace(trace)
    template = Path(__file__).with_name("chaos.html").read_text()
    payload = json.dumps(trace, separators=(",", ":"), allow_nan=False).replace("<", "\\u003c")
    Path(destination).write_text(template.replace("__TRACE__", payload))


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_manifest(output):
    output = Path(output)
    (output/"manifest.json").write_text(json.dumps({
        "schema": SCHEMA, "files": {name: digest(output/name) for name in FILES},
    }, indent=2) + "\n")


def verify(output):
    output = Path(output)
    manifest = json.loads((output/"manifest.json").read_text())
    if manifest.get("schema") != SCHEMA or set(manifest.get("files", {})) != set(FILES):
        raise ValueError("Incomplete chaos manifest")
    for name in FILES:
        if digest(output/name) != manifest["files"][name]:
            raise ValueError(f"Chaos hash mismatch: {name}")
    trace = json.loads((output/"trace.json").read_text())
    result = validate_trace(trace)
    html = (output/"index.html").read_text()
    marker = '<script id="chaos-data" type="application/json">'
    if html.count(marker) != 1:
        raise ValueError("Missing chaos browser data")
    embedded = json.loads(html.split(marker, 1)[1].split("</script>", 1)[0])
    if embedded != trace:
        raise ValueError("Chaos browser data differs from the source")
    return result


def record(output, seconds=20, world_count=WORLD_COUNT, device="cpu"):
    if (
        type(seconds) not in (int, float) or not math.isfinite(seconds)
        or not 1/FPS <= seconds <= 20 or abs(seconds*FPS-round(seconds*FPS)) > 1e-8
    ):
        raise ValueError("Duration must contain 1–600 whole 30 Hz intervals")
    if type(world_count) is not int or not 2 <= world_count <= 512:
        raise ValueError("Choose 2-512 worlds")
    if device not in ("cpu", "cuda:0"):
        raise ValueError("Choose cpu or cuda:0")
    output = Path(output)
    if output.exists() and any(output.iterdir()):
        raise ValueError("Output is not empty; choose a fresh directory")
    from importlib.metadata import version
    import newton
    import warp as wp
    from .chaos_usd import export_usd, check_usd

    if version("newton") != "1.6.0" or version("warp-lang") != "1.17.0":
        raise ValueError("Use newton==1.6.0 and warp-lang==1.17.0")
    wp.init()
    selected = wp.get_device(device)
    device_name = str(getattr(selected, "name", selected))
    with wp.ScopedDevice(selected):
        builder = newton.ModelBuilder(gravity=(0, 0, -9.81))
        for world in worlds(world_count):
            builder.begin_world(label=f"world_{world['id']:02}")
            links = [builder.add_link(label=f"w{world['id']:02}_{name}") for name in ("upper", "lower")]
            for link in links:
                builder.add_shape_box(link, hx=.8, hy=.09, hz=.09)
            joints = [
                builder.add_joint_revolute(
                    -1, links[0], axis=(0, 1, 0),
                    parent_xform=wp.transform(p=ANCHOR, q=wp.quat_from_axis_angle(
                        wp.vec3(0, 1, 0), world["release_angle_rad"])),
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
            builder.add_articulation(joints, label=f"pendulum_{world['id']:02}")
            builder.end_world()
        model = builder.finalize()
        if model.world_count != world_count:
            raise ValueError("Newton did not create the requested isolated worlds")
        current, next_state = model.state(), model.state()
        control = model.control()
        solver = newton.solvers.SolverXPBD(model)
        pipeline = newton.CollisionPipeline(model)
        contacts = pipeline.contacts()
        newton.eval_fk(model, model.joint_q, model.joint_qd, current)
        frames = []
        for i in range(round(seconds*FPS)+1):
            frames.append({"frame": i, "sim_time": i/FPS, "poses": current.body_q.numpy().tolist()})
            if i == round(seconds*FPS):
                break
            for _ in range(SUBSTEPS):
                current.clear_forces()
                pipeline.collide(current, contacts)
                solver.step(current, next_state, control, contacts, 1/(FPS*SUBSTEPS))
                current, next_state = next_state, current
    trace = {
        "schema": SCHEMA, "fps": FPS, "link_size_m": SIZE, "anchor_m": ANCHOR,
        "units": {"position": "m", "time": "s", "quaternion": "xyzw", "up_axis": "Z"},
        "source": {
            "engine": "newton", "engine_version": version("newton"), "warp_version": version("warp-lang"),
            "solver": "SolverXPBD", "device": device, "world_count": world_count,
            "device_name": device_name,
            "substeps": SUBSTEPS, "timestep": 1/(FPS*SUBSTEPS),
            "gravity_m_s2": [0, 0, -9.81], "initial_velocity": "zero",
            "world_isolation": "ModelBuilder.begin_world/end_world",
            "scene": "double_pendulum_release_sweep",
        },
        "worlds": worlds(world_count), "frames": frames,
    }
    trace["summary"] = measure(trace)
    validate_trace(trace)
    output.mkdir(parents=True, exist_ok=True)
    (output/"trace.json").write_text(json.dumps(trace, separators=(",", ":"), allow_nan=False) + "\n")
    export_viewer(trace, output/"index.html")
    export_usd(trace, output/"scene.usdc")
    usd_report = check_usd(trace, output/"scene.usdc")
    (output/"usd-check.json").write_text(json.dumps(usd_report, indent=2) + "\n")
    write_manifest(output)
    return verify(output)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("artifacts/chaos"))
    parser.add_argument("--seconds", type=float, default=20)
    parser.add_argument("--worlds", type=int, default=WORLD_COUNT, help="2-512 isolated worlds")
    parser.add_argument("--device", default="cpu", choices=("cpu", "cuda:0"))
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--check-usd", action="store_true")
    args = parser.parse_args()
    if args.check_usd and not args.verify:
        parser.error("--check-usd applies to --verify")
    try:
        result = (verify(args.output) if args.verify
                  else record(args.output, args.seconds, args.worlds, args.device))
        if args.check_usd:
            from .chaos_usd import check_usd
            result["usd"] = check_usd(json.loads((args.output/"trace.json").read_text()), args.output/"scene.usdc")
        print(json.dumps(result, indent=2))
    except (ValueError, OSError, KeyError, TypeError, ImportError) as exc:
        parser.exit(1, f"Chaos bundle error: {exc}\n")


if __name__ == "__main__":
    main()
