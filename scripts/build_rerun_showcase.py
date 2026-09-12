"""Package a verified RRD and an actual viewer screenshot for the homepage."""
import argparse
import json
from pathlib import Path
import shutil

from robot_reel.stress import file_hash
from robot_reel.stress_rerun import selection, verify

ROOT = Path(__file__).resolve().parents[1]


def build(recording, preview, output, seed=9):
    source = ROOT/"docs/stress"
    result = verify(source, recording, seed)
    _, traces, paths = selection(source, seed)
    inputs = [source/name for name in ("experiment.json", "attempts.json", "NOTICE.txt", "LICENSE")]
    for trace in traces:
        run = paths[trace["stress"]["trial_id"]]
        inputs.extend(run/name for name in ("trace.json", "main.mp4", "wrist.mp4"))
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    name = f"seed-{seed:02d}.rrd"
    shutil.copyfile(recording, output/name)
    shutil.copyfile(preview, output/"preview.png")
    manifest = {
        **result,
        "preview": {"kind": "actual Rerun web viewer screenshot", "source_sample": 0,
                    "viewer_version": result["rerun_version"]},
        "inputs": {path.relative_to(ROOT/"docs").as_posix(): file_hash(path) for path in inputs},
        "sha256": {filename: file_hash(output/filename) for filename in (name, "preview.png")},
    }
    (output/"manifest.json").write_text(json.dumps(manifest, indent=2)+"\n")
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--recording", type=Path, required=True)
    parser.add_argument("--preview", type=Path, required=True,
                        help="Reviewed viewer screenshot paused at source sample zero")
    parser.add_argument("--output", type=Path, default=ROOT/"docs/rerun")
    parser.add_argument("--seed", type=int, default=9)
    args = parser.parse_args()
    print(json.dumps(build(args.recording, args.preview, args.output, args.seed), indent=2))


if __name__ == "__main__":
    main()
