"""Package or verify the Factory Twin Blender + OpenUSD release asset.

    python3 scripts/package_factory_twin_blender.py --work artifacts/factory-twin \
        --lab docs/factory-twin --output artifacts/factory-twin-blender.zip
    python3 scripts/package_factory_twin_blender.py --verify artifacts/factory-twin-blender.zip \
        --lab docs/factory-twin

The archive holds both animated projects (closed loop and shadow), their
OpenUSD exports, per-mode Blender check reports, lab.json and the scripts that
built and checked them. Every project and USD file must match the SHA-256
recorded in the published ``blender-check.json`` receipt, so a download can be
traced to the page it came from without re-running Blender.
"""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
MODES = ("closed", "shadow")
SCRIPTS = ("build_factory_twin_blender.py", "check_factory_twin_blender.py", "render_factory_twin.py")
README = """# Factory Twin Lab — Blender 5.2 and OpenUSD projects

factory-twin-closed.blend / .usdc   the closed-loop shift (twin commands actuated)
factory-twin-shadow.blend / .usdc   the same seed with the twin in shadow mode
check-<mode>.json                   every channel at every frame + USD readback
lab.json                            the recorded samples that drive the animation

Open a .blend in Blender 5.2 LTS. Frame k+1 holds sample k (5 s of plant time) at
30 fps with constant interpolation; Blender performs no physics. Collections:
"Buildings / hall cutaway" hides the roof and south wall for interior views;
"Digital twin overlay" holds the twin's rings, ghosts, gauges and data links.
The `Digital twin` empty carries sim_time_s, good_units, wear_truth,
wear_estimate and grid_import_kw as animated custom properties (also exported
to USD as userProperties).

Rebuild or re-check with the scripts in this folder from a Robot Reel checkout:

  blender --background --factory-startup --python check_factory_twin_blender.py -- \\
    --lab lab.json --blend factory-twin-closed.blend --mode closed \\
    --usd /tmp/readback.usdc --report /tmp/check.json

Everything is procedural and simulated; see METHODS.md on the lab page.
Code: Apache-2.0. Model and renders: original work, Apache-2.0.
"""


def digest(data):
    return hashlib.sha256(data).hexdigest()


def members(work, lab):
    files = {"README.md": README.encode(), "lab.json": (lab / "lab.json").read_bytes(),
             "LICENSE": (ROOT / "LICENSE").read_bytes()}
    for mode in MODES:
        for ext in ("blend", "usdc"):
            files[f"factory-twin-{mode}.{ext}"] = (work / f"factory-twin-{mode}.{ext}").read_bytes()
        files[f"check-{mode}.json"] = (work / f"check-{mode}.json").read_bytes()
    for name in SCRIPTS:
        files[name] = (ROOT / "scripts" / name).read_bytes()
    files["factory_twin_scene.py"] = (ROOT / "robot_reel/factory_twin_scene.py").read_bytes()
    # Blender's USD exporter writes constant-colour textures beside the .usdc files.
    for path in sorted((work / "textures").glob("*")):
        files[f"textures/{path.name}"] = path.read_bytes()
    return files


def check(files, lab):
    receipt = json.loads((lab / "blender-check.json").read_text())
    if digest(files["lab.json"]) != receipt["inputs"]["lab.json"]:
        raise ValueError("lab.json differs from the published receipt")
    for mode in MODES:
        inputs = receipt["modes"][mode]["inputs"]
        report = json.loads(files[f"check-{mode}.json"])
        for key, name in (("blend", f"factory-twin-{mode}.blend"), ("usd", f"factory-twin-{mode}.usdc")):
            if digest(files[name]) != inputs[key] or report["inputs"][key] != inputs[key]:
                raise ValueError(f"{name} differs from the published receipt")
        if report["verified"] is not True or report["frames_checked"] != receipt["frames_checked"]:
            raise ValueError(f"check-{mode}.json is not a passing report")
    return {"verified": True, "files": len(files),
            "sha256": {n: digest(d) for n, d in files.items() if n.endswith((".blend", ".usdc"))}}


def package(work, lab, output):
    files = members(work, lab)
    result = check(files, lab)
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for name in sorted(files):
            info = zipfile.ZipInfo(name, (2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, files[name])
    return {**verify(output, lab), "bytes": output.stat().st_size, **{"packaged": result["files"]}}


def verify(path, lab):
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)) or any(
                PurePosixPath(n).is_absolute() or ".." in PurePosixPath(n).parts for n in names):
            raise ValueError("unsafe or duplicate archive members")
        expected = {"README.md", "lab.json", "LICENSE", "factory_twin_scene.py", *SCRIPTS,
                    *(f"factory-twin-{m}.{e}" for m in MODES for e in ("blend", "usdc")),
                    *(f"check-{m}.json" for m in MODES)}
        textures = {n for n in names if n.startswith("textures/") and n.count("/") == 1 and n.endswith(".exr")}
        if set(names) != expected | textures:
            raise ValueError("unexpected archive inventory")
        files = {n: archive.read(n) for n in names}
    return check(files, Path(lab))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lab", type=Path, default=ROOT / "docs/factory-twin")
    parser.add_argument("--work", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--verify", type=Path)
    args = parser.parse_args()
    try:
        if args.verify:
            result = verify(args.verify, args.lab)
        elif args.work and args.output:
            result = package(args.work, args.lab, args.output)
        else:
            parser.error("use --work and --output, or --verify")
    except (ValueError, OSError, KeyError, zipfile.BadZipFile) as exc:
        print(json.dumps({"verified": False, "error": str(exc)}))
        return 2
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
