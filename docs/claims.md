# Claims inventory

Every headline number in the [README](../README.md) and its [Chinese version](../README.zh-CN.md),
the evidence file it comes from and how
that evidence was produced. `python3 scripts/claims_inventory.py` recomputes each value from
its file and fails if the README, the evidence or this table drift apart (roadmap RR-03).
Generated; edit `scripts/claims_inventory.py`, then run it with `--write`.

| Evidence kind | Meaning |
| --- | --- |
| `real-recording` | Recorded run of a real simulator or policy in this project |
| `procedural-simulation` | Deterministic model written for this project; not calibrated to a real system |

## Scope of each lab

Read from the evidence files. Comparisons are within each lab; none is a benchmark.

| Lab | Evidence kind | What ran | Sample | Seeds / variation | Runtime | Compared against |
| --- | --- | --- | --- | --- | --- | --- |
| Stress Lab | `real-recording` | SmolVLA, libero_spatial task 0, conditions: reference, dim, camera | 30 trials, 160-action budget | 10 paired seeds (0–9) | policy on cuda | Reference lighting within each paired seed |
| Solver Lab | `real-recording` | Unconstrained ballistic flight, Genesis and Newton | 6 runs × 61 samples | Deterministic; one initial state | NVIDIA L40S | Analytic solution |
| Cloth Lab | `real-recording` | Newton SolverVBD cloth, bending coefficient sweep | 3 cases × 121 frames × 117 vertices | Deterministic | NVIDIA L40S | Between the three cases |
| Butterfly Lab | `real-recording` | Newton SolverXPBD double-pendulum release sweep | 12 worlds × 601 samples | Deterministic; 0.05° release offsets | cpu | Adjacent worlds |
| Newton | `real-recording` | Newton SolverXPBD double pendulum | 181 samples | Deterministic | cpu | None (one run) |
| VLA | `real-recording` | SmolVLA, libero_spatial: pick up the black bowl between the plate and the ramekin and place it on the plate | 1 episode | seed 0, initial state 0 | policy on cpu | None (one rollout) |
| Microduck Motion Lab | `real-recording` | Pollen Microduck ONNX walking policy in MuJoCo | 2 runs × 300 frames × 14 joints | Two speed commands: 0.3 m/s / 0.5 m/s | CPU (per microduck-lab.md) | Between the two speeds |
| Factory Twin Lab | `procedural-simulation` | Simulated factory and campus with a digital twin | 12 pairs × 2 modes × 2161 samples | seeds 1–12 | Python standard library | Shadow twin (same twin, commands not applied) |

## Headline numbers

| Lab | Evidence kind | README wording | 中文 README | Evidence |
| --- | --- | --- | --- | --- |
| Stress Lab | `real-recording` | 30 real closed-loop trials | 30 次真实闭环运行 | [stress/summary.json](stress/summary.json) |
| Stress Lab | `real-recording` | All 14 unsuccessful trials reached the action limit | 14 次未成功试次均达到动作预算上限 | [stress/reliability.json](stress/reliability.json) |
| Stress Lab | `real-recording` | 44.8 mm to 138.6 mm | 44.8–138.6 mm | [stress/reliability.json](stress/reliability.json) |
| Stress Lab | `real-recording` | three gains and one loss | 三次从未完成变为成功、一次从成功变为未完成 | [stress/summary.json](stress/summary.json) |
| Stress Lab | `real-recording` | 30 / 30 outcomes | 30 / 30 试次的结果 | [stress-reproducibility.json](stress-reproducibility.json) |
| Stress Lab | `real-recording` | 360 / 360 rendered frames | 360 / 360 个渲染帧一致 | [stress-reproducibility.json](stress-reproducibility.json) |
| Stress Lab | `real-recording` | One of 3,195 | 3,195 个仅用于记录的帧中有 1 帧不同 | [stress-reproducibility.json](stress-reproducibility.json) |
| Solver Lab | `real-recording` | 32.70 cm to 2.05 cm | 32.70 厘米降至 2.05 厘米 | [solver-lab/lab.json](solver-lab/lab.json) |
| Solver Lab | `real-recording` | 366 recorded position/velocity states | 366 个位置与速度状态 | [solver-lab/lab.json](solver-lab/lab.json) |
| Cloth Lab | `real-recording` | 42,471 vertex samples | 42,471 个顶点样本 | [cloth/blender-check.json](cloth/blender-check.json) |
| Butterfly Lab | `real-recording` | 14,424 body poses | 14,424 个刚体姿态 | [chaos/blender-check.json](chaos/blender-check.json) |
| Butterfly Lab | `real-recording` | 6.26 m gap | 6.26 米摆端距离 | [chaos/trace.json](chaos/trace.json) |
| Butterfly Lab | `real-recording` | at 12.5 s | 发生在 12.5 秒 | [chaos/trace.json](chaos/trace.json) |
| Factory Twin Lab | `procedural-simulation` | 0 spindle failures (shadow: 11) | 主轴故障为 0 次（影子模式 11 次） | [factory-twin/seeds.json](factory-twin/seeds.json) |
| Factory Twin Lab | `procedural-simulation` | 0 billing intervals over the demand limit (shadow: 8) | 计费时段 为 0 个（影子模式 8 个） | [factory-twin/seeds.json](factory-twin/seeds.json) |
| Factory Twin Lab | `procedural-simulation` | 10 pairs and fell in 2 | 10 组增加、2 组减少 | [factory-twin/seeds.json](factory-twin/seeds.json) |
| Factory Twin Lab | `procedural-simulation` | 676,393 animated values | 676,393 个动画数值 | [factory-twin/blender-check.json](factory-twin/blender-check.json) |
| Newton | `real-recording` | 362 checked body transforms | 全部 362 个刚体变换 | [newton/blender-check.json](newton/blender-check.json) |
| VLA | `real-recording` | 76 actions · one completed simulation task | 76 次动作 · 一次已完成的仿真任务 | [vla/trace.json](vla/trace.json) |
| Microduck Motion Lab | `real-recording` | 8,400 measured joint samples | 8,400 个实测关节样本 | [microduck-lab/data.json](microduck-lab/data.json) |
| Microduck Motion Lab | `real-recording` | 18,000 body transforms | 18,000 个变换 | [microduck-lab/kinematics-check.json](microduck-lab/kinematics-check.json) |
| Scene Lab | `real-recording` | 362 source frames | 共 362 帧 | scene-lab/motion/*/native-check.json |
| Director | `real-recording` | 420 vehicle samples | 全部 420 个车辆状态 | [director/animation-check.json](director/animation-check.json) |

## Other public surfaces

The same check covers headline numbers on the website landing page and the Hugging Face cards.

| Surface | Wording |
| --- | --- |
| `huggingface/README.md` | 30 trials on one task: 10 initial states × 3 conditions |
| `huggingface/README.md` | Download 366 positions and velocities |
| `huggingface/README.md` | 42,471 vertex samples |
| `huggingface/README.md` | 8,400 joint samples, 18,000 body transforms |
| `huggingface/README.md` | all 362 source frames |
| `huggingface/README.md` | 12 paired seeds |
| `huggingface/index.html` | 42,471 original cloth vertex samples |
| `huggingface/index.html` | 12 isolated Newton worlds |
| `huggingface/index.html` | 10 starts × 3 conditions |
| `huggingface/index.html` | Compare 12 paired shifts |
| `huggingface/index.html` | Microduck / ONNX / 14 joints |
| `scripts/landing.html` | 6.26 m gap |
| `scripts/landing.html` | all 362 frames |
| `scripts/landing.html` | Microduck: 8,400 joint samples · Solver: 366 states · Cloth: 42,471 vertex samples · Stress: 30 trials |
| `scripts/landing.html` | SmolVLA · LIBERO · 76 actions |
| `scripts/landing.html` | Newton · OpenUSD · 362 transforms |
| `scripts/landing.html` | 6 embedded videos · 405 observations · 41 policy calls |
| `scripts/landing.html` | across 12 paired shifts |
| `huggingface/results-card.md` | 30 recorded simulated trials, 20 reference/condition pairs |
| `huggingface/results-card.md` | All 30 planned trials completed in 30 attempts, with zero execution errors |
| `huggingface/results-card.md` | Reference succeeds in 5/10, reduced light in 4/10, and the shifted camera in 7/10 |

## Lab pages

Numbers written into the prose of each lab page. Data panels render from embedded payloads
that each lab's own verifier compares with its source files.

| Page | Wording |
| --- | --- |
| `docs/libero-plus/index.html` | Success · 77 actions |
| `docs/libero-plus/index.html` | Step limit · 220 actions |
| `docs/libero-plus/index.html` | 77 actions · 3.85 simulated seconds |
| `docs/libero-plus/index.html` | 220 actions · 11.00 simulated seconds |
| `docs/libero-plus/index.html` | Camera Viewpoints 609 Step limit 220 |
| `docs/libero-plus/index.html` | Light Conditions 2124 Success 87 |
| `docs/blender/index.html` | 360 vehicle samples |
| `docs/blender/index.html` | 180 FRAMES · 2 TRIALS |
| `docs/remix/index.html` | All 180 source samples |
| `docs/remix/index.html` | 360 native vehicle checks |
| `docs/director/index.html` | 180 source samples |
| `docs/chaos/index.html` | 12 isolated worlds on CPU |
| `docs/chaos/index.html` | Two 1.6 m links per world |
| `docs/chaos/index.html` | differ by 0.05°; the full sweep spans 0.55° |
| `docs/cloth/index.html` | 0.96 × 0.64 m sheet has 117 vertices and 192 triangles |
| `docs/cloth/index.html` | mass 0.01 kg; gravity is 9.81 |
| `docs/newton/index.html` | 30 samples/s · 300 physics steps/s |
| `docs/microduck-lab/index.html` | 14 JOINTS 2 × 300 FRAMES |
| `docs/microduck-lab/index.html` | All 18,000 body transforms |
| `docs/solver-lab/index.html` | 366 recorded states |
| `docs/solver-lab/index.html` | all 61 samples per run |
| `docs/stress/index.html` | 25% light Camera +12 cm |
| `docs/vla/index.html` | in order at 20 Hz |
| `docs/scene-lab/index.html` | all 4,225 collision samples |
| `docs/scene-lab/index.html` | Heightfield proxy 65 × 65 |

Numbers establish what these recordings contain, not general performance. Each lab's
methods page states its sample size and limits; the Factory Twin is a procedural
simulation and none of its numbers are measurements of a real factory.
