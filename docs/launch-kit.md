# Robot Reel launch copy

Drafts for the repository owner to publish. No external outreach has been sent.

## Newton / OpenUSD update — September 2026

Run the physics once. Share every pose.

Robot Reel now records a Newton 1.6 double pendulum on CPU and turns it into an
offline 3D browser replay plus an animated OpenUSD scene. Step through the real
poses, share a sample, then import the same motion into Blender. All 362 body
transforms were checked after actual Blender 5.2.1 import.

No GPU, model-service account or downloaded scene assets needed. This is a small
rigid-body example; it does not claim a robot policy, particles or a simulation
benchmark.

Demo: https://noteflowai.github.io/robot-reel/newton/
Preview: `docs/newton/preview.gif`
Reproduce: `pip install -e '.[newton]'`, then `robot-reel newton`

### 中文

物理只运行一次，每个姿态都能分享。

Robot Reel 接入了刚发布的 Newton 1.6：CPU 上运行真实双摆，在浏览器里逐帧检查，
再把同一段运动通过 OpenUSD 带进 Blender。362 个刚体变换均通过实际导入检查；
网页无需安装，录制无需 GPU，也没有模型 API 调用。

可以下载 USD 和源轨迹，把它改成自己的灯光、机位和场景。当前支持的是可复现
的刚体演示，尚未接入任意机器人场景或粒子仿真。

## Earlier launch drafts

## Short post

> A tiny duck, a braking comparison, and an agent-controlled arm.
>
> Robot Reel turns physical-AI simulations into shareable films with interactive
> motion traces. Try the Microduck replay without installing anything: jump to a
> shot, step a frame, and inspect the joint targets.
>
> The Microduck clip uses Pollen's official ONNX policy with a MuJoCo PD-actuator
> approximation. The driving clip is a clearly labeled 1D braking surrogate.
>
> Code and reproducible recordings: https://github.com/noteflowai/robot-reel
> Replay: https://noteflowai.github.io/robot-reel/

## 中文短文案

> 不只看机器鸭走路，也能逐帧看清它是怎么动的。
>
> Robot Reel 新增 Microduck 官方策略仿真、汽车早/晚制动对照，
> 以及可以跳转动作、查看关节曲线、分享具体时刻的交互回放。
>
> 网页无需安装；代码、原始画面、策略动作和校验清单一起开源。
> Microduck 使用 PD 电机近似；汽车是明确标注的一维控制实验。
>
> 演示：https://noteflowai.github.io/robot-reel/

## Submission angle

Lead with the interactive replay, not a claim to have built Microduck or a driving
foundation model. Credit Pollen Robotics prominently. Include the Microduck
media notice when distributing its clip.

Useful feedback to ask for: reproduction failures, missing telemetry, and which
real policy/simulator logs people want to inspect next.

## v0.3 update draft

Two runs. One clock. Robot Reel now compares two official Microduck policy runs
with different speed commands, or early/late braking in a toy vehicle simulation.
Watch synchronized raw footage, pause on a shared frame, inspect a channel, and
download the comparison film with source traces and checksums.

Microduck uses a MuJoCo PD approximation, not hardware. Braking uses scripted
controllers, not an autonomous-driving model. This is a reproducible demo tool,
not a safety benchmark. Code is Apache-2.0; Microduck model media retains upstream
BY-SA-NC terms.

Demo: https://noteflowai.github.io/robot-reel/compare/microduck/

Suggested feedback prompt: Which two compatible runs would you want to inspect
on one timeline?

## Blender update draft

Keep the motion. Change the scene.

Robot Reel now takes a verified braking recording into Blender 5.2: two cameras,
procedural materials, recorded-position keyframes, and animated speed/gap/contact
channels. Download the editable .blend or reproduce it from the included source
comparison. The saved-project check covers all 360 vehicle samples and held
positions between frames.

This is a stylized replay of a toy MuJoCo experiment. It does not rerun physics
in Blender or claim an autonomous-driving result.

Useful feedback: Which recorded simulation would you want to relight or inspect
from a different angle? Full robot import and a Blender MCP adapter are not shipped.
