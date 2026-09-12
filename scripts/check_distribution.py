"""Exercise the installed distribution outside the source checkout.

Run with a fresh environment containing the built wheel and the inspect extra.
The source checkout supplies input recordings and reference notices only.
"""
import argparse
from importlib.metadata import version
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import tomllib
import zipfile


def check(source):
    source = source.resolve()
    # An editable install or PYTHONPATH pointing at the checkout must not make
    # this check pass. The caller also changes cwd to an unrelated directory.
    import robot_reel
    from robot_reel.stress_site import build, verify_site
    from robot_reel.stress_mcap import check_mcap

    module = Path(robot_reel.__file__).resolve()
    if module.is_relative_to(source/"robot_reel") or Path.cwd().is_relative_to(source):
        raise ValueError("Run from outside the checkout with a non-editable wheel installation")
    expected = tomllib.loads((source/"pyproject.toml").read_text())["project"]["version"]
    if version("robot-reel") != expected:
        raise ValueError("Installed distribution version differs from pyproject.toml")
    with tempfile.TemporaryDirectory(prefix="robot-reel-installed-") as temporary:
        output = Path(temporary)/"stress"
        summary = build(source/"docs/stress", output)
        if verify_site(output) != summary or summary["completed_trials"] != 30:
            raise ValueError("Installed package did not preserve the complete experiment")
        # Verify actual MCAP records and decode all camera streams in build().
        from robot_reel.stress_site import load_collection
        _, _, traces = load_collection(output)
        telemetry = check_mcap(traces, output/"telemetry.mcap")
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
        return {"version": expected, "module": str(module),
                "stress_trials": summary["completed_trials"], "telemetry": telemetry,
                "vla": json.loads(result.stdout)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(check(args.source), indent=2))
