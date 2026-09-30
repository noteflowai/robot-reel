"""Render views of the factory twin project with Cycles (run with bpy).

blender --background --python scripts/render_factory_twin.py -- \
  --blend factory-twin-closed.blend --view hall --frames 1321 --output renders/ --samples 128

Views select a saved camera; ``cutaway`` views hide the hall roof and south
wall from the camera only (they still cast shadows and remain in the file).
"""
import argparse
import json
from pathlib import Path
import sys
import time

import bpy

VIEWS = {
    "hall": ("Camera / Hall cutaway", True),
    "aerial": ("Camera / Campus aerial", False),
    "aerial-cutaway": ("Camera / Campus aerial", True),
    "cnc": ("Camera / CNC twin close-up", True),
    "energy": ("Camera / Energy & parking", False),
    "line": ("Camera / Line level", False),
}


def gpu(scene):
    prefs = bpy.context.preferences.addons["cycles"].preferences
    for kind in ("OPTIX", "CUDA"):
        try:
            prefs.compute_device_type = kind
            prefs.get_devices()
            devices = [d for d in prefs.devices if d.type == kind]
            if devices:
                for d in prefs.devices:
                    d.use = d.type == kind
                scene.cycles.device = "GPU"
                return kind, [d.name for d in devices]
        except (TypeError, ValueError):
            continue
    scene.cycles.device = "CPU"
    return "CPU", []


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--blend", type=Path, required=True)
    parser.add_argument("--view", choices=sorted(VIEWS), required=True)
    parser.add_argument("--frames", required=True, help="Comma-separated frame numbers")
    parser.add_argument("--output", type=Path, required=True, help="Directory for PNG files")
    parser.add_argument("--prefix", default="")
    parser.add_argument("--samples", type=int, default=128)
    parser.add_argument("--width", type=int, default=1920)
    parser.add_argument("--height", type=int, default=1080)
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
    args = parser.parse_args(argv)
    bpy.ops.wm.open_mainfile(filepath=str(args.blend.resolve()))
    scene = bpy.context.scene
    device = gpu(scene)
    camera, cutaway = VIEWS[args.view]
    scene.camera = bpy.data.objects[camera]
    for o in bpy.data.collections["Buildings / hall cutaway"].all_objects:
        o.visible_camera = not cutaway
    scene.cycles.samples = args.samples
    scene.cycles.use_denoising = True
    scene.render.resolution_x, scene.render.resolution_y = args.width, args.height
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    args.output.mkdir(parents=True, exist_ok=True)
    rendered = []
    for frame in (int(f) for f in args.frames.split(",")):
        scene.frame_set(frame)
        path = args.output / f"{args.prefix}{args.view}-{frame:04d}.png"
        scene.render.filepath = str(path.resolve())
        start = time.time()
        bpy.ops.render.render(write_still=True)
        rendered.append({"frame": frame, "file": path.name, "seconds": round(time.time() - start, 2)})
    print("RENDER_RESULT " + json.dumps({"view": args.view, "camera": camera, "cutaway": cutaway,
                                         "device": device, "samples": args.samples, "frames": rendered}))


if __name__ == "__main__":
    main()
