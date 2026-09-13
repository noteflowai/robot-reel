---
pretty_name: Robot Reel paired policy outcomes
license: apache-2.0
language:
  - en
size_categories:
  - n<1K
tags:
  - robotics
  - physical-ai
  - smolvla
  - paired-evaluation
  - simulation
configs:
  - config_name: trials
    default: true
    data_files:
      - split: test
        path: trials.csv
  - config_name: pairs
    data_files:
      - split: test
        path: pairs.csv
---

# Robot Reel: see what a net score hides

**30 recorded simulated trials, 20 reference/condition pairs, one task.**
This is a small evaluation-results dataset, not robot training data, an official
LIBERO benchmark, or a general robustness score. The `test` splits hold the
complete pilot results; no training split or train/test partition is claimed.

[Open the interactive replay](https://huggingface.co/spaces/glayguo/robot-reel)
to inspect the original camera observations, controls and measured trajectories.

## Collection and coverage

Robot Reel recorded SmolVLA closed-loop rollouts on 2026-09-12 using an NVIDIA
L40S. One LIBERO Spatial task was fixed in advance, with ten paired initial
states, reference lighting, 25% light and a +12 cm camera shift. The horizon
was 160 applied actions / 8 simulation seconds per trial.

All 30 planned trials completed in 30 attempts, with zero execution errors.
Reference succeeds in 5/10, reduced light in 4/10, and the shifted camera in
7/10. The camera condition's net gain of two contains **three gains and one
loss**. Ten initial states, one checkpoint and one task cannot establish a
general policy ranking. Shared physics and inference-noise checks control this
specific comparison, not hardware-independent reproducibility.

## Files and units

- **trials**: 30 rows copied byte-for-byte from the source results CSV. It
  includes trial/seed/condition, recorded outcome, action count, simulation
  seconds, inference calls, mean policy seconds and wall seconds.
- **pairs**: 20 reference-versus-condition rows. `outcome_group` is
  `both_success`, `lost_success`, `gained_success` or `neither_success`.
  Incomplete tasks include step limits or environment termination, not execution
  errors. There is no second independent reference run in each pair.
- `max_eef_distance_m` measures end-effector separation on the shared observation
  prefix. `max_eef_frame` is its source sample; `first_action_l2` compares normalized
  controls, not meters or joint angles. Held final samples are excluded.
- Policy time includes preprocessing and action conversion. Simulation time is
  a different clock; wall time excludes model loading, reset and encoder flush.
- `paired-outcomes.json`, `summary.json` and `experiment.json` retain full counts,
  descriptive per-condition Wilson intervals and the locked plan.
- `source-manifest.json` records exact bytes, hashes and the generating commit.
  Hashes establish file consistency, not an independent attestation.

There are no images, videos, robot meshes, model weights or personal data in this
tabular export. Original recordings and their notices remain in Robot Reel.

## Provenance and reproduction

Generated from [Robot Reel commit __SOURCE_COMMIT__](https://github.com/noteflowai/robot-reel/tree/__SOURCE_COMMIT__).
Check out that commit, then run:

```bash
python3 scripts/build_hf_results.py --output artifacts/hf-results
python3 -m robot_reel.cli stress docs/stress --paired-report artifacts/hf-results/paired-outcomes.json
```

The builder checks every original trial, paired initial state, complete
denominator, summary, CSV and source manifest before producing this export.
[Full method and measurement limits](https://github.com/noteflowai/robot-reel/blob/__SOURCE_COMMIT__/docs/stress.md).

Policy: `HuggingFaceVLA/smolvla_libero`, revision
`6721902bc4d61e50a3bfdb11dfb4cb626f05d102`; LeRobot 0.6.1.
Simulation assets: `lerobot/libero-assets`, revision
`0b3ea86be5fe169d0fd036ae63d1070ec09e90f6`. See `NOTICE.txt` for source credits.
The license applies to this project's tabular export and does not relicense
upstream assets. This is an independent Note Flow AI project, developed and
documented with AI assistance; no upstream endorsement is implied.
