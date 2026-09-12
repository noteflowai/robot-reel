<p align="center">
  <a href="https://noteflowai.github.io/robot-reel/remix/">
    <picture>
      <source media="(prefers-reduced-motion: reduce)" srcset="docs/showcase/hero.png">
      <img src="docs/showcase/hero.gif" width="100%" alt="Robot Reel — Physical AI. In motion. On record. Three real demos: SmolVLA robot actions, an MCP Blender director, and Newton physics exported to OpenUSD.">
    </picture>
  </a>
</p>

<h1 align="center">Give Physical AI a replay button.</h1>

<p align="center">
  Real policy rollouts. Films you can inspect. 3D scenes you can edit.<br>
  Watch the behavior, step through the evidence, and take the scene with you.
</p>

<p align="center">
  <a href="https://github.com/noteflowai/robot-reel/actions/workflows/check.yml"><img src="https://github.com/noteflowai/robot-reel/actions/workflows/check.yml/badge.svg?branch=main" alt="CI status"></a>
  <a href="https://github.com/noteflowai/robot-reel/releases/latest"><img src="https://img.shields.io/github/v/release/noteflowai/robot-reel?color=79dfc3&amp;label=release" alt="Latest release"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/code-Apache--2.0-c1b1ff" alt="Code license: Apache-2.0"></a>
  <a href="https://noteflowai.github.io/robot-reel/"><img src="https://img.shields.io/badge/live%20demos-12%20replays-ffca85" alt="Live demos: 12 replays"></a>
  <a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/python-3.12%2B-3776ab" alt="Python 3.12+"></a>
  <a href="https://github.com/noteflowai/robot-reel/stargazers"><img src="https://img.shields.io/github/stars/noteflowai/robot-reel?style=flat&amp;color=edf4ef" alt="GitHub stars"></a>
</p>

<p align="center">
  <a href="https://noteflowai.github.io/robot-reel/stress/"><strong>◉ Explore the Stress Lab</strong></a> &nbsp; · &nbsp;
  <a href="https://noteflowai.github.io/robot-reel/chaos/"><strong>✦ Enter the Butterfly Lab</strong></a> &nbsp; · &nbsp;
  <a href="https://noteflowai.github.io/robot-reel/remix/"><strong>◐ Try the before / after</strong></a> &nbsp; · &nbsp;
  <a href="https://github.com/noteflowai/robot-reel/releases/latest"><strong>Download the demos ↓</strong></a> &nbsp; · &nbsp;
  <a href="README.zh-CN.md">中文</a>
</p>

<p align="center"><sub>No account or install to watch. Preview panels show independent recorded runs.</sub></p>

## Quick start

Python 3.12+ and the standard library are enough to check a real recording:

```bash
git clone https://github.com/noteflowai/robot-reel.git
cd robot-reel

# Check the recorded policy episode and its evidence.
python3 -m robot_reel.cli vla docs/vla

# Turn the included braking comparison into a checked storyboard.
python3 -m robot_reel.cli direct docs/compare/braking \
  --plan examples/contact-storyboard.json --output artifacts/director
```

[![Open in Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/noteflowai/robot-reel/blob/main/examples/quickstart.ipynb)
Or use the [verified installation packages or non-root Docker image](docs/distribution.md).
Recording new runs needs the [full runtime](docs/recording.md); the browser demos need nothing.


## New / Same task. Change the view.

**The Stress Lab.** SmolVLA runs the same task under reference lighting, reduced
light and a shifted camera. Explore **30 real closed-loop trials** across ten
paired initial states. Select any outcome in the matrix, compare both policy
cameras, and jump to the largest measured trajectory difference. Recorded with
**NVIDIA L40S / CUDA inference**, with hardware and timing in every trace.

<a href="https://noteflowai.github.io/robot-reel/stress/">
  <picture>
    <source media="(prefers-reduced-motion: reduce)" srcset="docs/stress/poster.png">
    <img src="docs/stress/preview.gif" width="100%" alt="Three real SmolVLA rollouts from the same initial state under reference lighting, reduced light and a shifted camera. Each view retains its source sample and actual outcome.">
  </picture>
</a>

**[Compare the policy runs ↗](https://noteflowai.github.io/robot-reel/stress/)** ·
[Complete offline lab ↓](https://github.com/noteflowai/robot-reel/releases/download/v0.4.0/robot-reel-stress-experiment.zip) ·
[MCAP telemetry ↓](https://noteflowai.github.io/robot-reel/stress/telemetry.mcap) ·
[Open it in Foxglove](docs/telemetry.md) ·
[Reproduce & inspect](docs/stress.md)

<sub>One task × three native scene conditions × ten paired seeds. Fixed budget:
160 actions / 8 simulation seconds per trial. Every trial is retained; execution
errors stay in the attempt ledger. Inspect applied controls, measured state,
separate inference/simulation timings and per-condition confidence intervals.
This is a controlled diagnostic, not an official LIBERO benchmark score.
Preview plays on simulation time; shorter runs explicitly hold their final sample.</sub>

## Same seed. Different endings.

**Native Rerun inspection.** Open three paired Stress Lab trials with six
embedded camera videos, measured 3D end-effector paths, applied controls and
policy-timing curves on one clock. The portable recording keeps the original
JSON and has been read back against every source sample.

<a href="https://app.rerun.io/version/0.37.2/?url=https%3A%2F%2Fnoteflowai.github.io%2Frobot-reel%2Frerun%2Fseed-09.rrd"><img src="docs/rerun/preview.png" width="100%" alt="Actual Rerun workspace with three policy camera views, measured 3D paths and applied-control curves from paired seed 09."></a>

**[Open the Rerun workspace ↗](https://app.rerun.io/version/0.37.2/?url=https%3A%2F%2Fnoteflowai.github.io%2Frobot-reel%2Frerun%2Fseed-09.rrd)** ·
[Portable recording ↓](https://noteflowai.github.io/robot-reel/rerun/seed-09.rrd) ·
[Rebuild & verify](docs/telemetry.md#native-rerun-workspace)

<sub>Selected seed 09: reference succeeds; dim lighting and the shifted camera
reach the step limit. 405 observations · 41 policy calls · 6 embedded videos.
The full experiment still contains 30 trials. Desktop browser recommended;
the downloaded file opens locally in Rerun 0.37.2.</sub>

## 0.05° apart. Worlds apart.

**The Butterfly Lab.** Twelve isolated Newton worlds begin at nearly identical angles.
Their recorded paths become a luminous 3D time sculpture. Drag to orbit, switch
to a motion overlay, and find the moment a tiny release difference becomes a
6.26 m gap.

<a href="https://noteflowai.github.io/robot-reel/chaos/">
  <picture>
    <source media="(prefers-reduced-motion: reduce)" srcset="docs/chaos/poster.png">
    <img src="docs/chaos/preview.gif" width="100%" alt="Twelve measured Newton pendulum trajectories unfold into a colored time sculpture. Depth represents simulation time; adjacent releases differ by 0.05 degrees.">
  </picture>
</a>

**[Explore the Butterfly Lab ↗](https://noteflowai.github.io/robot-reel/chaos/)** ·
[OpenUSD scene ↓](https://noteflowai.github.io/robot-reel/chaos/scene.usdc) ·
[Offline experiment ↓](https://noteflowai.github.io/robot-reel/chaos/experiment.zip) ·
[Reproduce & inspect](docs/chaos.md)

<sub>601 samples × 12 worlds. All 14,424 body poses checked in native Blender.
Adjacent release offsets are 0.05°; the sweep spans 0.55°. The largest recorded
gap is world 04 versus 01 (+0.15°), at 12.5 s. Sculpture depth represents time,
not physical travel. Preview plays at 3.33×; the interactive replay defaults to 1×.</sub>

## One recording. Two looks.

Drag between the original MuJoCo simulation and its Blender replay. Jump to
the recorded contact, step both views together, then take the editable scene
into your own project.

<a href="https://noteflowai.github.io/robot-reel/remix/">
  <picture>
    <source media="(prefers-reduced-motion: reduce)" srcset="docs/remix/poster.png">
    <img src="docs/remix/preview.gif" width="100%" alt="Animated divider between the original MuJoCo footage and its Blender replay, with the same recorded source frame and simulator time.">
  </picture>
</a>

**[Drag to compare ↗](https://noteflowai.github.io/robot-reel/remix/)** ·
[How the samples match](docs/remix.md) ·
[Download the Blender scene](https://noteflowai.github.io/robot-reel/blender/replay.blend)

## Choose your front-row seat

<table>
<tr>
<td width="50%" valign="top">
<h3>01 / Words → robot actions</h3>
<a href="https://noteflowai.github.io/robot-reel/vla/"><img src="docs/showcase/vla.png" width="100%" alt="SmolVLA's scene and wrist cameras after the recorded bowl-to-plate task."></a>
<p>A language instruction becomes an actual SmolVLA rollout in LIBERO. Inspect both camera views, measured state and each applied control.</p>
<p><strong>76 actions · one completed simulation task</strong></p>
<p><a href="https://noteflowai.github.io/robot-reel/vla/">Play the task ↗</a> · <a href="docs/vla.md">Reproduce it</a> · <a href="https://noteflowai.github.io/robot-reel/vla/episode.zip">Episode + evidence ↓</a></p>
</td>
<td width="50%" valign="top">
<h3>02 / Brief → Blender film</h3>
<a href="https://noteflowai.github.io/robot-reel/director/"><img src="docs/showcase/director.png" width="100%" alt="A Blender camera shows two recorded braking trials at the contact sequence."></a>
<p>Connect an MCP agent to plan camera cuts, captions and slow motion. Build an editable film whose frames map back to the original recording.</p>
<p><strong>4 camera views · all 180 source samples retained</strong></p>
<p><a href="https://noteflowai.github.io/robot-reel/director/">Explore the film ↗</a> · <a href="docs/director.md">Connect an agent</a> · <a href="https://noteflowai.github.io/robot-reel/director/project.zip">Blender project ↓</a></p>
</td>
</tr>
<tr>
<td width="50%" valign="top">
<h3>03 / Physics → editable 3D</h3>
<a href="https://noteflowai.github.io/robot-reel/newton/"><img src="docs/showcase/newton.png" width="100%" alt="Recorded Newton double-pendulum poses and their motion trail in the browser's 3D replay."></a>
<p>Record Newton physics on CPU. Explore measured poses in a browser, then open the animated OpenUSD scene in Blender to light, edit and render.</p>
<p><strong>181 source samples · 362 checked body transforms</strong></p>
<p><a href="https://noteflowai.github.io/robot-reel/newton/">Inspect the physics ↗</a> · <a href="docs/newton.md">Build the scene</a> · <a href="https://noteflowai.github.io/robot-reel/newton/scene.usda">OpenUSD ↓</a></p>
</td>
<td width="50%" valign="top">
<h3>04 / A tiny robot. A learned policy.</h3>
<a href="https://noteflowai.github.io/robot-reel/microduck/"><img src="docs/microduck/media/poster.png" width="100%" alt="Microduck's official ONNX walking policy recorded in MuJoCo, with measured joint telemetry."></a>
<p>Watch Pollen Robotics' Microduck walk with its official ONNX policy. Follow joint targets, measured responses and base motion, or compare two speed commands.</p>
<p><strong>50 Hz policy · 14 joint targets and responses</strong></p>
<p><a href="https://noteflowai.github.io/robot-reel/microduck/">Meet Microduck ↗</a> · <a href="https://noteflowai.github.io/robot-reel/compare/microduck/">Compare speeds</a> · <a href="docs/recording.md">Record your own</a></p>
</td>
</tr>
</table>

**More scenes:** [Early vs. late braking](https://noteflowai.github.io/robot-reel/compare/braking/) ·
[SO-100 arm studio](https://noteflowai.github.io/robot-reel/studio/) ·
[Editable braking scene](https://noteflowai.github.io/robot-reel/blender/)

## Keep the run behind the film

| Watch | Inspect | Reuse |
| --- | --- | --- |
| Browser replays, synchronized views, shot navigation and frame links. | Applied actions, measured poses, recorded outcomes and source revisions. | Offline episodes, MP4s, JSON traces, editable Blender projects and OpenUSD scenes. |

**The evidence travels with the demo.** Validators check file hashes, timestamps,
frame mappings and outcome consistency. Native Blender checks cover all 420
vehicle samples in the directed film and all 362 body transforms in the Newton
import. [Director check](docs/director/animation-check.json) ·
[Newton check](docs/newton/blender-check.json).

The browser plays recorded simulations. The VLA example is one seeded rollout,
with inference waiting time omitted; new director briefs use your connected
agent and a new render. Microduck uses the XML PD-actuator fallback.
[Scope, provenance and asset terms](THIRD_PARTY.md).

## How it differs

Robot Reel is not a simulator, a training framework or a benchmark. It sits
after them: it records a run from those tools, verifies the trace, and turns it
into something people can watch, inspect and reuse.

| | Focus | Where Robot Reel fits |
| --- | --- | --- |
| [LeRobot](https://github.com/huggingface/lerobot) | Datasets, policies and training for real and simulated robots | Runs a LeRobot policy (SmolVLA), then keeps every applied action, both cameras and the hardware/timing record as a replay |
| [MuJoCo Playground](https://github.com/google-deepmind/mujoco_playground), [Isaac Lab](https://github.com/isaac-sim/IsaacLab) | GPU-scale environments and RL training | Takes a single rollout from a simulator and makes it inspectable, comparable and editable |
| [Genesis](https://github.com/Genesis-Embodied-AI/Genesis), [Newton](https://github.com/newton-physics/newton) | Physics engines | Records Newton on CPU and exports the measured motion as an animated OpenUSD scene with a native Blender check |
| Rerun, Foxglove | General telemetry viewers | Publishes self-contained HTML replays, MCAP telemetry and a verified native Rerun workspace with embedded videos |

What is unique here is the chain: hash-verified traces, paired comparisons on
one clock, an MCP agent that directs a Blender film from the recording, and 3D
scenes whose keyframes map back to the original samples.

## Build your own scene

Choose the workflow you want to build:

| I want to… | Start here |
| --- | --- |
| Run paired VLA stress trials on GPU | [CUDA setup, fixed experiment and evidence checks](docs/stress.md) |
| Inspect paired trials in Rerun | [Portable video, 3D paths and native readback](docs/telemetry.md#native-rerun-workspace) |
| Run SmolVLA locally | [Isolated CPU environment + pinned models](docs/vla.md) |
| Let an agent direct a film | [MCP setup + Blender build/render](docs/director.md) |
| Export real physics to a DCC | [Newton → OpenUSD → Blender](docs/newton.md) |
| Explore a physics parameter sweep | [Butterfly Lab → twelve isolated worlds](docs/chaos.md) |
| Record Microduck, braking or the arm | [Recording packs + runtime setup](docs/recording.md) |
| Compare two captured runs | [Comparison contract + CLI](docs/comparison.md) |

## Make the next scene

Contributions with a working replay and inspectable source data are welcome:
new simulation adapters, measured policy comparisons, accessible viewers and
editable 3D exports. [Contributing](CONTRIBUTING.md) ·
[Development and checks](docs/recording.md#development) ·
[Issues](https://github.com/noteflowai/robot-reel/issues).

Built with [LeRobot](https://github.com/huggingface/lerobot),
[MuJoCo](https://github.com/google-deepmind/mujoco),
[Newton](https://github.com/newton-physics/newton),
[Blender](https://www.blender.org),
[OpenUSD](https://github.com/PixarAnimationStudios/OpenUSD),
[Strands Robots](https://github.com/strands-labs/robots), and
[Pollen Robotics](https://github.com/pollen-robotics/microduck).

<sub>Recorder code: Apache-2.0. VLA images retain their <a href="licenses/VLA-MEDIA-NOTICE.txt">upstream attribution and asset terms</a>; Microduck media retains its <a href="docs/microduck/media/MICRODUCK-MEDIA-NOTICE.txt">noncommercial/share-alike terms</a>. The <a href="docs/showcase/manifest.json">cover's source mapping</a> and <a href="docs/showcase/NOTICE.txt">media notice</a> accompany the preview. Independent project; no upstream endorsement is implied.</sub>
