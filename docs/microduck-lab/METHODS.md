# Microduck Motion Lab

An original, offline-capable companion to [Microduck Anatomy by mishig](https://huggingface.co/spaces/mishig/microduck-anatomy).
The anatomy viewer prompted a different question: **what did the walking policy
ask each joint to do, and what happened in the recorded simulation?**

[Open the lab](https://noteflowai.github.io/robot-reel/microduck-lab/)
or use the fourth lab in the [Robot Reel Space](https://huggingface.co/spaces/glayguo/robot-reel).
Tap a joint in the schematic (or use the joint selector), drag to orbit, overlay its target pose, click a heatmap
cell, and compare the 0.3 and 0.5 m/s command recordings at the same frame.
The selected joint's complete measured/target curves and signed residual remain
in radians. “Largest residual” searches all 300 frames and all 14 joints in the
selected run; this is a descriptive tracking diagnostic, not a failure label.

## What is recorded, derived and drawn

- **Recorded:** two original 10-second MuJoCo captures, 300 video/telemetry frames
  and 500 ONNX policy steps per run. All 14 measured hinge angles, commanded
  targets, base positions and measured forward speeds retain their original
  values. The 0.3 / 0.5 labels are requested speeds, not achieved speeds.
- **Derived:** forward kinematics from the pinned model, for both measured and
  target joint angles. The floating root is fixed at the origin with identity
  rotation. Original recordings do **not** contain root orientation; the
  schematic does not reconstruct world attitude, balance, foot contact or
  physical motion of the target pose.
- **Drawn:** body-local axis-aligned bounding boxes of the visual mesh vertices,
  joint axes and connecting lines. These are simplified envelopes, not CAD
  meshes, collision shapes or contact surfaces. The target overlay is a
  geometric reference, not another simulated rollout. Orbit controls affect
  only the presentation.
- **Timing:** frame *i* appears at video time *i*/30. The recorded simulation
  sample clock is displayed separately (first sample 0.035 s). A sample's target
  comes from its recorded preceding policy step; video and control clocks are
  not assumed identical. Stand, walk and stop use the recorded command value.
  UI playback follows video time, including buffering and seeking.

The error heatmap uses one fixed 0–0.5 rad color scale in both runs; values above
0.5 saturate. The numeric readout and exported values retain the full residual.
Mean forward speed uses the 210 saved frames with a nonzero command. These two
runs use the same policy and starting pose but are not a robustness benchmark.
Head/neck controls remain part of the official 14-channel policy.

The policy ran on CPU at 50 Hz, with 200 Hz MuJoCo physics, using the XML
position-actuator fallback. **This approximates the motors with PD actuators;
it does not use the official BAM motor model and is not a hardware result.**
The browser performs no policy inference or physics simulation.

## Sources and rights

- [Model and observation conventions](https://github.com/pollen-robotics/microduck_rl/tree/53b8971b61baf5b7f3c16d135dd7cac37623de4b):
  Pollen Robotics, pinned model commit
  `53b8971b61baf5b7f3c16d135dd7cac37623de4b`.
- [Official ONNX policy](https://huggingface.co/pollen-robotics/microduck-policies/tree/088524a64e2557dc453256b6071dbb9d23888802):
  `alpha_walking.onnx`, revision `088524a64e2557dc453256b6071dbb9d23888802`,
  SHA-256 `e36332d383997d51401897734cd3e79cf5038406feddb18b4d57ecfb141daa6c`.
- [Original comparison recordings](https://github.com/noteflowai/robot-reel/tree/main/docs/compare/microduck).
  Their trace and video bytes are copied unchanged; hashes identify each run.
- [Microduck Anatomy reference](https://huggingface.co/spaces/mishig/microduck-anatomy/tree/5329ff5db7c6baa5c15def88085f842e0221395e),
  inspected 2026-09-14. No explicit repository license was found. This lab
  credits the interaction inspiration; it copies no source code, trajectory
  tables, mesh files, fonts or graphics from that Space.

The original upstream README labels **3D models Creative Commons BY-SA-NC,
without specifying a version**. The derived schematic geometry and depicted
footage retain those noncommercial/share-alike terms. Keep
`MICRODUCK-MEDIA-NOTICE.txt` with them. Robot Reel implementation code is
Apache-2.0; its code license does not relicense the robot assets. This is an
independent project, with no implied endorsement by Pollen Robotics or mishig.

## Verify, export and reproduce

The offline ZIP includes both complete traces, both videos, the schematic
description, native MuJoCo readback, embedded viewer and these methods. Unzip
and open `index.html`; no server or external runtime request is needed.
Selected-frame JSON contains the original trace hash, run, joint, policy step,
exact simulation clock, measured angle and target. CSV exports all 4,200 joint
samples of the selected run. Neither export implies a security attestation.
Share links preserve the frame, run, joint, orbit and target visibility.

To review someone else's exported frame, choose **Open frame JSON**. The browser
checks every field against its bundled recording, including the trace hash,
model commit, run, joint, clocks, angles and signed residual. A matching file
restores the run, frame and joint, pauses playback and preserves your orbit and
target visibility. Files stay in the browser; this also works from the offline ZIP.
Changed facts, extra fields, duplicate keys, invalid UTF-8 and files over 16 KiB
are rejected without changing the selected view. This confirms agreement with
the bundled recording; it does not authenticate who sent the file.

From a source checkout, the independent standard-library verifier first checks
the complete lab, then checks the exported frame against those source values:

```bash
# Verify all copied sources, derived transforms, native readback and ZIP members.
python scripts/build_microduck_lab.py --verify

# Check a downloaded or received frame JSON (reads only; no rebuild).
python scripts/build_microduck_lab.py --verify --frame-json /path/to/microduck-right-frame-120.json

# Optional: independently check all 18,000 body transforms against MuJoCo.
# Uses cached pinned model assets; no simulation, policy inference or GPU needed.
python scripts/export_microduck_kinematics.py --check
```

The native check covers every body in both measured and target poses, for both
runs. Position and rotation-matrix differences must each remain below 1e-9.
Standard-library replay verification allows 1e-12 roundoff in derived body
transforms across platform math libraries. Recorded values, source hashes and
video bytes remain exact.
No checks depend on the look of the final preview. The committed preview is
captured from the actual viewer at frame 120, 0.5 m/s run, left knee selected.

To rebuild into a new, empty folder, run `build_microduck_lab.py --output PATH`,
capture the preview with `render_microduck_preview.cjs PATH`, and then run
`build_microduck_lab.py --output PATH --seal`. Model extraction is a separate
step so normal site builds and verification use only the Python standard
library and the committed numeric description.
