"""Check all 24 chaos links at every recorded frame after native Blender import.

blender --background --python scripts/check_chaos_blender.py -- --bundle DIR
Or run with a Python environment containing bpy.
"""
import argparse
import json
import math
from pathlib import Path
import sys


def main():
    import bpy
    from mathutils import Vector

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from robot_reel.chaos import digest, verify
    from robot_reel.chaos_usd import offset
    from robot_reel.newton import point

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, required=True)
    args = parser.parse_args(sys.argv[sys.argv.index("--")+1:] if "--" in sys.argv else None)
    verify(args.bundle)
    trace = json.loads((args.bundle/"trace.json").read_text())
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.render.fps = trace["fps"]
    scene.render.fps_base = 1
    bpy.ops.wm.usd_import(filepath=str((args.bundle/"scene.usdc").resolve()))
    if scene.frame_start != 1 or scene.frame_end != len(trace["frames"]):
        raise ValueError("Wrong Blender frame range")
    if scene.rigidbody_world is not None:
        raise ValueError("Unexpected resimulation")
    maximum = 0.
    count = 0
    for frame in trace["frames"]:
        scene.frame_set(frame["frame"]+1)
        depsgraph = bpy.context.evaluated_depsgraph_get()
        for world in trace["worlds"]:
            i = world["id"]
            for link, name in enumerate(("upper", "lower")):
                obj = bpy.data.objects[f"w{i:02}_{name}"].evaluated_get(depsgraph)
                if obj.type != "MESH" or obj.rigid_body is not None:
                    raise ValueError("Expected imported presentation geometry")
                for local in ([0, 0, 0], [.5, 0, 0], [0, .5, 0], [0, 0, .5]):
                    actual = list(obj.matrix_world @ Vector(local))
                    expected = point(frame["poses"][i*2+link], [v*s for v, s in zip(local, trace["link_size_m"])])
                    expected = [v+shift for v, shift in zip(expected, offset(i))]
                    error = math.dist(actual, expected)
                    if not math.isfinite(error) or error > 1e-5:
                        raise ValueError(f"Blender pose mismatch: world {i}, sample {frame['frame']}: {error}")
                    maximum = max(maximum, error)
                count += 1
    report = {
        "blender_version": bpy.app.version_string, "checked_body_samples": count,
        "fps": scene.render.fps, "frame_start": scene.frame_start, "frame_end": scene.frame_end,
        "maximum_transform_error_m": maximum,
        "trace_sha256": digest(args.bundle/"trace.json"), "usd_sha256": digest(args.bundle/"scene.usdc"),
    }
    (args.bundle/"blender-check.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
