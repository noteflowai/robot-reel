# Robot Reel launch copy

Drafts for the repository owner to publish. No external outreach has been sent.

## Landing page, Stress Lab and Butterfly Lab — September 2026

Assets: social preview `docs/showcase/social.png` (upload once under Settings →
Social preview), landing page https://noteflowai.github.io/robot-reel/, Stress
Lab GIF `docs/stress/preview.gif`, Butterfly Lab GIF `docs/chaos/preview.gif`.
Timing hook: Newton 1.6 shipped days ago and the Butterfly Lab records it.

### Show HN title candidates (≤ 80 characters)

- Show HN: Robot Reel – a replay button for physical AI (SmolVLA, Newton, Blender)
- Show HN: 30 real SmolVLA rollouts you can step through frame by frame, in the browser
- Show HN: Twelve Newton worlds 0.05° apart, recorded as a 3D time sculpture

### Show HN first comment

> Robot Reel records a run from a robotics stack and turns it into something you
> can watch, inspect and reuse. Nothing is re-simulated in the browser; every page
> is a self-contained HTML file with the source trace and checksums next to it.
>
> Two new demos. The Stress Lab runs SmolVLA on the same LIBERO task under
> reference lighting, reduced light and a shifted camera: 30 closed-loop trials
> across ten paired initial states on an L40S, every trial retained, failures
> included. Pick any outcome in the matrix, compare both policy cameras, jump to
> the largest measured end-effector difference. The Butterfly Lab records twelve
> isolated Newton 1.6 worlds released 0.05° apart and lets you orbit their paths
> as a 3D time sculpture; the OpenUSD export was checked body-by-body in Blender.
>
> What it is not: a simulator, a training framework or a benchmark. It sits after
> LeRobot / MuJoCo / Newton and keeps the evidence behind the film. The Stress
> Lab is a controlled diagnostic, not an official LIBERO score.
>
> Standard-library quick start: clone, `python3 -m robot_reel.cli vla docs/vla`
> verifies the included episode against its trace. Recording new runs needs the
> full runtime (MuJoCo, LeRobot in its own venv; CUDA for the stress lab).
>
> Most useful feedback: which policy or simulator log would you want to inspect
> next, and what telemetry is missing when you step through a failure?

### Reddit (r/robotics, r/MachineLearning, r/blender, r/LocalLLaMA)

- r/robotics: lead with the Stress Lab GIF; ask which failure modes people want
  paired comparisons for.
- r/MachineLearning: lead with "every trial retained, failures included, MCAP
  telemetry"; link docs/stress.md for the fixed protocol.
- r/blender: lead with the remix divider and the editable .blend / OpenUSD;
  the MCP director is a secondary point.
- Disclose it is your project; answer every comment in the first two hours.

### 掘金 / 知乎

标题候选：

- 给物理 AI 加一个「回放键」：30 次真实 SmolVLA 运行、12 个 Newton 世界，浏览器里逐帧看
- 策略在暗光下为什么失败？把每一次运行都留下来再看
- 0.05° 的差别，如何在 12.5 秒后变成 6.26 米

正文要点：

> Robot Reel 不是仿真器，也不是训练框架。它做的事情只有一件：把一次运行录下来，
> 校验轨迹，做成能看、能查、能改的东西。
>
> 策略压力实验室：同一个 LIBERO 任务，参考光照 / 暗光 / 移机位三种条件、十组配对
> 初始状态，SmolVLA 在 L40S 上跑了 30 次真实闭环。全部保留，失败也在；点结果矩阵
> 任意一格，对照双相机，一键跳到末端轨迹差异最大的时刻。
>
> 蝴蝶效应实验室：12 个隔离的 Newton 1.6 世界，释放角只差 0.05°，录下来的路径
> 拼成一座可以旋转的 3D「时间雕塑」。导出的 OpenUSD 在 Blender 里逐个刚体检查过。
>
> 网页全部可离线打开，附源轨迹和哈希。快速开始只需要 Python 标准库。
> 说明：压力实验是受控诊断，不是 LIBERO 官方成绩；Newton 演示是刚体示例。
>
> 仓库：https://github.com/noteflowai/robot-reel （Apache-2.0）
> 在线演示：https://noteflowai.github.io/robot-reel/

### Where else to link

Upstream discussions where the recording is on-topic, only when answering a real
question: LeRobot (SmolVLA evaluation under lighting/camera shifts), Newton
(recording to OpenUSD), Blender community (importing measured motion). Credit the
upstream project first; link the specific demo, not the repo root.

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
comparison. The saved-project check covers all 420 vehicle samples and held
positions between frames.

This is a stylized replay of a toy MuJoCo experiment. It does not rerun physics
in Blender or claim an autonomous-driving result.

Useful feedback: Which recorded simulation would you want to relight or inspect
from a different angle? Full robot import and a Blender MCP adapter are not shipped.
