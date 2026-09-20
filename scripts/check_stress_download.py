"""Require the published Stress Lab download to match the checked source files."""

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from robot_reel.stress_site import PUBLISHED_ARCHIVE_HREF, verify_site


def check(source, archive=None):
    source = Path(source)
    summary = verify_site(source)
    names = set(json.loads((source / "manifest.json").read_text())["files"]) | {"manifest.json"}
    with tempfile.TemporaryDirectory(prefix="robot-reel-stress-download-") as temporary:
        collection = Path(temporary) / "collection"
        for name in names:
            destination = collection / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source / name, destination)
        received = collection / "experiment.zip"
        if archive is None:
            # Bound the response by the uncompressed source size plus ZIP metadata.
            remaining = sum((source / name).stat().st_size for name in names) + 1024 * 1024
            with urlopen(PUBLISHED_ARCHIVE_HREF, timeout=60) as response, received.open("xb") as output:
                while chunk := response.read(min(1024 * 1024, remaining + 1)):
                    remaining -= len(chunk)
                    if remaining < 0:
                        raise ValueError("Stress download exceeds the source archive size bound")
                    output.write(chunk)
        else:
            shutil.copyfile(archive, received)
        # This compares every ZIP member with the same files used by the website,
        # including the viewer, methodology, manifest and original trial evidence.
        if verify_site(collection) != summary:
            raise ValueError("Downloaded Stress Lab differs from the published collection")
        return {
            "verified": True,
            "members": len(names),
            "completed_trials": summary["completed_trials"],
            "archive_sha256": hashlib.sha256(received.read_bytes()).hexdigest(),
            "source": str(archive) if archive is not None else PUBLISHED_ARCHIVE_HREF,
        }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=ROOT / "docs/stress")
    parser.add_argument("--archive", type=Path, help="Check a prepared local archive before publication")
    args = parser.parse_args()
    print(json.dumps(check(args.source, args.archive), indent=2))
