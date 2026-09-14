"""Build and verify an inspectable photogrammetry scene without rerunning Blender."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import tempfile
import zipfile

from robot_reel.solver_lab import decode, digest, read

VARIANTS = ("baseline", "edited")
SCENE_FILES = (
    "scene.json", "native-check.json", "edit.json", "preview.png", "scene.glb",
    "terrain.splat", "collision-heightfield.json",
)
VENDOR_FILES = (
    "three.module.min.js", "three.core.min.js", "spark.module.min.js",
    "addons/controls/OrbitControls.js", "addons/loaders/GLTFLoader.js",
    "addons/utils/BufferGeometryUtils.js", "addons/postprocessing/Pass.js",
    "THREE-LICENSE", "SPARK-LICENSE", "vendor.json",
)


def checked_scene(root, *, native=True):
    scene = decode(read(root, "scene.json"))
    check = decode(read(root, "native-check.json"))
    if (
        scene.get("schema") != "robot-reel.scene-lab.v1"
        or scene.get("source", {}).get("license") != "CC0-1.0"
        or scene.get("representations", {}).get("gaussians", {}).get("trained_3dgs") is not False
        or check.get("schema") != "robot-reel.scene-native-check.v1"
        or check.get("passed") is not True
        or check.get("edit") != scene["edit"]
        or check.get("scene_sha256") != scene["files"]["scene.blend"]["sha256"]
    ):
        raise ValueError("scene provenance or native readback is inconsistent")
    names = (*SCENE_FILES[2:], *(("scene.blend",) if native else ()))
    for name in names:
        content = read(root, name)
        if scene["files"].get(name) != {"sha256": digest(content), "bytes": len(content)}:
            raise ValueError(f"scene file identity differs: {name}")
    if decode(read(root, "edit.json")) != {"schema": "robot-reel.scene-edit.v1", **scene["edit"]}:
        raise ValueError("edit recipe differs from the recorded scene")
    count = scene["representations"]["gaussians"]["count"]
    if type(count) is not int or not 1000 <= count <= 100000:
        raise ValueError("invalid Gaussian count")
    if len(read(root, "terrain.splat")) != 32 * count or check["checked_surface_gaussians"] != count:
        raise ValueError("Gaussian records differ from the native check")
    return scene


METHODS = """# Scene Lab: captured geometry, editable representations

The source is Poly Haven's **Coast Rocks 02**, CC0-1.0, photographed and processed
by Rob Tuytel, cleaned up by Rico Cilliers. Each `scene.json` preserves the exact
source URLs, SHA-256 identities, API MD5 values and attribution.

The source mesh is decimated from 1,260,423 polygons to 119,999 triangles.
Units remain metres. The scan is recentered in XY and placed at Z=0.
25,000 area-weighted samples, seed 20260914, form a normal-oriented Gaussian
surface with sampled texture colors. **This is not trained multi-view 3DGS.**
The standard 32-byte SPLAT representation uses browser Y-up coordinates.
Spark 2.2.0 and Three.js 0.180.0 are pinned, locally served MIT dependencies.
The browser uses neutral inspection lighting; the PNG preserves the Blender render.

The separate collision representation samples the highest scanned surface at
65 × 65 points. 1,789 absent samples become the base height. This heightfield
cannot model caves or overhangs and has not been calibrated to real-world contact.
Visual detail must not be treated as collision fidelity.

The edited variant multiplies native terrain Z by 1.4, sets the sun azimuth to
310 degrees and energy to 3. Original settings are 1.0, 135 degrees and 2.
Blender 4.5.13 LTS rendered both scenes with Cycles OptiX, 32 samples, on an
NVIDIA L40S. Independent reopening checks textures, bounds, edit parameters,
all collision samples, both GLB meshes and every SPLAT record.
Readback checks file consistency; it is not producer authentication.

## Reproduce

Use the exact source files listed in `baseline/scene.json`, preserving their
relative names. Verify both size and SHA-256. Copy its `source` object to
`checked-source/source-manifest.json`. Use the repository scripts:

```sh
blender --background --factory-startup --disable-autoexec --python-exit-code 1 \\
  --python scripts/build_scene_lab.py -- \\
  --source checked-source --output original
blender --background --factory-startup --disable-autoexec --python-exit-code 1 \\
  --python scripts/build_scene_lab.py -- \\
  --source checked-source --edit edited/edit.json --output changed
blender --background --factory-startup --disable-autoexec --python-exit-code 1 \\
  --python scripts/check_scene_lab.py -- --scene changed
robot-reel scene-lab --output docs/scene-lab --verify
```

The build script permits only three bounded numeric edit fields. It never
executes code supplied in an edit recipe. Blender output uses `--python-exit-code 1`
so a Python failure cannot be mistaken for a successful render.
Native `.blend` files are in the versioned release's `scene-lab-native.zip`;
the web page loads only GLB/SPLAT data after explicit interaction.

Serve this directory over HTTP, for example `python3 -m http.server 8000`.
ES modules and fetch do not support a double-clicked file URL consistently.
No remote CDN, login, private session or inference server is needed for inspection.
"""


def verify(root):
    root = Path(root)
    manifest = decode(read(root, "manifest.json"))
    expected = {
        "index.html", "scene_lab.js", "METHODS.md",
        *(f"{variant}/{name}" for variant in VARIANTS for name in SCENE_FILES),
        *(f"vendor/{name}" for name in VENDOR_FILES),
    }
    if manifest.get("schema") != "robot-reel.scene-site.v1" or set(manifest.get("files", {})) != expected:
        raise ValueError("scene site inventory differs")
    for name in sorted(expected):
        content = read(root, name)
        if manifest["files"][name] != {"sha256": digest(content), "bytes": len(content)}:
            raise ValueError(f"scene site changed: {name}")
    scenes = {name: checked_scene(root / name, native=False) for name in VARIANTS}
    if scenes["baseline"]["source_manifest_sha256"] != scenes["edited"]["source_manifest_sha256"]:
        raise ValueError("scene variants have different captured sources")
    if scenes["baseline"]["edit"]["terrain_z_scale"] != 1 or scenes["edited"]["edit"]["terrain_z_scale"] != 1.4:
        raise ValueError("published variant labels do not match terrain edits")
    return {"valid": True, "variants": list(scenes), "files": len(expected)}


def build(baseline, edited, vendor, output, native_archive=None):
    sources = {"baseline": Path(baseline), "edited": Path(edited)}
    for path in sources.values():
        checked_scene(path)
    output = Path(output)
    if output.exists():
        raise ValueError("choose a new scene site directory")
    if native_archive and Path(native_archive).exists():
        raise ValueError("choose a new native archive path")
    with tempfile.TemporaryDirectory(prefix="robot-reel-scene-") as temporary:
        stage = Path(temporary) / "site"
        stage.mkdir()
        for variant, source in sources.items():
            (stage / variant).mkdir()
            for name in SCENE_FILES:
                (stage / variant / name).write_bytes(read(source, name))
        for name in VENDOR_FILES:
            destination = stage / "vendor" / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(read(vendor, name))
        for name, source in (("index.html", "scene_lab.html"), ("scene_lab.js", "scene_lab.js")):
            (stage / name).write_bytes(Path(__file__).with_name(source).read_bytes())
        (stage / "METHODS.md").write_text(METHODS)
        files = {
            path.relative_to(stage).as_posix(): {"sha256": digest(path.read_bytes()), "bytes": path.stat().st_size}
            for path in sorted(stage.rglob("*")) if path.is_file()
        }
        (stage / "manifest.json").write_text(json.dumps({
            "schema": "robot-reel.scene-site.v1", "files": files,
        }, indent=2) + "\n")
        verify(stage)
        shutil.copytree(stage, output)
    if native_archive:
        with zipfile.ZipFile(native_archive, "w", zipfile.ZIP_STORED) as archive:
            for variant, source in sources.items():
                for name in ("scene.blend", "scene.json", "native-check.json", "edit.json"):
                    archive.writestr(f"{variant}/{name}", read(source, name))
            archive.writestr("METHODS.md", METHODS)
    return verify(output)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--baseline", type=Path)
    parser.add_argument("--edited", type=Path)
    parser.add_argument("--vendor", type=Path)
    parser.add_argument("--native-archive", type=Path)
    args = parser.parse_args(argv)
    if not args.verify and not all((args.baseline, args.edited, args.vendor)):
        parser.error("building requires --baseline, --edited and --vendor")
    try:
        result = verify(args.output) if args.verify else build(
            args.baseline, args.edited, args.vendor, args.output, args.native_archive,
        )
    except (ValueError, OSError, KeyError) as error:
        parser.exit(2, f"Scene Lab: {error}\n")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
