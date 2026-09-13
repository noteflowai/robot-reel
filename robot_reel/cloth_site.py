"""Export an existing, checked cloth recording without rerunning its physics."""
from importlib.resources import files
import json
import math
from pathlib import Path
import shutil
import tempfile
import zipfile

from .cloth import FILES, digest, export_viewer, load, verify, write_manifest

ARCHIVED = (*FILES, "manifest.json", "usd-check.json", "blender-check.json", "METHODS.md", "LICENSE")
SOURCES = (*FILES[:4], "usd-check.json", "blender-check.json")


def check_reports(bundle):
    """Check saved native reports against source hashes, without importing USD."""
    bundle = Path(bundle)
    result = verify(bundle)
    trace, _, _ = load(bundle)
    for name in ("usd", "blender"):
        report = json.loads((bundle/f"{name}-check.json").read_text())
        hashes = [("positions_sha256", "positions.f32"), ("usd_sha256", "scene.usdc")]
        hashes.append(("trace_sha256", "trace.json") if name == "blender"
                      else ("velocities_sha256", "velocities.f32"))
        for key, filename in hashes:
            if report.get(key) != digest(bundle/filename):
                raise ValueError(f"{name} report belongs to different {filename}")
        error = report.get("maximum_position_error_m")
        tolerance = 1e-5 if name == "blender" else 1e-7
        if (type(report.get("checked_vertex_samples")) is not int
                or report["checked_vertex_samples"] != result["vertex_samples"]
                or type(error) not in (int, float) or not math.isfinite(error) or not 0 <= error < tolerance):
            raise ValueError(f"Incomplete {name} cloth readback")
        if name == "blender":
            expected = {"fps": trace["fps"], "frame_start": 1, "frame_end": trace["frame_count"]}
            if any(type(report.get(k)) is not int or report[k] != v for k, v in expected.items()):
                raise ValueError("Blender cloth clock mismatch")
            if not isinstance(report.get("blender_version"), str) or not report["blender_version"]:
                raise ValueError("Missing Blender version")
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


def build(bundle, destination, *, check_native=False):
    """Write a fresh export atomically; saved reports are preserved, not regenerated.

    Optional native readback checks the existing USD before any output is created.
    Rebuilding the viewer never changes source positions, velocities or the scene.
    """
    bundle, destination = Path(bundle).resolve(), Path(destination)
    target = destination.resolve()
    if destination.is_symlink() or target.is_relative_to(bundle) or bundle.is_relative_to(target):
        raise ValueError("Cloth input and output directories must be separate")
    if destination.exists() and (not destination.is_dir() or any(destination.iterdir())):
        raise ValueError("Cloth export output is not empty; choose a fresh directory")
    check_reports(bundle)
    if check_native:
        from .cloth_usd import check_usd
        check_usd(*load(bundle), bundle/"scene.usdc")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".cloth-export-", dir=destination.parent) as temporary:
        staging = Path(temporary)/"site"
        staging.mkdir()
        for name in SOURCES:
            shutil.copyfile(bundle/name, staging/name)
        export_viewer(*load(staging), staging/"index.html", archive=True)
        write_manifest(staging)
        resources = files("robot_reel").joinpath("resources", "cloth")
        for source, name in (("METHODS.txt", "METHODS.md"), ("LICENSE.txt", "LICENSE")):
            (staging/name).write_bytes(resources.joinpath(source).read_bytes())
        with zipfile.ZipFile(staging/"experiment.zip", "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
            for name in ARCHIVED:
                archive.write(staging/name, name)
        result = verify_site(staging)
        # Removing an empty placeholder also permits the final rename on Windows.
        # rmdir refuses to remove a directory if another writer populated it.
        if destination.is_dir():
            destination.rmdir()
        staging.replace(destination)
    return result
