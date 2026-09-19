---
title: Robot Reel
emoji: 🎬
colorFrom: green
colorTo: purple
sdk: static
app_file: index.html
fullWidth: true
header: default
short_description: Inspect VLA outcomes, Microduck joints and GPU cloth.
license: apache-2.0
models:
  - HuggingFaceVLA/smolvla_libero
  - pollen-robotics/microduck-policies
datasets:
  - lerobot/libero-assets
  - Sylvest/LIBERO-plus
tags:
  - robotics
  - physical-ai
  - smolvla
  - lerobot
  - newton
  - genesis
  - blender
  - openusd
  - simulation
  - policy-evaluation
  - microduck
  - onnx
thumbnail: https://huggingface.co/spaces/glayguo/robot-reel/resolve/main/thumbnail.png
pinned: true
---

# Give Physical AI a replay button.

**Review policy behavior, inspect simulation error, and edit captured scenes.**
Seven interactive experiments include their original recordings, source data
and downloadable files. Start with a workflow below; no installation or
model-service account is needed to explore.

## Choose a starting point

- **Policy review:** compare paired outcomes in SmolVLA Stress Lab, then inspect
  the actions and camera views behind a failure.
- **Simulation diagnostics:** compare Genesis and Newton timesteps in Solver Lab,
  then export the measured errors and original samples.
- **3D creation:** inspect a captured asset in Scene Lab, compare a Blender edit,
  and download the native projects and edit parameters.

## Explore the experiments

| Experiment | Try this | Evidence you can take away |
| --- | --- | --- |
| **Scene Lab** | Replay Microduck on captured terrain; step through the source camera, body poses and contacts, then compare the Blender frame. | All 362 source frames, both original and edited scenes, checked videos, animated USD/Blender projects, GLB/SPLAT and edit recipes. |
| **LIBERO-Plus** | Compare three runs of one task from one paired initial state: baseline, camera and lighting conditions. | Official perturbation IDs, source clips, applied controls and native scene parameters. |
| **Solver Lab** | Compare six Genesis and Newton runs at three timesteps against the analytic flight. | 366 recorded positions/velocities, native Genesis trajectories, OpenUSD, CSV and an offline ZIP. |
| **SmolVLA Stress Lab** | Compare 30 simulation trials on one task: 10 initial states × 3 conditions. Open each paired success or failure. | Paired-outcome report, two camera views, applied controls, source traces, CSV and MCAP. |
| **GPU Cloth Lab** | Release three identical sheets with different bending coefficients. Orbit, overlay, export a figure, and reopen a checked sample JSON. | 42,471 original vertex samples, positions and velocities, OpenUSD, native Blender checks. |
| **Butterfly Lab** | Orbit twelve Newton worlds released 0.05° apart. | Original poses, measured separation, source clocks and an editable OpenUSD scene. |
| **Microduck Motion Lab** | Tap a joint, orbit its body-fixed schematic, overlay targets and reopen a shared frame JSON after checking its facts. | Two original walks, 8,400 measured joint samples, 18,000 body transforms checked against MuJoCo, JSON/CSV and an offline ZIP. |

The browser replays saved data; new inference, simulation and Blender rendering
use the project's local workflows. SmolVLA inference, cloth recording and the Solver Lab used an NVIDIA L40S; the
Butterfly Lab and Microduck policy ran on CPU. Share links also work when the viewer is
embedded and clipboard access is unavailable.

**In Microduck Motion Lab:** use the four view buttons with a keyboard, step between
frames beside the schematic, or follow the link to the original video. If a video
request fails, **Retry video** keeps your selected frame and joint in place.
Frame JSON and joint CSV remain available from the bundled data.

## Inspect and reproduce

[Explore the curated model and data collection](https://huggingface.co/collections/glayguo/robot-reel-physical-ai-replay-lab-6aa67e950ba650285033a4d0): start with this
Space, then inspect the actual policy and asset snapshots behind its recordings.

- [Source code, all recorded demos and Chinese README](https://github.com/noteflowai/robot-reel)
- [Complete project website](https://noteflowai.github.io/robot-reel/)
- [SmolVLA protocol and limits](https://github.com/noteflowai/robot-reel/blob/main/docs/stress.md)
- [Cloth data, checked samples and Blender workflow](https://github.com/noteflowai/robot-reel/blob/main/docs/cloth.md)
- [Solver Lab equations, error measurements and reproduction](https://github.com/noteflowai/robot-reel/blob/main/docs/solver-lab.md)
- [Newton release sweep](https://github.com/noteflowai/robot-reel/blob/main/docs/chaos.md)
- [Review a Microduck frame with an agent and Skills Anywhere](https://github.com/noteflowai/robot-reel/blob/main/docs/agent-review.md)
- [Microduck methods, source model and numerical checks](https://github.com/noteflowai/robot-reel/blob/main/docs/microduck-lab.md)
- [Skill Impact Lab: all 27 model trials, including failures](https://noteflowai.github.io/evalarc/skill-impact/) and [research scope](https://github.com/noteflowai/robot-reel/blob/main/docs/research-pilots.md)

`space-manifest.json` identifies the source Git commit and hashes every
distributed file. Source traces, videos, vertex arrays and native readback
reports retain their original bytes. Navigation is adapted for this Space;
its page manifests and copied offline archives are refreshed accordingly.

## Scope and attribution

The Stress Lab is **one LIBERO Spatial task, ten paired initial states and three
conditions**, with a 160-action limit per trial. Every trial is retained,
including failures. The results describe this simulation experiment; full
benchmark evaluation and real-robot testing require separate runs.

LIBERO-Plus uses a separate three-run plan with a 220-action limit per run.
The baseline and lighting runs succeed; the camera run reaches the limit.
[Its method](https://github.com/noteflowai/robot-reel/blob/main/docs/libero-plus/METHODS.md)
records the selected official perturbations and the shared initial state.

Scene Lab's Gaussians are sampled from the captured mesh; no multi-view 3DGS
training is performed. The heightfield is a geometric collision approximation.
[Its method](https://github.com/noteflowai/robot-reel/blob/main/docs/scene-lab/METHODS.md)
documents the conversion, Blender edits and file checks. The two new motion
recordings include full floating-root poses; both robots fall and slide. Each
uses the same placement rule relative to its terrain, so initial world heights
differ. Browser/native checks establish virtual-camera registration. Full
meshes, body bounds/proxy and recorded-video modes provide explicit fallback.
[L40S and SwiftShader measurements](https://github.com/noteflowai/robot-reel/tree/main/examples/scene-motion)
report render FPS, transfer bytes and sampled memory for the measured build.

Cloth coefficients are solver settings, not calibrated fabric properties; no
collisions or self-contact are modeled. Butterfly sculpture depth represents
time, not physical displacement.

Solver Lab measures integration error in a no-contact, constant-gravity flight.
Its two engines match under these recorded conditions; the experiment is a
timestep diagnostic rather than an engine ranking.

The separate Microduck Motion Lab's 0.3 / 0.5 m/s labels are speed commands, not achieved speeds.
Its schematic fixes the floating root because the original recording did not
save root orientation. Targets are geometric overlays, not independent physics
outcomes. The recordings use the XML PD-actuator fallback, not BAM or hardware.
The original implementation was inspired by
[mishig's Microduck Anatomy](https://huggingface.co/spaces/mishig/microduck-anatomy);
no code, trajectory or assets were copied from that Space.

Robot Reel code and procedural scenes are Apache-2.0. SmolVLA was recorded with
`HuggingFaceVLA/smolvla_libero` revision
`6721902bc4d61e50a3bfdb11dfb4cb626f05d102` using LeRobot.
The model and dataset metadata above identify the recording's sources, not
weights or assets loaded at runtime. Microduck uses
`pollen-robotics/microduck-policies` revision
`088524a64e2557dc453256b6071dbb9d23888802`.
**Microduck model-derived geometry and footage retain the upstream Creative
Commons BY-SA-NC terms (version unspecified); the code license does not
relicense them.** See [its media notice](https://github.com/noteflowai/robot-reel/blob/main/docs/microduck-lab/MICRODUCK-MEDIA-NOTICE.txt).
Recorded LIBERO images retain their
upstream terms; see [the full media notice](https://github.com/noteflowai/robot-reel/blob/main/docs/stress/NOTICE.txt). This project is
independent and is not endorsed by Pollen Robotics, mishig, Hugging Face, the LIBERO authors, Newton or
Blender.

Feedback is welcome in this Space's Community tab or in the
[GitHub issues](https://github.com/noteflowai/robot-reel/issues):
**which recorded policy or simulator output would you want to inspect next?**
