"""Publish a cloth site after native readback; retained as a maintainer wrapper."""
import argparse
import json
from pathlib import Path
import shutil
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from robot_reel.cloth_site import ARCHIVED, build as export, check_reports, verify_site


def build(bundle, destination):
    """Update the explicit publishing directory while preserving preview assets."""
    destination = Path(destination)
    # Finish native validation and export before touching the published files.
    with tempfile.TemporaryDirectory(prefix="robot-reel-cloth-site-") as temporary:
        staging = Path(temporary)/"site"
        export(bundle, staging, check_native=True)
        destination.mkdir(parents=True, exist_ok=True)
        for name in (*ARCHIVED, "experiment.zip"):
            shutil.copyfile(staging/name, destination/name)
    return verify_site(destination)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--destination", type=Path, default=ROOT/"docs/cloth")
    args = parser.parse_args()
    print(json.dumps(build(args.bundle, args.destination), indent=2))
