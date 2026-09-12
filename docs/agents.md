# Agent launcher and GPU access

`scripts/agents.py` manages Kiro, Codex and Claude in separate Git worktrees and
tmux windows. It preserves active conversations and never types commands into
an existing agent. Run it as your normal login user.

The launcher previously forced Codex into `workspace-write`, including when
the user explicitly selected another mode in the global Codex configuration.
That override prevented this host's L40S device access in the coding sandbox.

The updated launcher separates the choices:

- `--approvals auto` retains no-prompt startup flags for all three agents.
- `--codex-sandbox configured` is the default. It forwards the user's configured
  `sandbox_mode` or `default_permissions` to both new and resumed Codex sessions.
  With no explicit user selection, Codex resolves its own configuration.
- Explicit `--codex-sandbox workspace-write` still confines writes. It preserves
  configured writable roots and adds the common Git directory so linked
  worktrees can commit. An explicit network restriction is retained.
- GPU detection does not automatically select full access.
- `--require-gpu` checks NVIDIA device availability and `nvidia-smi` before
  starting any agent. Missing devices cause an error before creating windows
  or worktrees. The check is for the launcher's environment; the selected
  agent sandbox may still restrict device access.

Full access is a broad filesystem permission mode, not a GPU-only grant.
Separate worktrees still separate working files, but do not enforce filesystem
confinement in that mode. The launcher prints the selected mode and its source.
Administrator-managed requirements can still constrain the actual session.

## Install the reviewed change

From the host terminal:

```bash
cd /home/dcvuser/work/robot-reel-agents/codex
python3 scripts/install_agents.py
agents --check
```

The installer preserves an exact backup and replaces the launcher atomically.
It refuses to overwrite a launcher that changed after the reviewed version.
It does not modify the user's Codex configuration or running sessions.

Exit the active Codex CLI normally, then run:

```bash
agents -a codex --require-gpu
```

The default is to resume the existing conversation. An active CLI is retained
with its original permissions; running `agents` again cannot change that
process's sandbox. The other two agents remain in their own windows.

For the VLA workload, prepare a separate CUDA environment if it does not already
exist. The ordinary Robot Reel environment has a different MuJoCo pin:

```bash
python3 -m venv .venv-vla-gpu
.venv-vla-gpu/bin/python -m pip install -r requirements/vla-gpu.txt
```

In the new Codex session, verify actual CUDA computation:

```bash
.venv-vla-gpu/bin/python scripts/check_vla_gpu.py
```

Only a successful device-and-computation check establishes GPU readiness.
The report distinguishes a host GPU, visible NVIDIA device nodes, a CUDA-enabled
PyTorch build and a checked matrix operation actually performed on the GPU.

Environment equivalents are `AGENTS_CODEX_SANDBOX` and
`AGENTS_REQUIRE_GPU=1`. An explicit `AGENTS_CMD_CODEX` continues to own its
complete argument list; the launcher does not rewrite that custom command.

Official configuration reference:
https://developers.openai.com/codex/config-reference/
