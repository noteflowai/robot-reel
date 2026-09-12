#!/usr/bin/env bash
# Run on the GPU host (or a runner that exposes its NVIDIA devices).
set -euo pipefail
reel_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd -- "$reel_root"
gpu_python="$reel_root/.venv-vla-gpu/bin/python"
if [[ ! -x "$gpu_python" ]]; then
  printf '%s\n' 'Create .venv-vla-gpu and install requirements/vla-gpu.txt first.' >&2
  exit 2
fi
mkdir -p artifacts
"$gpu_python" scripts/check_vla_gpu.py --output artifacts/gpu-access-report.json
export HF_HOME="$reel_root/artifacts/vla-cache/huggingface"
export HF_HUB_OFFLINE=1
export MUJOCO_GL=egl
exec "$gpu_python" scripts/record_stress.py \
  --output artifacts/stress-gpu-30 --cache artifacts/vla-cache "$@" --device cuda
