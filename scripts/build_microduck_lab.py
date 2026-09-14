"""Build the Microduck Motion Lab from two original recordings, without simulation.

The small kinematic description comes from export_microduck_kinematics.py.
Forward kinematics is checked separately against MuJoCo for every measured and
target pose. No root attitude, contact state or new policy output is invented.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from robot_reel.microduck import MODEL_COMMIT, POLICY_REVISION, POLICY_SHA256
from robot_reel.pages import digest

SOURCE = ROOT/"docs/compare/microduck"
KINEMATICS = ROOT/"scripts/assets/microduck-kinematics.json"
from robot_reel.microduck_review import (
    FILES, JOINTS, frame_record, read_frame, verify_frame, multiply, rotate, poses,
    validate_trace, make_data, same_data, verify_bundle,
)


def verify_showcase(site, *, check_sources=False):
    site = Path(site)
    record = json.loads((site/"showcase-manifest.json").read_text())
    expected = {*FILES, "poster.png", "experiment.zip"}
    if record.get("schema") != "robot-reel-microduck-showcase-1" or set(record.get("files", {})) != expected:
        raise ValueError("Unexpected Microduck file inventory")
    if any(p.is_symlink() for p in site.rglob("*")):
        raise ValueError("Microduck lab contains a symlink")
    for name, checksum in record["files"].items():
        if digest(site/name) != checksum:
            raise ValueError(f"Changed Microduck file: {name}")
    verify_bundle(site)
    with zipfile.ZipFile(site/"experiment.zip") as archive:
        if len(archive.namelist()) != len(FILES) or set(archive.namelist()) != set(FILES):
            raise ValueError("Unexpected Microduck offline archive")
        for name in FILES:
            if archive.read(name) != (site/name).read_bytes():
                raise ValueError(f"Changed offline Microduck file: {name}")
    if check_sources:
        for name in ("left-trace.json", "right-trace.json", "left.mp4", "right.mp4"):
            if digest(site/name) != digest(SOURCE/name):
                raise ValueError(f"Microduck original source changed: {name}")
        if digest(KINEMATICS) != digest(site/"kinematics.json"):
            raise ValueError("Microduck model description changed")
    return {"runs": 2, "frames": 600, "joint_samples": 8400,
            "checked_body_transforms": 18000, "source_data_unchanged": check_sources}


def build(site):
    site = Path(site).absolute()
    if site.is_symlink() or any(p.is_symlink() for p in site.parents):
        raise ValueError("Choose a destination without symlinks")
    if site.exists() and any(site.iterdir()):
        raise ValueError("Choose an empty Microduck destination")
    kin = json.loads(KINEMATICS.read_text())
    data = make_data(SOURCE, kin)
    site.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".microduck-", dir=site.parent) as temporary:
        stage = Path(temporary)
        for name in ("left-trace.json", "right-trace.json", "left.mp4", "right.mp4",
                     "MICRODUCK-MEDIA-NOTICE.txt"):
            shutil.copyfile(SOURCE/name, stage/name)
        with (stage/"MICRODUCK-MEDIA-NOTICE.txt").open("a") as notice:
            notice.write("\nThe Motion Lab's simplified body envelopes and kinematic description "
                         "are derived from the same pinned model. They retain the upstream "
                         "noncommercial/share-alike terms too; the Apache-2.0 code license "
                         "does not relicense this geometry.\n")
        shutil.copyfile(KINEMATICS, stage/"kinematics.json")
        shutil.copyfile(KINEMATICS.with_name("microduck-kinematics-check.json"), stage/"kinematics-check.json")
        shutil.copyfile(ROOT/"LICENSE", stage/"LICENSE")
        shutil.copyfile(ROOT/"docs/microduck-lab.md", stage/"METHODS.md")
        payload = json.dumps(data, separators=(",", ":"), allow_nan=False)
        (stage/"data.json").write_text(payload+"\n")
        template = (ROOT/"scripts/microduck_lab.html").read_text()
        (stage/"index.html").write_text(template.replace("__LAB_DATA__", payload.replace("<", "\\u003c")))
        # The poster is captured from the actual viewer, then the bundle is sealed.
        if site.exists():
            site.rmdir()
        shutil.copytree(stage, site)
    return data


def seal(site):
    site = Path(site)
    (site/"manifest.json").write_text(json.dumps({
        "schema": "robot-reel-microduck-motion-bundle-1",
        "sha256": {name: digest(site/name) for name in FILES if name != "manifest.json"},
    }, indent=2)+"\n")
    with zipfile.ZipFile(site/"experiment.zip", "w", zipfile.ZIP_DEFLATED) as archive:
        for name in FILES:
            info = zipfile.ZipInfo(name, date_time=(2026, 9, 14, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, (site/name).read_bytes())
    (site/"showcase-manifest.json").write_text(json.dumps({
        "schema": "robot-reel-microduck-showcase-1", "poster": {"run": "right", "frame": 120, "joint": 3},
        "files": {name: digest(site/name) for name in (*FILES, "poster.png", "experiment.zip")},
    }, indent=2)+"\n")
    return verify_showcase(site, check_sources=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT/"docs/microduck-lab")
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--seal", action="store_true")
    parser.add_argument("--frame-json", type=Path,
                        help="Verify a frame export against the verified lab; never builds or writes")
    args = parser.parse_args()
    if args.frame_json:
        if args.seal:
            parser.error("--frame-json cannot be combined with --seal")
        result = verify_showcase(args.output, check_sources=True)
        result["frame"] = verify_frame(json.loads((args.output/"data.json").read_text()),
                                       read_frame(args.frame_json))
    else:
        result = (verify_showcase(args.output, check_sources=True) if args.verify else
                  seal(args.output) if args.seal else {"runs": len(build(args.output)["runs"])})
    print(json.dumps(result, indent=2))
