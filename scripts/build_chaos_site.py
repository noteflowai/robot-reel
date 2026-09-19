"""Publish verified source poses, an offline viewer and a Blender-checked USD."""
import argparse
import json
import math
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from robot_reel.chaos import digest, export_viewer, verify, write_manifest


def check_report(bundle):
    bundle = Path(bundle)
    measured = verify(bundle)
    trace = json.loads((bundle/"trace.json").read_text())
    report = json.loads((bundle/"blender-check.json").read_text())
    for field, name in (("trace_sha256", "trace.json"), ("usd_sha256", "scene.usdc")):
        if report.get(field) != digest(bundle/name):
            raise ValueError(f"Blender report belongs to a different {name}")
    error = report.get("maximum_transform_error_m")
    if (
        report.get("checked_body_samples") != measured["body_samples"]
        or report.get("frame_start") != 1 or report.get("frame_end") != len(trace["frames"])
        or report.get("fps") != trace["fps"]
        or type(error) not in (int, float) or not math.isfinite(error) or not 0 <= error < 1e-5
        or not isinstance(report.get("blender_version"), str)
    ):
        raise ValueError("Incomplete chaos Blender check")
    usd = json.loads((bundle/"usd-check.json").read_text())
    usd_error = usd.get("maximum_transform_error_m")
    if (
        usd.get("usd_sha256") != digest(bundle/"scene.usdc")
        or usd.get("checked_body_samples") != measured["body_samples"]
        or type(usd_error) not in (int, float) or not math.isfinite(usd_error) or not 0 <= usd_error < 1e-5
    ):
        raise ValueError("Incomplete chaos USD check")
    return measured


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--destination", type=Path, default=ROOT/"docs/chaos")
    args = parser.parse_args()
    check_report(args.bundle)
    from robot_reel.chaos_usd import check_usd
    trace = json.loads((args.bundle/"trace.json").read_text())
    check_usd(trace, args.bundle/"scene.usdc")
    args.destination.mkdir(parents=True, exist_ok=True)
    for name in ("trace.json", "scene.usdc", "blender-check.json", "usd-check.json"):
        shutil.copyfile(args.bundle/name, args.destination/name)
    export_viewer(trace, args.destination/"index.html")
    write_manifest(args.destination)
    check_report(args.destination)
    print(
        f"Built {args.destination}: {len(trace['frames'])} samples "
        f"× {2 * trace['source']['world_count']} bodies"
    )


if __name__ == "__main__":
    main()
