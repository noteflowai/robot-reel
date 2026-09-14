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
