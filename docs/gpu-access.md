# GPU collection and access checks

CUDA computation was verified on **2026-09-12** using an **NVIDIA L40S**,
driver **595.91.07**, PyTorch **2.11.0+cu130** and CUDA **13.0**. The preflight
checked a matrix multiplication on `cuda:0`; the three-condition short run
then passed paired-state/noise validation and decoded-camera checks.
The complete [published experiment](stress.md) subsequently recorded all
30 CUDA trials: 3,525 applied actions and 360 policy calls, with zero execution
errors. Mean measured policy time was 0.491 seconds per call.

The separate `.venv-vla-gpu` environment keeps the pinned LeRobot, LIBERO and
MuJoCo versions. The ordinary Robot Reel rendering environment has a different
MuJoCo pin and should not be installed into this VLA environment.

From a GPU-capable host or coding session:

```bash
cd /home/dcvuser/work/robot-reel-agents/codex
bash scripts/run_stress_gpu.sh
```

The job first checks the actual CUDA device and matrix computation, then
records a separate GPU experiment in `artifacts/stress-gpu-30`. It uses the
cached, pinned weights and assets. No additional model download is needed
when those snapshots are cached. If device access is absent, it exits with
diagnostics before any trial starts. Pass `--resume` to continue the unchanged
experiment. CPU trials and short smoke runs do not contribute to the published
GPU results.

## If a host GPU is invisible inside the agent

Check from the environment that will actually run inference:

```bash
.venv-vla-gpu/bin/python scripts/check_vla_gpu.py
```

The report distinguishes host hardware, `/dev/nvidia*` access, a CUDA-enabled
PyTorch build, and actual computation. Host `nvidia-smi` alone cannot establish
that an agent's commands have device access.

The tracked [agent launcher](agents.md) respects the user's chosen Codex
permissions. Installing the launcher does not update an active session's
effective permissions. On this host, a resumed conversation still used
`workspace-write`; CUDA became accessible after the user changed that session
to Full Access with `/permissions`. `/status` and `/debug-config` help inspect
the effective configuration and its layers.

Full Access grants broad host access, not a device-only exception. A sandboxed
runner instead needs explicit GPU support from its execution environment.
Do not assume adding a writable filesystem path enables device passthrough.
Always repeat the real CUDA check after changing session or runner permissions.

Official configuration and session commands:

- https://developers.openai.com/codex/config-reference/
- https://developers.openai.com/codex/cli/slash-commands/
