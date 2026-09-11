import argparse
import json
import os
from pathlib import Path


def main():
    ap = argparse.ArgumentParser(description="Record a robot simulation and export shareable films.")
    ap.add_argument("--output", type=Path, default=Path("artifacts/demo"))
    ap.add_argument("--agent", action="store_true", help="Use a live Bedrock agent (billable); otherwise scripted")
    ap.add_argument("--model", help="Bedrock model or inference profile ID; required with --agent")
    ap.add_argument("--region", default="us-west-2")
    ap.add_argument("--render-only", action="store_true", help="Re-edit an existing capture without a model call")
    args = ap.parse_args()
    if args.agent and not args.model:
        ap.error("--agent requires an explicit --model")
    os.environ.setdefault("MUJOCO_GL", "egl")
    args.output.mkdir(parents=True, exist_ok=True)
    from .capture import Capture, manifest, run_arm
    from .film import render
    if not args.render_only:
        if (args.output / "so100-trace.json").exists():
            ap.error("Output already contains a capture; choose a fresh directory or use --render-only")
        print("Recording SO-100...", flush=True)
        run_arm(args.output, args.agent, args.model, args.region)
        print("Recording G1 (scripted kinematic showcase)...", flush=True)
        g1 = Capture(args.output, "unitree_g1")
        try:
            g1.showcase()
        finally:
            g1.close()
    print("Exporting landscape and portrait films...", flush=True)
    render(args.output)
    if args.render_only:
        previous = json.loads((args.output / "manifest.json").read_text())
        manifest(args.output, previous["arm_director"], previous["model_id"], previous["region"])
    else:
        manifest(args.output, "agent" if args.agent else "scripted", args.model, args.region)
    print(f"Done: {args.output.resolve()}", flush=True)


if __name__ == "__main__":
    main()
