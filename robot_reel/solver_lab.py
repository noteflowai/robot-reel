"""Verify and export the recorded Genesis/Newton timestep experiment."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import tempfile
import zipfile

SCHEMA = "robot-reel-solver-lab-1"
FPS = 30
SAMPLES = 61
SUBSTEPS = (1, 4, 16)
ENGINES = {"genesis": "1.4.1", "newton": "1.6.0"}
SCENE = {
    "name": "ballistic-flight", "gravity_m_s2": [0, 0, -9.81],
    "initial_position_m": [0, 0, 1], "initial_velocity_m_s": [2, 0, 10],
    "mass_kg": 1, "radius_m": 0.1, "collisions": False, "drag": False,
    "angular_velocity_rad_s": [0, 0, 0],
}
IDS = tuple(f"{engine}-{n}" for engine in ENGINES for n in SUBSTEPS)
FILES = (
    "lab.json", "index.html", "METHODS.md", "LICENSE", "scene.usda", "native-check.json",
    *(f"{name}.json" for name in IDS),
    *(f"genesis-{n}.{ext}" for n in SUBSTEPS for ext in ("gs", "gstraj")),
)
MAX_FILE = 20 * 1024 * 1024


def digest(data):
    return hashlib.sha256(data).hexdigest()


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON key")
        result[key] = value
    return result


def decode(data):
    def reject(value):
        raise ValueError(f"Non-finite JSON number: {value}")
    return json.loads(data, object_pairs_hook=_pairs, parse_constant=reject)


def read(root, name):
    path = Path(root) / name
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError(f"Symlink in input path: {name}")
    if not path.is_file() or path.stat().st_size > MAX_FILE:
        raise ValueError(f"Missing, non-regular or oversized file: {name}")
    with path.open("rb") as stream:
        data = stream.read(MAX_FILE + 1)
    if len(data) > MAX_FILE:
        raise ValueError(f"Oversized file: {name}")
    return data


def analytic(time):
    return {
        "position_m": [2 * time, 0, 1 + 10 * time - 9.81 * time * time / 2],
        "velocity_m_s": [2, 0, 10 - 9.81 * time],
    }


def metrics(run):
    rows = []
    for frame in run["frames"]:
        exact = analytic(frame["time_s"])
        position, velocity = frame["position_m"], frame["velocity_m_s"]
        rows.append({
            "position_error_m": math.dist(position, exact["position_m"]),
            "velocity_error_m_s": math.dist(velocity, exact["velocity_m_s"]),
            "specific_energy_drift_j_kg": (
                sum(v * v for v in velocity) / 2 + 9.81 * position[2] - 61.81
            ),
        })
    return {
        "max_position_error_m": max(row["position_error_m"] for row in rows),
        "max_velocity_error_m_s": max(row["velocity_error_m_s"] for row in rows),
        "max_abs_specific_energy_drift_j_kg": max(
            abs(row["specific_energy_drift_j_kg"]) for row in rows),
        "final_position_error_m": rows[-1]["position_error_m"],
        "samples": rows,
    }


def validate_run(run, identity):
    engine, n = identity.split("-")
    n = int(n)
    if (not isinstance(run, dict) or run.get("schema") != SCHEMA
            or run.get("id") != identity or run.get("scene") != SCENE
            or run.get("engine") != engine or run.get("engine_version") != ENGINES[engine]
            or type(run.get("substeps")) is not int or run["substeps"] != n
            or run.get("dt_s") != 1 / (FPS * n) or run.get("fps") != FPS):
        raise ValueError(f"Scene, engine or clock mismatch: {identity}")
    source = run.get("source", {})
    if (not isinstance(source, dict) or source.get("device") != "cuda:0" or source.get("precision") != "float32"
            or source.get("solver") != {"genesis": "RigidSolver/Euler", "newton": "SolverXPBD"}[engine]
            or not isinstance(source.get("gpu"), str) or not source["gpu"]
            or not isinstance(source.get("versions"), dict) or not source["versions"]):
        raise ValueError(f"Missing recording provenance: {identity}")
    mass = run.get("measured_mass_kg")
    if type(mass) not in (int, float) or not math.isfinite(mass) or abs(mass - 1) > 1e-5:
        raise ValueError(f"Unexpected measured mass: {identity}")
    frames = run.get("frames")
    if not isinstance(frames, list) or len(frames) != SAMPLES:
        raise ValueError(f"Expected all {SAMPLES} samples: {identity}")
    for i, frame in enumerate(frames):
        if (not isinstance(frame, dict)
                or set(frame) != {"sample", "time_s", "position_m", "velocity_m_s"}
                or type(frame["sample"]) is not int or frame["sample"] != i
                or type(frame["time_s"]) not in (float, int) or frame["time_s"] != i / FPS):
            raise ValueError(f"Invalid source clock: {identity}/{i}")
        for key in ("position_m", "velocity_m_s"):
            values = frame[key]
            if not isinstance(values, list) or len(values) != 3 or not all(
                type(v) in (int, float) and math.isfinite(v) and abs(v) < 100 for v in values
            ):
                raise ValueError(f"Invalid state vector: {identity}/{i}")
    for key, expected in (("position_m", SCENE["initial_position_m"]),
                          ("velocity_m_s", SCENE["initial_velocity_m_s"])):
        if math.dist(frames[0][key], expected) > 1e-6:
            raise ValueError(f"Initial state differs: {identity}")
    return metrics(run)


def make_lab(runs):
    if not isinstance(runs, list) or len(runs) != len(IDS):
        raise ValueError("Expected all six runs")
    measured = {identity: validate_run(run, identity) for identity, run in zip(IDS, runs)}
    return {"schema": SCHEMA, "scene": SCENE, "fps": FPS, "runs": runs, "metrics": measured}


def verify(root, *, check_archive=True):
    root = Path(root)
    manifest = decode(read(root, "manifest.json"))
    if (not isinstance(manifest, dict) or manifest.get("schema") != SCHEMA
            or not isinstance(manifest.get("files"), dict) or set(manifest["files"]) != set(FILES)):
        raise ValueError("Unexpected experiment inventory")
    data = {name: read(root, name) for name in FILES}
    for name, content in data.items():
        if manifest["files"][name] != {"sha256": digest(content), "bytes": len(content)}:
            raise ValueError(f"File hash or size mismatch: {name}")
    runs = [decode(data[f"{identity}.json"]) for identity in IDS]
    lab = make_lab(runs)
    if decode(data["lab.json"]) != lab:
        raise ValueError("Derived metrics or lab payload differs from source runs")
    marker = '<script id="lab-data" type="application/json">'
    html = data["index.html"].decode("utf-8")
    if html.count(marker) != 1 or decode(html.split(marker)[1].split("</script>", 1)[0]) != lab:
        raise ValueError("Browser payload differs from source runs")
    native = decode(data["native-check.json"])
    native_files = ("scene.usda", *(f"genesis-{n}.gstraj" for n in SUBSTEPS),
                    *(f"genesis-{n}.gs" for n in SUBSTEPS),
                    *(f"{identity}.json" for identity in IDS))
    if (not isinstance(native, dict) or native.get("schema") != SCHEMA
            or native.get("inputs") != {name: digest(data[name]) for name in native_files}
            or native.get("usd_samples_checked") != SAMPLES * len(IDS)
            or native.get("genesis_replay_samples_checked") != SAMPLES * 3
            or native.get("genesis_exact_replay") is not True):
        raise ValueError("Native readback receipt does not match source files")
    if check_archive and (root / "experiment.zip").exists():
        read(root, "experiment.zip")  # Enforce regular-file and byte limits before opening.
        with zipfile.ZipFile(root / "experiment.zip") as archive:
            names = (*FILES, "manifest.json")
            if len(archive.infolist()) != len(names) or set(archive.namelist()) != set(names):
                raise ValueError("Unexpected offline archive inventory")
            for name in names:
                original = read(root, name)
                if archive.getinfo(name).file_size != len(original) or archive.read(name) != original:
                    raise ValueError(f"Offline archive differs: {name}")
    return {"verified": True, "runs": len(IDS), "samples": SAMPLES * len(IDS),
            "native_readback_reexecuted": False,
            "max_position_error_m": {k: v["max_position_error_m"] for k, v in lab["metrics"].items()}}


def seal(root):
    root = Path(root)
    files = {}
    for name in FILES:
        data = read(root, name)
        files[name] = {"sha256": digest(data), "bytes": len(data)}
    (root / "manifest.json").write_text(json.dumps({"schema": SCHEMA, "files": files}, indent=2) + "\n")
    verify(root, check_archive=False)
    # Stable metadata makes identical experiment inputs produce identical archives.
    with zipfile.ZipFile(root / "experiment.zip", "w", zipfile.ZIP_DEFLATED) as archive:
        for name in (*FILES, "manifest.json"):
            info = zipfile.ZipInfo(name, (2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, read(root, name))


def export(source, destination):
    source, destination = Path(source).absolute(), Path(destination).absolute()
    if any(p.is_symlink() for p in (source, *source.parents, destination, *destination.parents)):
        raise ValueError("Output path cannot contain symlinks")
    source, destination = source.resolve(), destination.resolve()
    if destination == source or destination.is_relative_to(source) or source.is_relative_to(destination):
        raise ValueError("Output overlaps source")
    if destination.exists() and (not destination.is_dir() or any(destination.iterdir())):
        raise ValueError("Choose an empty output directory")
    verify(source)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=destination.parent, prefix=".solver-lab-") as temporary:
        stage = Path(temporary) / "lab"
        stage.mkdir()
        for name in FILES:
            (stage / name).write_bytes(read(source, name))
        lab = decode(read(stage, "lab.json"))
        template = Path(__file__).with_name("solver_lab.html").read_text()
        (stage / "index.html").write_text(template.replace(
            "__LAB_DATA__", json.dumps(lab, separators=(",", ":"), allow_nan=False).replace("<", "\\u003c")))
        seal(stage)
        if destination.exists():
            destination.rmdir()
        stage.rename(destination)
    return verify(destination)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--verify", action="store_true")
    mode.add_argument("--export-from", type=Path)
    parser.add_argument("--check-usd", action="store_true", help="Read every USD sample again (usd-core required)")
    args = parser.parse_args(argv)
    if args.check_usd and not args.verify:
        parser.error("--check-usd requires --verify")
    try:
        result = verify(args.output) if args.verify else export(args.export_from, args.output)
        if args.check_usd:
            from .solver_usd import check
            result["usd_samples_checked"] = check(args.output)
        print(json.dumps(result, indent=2))
        return 0
    except (ValueError, OSError, KeyError, TypeError, ImportError, RuntimeError, zipfile.BadZipFile) as exc:
        print(json.dumps({"verified": False, "error": str(exc)}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
