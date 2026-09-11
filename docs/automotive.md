# Automotive physical AI: what is connected today

Robot Reel's automotive pack is a **small recording and comparison example**.
It is not an autonomous-driving stack and does not run an NVIDIA model.

## The broader ecosystem

Official sources checked on 2026-09-11:

- [NVIDIA Alpamayo](https://github.com/NVlabs/alpamayo) connects driving
  trajectory generation with causal reasoning.
- [Alpamayo 2 Super](https://github.com/NVlabs/alpamayo2) is a 34B multi-task
  model. Its README describes trajectory inference and a more demanding,
  separately documented two-GPU example.
- [AlpaSim](https://github.com/NVlabs/alpasim) provides a modular closed-loop
  simulation platform for end-to-end autonomous-vehicle policies.
- [CARLA](https://github.com/carla-simulator/carla) is an open simulator for
  autonomous-driving research.

These projects motivate the workflow: **record an action, observe the resulting
world state, compare outcomes, and keep the evidence with the video**.
The current Robot Reel pack implements that workflow at a deliberately small scale.

## Reproduce the shipped example

```bash
robot-reel --pack braking --output artifacts/braking
python -m robot_reel.verify artifacts/braking
```

Both trials use the same MuJoCo scene, a single longitudinal degree of freedom,
a 500 kg rigid body, 8 m/s initial speed, and a stationary obstacle. The controller
applies a bounded braking force equivalent to 6 m/s² in free motion.

The only policy difference is when braking starts:

| Controller | Trigger: obstacle gap | Published recorded result |
| --- | --- | --- |
| Late | 2 m | Contact recorded at about 3.594 s |
| Early | 14 m | No contact during the 6 s trial; final gap about 8.661 m |

These are **results from the supplied surrogate**, not vehicle performance
claims. There are no tires, steering dynamics, perception uncertainty, pedestrians,
traffic rules, weather effects, or learned driving policy. Wheel meshes in the
video are decorative; the chassis moves on a slide joint.

The record includes configuration, `vehicle.xml`, speed, position, obstacle gap,
brake force, cumulative contact flags, and an outcome summary. Contact is derived
from MuJoCo chassis/obstacle contacts rather than an editorial pass/fail label.
The plotted reference is the nominal early-braking standstill state.

## A useful next integration

A future AlpaSim/CARLA importer should accept an already executed run and preserve:

1. Simulator, scene, policy, configuration and seed identifiers.
2. Timestamped video, commands, ego-state and observation alignment.
3. Collision events and task-specific outcome definitions.
4. Clear separation between open-loop trajectory error and closed-loop outcomes.
5. References to original logs, with checksums and reproducible replay instructions.

That importer is **not implemented in v0.2.0**. A claim of running Alpamayo requires
actual model inference, its correct sensor/observation contract, and the appropriate
simulator integration; a simple brake controller is not a substitute.
