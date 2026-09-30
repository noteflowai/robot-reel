# Claims inventory

Every headline number in the [README](../README.md), the evidence file it comes from and how
that evidence was produced. `python3 scripts/claims_inventory.py` recomputes each value from
its file and fails if the README, the evidence or this table drift apart (roadmap RR-03).
Generated; edit `scripts/claims_inventory.py`, then run it with `--write`.

| Evidence kind | Meaning |
| --- | --- |
| `real-recording` | Recorded run of a real simulator or policy in this project |
| `procedural-simulation` | Deterministic model written for this project; not calibrated to a real system |

| Lab | Evidence kind | README wording | Evidence |
| --- | --- | --- | --- |
| Stress Lab | `real-recording` | 30 real closed-loop trials | [stress/summary.json](stress/summary.json) |
| Stress Lab | `real-recording` | All 14 unsuccessful trials reached the action limit | [stress/reliability.json](stress/reliability.json) |
| Stress Lab | `real-recording` | 44.8 mm to 138.6 mm | [stress/reliability.json](stress/reliability.json) |
| Stress Lab | `real-recording` | three gains and one loss | [stress/summary.json](stress/summary.json) |
| Stress Lab | `real-recording` | 30 / 30 outcomes | [stress-reproducibility.json](stress-reproducibility.json) |
| Stress Lab | `real-recording` | 360 / 360 rendered frames | [stress-reproducibility.json](stress-reproducibility.json) |
| Stress Lab | `real-recording` | One of 3,195 | [stress-reproducibility.json](stress-reproducibility.json) |
| Solver Lab | `real-recording` | 32.70 cm to 2.05 cm | [solver-lab/lab.json](solver-lab/lab.json) |
| Solver Lab | `real-recording` | 366 recorded position/velocity states | [solver-lab/lab.json](solver-lab/lab.json) |
| Cloth Lab | `real-recording` | 42,471 vertex samples | [cloth/blender-check.json](cloth/blender-check.json) |
| Butterfly Lab | `real-recording` | 14,424 body poses | [chaos/blender-check.json](chaos/blender-check.json) |
| Butterfly Lab | `real-recording` | 6.26 m gap | [chaos/trace.json](chaos/trace.json) |
| Butterfly Lab | `real-recording` | at 12.5 s | [chaos/trace.json](chaos/trace.json) |
| Factory Twin Lab | `procedural-simulation` | 0 spindle failures (shadow: 11) | [factory-twin/seeds.json](factory-twin/seeds.json) |
| Factory Twin Lab | `procedural-simulation` | 0 billing intervals over the demand limit (shadow: 8) | [factory-twin/seeds.json](factory-twin/seeds.json) |
| Factory Twin Lab | `procedural-simulation` | 10 pairs and fell in 2 | [factory-twin/seeds.json](factory-twin/seeds.json) |
| Factory Twin Lab | `procedural-simulation` | 676,393 animated values | [factory-twin/blender-check.json](factory-twin/blender-check.json) |
| Newton | `real-recording` | 362 checked body transforms | [newton/blender-check.json](newton/blender-check.json) |
| VLA | `real-recording` | 76 actions · one completed simulation task | [vla/trace.json](vla/trace.json) |
| Microduck Motion Lab | `real-recording` | 8,400 measured joint samples | [microduck-lab/data.json](microduck-lab/data.json) |
| Microduck Motion Lab | `real-recording` | 18,000 body transforms | [microduck-lab/kinematics-check.json](microduck-lab/kinematics-check.json) |
| Scene Lab | `real-recording` | 362 source frames | scene-lab/motion/*/native-check.json |
| Director | `real-recording` | 420 vehicle samples | [director/animation-check.json](director/animation-check.json) |

Numbers establish what these recordings contain, not general performance. Each lab's
methods page states its sample size and limits; the Factory Twin is a procedural
simulation and none of its numbers are measurements of a real factory.
