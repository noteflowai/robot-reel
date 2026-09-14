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
tags:
  - robotics
  - physical-ai
  - smolvla
  - lerobot
  - newton
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

**Four interactive experiments, with their original recordings hosted in this
Space.** Explore a failure, rotate a deforming mesh, or turn physics into a
three-dimensional motion sculpture. Inspect the 14 joints inside a learned
Microduck walk. No installation or model-service account
is needed to watch.

| Experiment | Try this | Evidence you can take away |
| --- | --- | --- |
| **SmolVLA Stress Lab** | Group paired successes and failures, open any seed, then inspect all 30 trials. | Paired-outcome report, two camera views, applied controls, source traces, CSV and MCAP. |
| **GPU Cloth Lab** | Release three identical sheets with different bending coefficients. Orbit, overlay, export a figure, and reopen a checked sample JSON. | 42,471 original vertex samples, positions and velocities, OpenUSD, native Blender checks. |
| **Butterfly Lab** | Orbit twelve Newton worlds released 0.05° apart. | Original poses, measured separation, source clocks and an editable OpenUSD scene. |
| **Microduck Motion Lab** | Select a joint, orbit its body-fixed schematic, overlay targets and inspect the residual heatmap. | Two original walks, 8,400 measured joint samples, 18,000 body transforms checked against MuJoCo, JSON/CSV and an offline ZIP. |

The browser replays saved data. **No model inference or simulation runs in this
Space.** SmolVLA inference and the cloth recording used an NVIDIA L40S; the
Butterfly Lab and Microduck policy ran on CPU. Share links also work when the viewer is
embedded and clipboard access is unavailable.

## Inspect and reproduce

[Explore the curated model and data collection](https://huggingface.co/collections/glayguo/robot-reel-physical-ai-replay-lab-6aa67e950ba650285033a4d0): start with this
Space, then inspect the actual policy and asset snapshots behind its recordings.

- [Source code, all 14 demos and Chinese README](https://github.com/noteflowai/robot-reel)
- [Complete project website](https://noteflowai.github.io/robot-reel/)
- [SmolVLA protocol and limits](https://github.com/noteflowai/robot-reel/blob/main/docs/stress.md)
- [Cloth data, checked samples and Blender workflow](https://github.com/noteflowai/robot-reel/blob/main/docs/cloth.md)
- [Newton release sweep](https://github.com/noteflowai/robot-reel/blob/main/docs/chaos.md)
- [Microduck methods, source model and numerical checks](https://github.com/noteflowai/robot-reel/blob/main/docs/microduck-lab.md)

`space-manifest.json` identifies the source Git commit and hashes every
distributed file. Source traces, videos, vertex arrays and native readback
reports retain their original bytes. Navigation is adapted for this Space;
its page manifests and copied offline archives are refreshed accordingly.

## Scope and attribution

The Stress Lab is **one LIBERO Spatial task, ten paired initial states and three
conditions**, with a 160-action limit per trial. Every trial is retained,
including failures. It is a controlled diagnostic, not an official LIBERO score
or a real-robot result.

Cloth coefficients are solver settings, not calibrated fabric properties; no
collisions or self-contact are modeled. Butterfly sculpture depth represents
time, not physical displacement.

Microduck's 0.3 / 0.5 m/s labels are speed commands, not achieved speeds.
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
