"""Render a compact Cycles preview from a checked .blend, without changing it."""
import argparse
from pathlib import Path
import sys


def main():
    import bpy
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--blend", type=Path, required=True)
    parser.add_argument("--frames", type=Path, required=True)
    parser.add_argument("--scale", type=int, default=75, help="Percentage of the project's render resolution")
    parser.add_argument("--samples", type=int, default=8)
    parser.add_argument("--threads", type=int, default=4)
    args_list = sys.argv[sys.argv.index("--")+1:] if "--" in sys.argv else sys.argv[1:]
    args = parser.parse_args(args_list)
    if not 1 <= args.scale <= 100 or args.samples < 1 or not 1 <= args.threads <= 32:
        parser.error("--scale must be 1–100, --samples positive, and --threads 1–32")
    if args.frames.exists() and any(args.frames.iterdir()):
        parser.error("Use an empty PNG sequence directory")
    bpy.ops.wm.open_mainfile(filepath=str(args.blend.resolve()), use_scripts=False)
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.render.resolution_percentage = args.scale
    scene.render.threads_mode = "FIXED"
    scene.render.threads = args.threads
    scene.render.use_persistent_data = True
    scene.cycles.samples = args.samples
    scene.cycles.use_denoising = True
    scene.cycles.denoising_prefilter = "FAST"
    scene.cycles.denoising_quality = "FAST"
    scene.render.image_settings.file_format = "PNG"
    args.frames.mkdir(parents=True, exist_ok=True)
    scene.render.filepath = str(args.frames.resolve() / "frame-")
    bpy.ops.render.render(animation=True)
    print(f"Rendered all {scene.frame_end-scene.frame_start+1} frames with Blender {bpy.app.version_string}")


if __name__ == "__main__":
    main()
