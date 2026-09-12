"""Import the Newton USD in Blender and check every recorded body transform.

blender --background --python scripts/check_newton_blender.py -- --bundle DIR
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import sys


def main():
    import bpy
    from mathutils import Vector

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from robot_reel.newton import point, verify

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--report", type=Path)
    argv = sys.argv[sys.argv.index("--")+1:] if "--" in sys.argv else sys.argv[1:]
    args = parser.parse_args(argv)
    verify(args.bundle)
    trace = json.loads((args.bundle/"trace.json").read_text())
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    # Blender imports the USD frame range but does NOT adopt its fps automatically.
    scene.render.fps = trace["fps"]
    scene.render.fps_base = 1
    bpy.ops.wm.usd_import(filepath=str((args.bundle/"scene.usda").resolve()))
    if scene.frame_start != 1 or scene.frame_end != len(trace["frames"]):
        raise ValueError("Blender imported an incorrect frame range")
    if scene.rigidbody_world is not None:
        raise ValueError("Unexpected Blender physics")
    maximum = 0.
    count = 0
    for frame in trace["frames"]:
        scene.frame_set(frame["frame"]+1)
        depsgraph = bpy.context.evaluated_depsgraph_get()
        for index, body in enumerate(trace["bodies"]):
            obj = bpy.data.objects[body["name"]].evaluated_get(depsgraph)
            if obj.type != "MESH" or obj.rigid_body is not None:
                raise ValueError("Expected imported presentation geometry")
            for local in ([0, 0, 0], [.5, 0, 0], [0, .5, 0], [0, 0, .5]):
                actual = list(obj.matrix_world @ Vector(local))
                expected = point(frame["poses"][index], [v*s for v, s in zip(local, body["size"])])
                error = math.dist(actual, expected)
                if not math.isfinite(error) or error > 1e-5:
                    raise ValueError(f"Blender transform mismatch: {body['name']}, sample {frame['frame']}: {error}")
                maximum = max(maximum, error)
            count += 1
    report = {
        "blender_version": bpy.app.version_string, "checked_body_samples": count,
        "fps": scene.render.fps, "frame_start": scene.frame_start, "frame_end": scene.frame_end,
        "maximum_transform_error_m": maximum,
        "trace_sha256": hashlib.sha256((args.bundle/"trace.json").read_bytes()).hexdigest(),
        "usd_sha256": hashlib.sha256((args.bundle/"scene.usda").read_bytes()).hexdigest(),
    }
    if args.report:
        args.report.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
