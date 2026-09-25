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
Eight interactive experiments include their original recordings, source data
and downloadable files. Start with a workflow below; no installation or
model-service account is needed to explore.

Install the CLI from [PyPI](https://pypi.org/project/robot-reel/) with
`python -m pip install robot-reel==0.16.0` (Python 3.12+).
See the [installation guide](https://github.com/noteflowai/robot-reel/blob/main/docs/distribution.md)
for optional dependencies and verified downloads.

## Review a model explanation

The Qwen3.8 review pairs six actual model outputs with three original SmolVLA
episodes. Compare sampled images with images plus outcome records, replay both
cameras and download every response and independent fact check. Explanations
remain unverified interpretations.
[Method and source records](https://github.com/noteflowai/robot-reel/blob/main/docs/model-review.md).

[First review with the published CLI](https://github.com/noteflowai/robot-reel/blob/main/docs/first-claim-review.md): Install the released CLI and check one original model response against its recorded robot trace.
The 30-second walkthrough uses four annotated views of the actual interface,
with captions and source hashes. No GPU or model-service account is needed.

## Choose a starting point

- **Policy review:** compare paired outcomes in SmolVLA Stress Lab, then inspect
  the actions and camera views behind a failure.
- **Simulation diagnostics:** compare Genesis and Newton timesteps in Solver Lab,
  then export the measured errors and original samples.
- **3D creation:** inspect a captured asset in Scene Lab, compare a Blender edit,
  and download the native projects and edit parameters.

## Explore the experiments

- **Scene Lab.** Replay Microduck on captured terrain, inspect its camera, body
  poses and contacts, and compare the Blender frame. Take away all 362 source
  frames, both original and edited scenes, checked videos, animated USD and
  Blender projects, GLB, SPLAT and edit recipes.
- **LIBERO-Plus.** Compare baseline, camera and lighting runs of one task from
  one paired initial state. Inspect official perturbation IDs, source clips,
  applied controls and native scene parameters.
- **Solver Lab.** Compare six Genesis and Newton runs at three timesteps
  against the analytic flight. Download 366 positions and velocities, native
  Genesis trajectories, OpenUSD, CSV and an offline ZIP.
- **SmolVLA Stress Lab.** Open each paired success or failure across 30 trials
  on one task: 10 initial states × 3 conditions. Keep the outcome report,
  two camera views, applied controls, source traces, CSV and MCAP.
- **GPU Cloth Lab.** Orbit and overlay three sheets with different bending
  coefficients, export a figure and reopen a checked sample JSON. Inspect
  42,471 vertex samples, positions and velocities, OpenUSD and native Blender checks.
- **Butterfly Lab.** Orbit twelve Newton worlds released 0.05° apart.
  Follow original poses, measured separation and source clocks, or edit the
  exported OpenUSD scene.
- **Microduck Motion Lab.** Tap a joint, orbit its body-fixed schematic,
  overlay targets and reopen a checked frame JSON. Download two walks, 8,400
  joint samples, 18,000 body transforms checked against MuJoCo, JSON, CSV and
  an offline ZIP.

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

## Methods and reuse

Each lab answers a specific question using a recorded experiment. Results apply
to its stated task, conditions and simulator configuration. All recorded trials,
including failures, remain available for inspection.

<details>
<summary>Recording methods and experiment boundaries</summary>

- **Stress Lab:** one LIBERO Spatial task, ten paired initial states, three
  conditions; at most 160 actions per trial. Full-benchmark and real-robot
  evaluation require separate runs. [Protocol and results](https://github.com/noteflowai/robot-reel/blob/main/docs/stress.md).
- **LIBERO-Plus:** a separate three-run plan with a 220-action limit. Baseline
  and lighting succeed; the camera run reaches the limit.
  [Selected perturbations and shared initial state](https://github.com/noteflowai/robot-reel/blob/main/docs/libero-plus/METHODS.md).
- **Scene Lab:** Gaussians are sampled from a captured mesh, without multi-view
  3DGS training. The collision heightfield approximates its geometry. Both
  floating-root motion recordings retain falls and slides. The shared
  terrain-relative placement rule gives different initial world heights.
  [Asset conversion](https://github.com/noteflowai/robot-reel/blob/main/docs/scene-lab/METHODS.md) ·
  [Virtual-camera checks, rendering modes and measured performance](https://github.com/noteflowai/robot-reel/tree/main/examples/scene-motion).
- **Cloth Lab:** bending coefficients are solver settings; fabric properties
  are uncalibrated. Collisions and self-contact are disabled.
  [Recording and native checks](https://github.com/noteflowai/robot-reel/blob/main/docs/cloth.md).
- **Butterfly Lab:** sculpture depth encodes time. Recorded poses supply the
  physical displacement. [Release sweep](https://github.com/noteflowai/robot-reel/blob/main/docs/chaos.md).
- **Solver Lab:** timestep diagnostics for no-contact, constant-gravity
  flight. Both engines match in these conditions; this experiment does not
  rank simulators. [Equations and error measurements](https://github.com/noteflowai/robot-reel/blob/main/docs/solver-lab.md).
- **Microduck Motion Lab:** the 0.3 / 0.5 m/s labels are commands. The schematic
  fixes the root because its recording lacks root orientation. Targets are
  geometric overlays. Runs use the XML PD-actuator fallback, without BAM or
  hardware validation. [Model and numerical checks](https://github.com/noteflowai/robot-reel/blob/main/docs/microduck-lab.md).

</details>

### Attribution and asset licenses

Microduck Motion Lab's interaction design was inspired by
[mishig's Microduck Anatomy](https://huggingface.co/spaces/mishig/microduck-anatomy).
Its code, trajectories and assets were developed or sourced separately.

Robot Reel code and procedural scenes are Apache-2.0. SmolVLA was recorded with
`HuggingFaceVLA/smolvla_libero` revision
[6721902](https://huggingface.co/HuggingFaceVLA/smolvla_libero/tree/6721902bc4d61e50a3bfdb11dfb4cb626f05d102) using LeRobot.
The model and dataset metadata above identify the recording's sources, not
weights or assets loaded at runtime. Microduck uses
`pollen-robotics/microduck-policies` revision
[088524a](https://huggingface.co/pollen-robotics/microduck-policies/tree/088524a64e2557dc453256b6071dbb9d23888802).
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
