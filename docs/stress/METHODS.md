# Stress Lab: change the view, check the policy

The Stress Lab records **new closed-loop SmolVLA inference** for each condition.
The public experiment fixes one task, ten paired initial states and three
conditions before collection: **30 planned trials**, with at most 160 applied
actions (8 simulation seconds) per trial. All results are retained.

This is a small, controlled diagnostic, **not an official LIBERO or LIBERO-plus
benchmark score**. The shorter horizon, single task, checkpoint and native
perturbations define this experiment only. A task that reaches the budget
without success is labelled `step_limit`, not an execution error. Confidence
intervals do not establish general robustness.

## Published GPU experiment

Recorded on 2026-09-12 with NVIDIA L40S and PyTorch 2.11.0+cu130:

| Condition | Successes | Step limits | 95% Wilson interval |
|---|---:|---:|---:|
| Reference | 5/10 | 5 | 23.7–76.3% |
| 25% light | 4/10 | 6 | 16.8–68.7% |
| Camera +12 cm | 7/10 | 3 | 39.7–89.2% |

All 30 planned trials completed in 30 attempts, with zero execution errors.
The record contains 3,525 applied actions, 3,555 observations, 60 camera videos
and 360 policy calls. Mean measured policy time was 0.491 seconds per call,
including the first call of each collector process. The public MCAP contains
all 3,915 observation/inference messages.

The camera change helped three paired seeds and hurt one; reduced lighting
changed one paired success to a step limit. These are observations within this
fixed experiment, not evidence that a camera offset generally improves a
policy. The intervals overlap and the task, initial states and horizon are
limited. Earlier CPU trials and short GPU smoke runs are separate collections
and do not enter these counts.

## Compare paired outcomes

The current website and Hugging Face Stress Lab include **Same starts. Which
outcomes changed?** Select either changed condition to split all ten paired
seeds into four groups: both successful, success lost, success gained, and
neither completed. Open any seed directly in the paired replay. The camera
condition's net gain of two successes contains **three gained successes and one
lost success**; the grouped view keeps both directions visible.

**Export all paired outcomes** downloads both conditions, every seed group,
the full experiment's trial/attempt counts and the locked plan hash. The active
UI filter never removes pairs from the report. “Not completed” combines
`step_limit` and `terminated`; execution errors stay separately counted.
## What the failures were, and whether a repeat agrees

A success rate does not say what a failure was. All fourteen failures here end at
the step limit, and that label covers two different things: a policy that stopped,
and an arm still moving when the budget expired. This measurement describes
the recorded motion; it does not identify which intervention would fix the task.

```bash
python3 -m robot_reel.cli stress docs/stress --reliability
```

Measured over the published collection, **every one of the fourteen failures was
still in motion at the cut-off**; none had stalled. End-effector travel over the
final tenth of each episode ranges from 44.8 mm to 138.6 mm, against a stall
threshold of 1 mm. The 160-action budget expired while motion continued.
That does not establish progress toward the goal or that a larger budget would
change the success rate; either conclusion would require a new controlled run.

Failures also wander further to end up no further along: median path-to-
displacement ratio 3.17 against 1.92 for successes. The ranges overlap, so that
is a description of what these failures look like and not a way to tell them
apart.

## Reproducibility of the paired comparison

The paired groups describe outcome differences under the recorded conditions.
Repeating the plan checks the stability of those observations on the same
machine and software stack. A matching repeat alone does not establish causal
attribution or account for variation outside this experiment.

The full plan was re-run once on the same NVIDIA L40S, with the pinned policy,
assets and simulator versions, and compared at every level:

```bash
python3 -m robot_reel.cli stress docs/stress --repeat artifacts/repro-gpu-30
```

| Level | Result |
| --- | --- |
| Same outcome | 30 / 30 trials |
| Same action count | 30 / 30 trials |
| Numerically equal recorded robot states | 30 / 30 trials |
| Numerically equal recorded actions | 30 / 30 trials |
| Identical renders on frames a policy call consumed | 360 / 360 frames |
| Identical renders on frames recorded only | 3194 / 3195 frames |

The two render levels separate policy inputs from images saved only for review.
The policy is called once every ten steps, so most recorded frames never reach
it. The single differing frame is the wrist view at frame 3 of
`seed-05-camera`, which no policy call consumed; the recorded robot states and actions
of that trial compare numerically equal throughout. This compares the saved
`state` and `action` arrays, not every internal MuJoCo variable or floating-point
bit pattern (for example, numeric equality treats signed zeros as equal).

The differing image is retained as an observed rendering discrepancy. It was
not a policy input, and the recorded state/action comparison found no numerical
change in that trial. These records do not measure the effect that a different
image at an inference step would have on the policy or task outcome.

The failure taxonomy is committed inside the pack as `reliability.json`, and
verification recomputes it from the traces rather than only checking its hash.
The reproducibility aggregate is `docs/stress-reproducibility.json`, beside the
pack rather than inside it: it is a property of two collections, so it does not
belong to either one. This is one repeat of one plan on one machine, and it does
not establish determinism on other hardware, drivers or stack versions.

These are descriptive paired outcomes, not a significance test or a claim of
general robustness.

With Robot Reel **0.8.0+** installed and the offline experiment extracted as
`stress-lab`, export or independently verify a report:

```bash
robot-reel stress stress-lab --paired > paired-outcomes.json
robot-reel stress stress-lab --paired-report paired-outcomes.json
```

Both commands first verify the complete source collection. The second compares
the plan hash, every group and every count, including numeric types. This
establishes consistency with the supplied recordings, not external certification.
The 0.8.0 release includes the matching report, wheel and complete offline viewer.
See the [download guide](https://github.com/noteflowai/robot-reel/blob/main/docs/offline-lab.md). From a source checkout, the equivalent
command is `python3 -m robot_reel.cli stress docs/stress --paired`.
Earlier release assets retain their original viewer; the current verifier can
also read their complete collection.

## What changes

| Condition | Native simulator change before policy inference |
|---|---|
| Reference | Unmodified camera and lighting |
| 25% light | All MuJoCo light ambient, diffuse and specular RGB values multiplied by 0.25 |
| Camera +12 cm | World-fixed `agentview` camera translated +0.12 m on world X |

The light multiplier describes simulator settings, **not calibrated lux or a
75% reduction in image luminance**. Ambient materials, shadows, textures and
the renderer also affect image intensity. The wrist camera position does not
change. Both camera observations are refreshed after the changes and before
the first policy call; subsequent observations come from each real environment
step. The input videos show the actual policy views, with LeRobot's two-axis
image flip. There are no image filters used to impersonate a new rollout.

Task: `libero_spatial`, task ID 0. Seed N uses LIBERO initial state N through
the adapter's `episode_index`, not just `reset(seed=N)`. There are ten settling
steps before sample zero. Every pair must match initial simulator time,
`qpos`, `qvel`, original camera/light settings and task BDDL hash exactly.
Changes to native rendering settings must leave physical state unchanged.

An independent CPU `torch.Generator` is seeded with N for policy noise.
Corresponding inference calls across conditions use the same noise sequence;
hashes of those tensors are checked, including the shared prefix when run
lengths differ. This controls the random input, not a guarantee of identical
trajectories across different software or hardware.

## Policy and clocks

- `HuggingFaceVLA/smolvla_libero`, revision
  `6721902bc4d61e50a3bfdb11dfb4cb626f05d102`.
- Tokenizer: `HuggingFaceTB/SmolVLM2-500M-Instruct`, revision
  `7b375e1b73b11138ff12fe22c8f2822d8fe03467`.
- Assets: `lerobot/libero-assets`, revision
  `0b3ea86be5fe169d0fd036ae63d1070ec09e90f6`.
- LeRobot 0.6.1, hf-libero 0.1.4, robosuite 1.4.0, MuJoCo 3.8.1.
  The full installed versions, checkpoint SHA-256, CPU, thread count and
  precision are included in every trace.
- Float32, two CPU PyTorch threads, ten denoising steps, ten applied controls
  per policy chunk. The model is loaded with strict checkpoint matching.
  GPU runs declare `device: cuda` in their own locked plan, record the GPU model,
  disable TF32 and synchronize CUDA work for inference timing. CPU and GPU
  trials cannot be mixed in the same experiment.
- Two 256 × 256 policy cameras; 20 Hz simulator control. An action at sample
  N is chosen from that observation or its recorded chunk and produces
  observation N+1. The final observation has **no action**.
- `policy_seconds` measures preprocessing, policy selection and action
  conversion on inference steps. `env_step_seconds` separately measures the
  first simulator step for that chunk; each action frame also records its own
  simulator step time. These are wall-clock measurements, not 20 Hz inference.
  Policy latency depends on the recorded hardware and concurrent host load.
- `wall_seconds` on a run covers the observation/action loop and submission
  of camera frames to the video encoder. It excludes model loading, environment
  reset and the encoder's final flush. Inference records also include relative
  start/end wall times.

Applied commands are clipped to [-1, 1] after the upstream processors. They are
normalized relative end-effector/gripper controls, not joint angles or meters.
The trace separately contains measured end-effector state and seven robot
joint positions.

The success predicate is the environment's `is_success` after a step. Collection
stops at success, environment termination/truncation, or the predeclared budget.
The viewer retains separate source clocks and explicitly labels a shorter
run's held final sample. Replay runs on simulation time; no model executes in
the browser.

The separation chart uses Euclidean distance between the two measured
end-effector xyz positions at the same sample. It only uses their shared
observation prefix, never a held final frame. “Peak separation” jumps to the
first maximum on that prefix. This is a trajectory difference, not an accuracy,
task-error or robustness score. The summary also records the L2 difference of
the first applied control vector.

## Complete evidence

The published folder includes:

- `experiment.json`: immutable settings, seeds and perturbations.
- `attempts.json`: every attempt, including interrupted/error attempts on
  resume. Completed trials are never rerun just because their task failed.
- `runs/seed-NN-CONDITION/attempt-NNN/`: two MP4s, two exact initial RGB posters,
  source trace and per-run file hashes.
- `summary.json` and `results.csv`: all planned results; per-condition 95%
  Wilson intervals and paired success outcomes. These intervals are
  descriptive binomial intervals, not a paired significance test.
- `telemetry.mcap`: JSON observation and inference channels per trial. Log and
  publish timestamps are **episode-relative nanoseconds starting at zero**,
  not UTC. Every serialized sample, topic, sequence and timestamp is read back
  and compared to its source. MCAP does not bundle video, model weights or a
  preconfigured Rerun/Foxglove visualization.
- `media-checks.json`: all MP4 frames are decoded, dimensions/fps/counts checked
  against traces, and lossless initial PNG pixels hashed against the raw input.
  MP4 is lossy: raw frame hashes document observations and are not claimed to
  match decoded MP4 pixels bit for bit.
- A self-contained HTML viewer, notices, file manifest and `experiment.zip`.
  Extract the whole ZIP and open `index.html`; no HTTP server is required.
  The published site under `docs/stress/` does not carry the 56 MB archive; it
  is the release asset `robot-reel-stress-experiment.zip` (listed in the
  release's `SHA256SUMS`), so large bundles stay out of the repository history.

Hashes detect accidental changes; they are not an external attestation of the
collector. Validators also check trial denominators, paired physical states,
model/runtime identity, native perturbations, shared noise, terminal action
semantics, summary/CSV recomputation and the HTML's embedded telemetry.

Execution errors are counted separately from task outcomes and remain in the
attempt ledger. A public pack can only be sealed when all planned trials have
a valid completed record. An error can be resumed without removing its history.
For an externally interrupted process, the ledger records when the interruption
was detected on resume; it does not invent an exact process-finish timestamp.
Partial camera files from interrupted attempts stay in the source collection;
only sealed runs enter the portable pack.

## Share a moment for review

In the current Stress Lab, select a seed, condition, camera and sample, then use
**Turn a moment into a review** below the controls. Add an optional note and
download the JSON for checking, or Markdown for a readable discussion. The
Markdown links to `index.html` with the sample fragment; place it beside the lab's
index to use that relative link. It does not include your machine's file path or
browser origin. Downloads do include your note.

The JSON carries the locked plan and its settings hash, full-experiment counts
and condition summaries, both selected source observations and their original
results, runtime/checkpoint identity, raw camera hashes and active inference
records. A shorter run keeps its actual source sample and `held_final` flag.
Terminal observations have neither an action nor an active inference record.
Controls retain their recorded units. Selecting a pair does not change the
experiment's denominator.

Open the JSON using the lab's file picker to compare it with the loaded records
before restoring the selection and note. A mismatch leaves the existing
selection and note intact. Processing is local and also works from `file://`;
notes are not uploaded or stored between visits. User notes are limited to 4,000
characters and imports to 128 KiB. In Markdown, notes appear as literal text.

For an independent comparison, use **Robot Reel 0.6.0 or newer**, or the current
checkout:

```bash
python3 -m robot_reel.cli stress docs/stress --review review.json
```

Replace `docs/stress` with your complete lab folder and `review.json` with the
downloaded filename. The standard-library command first validates the collection
and its manifest, then compares every review fact against the selected source
records. Its output distinguishes `recorded_facts_match: true` from
`user_note_verified: false`. Editing a note is allowed; changing recorded facts,
outcomes, clocks or counts fails verification. Notes are human interpretation.
The plan hash identifies settings, not a unique recording or an external
attestation. This check establishes consistency with the supplied collection.

The 0.6.0 release includes this viewer in its complete offline ZIP, together with
a separate sample review and start guide. The existing v0.4.0 release ZIP remains
an immutable older viewer. Both contain the same underlying 30-trial evidence;
either extracted collection can be supplied to the current CLI. Custom exports
also include these review controls automatically.

## Reproduce

Use Python 3.12 and a separate environment: the recorder requires MuJoCo 3.8.1,
while Robot Reel's rendering environment uses 3.13.0. The first download needs
network access and several GB of cache/disk. A CPU experiment takes tens of
minutes, not the eight seconds shown on the simulation clock. Prefer a GPU
runner when one is available.

For CUDA inference, create the separate environment and run a real device
check before collecting anything:

```bash
python3 -m venv .venv-vla-gpu
.venv-vla-gpu/bin/python -m pip install -r requirements/vla-gpu.txt
.venv-vla-gpu/bin/python scripts/check_vla_gpu.py
MUJOCO_GL=egl .venv-vla-gpu/bin/python scripts/record_stress.py \
  --device cuda --output artifacts/stress-gpu-30 --cache artifacts/vla-cache
```

The GPU check distinguishes host PCI/driver evidence from device access in the
actual execution environment. It then runs and checks a matrix multiplication
on CUDA. Merely having `nvidia-smi` installed, or a CUDA-enabled PyTorch wheel,
does not pass this check. The collector refuses an unavailable CUDA request;
it does not silently fall back to CPU.

Once the pinned snapshots are cached, `bash scripts/run_stress_gpu.sh` combines
that preflight with the same GPU collection command in offline cache mode.
Run it from a host terminal or runner that exposes the NVIDIA device nodes.
Pass `--resume` to continue its unchanged GPU experiment.

CPU recording remains available:

```bash
python3 -m venv .venv-vla
.venv-vla/bin/python -m pip install -r requirements/vla.txt
MUJOCO_GL=egl \
  .venv-vla/bin/python scripts/record_stress.py \
  --output artifacts/stress-30 --cache artifacts/vla-cache
```

On CPU hosts with multiple EGL drivers, Mesa can be selected using
`__EGL_VENDOR_LIBRARY_FILENAMES=/usr/share/glvnd/egl_vendor.d/50_mesa.json`
when that file exists. The published CUDA experiment uses the GPU host's EGL
renderer without this Mesa override. The collector does not need root.
To resume, pass the same arguments plus `--resume`; changing the plan is rejected.
For runners with a limited job lifetime, add `--stop-after 1` (or another
positive trial count), then invoke it again with `--resume`. This stops only
after sealing complete trials and never changes the planned denominator.
Once all pinned snapshots are cached, `HF_HUB_OFFLINE=1` avoids Hub requests
during subsequent invocations. It uses those same cached revisions; it does not
change policy inference or the experiment plan.
Do not run two collectors against the same output directory.

Package and verify using Robot Reel's regular environment:

```bash
python -m pip install -e '.[inspect]'
python -m robot_reel.stress_site artifacts/stress-gpu-30 artifacts/stress-site
robot-reel stress artifacts/stress-site --check-media --check-mcap
```

The download button defaults to the generated `experiment.zip` beside the page,
so a custom experiment always downloads its own evidence. If that exact archive
will be hosted elsewhere, pass `--archive-href` with its download location.
For the published 30-trial experiment, use:

```bash
python -m robot_reel.stress_site artifacts/stress-gpu-30 artifacts/stress-published \
  --archive-href https://github.com/noteflowai/robot-reel/releases/download/stress-evidence-20260920-q8/robot-reel-stress-experiment.zip
```

The `stress-evidence-20260920-q8` snapshot re-encodes the sixty camera MP4s at
`quality=8`, reducing their total size from 46.7 MiB to 28.7 MiB while retaining
every frame. It also refreshes the video checksums, viewer and methodology.
The 30 trials, original traces and policy-input hashes, controls, telemetry,
outcomes and trial posters retain their previous bytes. These MP4s are lossy
viewing derivatives; the policy-input hashes identify the original observations,
not the pixels decoded from the re-encoded videos.

The preview, portable Rerun recording and Space thumbnail are rebuilt from the
updated media as separate website assets. This is an evidence snapshot, not a
new software version or a new experiment. The earlier `stress-evidence-20260920`
and software-release archives retain their original bytes.

That release link identifies the published experiment; keep the default for a
different collection. Page synchronization updates local ZIPs only. To distribute
an updated viewer through Releases, publish a new archive and use its new link.

The published pack can be verified without ML packages:
`python -S -m robot_reel.stress docs/stress`.
MCAP reading requires the optional `inspect` extra; media decoding requires
the ordinary imageio-ffmpeg/Pillow dependencies. Neither check reruns a policy.

## Primary sources

- LeRobot LIBERO adapter:
  https://github.com/huggingface/lerobot/blob/v0.6.1/src/lerobot/envs/libero.py
- SmolVLA policy:
  https://github.com/huggingface/lerobot/blob/v0.6.1/src/lerobot/policies/smolvla/modeling_smolvla.py
- Policy checkpoint: https://huggingface.co/HuggingFaceVLA/smolvla_libero
- LIBERO: https://github.com/Lifelong-Robot-Learning/LIBERO
- MCAP Python API: https://mcap.dev/docs/python/mcap-apidoc/mcap.writer

See the included media notice for third-party attribution. Model weights and
upstream simulation meshes are not redistributed in the public experiment.

## Inspect final motion and retain legacy packs

Stress Lab now groups the recorded outcomes and lets a reviewer jump to the final tenth of samples of any selected episode. It displays the exact sample window and end-effector path length, with a stated 1 mm threshold. Movement alone cannot establish progress or the effect of a larger action budget. The full matrix, denominators and attempt ledger remain available.

The verifier accepts the original exact inventory of releases through v0.11.0, which predated `reliability.json`. New exports include the derived taxonomy and independently recompute it. A missing consumed frame, or absent camera hashes in both runs, cannot count as identical policy input.
