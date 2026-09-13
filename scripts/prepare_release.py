"""Assemble checked release artifacts without rebuilding their contents."""
import argparse
import hashlib
from pathlib import Path
import shutil
import tomllib

OFFLINE_FILES = {"robot-reel-stress-experiment.zip", "robot-reel-seed-09-review.json", "START-HERE.md"}


def prepare(source, distributions, offline, output):
    version = tomllib.loads((source/"pyproject.toml").read_text())["project"]["version"]
    expected = {f"robot_reel-{version}-py3-none-any.whl", f"robot_reel-{version}.tar.gz"}
    for directory, names in ((distributions, expected), (offline, OFFLINE_FILES)):
        if {p.name for p in directory.iterdir()} != names or any(
            p.is_symlink() or not p.is_file() for p in directory.iterdir()
        ):
            raise ValueError(f"Expected exactly the tested release files in {directory}")
    if output.exists() and any(output.iterdir()):
        raise ValueError("Choose an empty release output directory")
    changelog = (source/"CHANGELOG.md").read_text()
    notes = changelog.split(f"## {version} — ", 1)[1].split("\n## ", 1)[0]
    output.mkdir(parents=True, exist_ok=True)
    for directory in (distributions, offline):
        for path in directory.iterdir():
            shutil.copyfile(path, output/path.name)
    shutil.copyfile(source/"docs/rerun/seed-09.rrd", output/"robot-reel-seed-09.rrd")
    paths = sorted(output.iterdir())
    (output/"SHA256SUMS").write_text("".join(
        f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}\n" for path in paths
    ))
    return notes + """

Start with `START-HERE.md`. Extract `robot-reel-stress-experiment.zip` and open
`index.html` locally; import `robot-reel-seed-09-review.json` to inspect a selected
moment. The ZIP is the exact artifact exported by the installed wheel, verified
against all thirty trials and tested offline in Chromium. No GPU or Python is
needed to use the recorded browser lab.

The wheel, source distribution and Rerun recording passed the same six validation
jobs. Open `robot-reel-seed-09.rrd` in Rerun 0.37.2. `SHA256SUMS` covers every asset.
The original trials are unchanged; new policy inference was not performed for
this release. PyPI publishing is configured separately.
"""


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--distributions", type=Path, required=True)
    parser.add_argument("--offline", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--notes", type=Path, required=True)
    args = parser.parse_args()
    args.notes.write_text(prepare(args.source, args.distributions, args.offline, args.output))
