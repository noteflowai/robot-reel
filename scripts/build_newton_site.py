"""Build a public replay from a verified Newton run and a matching Blender check."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import shutil

from robot_reel.newton import export_viewer, verify, write_manifest
from robot_reel.newton_usd import check_usd


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--destination", type=Path, default=Path("docs/newton"))
    args = parser.parse_args()
    verify(args.bundle)
    trace = json.loads((args.bundle/"trace.json").read_text())
    check_usd(trace, args.bundle/"scene.usda")
    report = json.loads((args.bundle/"blender-check.json").read_text())
    for field, name in (("trace_sha256", "trace.json"), ("usd_sha256", "scene.usda")):
        if report[field] != hashlib.sha256((args.bundle/name).read_bytes()).hexdigest():
            raise ValueError(f"Blender check belongs to a different {name}")
    if (
        report["checked_body_samples"] != len(trace["frames"])*2
        or report["frame_start"] != 1 or report["frame_end"] != len(trace["frames"])
        or report["fps"] != trace["fps"] or not math.isfinite(report["maximum_transform_error_m"])
        or not 0 <= report["maximum_transform_error_m"] < 1e-5
    ):
        raise ValueError("Incomplete Blender check")
    args.destination.mkdir(parents=True, exist_ok=True)
    for name in ("trace.json", "scene.usda", "blender-check.json"):
        shutil.copyfile(args.bundle/name, args.destination/name)
    export_viewer(trace, args.destination/"index.html")
    write_manifest(args.destination)
    verify(args.destination)
    print(f"Built {args.destination.resolve()}: {len(trace['frames'])} samples")


if __name__ == "__main__":
    main()
