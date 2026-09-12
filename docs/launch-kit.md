# Robot Reel v0.2 launch copy

Drafts for the repository owner to publish. No external outreach has been sent.

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
