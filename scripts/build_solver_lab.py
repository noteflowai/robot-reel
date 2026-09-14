"""Assemble the six real recordings and native readback results into an offline lab."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from robot_reel.solver_lab import (
    IDS, SCHEMA, SUBSTEPS, decode, digest, make_lab, read, seal, verify,
)
from robot_reel.solver_usd import write


def build(genesis, newton, output):
    output = Path(output).absolute()
    inputs = [Path(genesis).resolve(), Path(newton).resolve(), ROOT/"docs", ROOT/"robot_reel",
              ROOT/"scripts"]
    if any(p.is_symlink() for p in (output, *output.parents)):
        raise ValueError("Symlink in output path")
    if any(output == p or p.is_relative_to(output) or output.is_relative_to(p) for p in inputs):
        raise ValueError("Output overlaps inputs; build in a fresh artifacts directory")
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        raise ValueError("Choose an empty output directory")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=output.parent, prefix=".solver-build-") as temporary:
        stage = Path(temporary)/"lab"
        stage.mkdir()
        for name in IDS:
            source = genesis if name.startswith("genesis") else newton
            (stage/f"{name}.json").write_bytes(read(source, f"{name}.json"))
        for n in SUBSTEPS:
            result = decode(read(genesis, f"genesis-{n}-readback.json"))
            expected = {f"genesis-{n}.{ext}": digest(read(genesis, f"genesis-{n}.{ext}"))
                        for ext in ("json", "gs", "gstraj")}
            if result != {"samples": 61, "exact": True, "positions_and_velocities_equal": True,
                          "inputs": expected}:
                raise ValueError("Missing successful Genesis native readback")
            for ext in ("gs", "gstraj"):
                name = f"genesis-{n}.{ext}"
                (stage/name).write_bytes(read(genesis, name))
        runs = [decode(read(stage, f"{name}.json")) for name in IDS]
        lab = make_lab(runs)
        (stage/"lab.json").write_text(json.dumps(lab, indent=2, allow_nan=False)+"\n")
        data = json.dumps(lab, separators=(",", ":"), allow_nan=False).replace("<", "\\u003c")
        (stage/"index.html").write_text((ROOT/"robot_reel/solver_lab.html").read_text().replace("__LAB_DATA__", data))
        shutil.copyfile(ROOT/"docs/solver-lab.md", stage/"METHODS.md")
        shutil.copyfile(ROOT/"LICENSE", stage/"LICENSE")
        checked = write(stage)
        native_files = ("scene.usda", *(f"genesis-{n}.gstraj" for n in SUBSTEPS),
                        *(f"genesis-{n}.gs" for n in SUBSTEPS), *(f"{name}.json" for name in IDS))
        (stage/"native-check.json").write_text(json.dumps({
            "schema": SCHEMA, "inputs": {name: digest(read(stage, name)) for name in native_files},
            "usd_samples_checked": checked, "genesis_replay_samples_checked": 183,
            "genesis_exact_replay": True,
        }, indent=2)+"\n")
        seal(stage)
        if output.exists():
            output.rmdir()
        stage.rename(output)
    return verify(output)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--genesis", required=True, type=Path)
    parser.add_argument("--newton", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(build(args.genesis, args.newton, args.output), indent=2))
