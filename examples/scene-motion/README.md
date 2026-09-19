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

This directory provides the recording and native-checking workflow. Browser,
USD and Blender delivery will include their own readback and performance records.
