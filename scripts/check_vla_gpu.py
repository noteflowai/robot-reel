"""Check host GPU evidence, sandbox device access and actual CUDA computation."""
import argparse
import json
import os
from pathlib import Path
import time


def inspect():
    report = {"host_gpus": [], "device_nodes": {}, "ready": False}
    for path in sorted(Path("/proc/driver/nvidia/gpus").glob("*/information")):
        info = dict(line.split(":", 1) for line in path.read_text().splitlines() if ":" in line)
        report["host_gpus"].append({
            "model": info.get("Model", "").strip(), "pci": info.get("Bus Location", "").strip(),
        })
    for name in ("nvidia0", "nvidiactl", "nvidia-uvm"):
        path = Path("/dev")/name
        report["device_nodes"][name] = {"exists": path.exists(), "read_write": os.access(path, os.R_OK|os.W_OK)}
    try:
        import torch
    except ImportError:
        report["problem"] = "PyTorch is not installed in this interpreter."
        return report
    report.update(torch=torch.__version__, cuda_build=torch.version.cuda, cuda_available=torch.cuda.is_available())
    if not torch.cuda.is_available():
        if report["host_gpus"] and not all(v["exists"] for v in report["device_nodes"].values()):
            report["problem"] = "Host GPU detected, but required device nodes are absent in this execution environment."
        else:
            report["problem"] = "CUDA is unavailable; inspect the driver, device permissions and PyTorch build."
        if torch.version.cuda is None:
            report["pytorch_problem"] = "CPU-only PyTorch; install requirements/vla-gpu.txt in a separate environment."
        return report
    try:
        a = torch.arange(256*256, dtype=torch.float32, device="cuda").reshape(256, 256)
        b = torch.eye(256, device="cuda")
        torch.cuda.synchronize()
        start = time.perf_counter()
        product = a@b
        torch.cuda.synchronize()
        report.update(
            gpu=torch.cuda.get_device_name(), cuda_matrix_seconds=time.perf_counter()-start,
            tensor_device=str(product.device), computation_correct=bool(torch.equal(product, a)),
        )
        report["ready"] = report["computation_correct"] and product.is_cuda
    except RuntimeError as exc:
        report["problem"] = str(exc)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = inspect()
    text = json.dumps(report, indent=2)+"\n"
    if args.output:
        args.output.write_text(text)
    print(text, end="")
    raise SystemExit(0 if report["ready"] else 2)


if __name__ == "__main__":
    main()
