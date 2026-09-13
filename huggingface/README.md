---
title: Robot Reel
emoji: 🎬
colorFrom: green
colorTo: purple
sdk: static
app_file: index.html
fullWidth: true
header: mini
short_description: Replay SmolVLA trials, GPU cloth and Newton time sculptures.
license: apache-2.0
models:
  - HuggingFaceVLA/smolvla_libero
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
thumbnail: https://huggingface.co/spaces/glayguo/robot-reel/resolve/main/thumbnail.png
pinned: true
---

# Give Physical AI a replay button.

**Three interactive experiments, with their original recordings hosted in this
Space.** Explore a failure, rotate a deforming mesh, or turn physics into a
three-dimensional motion sculpture. No installation or model-service account
is needed to watch.

| Experiment | Try this | Evidence you can take away |
| --- | --- | --- |
| **SmolVLA Stress Lab** | Compare seed 09 under reference and reduced lighting, then inspect all 30 trials. | Two camera views, applied controls, source traces, CSV and MCAP. |
| **GPU Cloth Lab** | Release three identical sheets with different bending coefficients. Orbit, overlay, export a figure, and reopen a checked sample JSON. | 42,471 original vertex samples, positions and velocities, OpenUSD, native Blender checks. |
| **Butterfly Lab** | Orbit twelve Newton worlds released 0.05° apart. | Original poses, measured separation, source clocks and an editable OpenUSD scene. |

The browser replays saved data. **No model inference or simulation runs in this
Space.** SmolVLA inference and the cloth recording used an NVIDIA L40S; the
Butterfly Lab was recorded on CPU. Share links also work when the viewer is
embedded and clipboard access is unavailable.

## Inspect and reproduce

- [Source code, all 13 demos and Chinese README](https://github.com/noteflowai/robot-reel)
- [Complete project website](https://noteflowai.github.io/robot-reel/)
- [SmolVLA protocol and limits](https://github.com/noteflowai/robot-reel/blob/main/docs/stress.md)
- [Cloth data, checked samples and Blender workflow](https://github.com/noteflowai/robot-reel/blob/main/docs/cloth.md)
- [Newton release sweep](https://github.com/noteflowai/robot-reel/blob/main/docs/chaos.md)

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

Robot Reel code and procedural scenes are Apache-2.0. SmolVLA was recorded with
`HuggingFaceVLA/smolvla_libero` revision
`6721902bc4d61e50a3bfdb11dfb4cb626f05d102` using LeRobot.
The model and dataset metadata above identify the recording's sources, not
weights or assets loaded at runtime. Recorded LIBERO images retain their
upstream terms; see [the full media notice](https://github.com/noteflowai/robot-reel/blob/main/docs/stress/NOTICE.txt). This project is
independent and is not endorsed by Hugging Face, the LIBERO authors, Newton or
Blender.

Feedback is welcome in this Space's Community tab or in the
[GitHub issues](https://github.com/noteflowai/robot-reel/issues):
**which recorded policy or simulator output would you want to inspect next?**
