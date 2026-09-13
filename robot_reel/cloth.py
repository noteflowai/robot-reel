"""Record and verify three independent Newton cloth bending experiments."""
from __future__ import annotations

import argparse
from array import array
import base64
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import sys

SCHEMA = "robot-reel-cloth-1"
FPS, SUBSTEPS, ITERATIONS = 30, 10, 10
NX, NY, VERTICES = 12, 8, 117
CASES = [
    {"id": "bend_001", "edge_ke": .01, "color": "#79dfc3"},
    {"id": "bend_1", "edge_ke": 1., "color": "#ffca85"},
    {"id": "bend_100", "edge_ke": 100., "color": "#c1b1ff"},
]
SETUP = {
    "grid_cells": [NX, NY], "cell_size_m": [.08, .08],
    "origin_m": [0, 0, 1.5], "free_vertex_mass_kg": .01,
    "fixed_columns": [0, 1], "gravity_m_s2": [0, 0, -9.81],
    "tri_ke": 10000., "tri_ka": 10000., "tri_kd": .02,
    "edge_kd": .01, "particle_radius_m": .005,
    "contacts": False, "self_contact": False, "tile_solve": False,
    "substeps": SUBSTEPS, "iterations": ITERATIONS, "timestep_s": 1/(FPS*SUBSTEPS),
}
FILES = ("trace.json", "positions.f32", "velocities.f32", "scene.usdc", "index.html")
PINS = [i for i in range(VERTICES) if i % (NX+1) < 2]
FREE_EDGE = [i for i in range(VERTICES) if i % (NX+1) == NX]


def topology():
    faces = []
    for y in range(1, NY+1):
        for x in range(1, NX+1):
            a, b, c, d = (y-1)*(NX+1)+x-1, (y-1)*(NX+1)+x, y*(NX+1)+x, y*(NX+1)+x-1
            faces.extend([[a, b, d], [b, c, d]])
    return faces


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def floats(raw, count):
    if len(raw) != count*4:
        raise ValueError("Float32 byte count does not match the recording shape")
    values = array("f")
    values.frombytes(raw)
    if sys.byteorder != "little":
        values.byteswap()
    if not all(math.isfinite(v) for v in values):
        raise ValueError("Nonfinite recorded float32 value")
    return values


def vertex(values, frame, case, index):
    start = ((frame*len(CASES)+case)*VERTICES+index)*3
    return values[start:start+3]


def validate(trace, positions, velocities):
    """Validate source bytes and recompute diagnostics with only the stdlib.

    This verifies internal agreement, not authenticity or material calibration.
    """
    if not isinstance(trace, dict) or trace.get("schema") != SCHEMA:
        raise ValueError("Unsupported cloth schema")
    # JSON equality alone would accept True as 1; compare typed JSON here.
    for key, expected in (
        ("cases", CASES), ("setup", SETUP), ("triangles", topology()),
        ("pinned_vertices", PINS), ("free_edge_vertices", FREE_EDGE),
        ("fps", FPS), ("vertex_count", VERTICES),
        ("storage", {"dtype": "<f4", "axes": ["frame", "case", "vertex", "xyz"]}),
        ("units", {"position": "m", "velocity": "m/s", "time": "s", "up_axis": "Z"}),
        ("clock", {"initial_sample": 0, "usd_frame_offset": 1}),
    ):
        if json.dumps(trace.get(key), sort_keys=True) != json.dumps(expected, sort_keys=True):
            raise ValueError(f"Cloth contract mismatch: {key}")
    count = trace.get("frame_count")
    if type(count) is not int or not 2 <= count <= 301:
        raise ValueError("Expected 2–301 cloth samples")
    source = trace.get("source", {})
    if not isinstance(source, dict) or any(source.get(k) != v for k, v in {
        "engine": "newton", "engine_version": "1.6.0", "warp_version": "1.17.0",
        "solver": "SolverVBD", "mode": "physics", "execution": "direct_launches",
        "independent_cases": True,
    }.items()) or type(source.get("independent_cases")) is not bool:
        raise ValueError("Cloth source mismatch")
    if source.get("device") not in ("cpu", "cuda:0"):
        raise ValueError("Unsupported recorded device")
    for key in ("device_name", "recorded_at", "usd_version", "recorder_sha256"):
        if not isinstance(source.get(key), str) or not source[key]:
            raise ValueError(f"Missing source {key}")
    q = floats(positions, count*len(CASES)*VERTICES*3)
    v = floats(velocities, len(q))
    for case in range(len(CASES)):
        for i in range(VERTICES):
            expected = [(i % (NX+1))*.08, (i//(NX+1))*.08, 1.5]
            if math.dist(vertex(q, 0, case, i), expected) > 1e-7 or any(vertex(v, 0, case, i)):
                raise ValueError("Initial state differs from the common stationary grid")
    result = measurements(trace, q, v)
    if result["max_pin_error_m"] > 1e-7:
        raise ValueError("Fixed cloth vertices moved")
    for frame in range(count):
        for case in range(len(CASES)):
            if any(any(vertex(v, frame, case, i)) for i in PINS):
                raise ValueError("Fixed cloth vertices have nonzero velocity")
    # Python equality accepts False as 0; a boolean would break numeric browser
    # formatting despite appearing to match the measured summary.
    if json.dumps(trace.get("summary"), sort_keys=True, allow_nan=False) != json.dumps(result, sort_keys=True):
        raise ValueError("Cloth summary differs from recorded vertex data")
    return result


def measurements(trace, q, velocities):
    edges = sorted({tuple(sorted((face[i], face[(i+1) % 3]))) for face in topology() for i in range(3)})
    count = trace["frame_count"]
    cases, max_pin = [], 0.
    peak = {"frame": 0, "case": 0, "rms_m": 0.}
    for c in range(len(CASES)):
        drops, rms, peak_speed, min_ratio, max_ratio = [], [], 0., math.inf, 0.
        rest = [math.dist(vertex(q, 0, c, a), vertex(q, 0, c, b)) for a, b in edges]
        for f in range(count):
            points = [vertex(q, f, c, i) for i in range(VERTICES)]
            drops.append(1.5-sum(points[i][2] for i in FREE_EDGE)/len(FREE_EDGE))
            rms.append(math.sqrt(sum(math.dist(points[i], vertex(q, f, 0, i))**2
                                     for i in range(VERTICES))/VERTICES))
            if rms[-1] > peak["rms_m"]:
                peak = {"frame": f, "case": c, "rms_m": rms[-1]}
            max_pin = max(max_pin, *(math.dist(points[i], vertex(q, 0, c, i)) for i in PINS))
            peak_speed = max(peak_speed, *(math.hypot(*vertex(velocities, f, c, i)) for i in range(VERTICES)))
            ratios = [math.dist(points[a], points[b])/length for (a, b), length in zip(edges, rest)]
            min_ratio, max_ratio = min(min_ratio, *ratios), max(max_ratio, *ratios)
        cases.append({
            "free_edge_drop_m": drops, "rms_from_case_0_m": rms,
            "peak_vertex_speed_m_s": peak_speed, "min_edge_length_ratio": min_ratio,
            "max_edge_length_ratio": max_ratio,
        })
    return {"vertex_samples": count*len(CASES)*VERTICES, "max_pin_error_m": max_pin,
            "cases": cases, "peak": peak}


def export_viewer(trace, positions, velocities, destination, *, archive=False):
    validate(trace, positions, velocities)
    payload = {"trace": trace, "positions_base64": base64.b64encode(positions).decode("ascii")}
    data = json.dumps(payload, separators=(",", ":"), allow_nan=False).replace("<", "\\u003c")
    template = Path(__file__).with_name("cloth.html").read_text()
    Path(destination).write_text(template.replace("__CLOTH__", data).replace("__ARCHIVE_ATTR__", "" if archive else "hidden"))


def write_manifest(output):
    output = Path(output)
    (output/"manifest.json").write_text(json.dumps({
        "schema": SCHEMA, "files": {name: digest(output/name) for name in FILES},
    }, indent=2)+"\n")


def load(output):
    output = Path(output)
    return (json.loads((output/"trace.json").read_text()), (output/"positions.f32").read_bytes(),
            (output/"velocities.f32").read_bytes())


def verify(output):
    output = Path(output)
    manifest = json.loads((output/"manifest.json").read_text())
    if manifest.get("schema") != SCHEMA or set(manifest.get("files", {})) != set(FILES):
        raise ValueError("Incomplete cloth manifest")
    for name in FILES:
        if digest(output/name) != manifest["files"][name]:
            raise ValueError(f"Hash mismatch: {name}")
    trace, q, v = load(output)
    result = validate(trace, q, v)
    marker = '<script id="cloth-data" type="application/json">'
    html = (output/"index.html").read_text()
    if html.count(marker) != 1:
        raise ValueError("Missing browser cloth data")
    data = json.loads(html.split(marker, 1)[1].split("</script>", 1)[0])
    if data.get("trace") != trace or base64.b64decode(data.get("positions_base64", ""), validate=True) != q:
        raise ValueError("Browser cloth differs from source data")
    return result


def record(output, seconds=4, device="cuda:0"):
    if (type(seconds) not in (int, float) or not math.isfinite(seconds)
            or not 1/FPS <= seconds <= 10 or abs(seconds*FPS-round(seconds*FPS)) > 1e-8):
        raise ValueError("Duration must contain whole 30 Hz intervals, between 1/30 and 10 seconds")
    if device not in ("cpu", "cuda:0"):
        raise ValueError("Choose cpu or cuda:0")
    output = Path(output)
    if output.exists() and any(output.iterdir()):
        raise ValueError("Output is not empty; choose a fresh directory")
    from importlib.metadata import version
    import newton
    import numpy as np
    import warp as wp
    from .cloth_usd import export_usd, check_usd

    if version("newton") != "1.6.0" or version("warp-lang") != "1.17.0":
        raise ValueError("Cloth recording requires newton==1.6.0 and warp-lang==1.17.0")
    wp.init()
    # Requesting CUDA must fail if unavailable; never silently publish a CPU run.
    actual_device = wp.get_device(device)
    all_q, all_v = [], []
    with wp.ScopedDevice(actual_device):
        for case in CASES:
            builder = newton.ModelBuilder(gravity=-9.81)
            builder.add_cloth_grid(
                pos=wp.vec3(0, 0, 1.5), rot=wp.quat_identity(), vel=wp.vec3(0, 0, 0),
                dim_x=NX, dim_y=NY, cell_x=.08, cell_y=.08, mass=.01,
                tri_ke=SETUP["tri_ke"], tri_ka=SETUP["tri_ka"], tri_kd=SETUP["tri_kd"],
                edge_ke=case["edge_ke"], edge_kd=SETUP["edge_kd"], particle_radius=.005,
            )
            for i in PINS:
                builder.particle_mass[i] = 0.
                builder.particle_flags[i] &= ~newton.ParticleFlags.ACTIVE
            builder.color(include_bending=True)
            model = builder.finalize()
            if model.tri_indices.numpy().tolist() != topology():
                raise ValueError("Newton generated an unexpected mesh topology")
            solver = newton.solvers.SolverVBD(
                model, iterations=ITERATIONS, particle_enable_self_contact=False,
                particle_enable_tile_solve=False,
            )
            current, following, control = model.state(), model.state(), model.control()
            q, v = [], []
            for frame in range(round(seconds*FPS)+1):
                # Host copies synchronize the actual GPU result. Include the untouched initial state.
                q.append(current.particle_q.numpy().copy())
                v.append(current.particle_qd.numpy().copy())
                if frame == round(seconds*FPS):
                    break
                for _ in range(SUBSTEPS):
                    current.clear_forces()
                    solver.step(current, following, control, None, 1/(FPS*SUBSTEPS))
                    current, following = following, current
            all_q.append(q)
            all_v.append(v)
            print(f"Recorded {case['id']} on {actual_device}: {len(q)} samples", flush=True)
    positions = np.stack(all_q, axis=1).astype("<f4").tobytes()
    velocities = np.stack(all_v, axis=1).astype("<f4").tobytes()
    trace = {
        "schema": SCHEMA, "fps": FPS, "frame_count": round(seconds*FPS)+1,
        "vertex_count": VERTICES, "cases": CASES, "setup": SETUP,
        "triangles": topology(), "pinned_vertices": PINS, "free_edge_vertices": FREE_EDGE,
        "storage": {"dtype": "<f4", "axes": ["frame", "case", "vertex", "xyz"]},
        "units": {"position": "m", "velocity": "m/s", "time": "s", "up_axis": "Z"},
        "clock": {"initial_sample": 0, "usd_frame_offset": 1},
        "source": {
            "engine": "newton", "engine_version": version("newton"), "warp_version": version("warp-lang"),
            "usd_version": version("usd-core"), "solver": "SolverVBD", "mode": "physics",
            "device": str(actual_device), "device_name": actual_device.name,
            "execution": "direct_launches", "independent_cases": True,
            "recorded_at": datetime.now(timezone.utc).isoformat(), "recorder_sha256": digest(__file__),
        },
    }
    trace["summary"] = measurements(trace, floats(positions, len(positions)//4), floats(velocities, len(velocities)//4))
    validate(trace, positions, velocities)
    output.mkdir(parents=True, exist_ok=True)
    (output/"trace.json").write_text(json.dumps(trace, indent=2, allow_nan=False)+"\n")
    (output/"positions.f32").write_bytes(positions)
    (output/"velocities.f32").write_bytes(velocities)
    export_viewer(trace, positions, velocities, output/"index.html")
    export_usd(trace, positions, velocities, output/"scene.usdc")
    report = check_usd(trace, positions, velocities, output/"scene.usdc")
    (output/"usd-check.json").write_text(json.dumps(report, indent=2)+"\n")
    write_manifest(output)
    return verify(output)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("artifacts/cloth"))
    parser.add_argument("--seconds", type=float, help="New recording duration (default: 4 seconds)")
    parser.add_argument("--device", choices=("cpu", "cuda:0"), help="New recording device (default: cuda:0)")
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--verify", action="store_true")
    action.add_argument("--export-from", type=Path, metavar="BUNDLE",
                        help="Export a checked recording to a fresh --output, without new simulation")
    parser.add_argument("--check-usd", action="store_true",
                        help="Also read back the USD with its optional native dependency")
    args = parser.parse_args(argv)
    if (args.verify or args.export_from) and (args.seconds is not None or args.device is not None):
        parser.error("--seconds and --device apply only to new recordings")
    try:
        if args.export_from:
            from .cloth_site import build
            result = {
                "summary": build(args.export_from, args.output, check_native=args.check_usd),
                "exported_to": str(args.output.resolve()), "native_usd_checked": args.check_usd,
            }
        else:
            result = verify(args.output) if args.verify else record(
                args.output, 4 if args.seconds is None else args.seconds, args.device or "cuda:0")
            if args.check_usd:
                from .cloth_usd import check_usd
                result = {"summary": result, "usd": check_usd(*load(args.output), args.output/"scene.usdc")}
    except (ValueError, OSError, ImportError) as exc:
        parser.error(str(exc))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
