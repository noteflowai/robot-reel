# Robot Reel

**Words in. Motion out. Keep the proof.**

Turn a robot simulation into a shareable film, with the motion trace beside it.
Robot Reel records MuJoCo frames, overlays measured joint positions, and exports
landscape and portrait videos. An optional Strands agent directs the arm through
bounded tools; the default demo needs no model credentials.

[中文说明](README.zh-CN.md)

![Robot Reel recorded simulation preview](docs/media/preview.gif)

[Watch the film](https://noteflowai.github.io/robot-reel/) · [Download videos and evidence](https://github.com/noteflowai/robot-reel/releases/tag/v0.1.0)


## What the demo actually does

| Scene | How it moves | What is recorded |
| --- | --- | --- |
| SO-100 arm | Position actuators, smooth targets, real `mj_step` physics | Every video frame's measured joint positions, targets, simulation time, and per-action tracking error |
| Unitree G1 | Scripted joint-space poses with a fixed root and `mj_forward` | Pose values, explicitly labeled **kinematic** |

The optional agent inspects joint limits and the asset-defined home pose, then
issues four tool calls: sweep left, sweep right, rotate the wrist/open the jaw,
and return home. This is a constrained demonstration, not an autonomous task
planner. G1 does not walk or demonstrate a learned balancing policy.

Inference pauses are omitted from the edit. Motion frames stay in order.
All robot footage comes from the simulator; titles and overlays are drawn in code.
The soundtrack is an original synthesized pattern, with no third-party samples.

## Quick start

Python 3.12+ and a working OpenGL backend are required. First use may download
robot assets through `robot_descriptions`.

```bash
git clone https://github.com/noteflowai/robot-reel.git
cd robot-reel
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e .
robot-reel --output artifacts/my-first-film
python -m robot_reel.verify artifacts/my-first-film
```

Linux defaults to EGL. For software rendering, install your system's OSMesa
library and set `MUJOCO_GL=osmesa`. macOS users should set `MUJOCO_GL=glfw`.
The initial release was tested on Linux with an NVIDIA L40S and EGL.

The demo writes:

```text
robot-reel.mp4             1280 × 720, 30 fps
robot-reel-vertical.mp4     720 × 1280, 30 fps
poster.png
so100-raw.mp4              Original simulator view
unitree_g1-raw.mp4
so100-trace.json           Per-frame telemetry and action results
unitree_g1-trace.json
manifest.json             Provenance, versions, SHA-256 file checksums
```

The film lasts 31 seconds: a two-second title, sixteen seconds of arm motion,
ten seconds of G1 poses, and a three-second closing card.

## Let an agent direct the arm

Configure AWS credentials using the normal SDK credential chain. Choose a
Bedrock model or inference profile available in your region:

```bash
robot-reel --agent \
  --model YOUR_BEDROCK_MODEL_OR_INFERENCE_PROFILE \
  --region us-west-2 \
  --output artifacts/agent-film
```

This invokes a live, billable model. It also saves `prompt.txt` and
`agent-response.txt`. The agent tools reject unknown joints, nonfinite angles,
and out-of-range targets; no hardware mode is exposed. Agent behavior can vary:
the capture rejects runs that do not contain exactly four completed motions.
The verifier additionally checks final tracking and home error against a
0.05-radian demo tolerance.

```bash
robot-reel --render-only --output artifacts/agent-film
```

Re-edit existing frames without another inference call. Use a fresh directory
for a new capture; existing recordings are not silently overwritten.

## Why a separate project?

[Strands Robots](https://github.com/strands-labs/robots) provides the robot and
agent integration. [LeRobot](https://github.com/huggingface/lerobot) provides
tools for robot learning. Robot Reel focuses on a narrower deliverable:
**a reproducible robot demo that comes with a film and inspectable evidence**.
It builds on those ecosystems rather than claiming to replace them.

This preview supports two scenes, one backend, and one optional model provider.
The backend adapter currently uses private Strands Robots fields and pins
version 0.5.1. Hashes detect changed files relative to the manifest; they are
not signatures and do not establish third-party authenticity or task success.

## Development

```bash
python -m unittest discover -s tests -v
robot-reel --output artifacts/smoke
python -m robot_reel.verify artifacts/smoke
```

Useful contributions: a public backend adapter, better portable font support,
recording real policy rollouts, and more independently verifiable robot tasks.
See [CONTRIBUTING.md](CONTRIBUTING.md).

Apache-2.0 for this code. Robot assets retain their original licenses and are
downloaded separately. See [THIRD_PARTY.md](THIRD_PARTY.md).
