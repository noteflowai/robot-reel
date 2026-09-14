# Cosmos Policy: prediction versus execution recorder

The recorder is implemented, but **no Cosmos inference result is published in
this release**. On 2026-09-14 the authenticated dependency check returned HTTP
403 for the required NVIDIA Video2World checkpoint and tokenizer repository.
The public LIBERO-Plus replay uses SmolVLA and must not be described as a Cosmos run.

`scripts/record_cosmos_plus.py` prepares a closed-loop experiment in which a policy
predicts 16 actions, future wrist/scene images and a value estimate, then executes
those same actions in the native official LIBERO-Plus scene. It records the
predictions, executed controls and observations separately. RGB error and SSIM are
computed only when all 16 actions were executed, using the policy's same image
preparation on observations. A final partial horizon is explicitly unscored.

Image similarity measures appearance, not task completion. The value output is
a model estimate, not a calibrated success probability. A successful loader,
rendered initial scene or downloaded checkpoint is not a completed policy run.

## Reviewed dependencies

- Cosmos Policy source: `NVlabs/cosmos-policy`,
  commit `18a2accadf4e7a3531e56754102af5a24d2316da`.
- Policy checkpoint: `nvidia/Cosmos-Policy-LIBERO-Predict2-2B`,
  revision `cb689ec0e3347c13667d70a78a3447388f5c3bb8`.
  Exact file sizes and SHA-256 values are in `requirements/cosmos-model.json`.
- Additional base checkpoint/tokenizer: `nvidia/Cosmos-Predict2-2B-Video2World`,
  reviewed metadata revision `f50c09f5d8ab133a90cac3f4886a6471e9ba3f18`.
- Official LIBERO-Plus source and assets: the identities in the preselected
  `docs/libero-plus/plan.json`.

The Cosmos Policy code is Apache-2.0. The **policy weights use NVIDIA's NSCLv1
noncommercial license**; this prepared experiment is identified as research.
Do not treat the checkpoint as an unrestricted commercial deployment dependency.
Read the original model card and license before choosing it for a project.

## Run when the account has access

First check the existing Hub login; the helper does not accept terms or submit
an access request:

```sh
python scripts/check_cosmos_access.py --output cosmos-access.json
```

Use an isolated checkout of the pinned upstream source and its lockfile:

```sh
uv sync --extra cu128 --group libero --python 3.10
```

Install the official LIBERO-Plus source and `wand==0.6.13` into that environment;
the native runtime also needs ImageMagick's MagickWand shared library. Point
LIBERO at the checked source assets, not another simulator package's asset cache.
The recorder sets a noninteractive LIBERO configuration and uses the original
benchmark instruction from the pinned T5 cache; it rejects a missing cached
instruction instead of silently creating a new embedding.

From the Robot Reel checkout, call the upstream environment's Python:

```sh
/path/to/cosmos-policy/.venv/bin/python scripts/record_cosmos_plus.py \
  --cosmos-repo /path/to/cosmos-policy \
  --libero-repo /path/to/LIBERO-plus \
  --checkpoint /path/to/checked-policy-files \
  --plan docs/libero-plus/plan.json \
  --cache /path/to/isolated-runtime-cache \
  --output /path/to/new-recording
```

The recorder checks source revisions, tracked modifications, initial-state and
BDDL hashes, policy file identities and CUDA availability. It restores the
declared TF32 setting after the upstream loader. A completed run retains every
condition, including step limits and runtime failures. The preselected three
conditions are not a full LIBERO-Plus benchmark.

The dependency status and failed development load remain part of the release's
experiment ledger. A future completed prediction/observation comparison requires
actual model execution and new published evidence.
