# Captured-scene motion recording

This plan records two six-second Microduck simulations on the original and
edited Scene Lab heightfields. Both cases use the same command schedule,
initial-placement rule and camera offsets. The camera and initial root height
are relative to each terrain; the world-space initial states differ.

The recorder checks the 4,225 compiled height samples and the interiors of all
8,192 proxy triangles before inference. The local heightfield is rotated and
reindexed to preserve the existing Blender proxy's triangle diagonal, and its
vertical extent uses the sampled height range. The original display and collision
assets remain unchanged.

Use the reviewed Microduck model at the commit and file hashes listed in
`model-source-check.json`, plus the pinned official ONNX policy identified in
`robot_reel/microduck.py`. Run from a clean source checkout with MuJoCo 3.13.0,
ONNX Runtime 1.30.0, NumPy 2.5.3 and imageio-ffmpeg 0.6.0. The selected policy runs
on CPU; `MUJOCO_GL=egl` enables the available graphics device for recording.

```sh
MUJOCO_GL=egl python scripts/record_scene_motion.py \
  --plan examples/scene-motion/plan.json --case baseline \
  --model /path/to/reviewed/microduck \
  --source-check examples/scene-motion/model-source-check.json \
  --policy /path/to/alpha_walking.onnx --output runs/scene-motion/baseline
python scripts/check_scene_motion.py runs/scene-motion/baseline \
  --output runs/scene-motion/baseline-native-check.json
```

Repeat with `--case edited` and a new output directory. `--preflight-only`
checks source geometry and placement without running the policy. Recording
outputs include the compiled source inputs, full floating-root and joint state,
body transforms, camera parameters, contact samples, policy observations and
outputs, timing, source versions, and video. The checker recomputes body poses
and replays the saved controls without repeating policy inference.

The scene is a top-surface collision approximation, not measured real-world
contact geometry. Microduck uses the XML PD-actuator fallback, not BAM or
hardware. No walking-success threshold or general robustness estimate is defined.
Retain both cases and any errors. Video and robot-derived geometry keep the
upstream Creative Commons BY-SA-NC terms (version unspecified); the recorder
code is Apache-2.0. The captured coast asset is CC0-1.0. See the main repository's
third-party notices.

## USD and Blender

Export the recorded motion, robot geometry, source camera and collision proxy:

```sh
python scripts/export_scene_motion.py runs/scene-motion/baseline \
  --output runs/scene-motion/baseline-export
blender --background --factory-startup --disable-autoexec --python-exit-code 1 \
  --python scripts/build_scene_motion_blender.py -- \
  --scene /path/to/checked/scene-lab-baseline \
  --recording runs/scene-motion/baseline \
  --export runs/scene-motion/baseline-export \
  --output runs/scene-motion/baseline-blender --render-animation
blender --background --factory-startup --disable-autoexec --python-exit-code 1 \
  --python scripts/check_scene_motion_blender.py -- \
  --project runs/scene-motion/baseline-blender \
  --output runs/scene-motion/baseline-blender-check.json --check-renders
```

The USD workflow uses `usd-core==26.3`; the Blender workflow uses 4.5.13 LTS with
Cycles/OptiX. USD and Blender frames are the recorded source index plus one.
Original physics timestamps remain in `trace.json`; interpolation between
recorded frames is presentation, not additional simulation.

Fixed visual attachments are baked into body-local USD vertices to avoid static
Euler decomposition during import. Recorded body poses remain unchanged. glTF
retains shared meshes and quaternion attachments for browser inspection.
Camera filmback and lens units are authored for a metre stage, then checked
against the recorded pixel projection. This is virtual-camera registration;
the captured asset has no independently surveyed scale or real-camera calibration.

Keep `motion.usdc` next to `scene-motion.blend`; its animation cache uses a
relative path. `project.json` separates portable project inputs from the
producer's full PNG inventory. Native geometry/frame checks need the project
inputs; `--check-renders` additionally requires and hashes every listed PNG.
The published native download is `scene-motion-native.zip` in release 0.13.0.
It contains both complete motion projects and a standalone Blender checker.
The [complete producer archive](https://huggingface.co/datasets/glayguo/noteflow-research-pilots/resolve/v2026-09-19-scene-motion/artifacts/scene-motion-producer-20260919.zip)
contains original simulator inputs, every Blender PNG, video checks, browser
readback and a copy of the exact measured site. Both archives retain their
original source traces and license notices; no policy weights are included.
It was extracted to another directory and all 362 frames were checked again;
the projects need no path edits. Producer PNGs are a separate download.

## Browser delivery and received frames

Encode and independently check every rendered frame, repeating for `edited`:

```sh
python scripts/encode_scene_motion_video.py \
  --project runs/scene-motion/baseline-blender \
  --output runs/scene-motion/baseline-video
python scripts/package_scene_motion.py \
  --runs runs/scene-motion --scenes docs/scene-lab \
  --output runs/scene-motion/browser-motion
robot-reel scene-lab \
  --baseline /path/to/checked/scene-lab-baseline \
  --edited /path/to/checked/scene-lab-edited \
  --vendor docs/scene-lab/vendor \
  --motion runs/scene-motion/browser-motion --output runs/scene-motion/site
```

The package command requires both runs, exports, native projects, independent
checks and encoded videos. Its default input names follow the commands above.
`--locations` accepts a JSON object with optional per-case `recording`, `export`,
`project`, `native_check`, `blender_check` and `video` paths relative to `--runs`.
Package checks bind displayed summaries, native reports, source videos and
lightweight body bounds to the recorded source files.

Use the page's **Download this frame JSON** button, then check the received
record against the complete published site with Python 3.12+ and no simulator:

```sh
python -m robot_reel.scene_lab --output docs/scene-lab --verify \
  --frame /path/to/received-frame.json
```

The check includes the original source identity, full frame, camera, coordinate
system and Blender index. Source frame 1 is at **0.035 s** physics time, while
its video presentation timestamp is **1/30 s**. Changing one to the other is
rejected. A consistent record does not establish who produced it.

For an independent graphics check:

```sh
npm ci
npx playwright install chromium
node scripts/check_scene_motion_browser.cjs docs/scene-lab runs/browser-check
python scripts/check_scene_motion_browser_native.py \
  --browser-readback runs/browser-check/readback.json --recordings runs/scene-motion \
  --output runs/browser-check/native-check.json
```

The second command requires MuJoCo and the complete original recording inputs.
The browser checker records every body/visual matrix and projected body origin
for both cases. The native checker recomputes them from MuJoCo state, compares
mesh buffers and contacts, and retains the readback hash. It checks coordinate
and projection agreement, not equality of shaded raster images.

## Measured browser performance

[Raw measurements](performance.json) and the [measured site inventory](measured-site-manifest.json)
identify the actual tested files. Tests used Chromium 153.0.8010.12 on an
AMD EPYC 7R13 host with four logical CPUs and an NVIDIA L40S. Each measurement
used 3 seconds of warmup and 10 seconds of recorded motion, DPR 1 and the
recorded camera. Automatic adaptation was disabled; no artificial delay was
injected. Renderer names distinguish NVIDIA Vulkan from SwiftShader.

| Renderer | Viewport width | Full meshes, render FPS | Body bounds + proxy, render FPS |
| --- | ---: | ---: | ---: |
| NVIDIA L40S Vulkan | 1440 px | 60.0 | 60.0 |
| NVIDIA L40S Vulkan | 390 px | 60.0 | 60.0 |
| SwiftShader | 1440 px | 3.9 | 53.9 |
| SwiftShader | 390 px | 6.3 | 59.4 |

The 390px run is a narrow server viewport, not a physical phone test. The
recording advances at 30 source frames/s regardless of render FPS.
Initial HTTP payload was 1,690,194 bytes; first full 3D readiness used
19,991,534 cumulative bytes. Local click-to-ready measurements ranged from
474 to 987 ms. These localhost, cache-disabled values do not estimate public
network latency. They describe the saved measured build; later documentation
and download-link changes are outside that snapshot.

Peak sampled Chromium process-subtree RSS was 636–761 MiB across these runs.
Shared memory may be counted more than once; this is not GPU memory. Sampled
JavaScript heap ranged from 7.4 to 10.3 MiB. See the raw measurements for each
configuration and sampling count.

The viewer measures its own rendering intervals and switches from full meshes
to body bounds/proxy below 18 FPS, then to recordings below 12 FPS. Manual
selection disables adaptation. These thresholds are a responsiveness heuristic.
The separate browser test injects delay to check both transitions; those
results are excluded from the performance measurements above.
