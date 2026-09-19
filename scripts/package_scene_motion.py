"""Build the browser motion package from completed native recordings and checks."""

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from robot_reel.scene_motion_site import package

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=Path, required=True)
    parser.add_argument("--scenes", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--locations", type=Path, help="Optional per-case input paths relative to --runs")
    args = parser.parse_args()
    locations = json.loads(args.locations.read_text()) if args.locations else None
    print(json.dumps(package(args.runs, args.scenes, args.output, locations=locations), indent=2))
