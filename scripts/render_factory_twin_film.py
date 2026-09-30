"""Render the Factory Twin flythrough film from the checked closed-loop project (run with bpy).

blender --background --python scripts/render_factory_twin_film.py -- \
  --blend artifacts/factory-twin/factory-twin-closed.blend --output artifacts/factory-twin/film

The camera move is cinematography (a spline through fixed key poses); it is not
recorded data. Every film frame shows exactly one recorded sample, chosen by a
fixed piecewise-linear time map, and `plan.json` lists that mapping. The
scene itself is not edited: only the camera, render settings and camera
visibility of the cutaway collection change, and nothing is saved.
"""
import argparse
import json
import math
from pathlib import Path
import sys
import time

import bpy
from mathutils import Vector

FPS = 24
# (film seconds, camera location, look-at target, focal length mm)
KEYS = (
    (0.0, (190.0, -205.0, 132.0), (-6.0, 2.0, 0.0), 32),
    (4.0, (118.0, -150.0, 78.0), (-16.0, 0.0, 0.0), 32),
    (7.0, (12.0, -62.0, 32.0), (-30.0, -2.0, 2.0), 30),
    (10.0, (-35.5, -19.5, 6.5), (-45.0, -6.0, 2.6), 30),
    (12.5, (-19.0, -23.0, 7.0), (-28.0, 0.0, 1.5), 28),
    (15.0, (6.0, -24.0, 9.0), (-5.0, 0.0, 1.5), 28),
    (18.0, (62.0, -104.0, 30.0), (70.0, -56.0, 2.0), 30),
    (21.0, (150.0, -142.0, 60.0), (38.0, -28.0, 0.0), 32),
    (24.0, (200.0, -192.0, 122.0), (-10.0, 0.0, 0.0), 32),
)
# (film seconds, recorded sample): slow down around the service and demand events.
TIME_MAP = ((0.0, 0), (5.0, 300), (11.0, 520), (16.0, 1300), (21.0, 1700), (24.0, 2160))


def catmull(points, u):
    """Uniform Catmull–Rom through `points` at global parameter u in [0, len-1]."""
    n = len(points) - 1
    i = min(n - 1, max(0, int(math.floor(u))))
    t = u - i
    p0, p1, p2, p3 = (Vector(points[max(0, i - 1)]), Vector(points[i]), Vector(points[i + 1]),
                      Vector(points[min(n, i + 2)]))
    return 0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t * t
                  + (-p0 + 3 * p1 - 3 * p2 + p3) * t * t * t)


def key_parameter(seconds):
    times = [k[0] for k in KEYS]
    for i in range(len(times) - 1):
        if seconds <= times[i + 1]:
            f = (seconds - times[i]) / (times[i + 1] - times[i])
            return i + f * f * (3 - 2 * f)  # ease in and out of every key pose
    return len(times) - 1.0


def sample_at(seconds):
    for (t0, s0), (t1, s1) in zip(TIME_MAP, TIME_MAP[1:]):
        if seconds <= t1:
            return round(s0 + (s1 - s0) * (seconds - t0) / (t1 - t0))
    return TIME_MAP[-1][1]


def plan(frames):
    rows = []
    for f in range(frames):
        seconds = f / FPS
        u = key_parameter(seconds)
        lens = KEYS[min(len(KEYS) - 1, int(u))][3] + (KEYS[min(len(KEYS) - 1, int(u) + 1)][3]
                                                      - KEYS[min(len(KEYS) - 1, int(u))][3]) * (u - int(u))
        rows.append({"film_frame": f, "sample": sample_at(seconds),
                     "camera": [round(v, 4) for v in catmull([k[1] for k in KEYS], u)],
                     "target": [round(v, 4) for v in catmull([k[2] for k in KEYS], u)],
                     "lens_mm": round(lens, 3)})
    return rows


def gpu(scene):
    prefs = bpy.context.preferences.addons["cycles"].preferences
    for kind in ("OPTIX", "CUDA"):
        try:
            prefs.compute_device_type = kind
            prefs.get_devices()
            if any(d.type == kind for d in prefs.devices):
                for d in prefs.devices:
                    d.use = d.type == kind
                scene.cycles.device = "GPU"
                return kind
        except (TypeError, ValueError):
            continue
    return "CPU"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--blend", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--samples", type=int, default=48)
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--height", type=int, default=720)
    parser.add_argument("--seconds", type=float, default=KEYS[-1][0])
    parser.add_argument("--only", help="Comma-separated film frames (preview)")
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
    args = parser.parse_args(argv)
    bpy.ops.wm.open_mainfile(filepath=str(args.blend.resolve()))
    scene = bpy.context.scene
    device = gpu(scene)
    scene.cycles.samples = args.samples
    scene.cycles.use_denoising = True
    scene.cycles.denoiser = "OPTIX" if device == "OPTIX" else "OPENIMAGEDENOISE"
    scene.cycles.use_adaptive_sampling = True
    scene.cycles.adaptive_threshold = 0.03
    scene.cycles.max_bounces, scene.cycles.diffuse_bounces, scene.cycles.glossy_bounces = 6, 3, 3
    scene.cycles.transmission_bounces, scene.cycles.transparent_max_bounces = 4, 8
    scene.cycles.caustics_reflective = scene.cycles.caustics_refractive = False
    scene.render.use_persistent_data = True
    scene.render.resolution_x, scene.render.resolution_y = args.width, args.height
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    for o in bpy.data.collections["Buildings / hall cutaway"].all_objects:
        o.visible_camera = False
    data = bpy.data.cameras.new("Film camera")
    data.clip_start, data.clip_end = 0.1, 3000
    camera = bpy.data.objects.new("Camera / Film (cinematography, not recorded)", data)
    scene.collection.objects.link(camera)
    scene.camera = camera
    rows = plan(int(round(args.seconds * FPS)) + 1)
    args.output.mkdir(parents=True, exist_ok=True)
    wanted = None if not args.only else {int(v) for v in args.only.split(",")}
    started = time.time()
    for row in rows:
        path = args.output / f"film-{row['film_frame']:04d}.png"
        if (wanted is not None and row["film_frame"] not in wanted) or (wanted is None and path.exists()):
            continue
        scene.frame_set(row["sample"] + 1)  # frame k+1 holds sample k
        camera.location = row["camera"]
        camera.rotation_euler = (Vector(row["target"]) - Vector(row["camera"])).to_track_quat("-Z", "Y").to_euler()
        data.lens = row["lens_mm"]
        scene.render.filepath = str(path.resolve())
        bpy.ops.render.render(write_still=True)
    record = {"fps": FPS, "frames": len(rows), "device": device, "samples_per_pixel": args.samples,
              "resolution": [args.width, args.height], "blender_version": bpy.app.version_string,
              "keys": [{"seconds": k[0], "camera": k[1], "target": k[2], "lens_mm": k[3]} for k in KEYS],
              "time_map": [{"seconds": t, "sample": s} for t, s in TIME_MAP], "rows": rows,
              "render_seconds": round(time.time() - started, 1)}
    if wanted is None:
        (args.output / "plan.json").write_text(json.dumps(record, indent=1) + "\n")
    print("FILM_RESULT " + json.dumps({k: v for k, v in record.items() if k not in ("rows", "keys")}))


if __name__ == "__main__":
    main()
