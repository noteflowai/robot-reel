"""Build and verify an inspectable photogrammetry scene without rerunning Blender."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import tempfile
import zipfile

from robot_reel.solver_lab import decode, digest, read
from robot_reel.scene_motion_site import FILES as MOTION_FILES, verify as verify_motion, verify_frame

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

MOTION_METHODS = """
## A recorded robot in the captured scene

The motion extension contains two newly recorded six-second Microduck simulations.
The policy uses the pinned Pollen Robotics ONNX model and XML position actuators.
Inference runs on CPU; MuJoCo image rendering uses the L40S. Each trace retains
181 source frames, 300 policy calls, all 15 body poses, root quaternion, joint
states, controls, camera calibration and measured terrain contact records.
All simulator warning counters are preserved.

Both cases use one placement rule: the maximum height of nine proxy samples
under a 24 cm square, plus 0.125 m. The terrain edit therefore changes the
initial world height and the camera height. These are separate registrations,
not equal-world-state robot robustness trials. Both robots fall and slide;
no success classification is assigned or omitted.

The original heightfield triangles, including their diagonal, are preserved
in the MuJoCo mapping. Native checks compare all 4,225 compiled heights and
8,192 interior ray samples before inference. Independent saved-control replay
checks every stored state and contact, without repeating policy inference.

### Same frame, same virtual camera

Source and Blender coordinates use metres and Z-up. Browser coordinates use
metres and Y-up through `(x, y, z) -> (x, z, -y)`. The robot's original 70
visual geometries are attached to 15 bodies; the browser reuses one GLB for
both cases after checking that its static geometry is identical. Lightweight
body boxes enclose those same visual vertices. They are display aids, not
new collision shapes. The white line is 0.25 m long.

Each source frame has its original physics timestamp at 200 Hz. Source frame
`i` maps to Blender/USD frame `i+1` and video frame `i` at 30 fps. This does not
imply equally spaced physics samples or interpolated new physics states.
The original and Blender videos are lossy encodings; frame-step playback seeks
within the selected video frame. The explicit source frame remains authoritative.

The Recorded Camera uses the trace's axes, position and 45-degree vertical
field of view, letterboxed to 960:540. Blender's 50 mm virtual lens and filmback
produce that same projection. Every body and visual transform is checked in
the reopened saved project at all 181 frames, including all 2,715 body-origin
projections per case. Tolerances are 0.002 pixels for projection and 3e-6 for
world-matrix elements. This establishes virtual-camera registration, not a
physical survey or calibration of a real camera.

Blender motion renders use Cycles OptiX, 24 samples, on the L40S. Every PNG is
hashed before encoding. The MP4 is decoded in full, compared to its corresponding
PNG, and checked for frame count, dimensions and presentation timestamps.
`video-check.json` reports the comparison; no video frame is silently dropped.

### Inspect and reproduce the motion

`motion/motion.json` lists source identities. Each case includes the complete
trace, source simulator and Blender checks, MP4s and animated OpenUSD.
Follow `examples/scene-motion/README.md` in the repository for the pinned
model, registered plan, recording, native export and all-frame check commands.
Use `scripts/encode_scene_motion_video.py` to reproduce the checked encoding.

The Blender project uses the adjacent `motion.usdc` as a relative animation cache.
Keep the two files together when copying a native project. `project.json`
separates portable core files from the producer's complete PNG inventory.
`--check-renders` on the native checker additionally requires all PNGs;
the core project can be reopened without those producer render files.

### Rendering and fallback

Libraries and 3D geometry load after explicit interaction. Motion videos and
frame data can be loaded without a WebGL renderer. An orbit view is separate
from the recorded camera. Native video playback controls are independent;
the source-frame controls resynchronize the two videos and the 3D pose.
The complete small MP4 files are fetched and hash-checked before assigning
local Blob URLs. Frame seeking therefore also works on simple HTTP servers
that do not provide byte-range media responses.

After a three-second warmup, the viewer measures animation-frame intervals
over at least 2.5 seconds. Below 18 render frames/s it selects body bounds and
the collision proxy at pixel ratio 1. If that mode measures below 12 frames/s,
it switches to recorded videos. A manual detail selection disables adaptation.
This is a local responsiveness heuristic, not an engine or device benchmark.
Context loss also leaves the recordings, source-frame controls and downloads.

On the measured server, Chromium 153 rendered full meshes at 60.0 FPS with
NVIDIA L40S Vulkan. Default SwiftShader rendered 3.9 FPS at 1440px and 6.3 FPS
at 390px; body bounds plus proxy reached 53.9 and 59.4 FPS respectively.
Each run used 3 seconds of warmup, 10 seconds of measurement, DPR1 and no
artificial delay. A narrow server viewport is not a physical phone test.
Initial local HTTP payload was 1,690,194 bytes; first full 3D readiness used
19,991,534 cumulative bytes. Sampled Chromium subtree RSS was 636–761 MiB,
including potentially double-counted shared pages; it is not GPU VRAM.
These measurements apply to the saved measurement build, before subsequent
documentation/link edits. See the repository's
[raw report and measured-file inventory](https://github.com/noteflowai/robot-reel/tree/main/examples/scene-motion)
for renderer names, heap samples, timing protocol and exact source identities.

Download the complete portable projects in
[scene-motion-native.zip](https://github.com/noteflowai/robot-reel/releases/download/v0.13.0/scene-motion-native.zip).
Both projects were extracted elsewhere and reopened with all-frame native
checks. The archive includes the standalone checker and instructions.

The captured terrain remains CC0. Microduck-derived geometry and combined
robot footage retain upstream BY-SA-NC terms, with license version unspecified.
Read `motion/NOTICE.txt` before reusing the combined assets.
"""


def verify(root):
    root = Path(root)
    manifest = decode(read(root, "manifest.json"))
    expected = {
        "index.html", "scene_lab.js", "METHODS.md",
        *(f"{variant}/{name}" for variant in VARIANTS for name in SCENE_FILES),
        *(f"vendor/{name}" for name in VENDOR_FILES),
    }
    schema = manifest.get("schema")
    if schema == "robot-reel.scene-site.v2":
        expected |= {"scene_motion_view.js", *(f"motion/{name}" for name in MOTION_FILES)}
    if schema not in {"robot-reel.scene-site.v1", "robot-reel.scene-site.v2"} or set(manifest.get("files", {})) != expected:
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
    result = {"valid": True, "variants": list(scenes), "files": len(expected)}
    if schema == "robot-reel.scene-site.v2":
        result["motion"] = verify_motion(root / "motion", root)
    return result


def build(baseline, edited, vendor, output, native_archive=None, motion=None):
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
        if motion:
            for name in sorted(MOTION_FILES):
                destination = stage / "motion" / name
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(read(motion, name))
            (stage / "scene_motion_view.js").write_bytes(Path(__file__).with_name("scene_motion_view.js").read_bytes())
        (stage / "METHODS.md").write_text(METHODS + (MOTION_METHODS if motion else ""))
        files = {
            path.relative_to(stage).as_posix(): {"sha256": digest(path.read_bytes()), "bytes": path.stat().st_size}
            for path in sorted(stage.rglob("*")) if path.is_file()
        }
        (stage / "manifest.json").write_text(json.dumps({
            "schema": "robot-reel.scene-site.v2" if motion else "robot-reel.scene-site.v1", "files": files,
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
    parser.add_argument("--motion", type=Path, help="Completed and checked scene-motion package")
    parser.add_argument("--frame", type=Path, help="Also verify a received scene frame JSON")
    args = parser.parse_args(argv)
    if not args.verify and not all((args.baseline, args.edited, args.vendor)):
        parser.error("building requires --baseline, --edited and --vendor")
    if args.frame and not args.verify:
        parser.error("--frame requires --verify")
    try:
        result = verify(args.output) if args.verify else build(
            args.baseline, args.edited, args.vendor, args.output, args.native_archive, args.motion,
        )
        if args.frame:
            if args.frame.stat().st_size > 1048576:
                raise ValueError("received frame exceeds 1 MiB")
            result["frame_review"] = verify_frame(args.output / "motion", json.loads(args.frame.read_text()))
    except (ValueError, OSError, KeyError) as error:
        parser.exit(2, f"Scene Lab: {error}\n")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
