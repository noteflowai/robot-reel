import argparse
import json
import os
import sys
from pathlib import Path


def main():
    if sys.argv[1:2] == ["libero-plus"]:
        from .libero_plus_site import main as libero_main
        return libero_main(sys.argv[2:])
    if sys.argv[1:2] == ["scene-lab"]:
        from .scene_lab import main as scene_main
        return scene_main(sys.argv[2:])
    if sys.argv[1:2] == ["solver-lab"]:
        from .solver_lab import main as solver_main
        return solver_main(sys.argv[2:])
    if sys.argv[1:2] == ["microduck-review"]:
        from .microduck_review import main as review_main
        return review_main(sys.argv[2:])
    if sys.argv[1:2] == ["cloth"]:
        from .cloth import main as cloth_main
        return cloth_main(sys.argv[2:])
    if sys.argv[1:2] == ["stress"]:
        from .stress import main as stress_main
        return stress_main(sys.argv[2:])
    if sys.argv[1:2] == ["vla"]:
        from .vla import main as vla_main
        return vla_main(sys.argv[2:])
    if sys.argv[1:2] == ["direct"]:
        from .director import main as director_main
        return director_main(sys.argv[2:])
    if sys.argv[1:2] == ["mcp"]:
        from .director_mcp import main as mcp_main
        return mcp_main(sys.argv[2:])
    if sys.argv[1:2] == ["newton"]:
        from .newton import main as newton_main
        return newton_main(sys.argv[2:])
    if sys.argv[1:2] == ["blender"]:
        from .blender import main as blender_main
        return blender_main(sys.argv[2:])
    if sys.argv[1:2] == ["compare"]:
        from .compare import main as compare_main
        return compare_main(sys.argv[2:])
    ap = argparse.ArgumentParser(
        description="Record a robot simulation and export shareable films.",
        epilog="Other commands: libero-plus, scene-lab, solver-lab, microduck-review, compare, blender, newton, cloth, direct, mcp, vla, stress. Use COMMAND --help for details.",
    )
    ap.add_argument("--pack", choices=["studio", "microduck", "braking"], default="studio")
    ap.add_argument("--speed", type=float, help="Microduck forward command in m/s (0–0.6; default 0.5)")
    ap.add_argument("--output", type=Path, default=Path("artifacts/demo"))
    director = ap.add_mutually_exclusive_group()
    director.add_argument("--shots", type=Path, help="Four-shot JSON plan for the scripted arm")
    director.add_argument("--agent", action="store_true", help="Use a live Bedrock agent (billable); otherwise scripted")
    ap.add_argument("--model", help="Bedrock model or inference profile ID; required with --agent")
    ap.add_argument("--region", default="us-west-2")
    ap.add_argument("--render-only", action="store_true", help="Re-edit an existing capture without a model call")
    args = ap.parse_args()
    if args.speed is not None:
        if args.pack != "microduck":
            ap.error("--speed applies only to a new Microduck capture")
        from .microduck import validate_speed
        try:
            validate_speed(args.speed)
        except ValueError as exc:
            ap.error(str(exc))
    if args.agent and not args.model:
        ap.error("--agent requires an explicit --model")
    if args.render_only and (args.agent or args.shots):
        ap.error("--render-only cannot change the recording's director or shots")
    if args.pack != "studio":
        if args.agent or args.shots or args.render_only:
            ap.error("Demo packs use their own recorded controller; omit --agent, --shots, and --render-only")
        os.environ.setdefault("MUJOCO_GL", "glfw" if sys.platform == "darwin" else "egl")
        from .packs import run_pack
        run_pack(args.output, args.pack, speed=.5 if args.speed is None else args.speed)
        return
    shot_plan = None
    if args.shots:
        from .plans import load_plan
        try:
            shot_plan = load_plan(args.shots)
        except (ValueError, OSError) as exc:
            ap.error(str(exc))
    previous = None
    if args.render_only:
        from .verify import verify
        verify(args.output)
        previous = json.loads((args.output / "manifest.json").read_text())
    os.environ.setdefault("MUJOCO_GL", "glfw" if sys.platform == "darwin" else "egl")
    args.output.mkdir(parents=True, exist_ok=True)
    from .capture import Capture, manifest, run_arm
    from .film import render
    if not args.render_only:
        if (args.output / "so100-trace.json").exists():
            ap.error("Output already contains a capture; choose a fresh directory or use --render-only")
        print("Recording SO-100...", flush=True)
        run_arm(args.output, args.agent, args.model, args.region, shot_plan)
        print("Recording G1 (scripted kinematic showcase)...", flush=True)
        g1 = Capture(args.output, "unitree_g1")
        try:
            g1.showcase()
        finally:
            g1.close()
    print("Exporting landscape and portrait films...", flush=True)
    render(args.output, names=previous.get("scenes", ["so100", "unitree_g1"]) if previous else ("so100", "unitree_g1"))
    if args.render_only:
        manifest(args.output, previous["arm_director"], previous["model_id"], previous["region"], previous.get("scenes"), previous.get("pack"))
    else:
        manifest(args.output, "agent" if args.agent else "scripted", args.model, args.region)
    from .viewer import export_viewer
    export_viewer(args.output)
    if previous:
        manifest(args.output, previous["arm_director"], previous["model_id"], previous["region"], previous.get("scenes"), previous.get("pack"))
    else:
        manifest(args.output, "agent" if args.agent else "scripted", args.model, args.region)
    print(f"Done: {args.output.resolve()} (open index.html for interactive replay)", flush=True)


if __name__ == "__main__":
    sys.exit(main())
