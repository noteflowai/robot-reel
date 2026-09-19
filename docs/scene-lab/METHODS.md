# Scene Lab: captured geometry, editable representations

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
blender --background --factory-startup --disable-autoexec --python-exit-code 1 \
  --python scripts/build_scene_lab.py -- \
  --source checked-source --output original
blender --background --factory-startup --disable-autoexec --python-exit-code 1 \
  --python scripts/build_scene_lab.py -- \
  --source checked-source --edit edited/edit.json --output changed
blender --background --factory-startup --disable-autoexec --python-exit-code 1 \
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
