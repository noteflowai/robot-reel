"""Export the published pilot's tabular results for Hugging Face Datasets."""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from robot_reel.stress import canonical_hash
from robot_reel.stress_pairs import paired_report
from robot_reel.stress_site import verify_site

PAIR_FIELDS = (
    "seed", "condition", "reference_success", "condition_success", "outcome_group",
    "shared_observations", "max_eef_distance_m", "max_eef_frame", "first_action_l2",
)


def pairs_csv(pairs):
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=PAIR_FIELDS, lineterminator="\n")
    writer.writeheader()
    for pair in pairs:
        a, b = pair["reference_success"], pair["condition_success"]
        group = ("both_success" if a and b else "lost_success" if a
                 else "gained_success" if b else "neither_success")
        writer.writerow({**pair, "outcome_group": group})
    return stream.getvalue()


def build(output, allow_dirty=False):
    output = Path(output)
    if output.is_symlink() or output.exists():
        raise ValueError("Choose a new dataset output directory")
    source = subprocess.check_output(["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True).strip()
    dirty = bool(subprocess.check_output(["git", "-C", str(ROOT), "status", "--porcelain"], text=True).strip())
    if dirty and not allow_dirty:
        raise ValueError("Commit source changes before publishing")
    site = ROOT / "docs/stress"
    summary = verify_site(site)
    if summary["completed_trials"] != 30 or len(summary["pairs"]) != 20:
        raise ValueError("This dataset card describes the published 30-trial pilot")
    plan = json.loads((site / "experiment.json").read_text())
    report = paired_report(summary, canonical_hash(plan))
    card = (ROOT / "huggingface/results-card.md").read_text().replace("__SOURCE_COMMIT__", source)
    output.mkdir(parents=True)
    (output / "README.md").write_text(card)
    (output / "pairs.csv").write_text(pairs_csv(summary["pairs"]))
    (output / "paired-outcomes.json").write_text(json.dumps(report, indent=2) + "\n")
    for original, target in [
        (site / "results.csv", "trials.csv"),
        (site / "summary.json", "summary.json"),
        (site / "experiment.json", "experiment.json"),
        (ROOT / "LICENSE", "LICENSE"),
        (ROOT / "licenses/VLA-MEDIA-NOTICE.txt", "NOTICE.txt"),
    ]:
        shutil.copyfile(original, output / target)
    files = {}
    for path in sorted(output.iterdir()):
        content = path.read_bytes()
        files[path.name] = {"bytes": len(content), "sha256": hashlib.sha256(content).hexdigest()}
    record = {
        "schema": "robot-reel-results-dataset-1", "source_commit": source, "source_dirty": dirty,
        "plan_sha256": canonical_hash(plan), "trials": 30, "pairs": 20, "files": files,
    }
    (output / "source-manifest.json").write_text(json.dumps(record, indent=2) + "\n")
    return record


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--allow-dirty", action="store_true")
    args = parser.parse_args()
    print(json.dumps(build(args.output, args.allow_dirty), indent=2))
