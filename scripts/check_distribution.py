"""Exercise the installed distribution outside the source checkout.

Run with a fresh environment containing the built wheel and the inspect extra.
The source checkout supplies input recordings and reference notices only.
"""
import argparse
import hashlib
from importlib.metadata import version
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import tomllib
import zipfile


def check(source, release_assets=None):
    source = source.resolve()
    if release_assets is not None:
        release_assets = release_assets.resolve()
        if release_assets.exists() and any(release_assets.iterdir()):
            raise ValueError("Choose an empty release-assets directory")
    # An editable install or PYTHONPATH pointing at the checkout must not make
    # this check pass. The caller also changes cwd to an unrelated directory.
    import robot_reel
    from robot_reel.stress_site import build, verify_site
    from robot_reel.stress_mcap import check_mcap
    from robot_reel.stress_review import record
    from robot_reel.cloth_site import SOURCES, verify_site as verify_cloth_site

    module = Path(robot_reel.__file__).resolve()
    if module.is_relative_to(source/"robot_reel") or Path.cwd().is_relative_to(source):
        raise ValueError("Run from outside the checkout with a non-editable wheel installation")
    expected = tomllib.loads((source/"pyproject.toml").read_text())["project"]["version"]
    if version("robot-reel") != expected:
        raise ValueError("Installed distribution version differs from pyproject.toml")
    with tempfile.TemporaryDirectory(prefix="robot-reel-installed-") as temporary:
        cloth_output = Path(temporary)/"cloth"
        cloth_command = subprocess.run(
            [str(Path(sys.executable).with_name("robot-reel")), "cloth",
             "--export-from", str(source/"docs/cloth"), "--output", str(cloth_output)],
            check=True, capture_output=True, text=True, timeout=120,
        )
        cloth_export = json.loads(cloth_command.stdout)
        cloth = verify_cloth_site(cloth_output)
        if cloth_export["summary"] != cloth or cloth_export["native_usd_checked"] or cloth["vertex_samples"] != 42471:
            raise ValueError("Installed cloth CLI export or validation failed")
        for name in SOURCES:
            if (cloth_output/name).read_bytes() != (source/"docs/cloth"/name).read_bytes():
                raise ValueError(f"Installed cloth export changed original evidence: {name}")
        for original, name in (("docs/cloth.md", "METHODS.md"), ("LICENSE", "LICENSE")):
            if (cloth_output/name).read_bytes() != (source/original).read_bytes():
                raise ValueError(f"Installed cloth resource differs: {name}")
        output = Path(temporary)/"stress"
        summary = build(source/"docs/stress", output)
        if verify_site(output) != summary or summary["completed_trials"] != 30:
            raise ValueError("Installed package did not preserve the complete experiment")
        # Verify actual MCAP records and decode all camera streams in build().
        from robot_reel.stress_site import load_collection, payload
        collection = load_collection(output)
        traces = collection[2]
        telemetry = check_mcap(traces, output/"telemetry.mcap")
        review_path = Path(temporary)/"review.json"
        review_path.write_text(json.dumps(record(payload(*collection),
            {"seed": 9, "condition": "dim", "frame": 100, "camera": "wrist"},
            "Review prompt: inspect the dim-light run while the reference holds its final observation. "
            "This note is human interpretation, not a measured conclusion."), indent=2)+"\n")
        review = subprocess.run(
            [str(Path(sys.executable).with_name("robot-reel")), "stress", str(output),
             "--review", str(review_path)],
            check=True, capture_output=True, text=True, timeout=120,
        )
        review_check = json.loads(review.stdout)["review"]
        if not review_check["recorded_facts_match"] or review_check["user_note_verified"]:
            raise ValueError("Installed review validator did not separate source facts from user notes")
        with zipfile.ZipFile(output/"experiment.zip") as archive:
            for original, name in (
                ("licenses/VLA-MEDIA-NOTICE.txt", "NOTICE.txt"),
                ("LICENSE", "LICENSE"), ("docs/stress.md", "METHODS.md"),
            ):
                if archive.read(name) != (source/original).read_bytes():
                    raise ValueError(f"Installed archive resource differs: {name}")
        result = subprocess.run(
            [str(Path(sys.executable).with_name("robot-reel")), "vla",
             str(source/"docs/vla"), "--check-media"],
            check=True, capture_output=True, text=True, timeout=120,
        )
        report = {"version": expected, "module": str(module), "cloth_vertex_samples": cloth["vertex_samples"],
                  "stress_trials": summary["completed_trials"], "telemetry": telemetry,
                  "review": review_check, "vla": json.loads(result.stdout)}
        # Preserve the tested bytes before the temporary exported site is removed.
        # The release workflow consumes this artifact; it does not rebuild the ZIP.
        if release_assets is not None:
            release_assets.mkdir(parents=True, exist_ok=True)
            for original, name in (
                (output/"experiment.zip", "robot-reel-stress-experiment.zip"),
                (review_path, "robot-reel-seed-09-review.json"),
                (source/"docs/offline-lab.md", "START-HERE.md"),
                (cloth_output/"experiment.zip", "robot-reel-cloth-experiment.zip"),
                (cloth_output/"scene.usdc", "robot-reel-cloth-scene.usdc"),
            ):
                shutil.copyfile(original, release_assets/name)
            report["release_assets"] = {
                path.name: {"bytes": path.stat().st_size, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
                for path in sorted(release_assets.iterdir())
            }
        return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--release-assets", type=Path,
                        help="Preserve the verified archive, sample review and guide in an empty directory")
    args = parser.parse_args()
    print(json.dumps(check(args.source, args.release_assets), indent=2))
