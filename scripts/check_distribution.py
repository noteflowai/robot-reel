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
        trace_path = source/"docs/stress/runs/seed-09-dim/attempt-001/trace.json"
        trace = json.loads(trace_path.read_text())
        claims_path = Path(temporary)/"authored-claims-control.json"
        claims = {"outcome": trace["result"]["outcome"], "action_count": trace["result"]["actions"],
                  "cited_frames": [trace["frames"][0]["frame"]],
                  "explanation": "Authored installed-package control; not a model answer."}
        claims_path.write_text(json.dumps(claims))
        claims_command = [str(Path(sys.executable).with_name("robot-reel")), "review-claims",
                          str(trace_path), str(claims_path)]
        claims_checked = subprocess.run(claims_command, check=True, capture_output=True, text=True)
        claims_report = json.loads(claims_checked.stdout)
        if not claims_report["facts_match"] or claims_report["explanation_status"] != "not_assessed":
            raise ValueError("Installed claim review did not preserve its scope")
        claims["outcome"] = "success"
        claims_path.write_text(json.dumps(claims))
        claims_rejected = subprocess.run(claims_command, capture_output=True, text=True)
        if claims_rejected.returncode != 1 or json.loads(claims_rejected.stdout)["facts_match"]:
            raise ValueError("Installed claim reviewer accepted a contradicted outcome")
        microduck_output = Path(temporary)/"microduck"
        with zipfile.ZipFile(source/"docs/microduck-lab/experiment.zip") as archive:
            archive.extractall(microduck_output)
        microduck_command = [
            str(Path(sys.executable).with_name("robot-reel")), "microduck-review",
            str(microduck_output), "--frame-json", str(source/"examples/microduck-frame.json"),
        ]
        microduck = json.loads(subprocess.run(
            microduck_command, check=True, capture_output=True, text=True, timeout=120,
        ).stdout)
        if not microduck["verified"] or not microduck["frame"]["recorded_facts_match"]:
            raise ValueError("Installed Microduck verifier did not check the offline frame")
        changed_frame = Path(temporary)/"changed-frame.json"
        frame = json.loads((source/"examples/microduck-frame.json").read_text())
        frame["target_rad"] += .01
        changed_frame.write_text(json.dumps(frame))
        rejected = subprocess.run(
            microduck_command[:-1]+[str(changed_frame)],
            capture_output=True, text=True, timeout=120,
        )
        if rejected.returncode != 2 or json.loads(rejected.stdout)["verified"]:
            raise ValueError("Installed Microduck verifier accepted a changed frame")
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
        sample_command = [str(Path(sys.executable).with_name("robot-reel")), "cloth",
                          "--output", str(cloth_output), "--verify-sample",
                          str(source/"tests/fixtures/cloth-sample.json")]
        sample = subprocess.run(sample_command, check=True, capture_output=True, text=True, timeout=120)
        sample_check = json.loads(sample.stdout)
        if (not sample_check["recorded_facts_match"] or sample_check["sample"] != 29
                or sample_check["case_index"] != 2):
            raise ValueError("Installed cloth sample validator did not check the browser export")
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
        paired_path = Path(temporary)/"paired-outcomes.json"
        paired_command = [str(Path(sys.executable).with_name("robot-reel")), "stress", str(output)]
        paired = subprocess.run(paired_command+["--paired"], check=True, capture_output=True, text=True, timeout=120)
        paired_path.write_text(paired.stdout)
        paired_report = json.loads(paired.stdout)
        if (paired_report["scope"]["completed_trials"] != 30
                or paired_report["comparisons"][1]["groups"]["lost_success"] != [9]
                or paired_report["comparisons"][1]["groups"]["gained_success"] != [3, 4, 5]):
            raise ValueError("Installed paired report lost complete experiment outcomes")
        verified = subprocess.run(paired_command+["--paired-report", str(paired_path)],
                                  check=True, capture_output=True, text=True, timeout=120)
        if not json.loads(verified.stdout)["paired_report_verified"]:
            raise ValueError("Installed paired report did not verify")
        changed = json.loads(paired.stdout)
        changed["comparisons"][1]["groups"]["lost_success"] = []
        changed_path = Path(temporary)/"changed-pairs.json"
        changed_path.write_text(json.dumps(changed))
        rejected = subprocess.run(paired_command+["--paired-report", str(changed_path)],
                                  capture_output=True, text=True, timeout=120)
        if rejected.returncode == 0 or "differs from the complete source experiment" not in rejected.stderr:
            raise ValueError("Installed paired verifier accepted a changed outcome")
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
        solver_output = Path(temporary)/"solver"
        solver_command = [str(Path(sys.executable).with_name("robot-reel")), "solver-lab"]
        solver_result = subprocess.run(
            solver_command + ["--export-from", str(source/"docs/solver-lab"), "--output", str(solver_output)],
            check=True, capture_output=True, text=True, timeout=120,
        )
        solver = json.loads(solver_result.stdout)
        if not solver["verified"] or solver["samples"] != 366:
            raise ValueError("Installed Solver Lab export failed")
        # Check the exact archive generated by the installed wheel.
        from robot_reel.solver_lab import FILES
        with zipfile.ZipFile(solver_output/"experiment.zip") as archive:
            if set(archive.namelist()) != {*FILES, "manifest.json"}:
                raise ValueError("Unexpected solver archive inventory")
            for name in (*FILES, "manifest.json"):
                if archive.read(name) != (solver_output/name).read_bytes():
                    raise ValueError(f"Changed solver archive member: {name}")
        damaged = solver_output/"lab.json"
        original = damaged.read_bytes()
        damaged.write_bytes(original+b"changed")
        rejected = subprocess.run(
            solver_command + ["--output", str(solver_output), "--verify"],
            capture_output=True, text=True, timeout=120,
        )
        damaged.write_bytes(original)
        if rejected.returncode != 2 or json.loads(rejected.stdout)["verified"]:
            raise ValueError("Installed solver verifier accepted damaged evidence")
        new_labs = {}
        for name, arguments in (
            ("scene-lab", ["scene-lab", "--output", str(source/"docs/scene-lab"), "--verify"]),
            ("libero-plus", ["libero-plus", "verify", "--output", str(source/"docs/libero-plus"), "--media"]),
        ):
            checked = subprocess.run(
                [str(Path(sys.executable).with_name("robot-reel")), *arguments],
                check=True, capture_output=True, text=True, timeout=120,
            )
            new_labs[name] = json.loads(checked.stdout)
            if new_labs[name].get("valid") is not True:
                raise ValueError(f"Installed {name} verifier failed")
        report = {"version": expected, "module": str(module), "new_labs": new_labs,
                  "model_claim_control": claims_report,
                  "cloth_vertex_samples": cloth["vertex_samples"],
                  "solver_lab": solver,
                  "microduck": microduck,
                  "cloth_sample": sample_check,
                  "stress_trials": summary["completed_trials"], "telemetry": telemetry,
                  "review": review_check, "paired_outcomes_verified": True,
                  "vla": json.loads(result.stdout)}
        # Preserve the tested bytes before the temporary exported site is removed.
        # The release workflow consumes this artifact; it does not rebuild the ZIP.
        if release_assets is not None:
            release_assets.mkdir(parents=True, exist_ok=True)
            for original, name in (
                (output/"experiment.zip", "robot-reel-stress-experiment.zip"),
                (review_path, "robot-reel-seed-09-review.json"),
                (paired_path, "robot-reel-paired-outcomes.json"),
                (source/"docs/offline-lab.md", "START-HERE.md"),
                (cloth_output/"experiment.zip", "robot-reel-cloth-experiment.zip"),
                (cloth_output/"scene.usdc", "robot-reel-cloth-scene.usdc"),
                (source/"docs/microduck-lab/experiment.zip", "robot-reel-microduck-experiment.zip"),
                (source/"examples/microduck-frame.json", "robot-reel-microduck-frame.json"),
                (solver_output/"experiment.zip", "robot-reel-solver-experiment.zip"),
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
