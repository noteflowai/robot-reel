"""Record one pinned engine's three ballistic flights on CUDA; never render fake frames."""
from __future__ import annotations

import argparse
from importlib.metadata import version
import json
import math
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from robot_reel.solver_lab import ENGINES, FPS, SAMPLES, SCENE, SCHEMA, SUBSTEPS, digest, validate_run


def record_newton(output):
    import newton
    import warp as wp

    wp.init()
    device = wp.get_device("cuda:0")
    if not device.is_cuda:
        raise RuntimeError("A CUDA device is required")
    with wp.ScopedDevice(device):
        for n in SUBSTEPS:
            builder = newton.ModelBuilder(gravity=(0, 0, -9.81))
            # A free body is sufficient: contact geometry is deliberately absent.
            builder.add_body(
                xform=wp.transform(wp.vec3(0, 0, 1), wp.quat_identity()), mass=1,
                inertia=wp.mat33(.004, 0, 0, 0, .004, 0, 0, 0, .004), label="projectile")
            model = builder.finalize()
            current, following = model.state(), model.state()
            current.body_qd.assign([[2, 0, 10, 0, 0, 0]])
            control = model.control()
            solver = newton.solvers.SolverXPBD(model, angular_damping=0)
            frames = []
            for i in range(SAMPLES):
                frames.append({
                    "sample": i, "time_s": i / FPS,
                    "position_m": current.body_q.numpy()[0, :3].tolist(),
                    "velocity_m_s": current.body_qd.numpy()[0, :3].tolist(),
                })
                if i != SAMPLES - 1:
                    for _ in range(n):
                        current.clear_forces()
                        solver.step(current, following, control, None, 1 / (FPS * n))
                        current, following = following, current
            save(output, "newton", n, frames, float(model.body_mass.numpy()[0]),
                 "SolverXPBD", {"newton": version("newton"), "warp-lang": version("warp-lang")},
                 device.name)


def record_genesis(output):
    import genesis as gs
    import torch

    if not torch.cuda.is_available():
        raise RuntimeError("A CUDA device is required")
    gs.init(backend=gs.gpu, precision="32", seed=0, logging_level="warning")
    for n in SUBSTEPS:
        scene = gs.Scene(
            sim_options=gs.options.SimOptions(dt=1 / FPS, substeps=n, gravity=(0, 0, -9.81)),
            rigid_options=gs.options.RigidOptions(
                integrator=gs.integrator.Euler, enable_collision=False),
            show_viewer=False,
        )
        body = scene.add_entity(
            gs.morphs.Sphere(radius=.1, pos=(0, 0, 1)),
            material=gs.materials.Rigid(rho=1 / (4 * math.pi * .1 ** 3 / 3)),
            name="projectile")
        native = output / f"genesis-{n}.gstraj"
        scene.start_recording(gs.recorders.TrajectoryFile(filename=str(native), exact=True))
        scene.build()
        body.set_dofs_velocity([2, 0, 10, 0, 0, 0])
        scene.export(output / f"genesis-{n}.gs")
        frames = []
        for i in range(SAMPLES):
            frames.append({
                "sample": i, "time_s": i / FPS,
                "position_m": body.get_pos().tolist(), "velocity_m_s": body.get_vel().tolist(),
            })
            if i != SAMPLES - 1:
                scene.step()
        scene.stop_recording()
        save(output, "genesis", n, frames, body.get_mass().item(), "RigidSolver/Euler",
             {name: version(name) for name in ("genesis-world", "quadrants", "torch")},
             torch.cuda.get_device_name(0))
        check_genesis(output, n)


def check_genesis(output, n):
    import genesis as gs
    # Read back the actual native archive through the upstream public API.
    paths = [output / f"genesis-{n}.{ext}" for ext in ("json", "gs", "gstraj")]
    hashes = {p.name: digest(p.read_bytes()) for p in paths}
    frames = json.loads(paths[0].read_text())["frames"]
    replay = gs.Scene.load_trajectory(paths[2], show_viewer=False)
    if not replay.is_exact or len(replay) != SAMPLES:
        raise ValueError(f"Unexpected native trajectory inventory: {len(replay)}")
    for i, frame in enumerate(frames):
        replay.seek(i)
        restored = replay.scene.entities[0]
        if (restored.get_pos().tolist() != frame["position_m"]
                or restored.get_vel().tolist() != frame["velocity_m_s"]
                or abs(replay.time(i).item() - i / FPS) > 1e-6):
            raise ValueError(f"Genesis native replay mismatch: {n}/{i}")
    (output / f"genesis-{n}-readback.json").write_text(json.dumps({
        "samples": SAMPLES, "exact": True, "positions_and_velocities_equal": True,
        "inputs": hashes,
    }, indent=2) + "\n")


def save(output, engine, n, frames, mass, solver, versions, gpu):
    run = {
        "schema": SCHEMA, "id": f"{engine}-{n}", "engine": engine,
        "engine_version": ENGINES[engine], "fps": FPS, "substeps": n,
        "dt_s": 1 / (FPS * n), "scene": SCENE, "measured_mass_kg": mass,
        "source": {
            "solver": solver, "device": "cuda:0", "precision": "float32",
            "gpu": gpu, "versions": versions,
            "driver": subprocess.check_output([
                "nvidia-smi", "--query-gpu=driver_version", "--format=csv,noheader"
            ], text=True).splitlines()[0],
        },
        "frames": frames,
    }
    measured = validate_run(run, run["id"])
    (output / f"{run['id']}.json").write_text(json.dumps(run, indent=2, allow_nan=False) + "\n")
    print(json.dumps({"run": run["id"], "max_position_error_m": measured["max_position_error_m"]}),
          flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine", choices=tuple(ENGINES), required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--verify-native", action="store_true", help="Reopen existing Genesis native trajectories")
    args = parser.parse_args()
    if version({"genesis": "genesis-world", "newton": "newton"}[args.engine]) != ENGINES[args.engine]:
        parser.error("Install the pinned engine version before recording")
    if args.verify_native:
        if args.engine != "genesis":
            parser.error("--verify-native applies to Genesis")
        import genesis as gs
        gs.init(backend=gs.gpu, precision="32", logging_level="warning")
        for n in SUBSTEPS:
            check_genesis(args.output, n)
        print("All 183 Genesis native positions, velocities and clocks verified.")
        raise SystemExit(0)
    if args.output.exists() and any(args.output.iterdir()):
        parser.error("Choose a fresh output directory")
    args.output.mkdir(parents=True, exist_ok=True)
    {"genesis": record_genesis, "newton": record_newton}[args.engine](args.output)
