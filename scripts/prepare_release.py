"""Assemble checked release artifacts without rebuilding their contents."""
import argparse
import hashlib
from pathlib import Path
import shutil
import sys
import tempfile
import tomllib

sys.path.insert(0, str(Path(__file__).resolve().parent))
from research_release_assets import fetch_assets

OFFLINE_FILES = {
    "robot-reel-stress-experiment.zip", "robot-reel-seed-09-review.json", "START-HERE.md",
    "robot-reel-cloth-experiment.zip", "robot-reel-cloth-scene.usdc",
    "robot-reel-paired-outcomes.json",
    "robot-reel-microduck-experiment.zip", "robot-reel-microduck-frame.json",
    "robot-reel-solver-experiment.zip",
}


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
    with tempfile.TemporaryDirectory(prefix="robot-reel-release-") as temporary:
        for path in fetch_assets(source, Path(temporary)/"research"):
            shutil.copyfile(path, output/path.name)
    paths = sorted(output.iterdir())
    (output/"SHA256SUMS").write_text("".join(
        f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}\n" for path in paths
    ))
    return notes + """

Scene Lab adds `scene-lab-native.zip`: both packed Blender scenes and their
independent native checks. Release 0.13.0 also includes `scene-motion-native.zip`:
both animated Microduck projects, relative USD caches and a standalone checker.
The full producer PNGs and simulation inputs are a separate versioned dataset
download documented in `examples/scene-motion/README.md`.
`research-records.zip` contains the original 45 agent trials
(27 skill delivery, 12 composition, 6 handoff), including failures and Harbor
interop receipts. Research assets are fetched from a pinned immutable public dataset
revision, verified against committed sizes/SHA-256, and included in SHA256SUMS.
OpenEnv's actual recipe controls are documented with raw evidence in the repository.

Solver Lab includes six new CUDA recordings from Genesis 1.4.1 and Newton 1.6.0,
the analytic-reference diagnostics, native Genesis replays and editable USD.
The installed wheel exports its offline ZIP and verifies all 366 source samples.
Run `robot-reel solver-lab --output solver-lab --verify` after extraction.

Start with `START-HERE.md`. Extract an experiment ZIP and open its `index.html`
locally. Cloth Lab includes all 42,471 recorded vertex samples, original velocities,
the editable USD and native readback reports. The standalone cloth USD contains
the same bytes as the scene in the ZIP; import it into Blender at 30 fps.
For Stress Lab, import `robot-reel-seed-09-review.json` to inspect a selected moment
in the complete thirty-trial experiment. The Cloth and Stress ZIPs are the exact artifacts
exported by the installed wheel and tested offline in Chromium at desktop and
mobile sizes. No GPU or Python is needed to use these recorded browser labs.

Microduck Lab includes both original walks, all derived poses, and a frame sample.
With the wheel installed, run `robot-reel microduck-review microduck-lab
--frame-json robot-reel-microduck-frame.json` on the extracted archive. The installed
verifier checks all source facts and rejects an altered frame without simulation.

Stress Lab includes all four paired outcome groups and complete report export.
`robot-reel-paired-outcomes.json` was exported and verified by the installed CLI;
the offline browser produces the same report even after selecting a subset.
Use `robot-reel stress stress-lab --paired-report robot-reel-paired-outcomes.json`
to check it independently. Cloth Lab includes source-checked sample import,
portable JSON and 1080p figure export.

The wheel, source distribution and Rerun recording passed the same six validation
jobs. Open `robot-reel-seed-09.rrd` in Rerun 0.37.2. `SHA256SUMS` covers every asset.
The existing policy and cloth recordings are unchanged. Solver Lab contains new
ballistic-flight recordings. PyPI publishing is configured separately.
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
