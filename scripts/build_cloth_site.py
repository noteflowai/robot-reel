"""Publish a native-checked cloth recording and an exact portable source bundle."""
import argparse
import json
import math
from pathlib import Path
import shutil
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from robot_reel.cloth import FILES, digest, export_viewer, load, verify, write_manifest

ARCHIVED = (*FILES, "manifest.json", "usd-check.json", "blender-check.json", "METHODS.md", "LICENSE")


def check_reports(bundle):
    bundle = Path(bundle)
    result = verify(bundle)
    trace, _, _ = load(bundle)
    for name in ("usd", "blender"):
        report = json.loads((bundle/f"{name}-check.json").read_text())
        for key, filename in (
            ("positions_sha256", "positions.f32"), ("usd_sha256", "scene.usdc"),
            *(([("trace_sha256", "trace.json")] if name == "blender" else [("velocities_sha256", "velocities.f32")])),
        ):
            if report.get(key) != digest(bundle/filename):
                raise ValueError(f"{name} report belongs to different {filename}")
        error = report.get("maximum_position_error_m")
        if (report.get("checked_vertex_samples") != result["vertex_samples"]
                or type(error) not in (int, float) or not math.isfinite(error) or not 0 <= error < 1e-5):
            raise ValueError(f"Incomplete {name} cloth readback")
        if name == "blender":
            if (report.get("fps") != trace["fps"] or report.get("frame_start") != 1
                    or report.get("frame_end") != trace["frame_count"] or not report.get("blender_version")):
                raise ValueError("Blender cloth clock mismatch")
        else:
            error = report.get("maximum_velocity_error_m_s")
            if type(error) not in (int, float) or not math.isfinite(error) or not 0 <= error < 1e-7:
                raise ValueError("USD velocity readback mismatch")
    return result


def verify_site(site):
    site = Path(site)
    result = check_reports(site)
    with zipfile.ZipFile(site/"experiment.zip") as archive:
        if sorted(archive.namelist()) != sorted(ARCHIVED):
            raise ValueError("Cloth archive members differ from its contract")
        for name in ARCHIVED:
            if archive.read(name) != (site/name).read_bytes():
                raise ValueError(f"Cloth archive differs from source: {name}")
    return result


def build(bundle, destination):
    bundle, destination = Path(bundle), Path(destination)
    check_reports(bundle)
    from robot_reel.cloth_usd import check_usd
    check_usd(*load(bundle), bundle/"scene.usdc")
    destination.mkdir(parents=True, exist_ok=True)
    for name in (*FILES[:4], "usd-check.json", "blender-check.json"):
        if (bundle/name).resolve() != (destination/name).resolve():
            shutil.copyfile(bundle/name, destination/name)
    export_viewer(*load(destination), destination/"index.html", archive=True)
    write_manifest(destination)
    shutil.copyfile(ROOT/"docs/cloth.md", destination/"METHODS.md")
    shutil.copyfile(ROOT/"LICENSE", destination/"LICENSE")
    with zipfile.ZipFile(destination/"experiment.zip", "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for name in ARCHIVED:
            archive.write(destination/name, name)
    return verify_site(destination)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--destination", type=Path, default=ROOT/"docs/cloth")
    args = parser.parse_args()
    print(json.dumps(build(args.bundle, args.destination), indent=2))
