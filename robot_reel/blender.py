"""Export verified braking recordings as an editable Blender replay."""
import argparse
import json
import math
from pathlib import Path
import shutil
import tempfile

from .compare import compatible, digest, verify_comparison
from .verify import verify, verify_trace

NOTICE = (
    "Stylized Blender replay of recorded MuJoCo samples. Geometry and lighting "
    "are illustrative. No Blender physics, driving AI or new simulation is run. "
    "The two roads are display offsets of independent 1D trials, not a shared world."
)


def scene_document(traces, labels):
    if compatible(*traces) != "braking":
        raise ValueError("Blender export currently supports the braking pack only")
    runs = []
    for i, (trace, label) in enumerate(zip(traces, labels)):
        verify_trace(trace, "scripted")
        if trace["joints"] != ["speed", "gap", "position"] or trace.get("units") != ["m/s", "m", "m"]:
            raise ValueError("Blender braking export requires speed/gap/position channels in m/s and meters")
        config = trace["config"]
        if any(type(v) not in (int, float) or not math.isfinite(v) for v in config.values()):
            raise ValueError("Vehicle configuration must contain finite numbers")
        if config["car_half_length_m"] <= 0 or config["obstacle_half_length_m"] <= 0:
            raise ValueError("Vehicle and obstacle lengths must be positive")
        for frame in trace["frames"]:
            expected_gap = (config["obstacle_x_m"] - config["obstacle_half_length_m"]
                            - config["car_half_length_m"] - frame["qpos"][2])
            if not math.isclose(frame["qpos"][1], expected_gap, rel_tol=0, abs_tol=1e-7):
                raise ValueError("Recorded gap disagrees with the vehicle geometry and position")
            if type(frame["collision"]) is not bool:
                raise ValueError("Recorded contact flags must be booleans")
        runs.append({
            "id": ("left", "right")[i], "label": label,
            "robot": trace["robot"], "lane_y": (-2.4, 2.4)[i],
            "color": ([.06, .75, .62, 1], [.96, .22, .08, 1])[i],
            "config": config, "outcome": trace["outcome"], "frames": trace["frames"],
        })
    return {
        "schema": 1, "kind": "braking", "fps": traces[0]["fps"],
        "frame_count": len(traces[0]["frames"]), "units": "meters",
        "frame_mapping": "Blender frame 1 = source frame 0; no sample at simulation time zero is invented.",
        "interpolation": "CONSTANT: hold recorded samples between frames; no motion blur.",
        "notice": NOTICE, "runs": runs,
    }


def verify_export(directory):
    directory = Path(directory)
    manifest = json.loads((directory / "blender-manifest.json").read_text())
    required = {"scene.json", "build_scene.py", "left-trace.json", "right-trace.json",
                "left-source-manifest.json", "right-source-manifest.json"}
    hashes = manifest.get("sha256", {})
    if manifest.get("schema") != 1 or set(hashes) != required:
        raise ValueError("Incomplete Blender export manifest")
    for filename, expected in hashes.items():
        if digest(directory / filename) != expected:
            raise ValueError(f"Blender export hash mismatch: {filename}")
    traces, sources = [], []
    for side in ("left", "right"):
        trace = json.loads((directory / f"{side}-trace.json").read_text())
        source = json.loads((directory / f"{side}-source-manifest.json").read_text())
        if source.get("arm_director") != "scripted":
            raise ValueError("Blender braking replay requires scripted source traces")
        if source["sha256"].get(f'{trace["robot"]}-trace.json') != digest(directory / f"{side}-trace.json"):
            raise ValueError("Blender source trace does not match its original manifest")
        traces.append(trace)
        sources.append(source)
    if sources[0]["versions"] != sources[1]["versions"]:
        raise ValueError("Blender source engine versions differ")
    document = json.loads((directory / "scene.json").read_text())
    labels = manifest.get("labels", [])
    if len(labels) != 2 or any(not isinstance(s, str) or not s.strip() or len(s) > 48 for s in labels):
        raise ValueError("Exactly two nonempty labels of at most 48 characters are required")
    if document != scene_document(traces, labels):
        raise ValueError("Blender animation disagrees with its source traces")
    return {"kind": "braking", "frames": document["frame_count"], "fps": document["fps"]}


def export_blender(source, output):
    source, output = Path(source).resolve(), Path(output).resolve()
    if output == source or source in output.parents:
        raise ValueError("Choose an output directory outside the verified source bundle")
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        raise ValueError("Blender output must be empty; choose a new directory")
    if (source / "comparison-manifest.json").exists():
        summary = verify_comparison(source)
        if summary["family"] != "braking":
            raise ValueError("Blender export currently supports the braking pack only")
        inputs = [(source / f"{s}-trace.json", source / f"{s}-source-manifest.json")
                  for s in ("left", "right")]
        labels = json.loads((source / "comparison.json").read_text())["labels"]
    else:
        summary = verify(source)
        if set(summary) != {"braking_early", "braking_late"}:
            raise ValueError("Blender export requires both braking trials")
        inputs = [(source / f"{s}-trace.json", source / "manifest.json")
                  for s in ("braking_early", "braking_late")]
        labels = ["Early brake", "Late brake"]
    traces = [json.loads(trace.read_text()) for trace, _ in inputs]
    document = scene_document(traces, labels)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".blender-export-", dir=output.parent) as temporary:
        staging = Path(temporary)
        for side, (trace, manifest) in zip(("left", "right"), inputs):
            shutil.copyfile(trace, staging / f"{side}-trace.json")
            shutil.copyfile(manifest, staging / f"{side}-source-manifest.json")
        shutil.copyfile(Path(__file__).with_name("blender_scene.py"), staging / "build_scene.py")
        (staging / "scene.json").write_text(json.dumps(document, indent=2) + "\n")
        files = sorted(p for p in staging.iterdir() if p.is_file())
        (staging / "blender-manifest.json").write_text(json.dumps({
            "schema": 1, "labels": labels, "notice": NOTICE,
            "verification_scope": "Source bundle verified at export. This bundle retains source traces and hashes, not raw videos.",
            "sha256": {p.name: digest(p) for p in files},
        }, indent=2) + "\n")
        verify_export(staging)
        shutil.copytree(staging, output, dirs_exist_ok=True)
    return document


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="Verified braking capture or comparison directory")
    parser.add_argument("--output", type=Path, help="New Blender bundle directory")
    parser.add_argument("--verify", action="store_true", help="Verify an exported bundle instead")
    args = parser.parse_args(argv)
    try:
        if args.verify:
            if args.output:
                parser.error("--verify does not accept --output")
            print(json.dumps(verify_export(args.source)))
        else:
            if not args.output:
                parser.error("--output is required when exporting")
            document = export_blender(args.source, args.output)
            print(f'Exported {document["frame_count"]} recorded samples per trial to {args.output.resolve()}')
            print("Run Blender with --background --python build_scene.py -- --bundle BUNDLE --output replay.blend")
    except (OSError, ValueError, KeyError, TypeError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
