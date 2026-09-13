"""Read every imported deforming vertex through Blender's evaluated mesh."""
import argparse
import json
import math
from pathlib import Path
import sys


def main():
    import bpy
    from mathutils import Vector

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from robot_reel.cloth import CASES, VERTICES, digest, floats, load, verify, vertex
    from robot_reel.cloth_usd import offset

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args(sys.argv[sys.argv.index("--")+1:])
    verify(args.bundle)
    trace, positions, _ = load(args.bundle)
    q = floats(positions, len(positions)//4)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.render.fps = trace["fps"]
    scene.render.fps_base = 1
    bpy.ops.wm.usd_import(filepath=str((args.bundle/"scene.usdc").resolve()))
    if scene.frame_start != 1 or scene.frame_end != trace["frame_count"] or scene.rigidbody_world:
        raise ValueError("Blender imported an incorrect cloth scene or clock")
    maximum = 0.
    for f in range(trace["frame_count"]):
        scene.frame_set(f+1)
        depsgraph = bpy.context.evaluated_depsgraph_get()
        for c, case in enumerate(CASES):
            obj = bpy.data.objects[case["id"]].evaluated_get(depsgraph)
            if obj.type != "MESH" or obj.rigid_body or any(m.type == "CLOTH" for m in obj.modifiers):
                raise ValueError("Expected an imported vertex cache, without resimulation")
            mesh = obj.to_mesh()
            try:
                if len(mesh.vertices) != VERTICES or [list(p.vertices) for p in mesh.polygons] != trace["triangles"]:
                    raise ValueError("Blender cloth topology differs from source")
                for i, v in enumerate(mesh.vertices):
                    actual = obj.matrix_world @ Vector(v.co)
                    expected = [a+b for a, b in zip(vertex(q, f, c, i), offset(c))]
                    error = math.dist(actual, expected)
                    if not math.isfinite(error) or error > 1e-5:
                        raise ValueError(f"Blender cloth differs: case {c}, sample {f}, vertex {i}: {error}")
                    maximum = max(maximum, error)
            finally:
                obj.to_mesh_clear()
    report = {
        "blender_version": bpy.app.version_string,
        "checked_vertex_samples": trace["frame_count"]*len(CASES)*VERTICES,
        "maximum_position_error_m": maximum, "fps": scene.render.fps,
        "frame_start": scene.frame_start, "frame_end": scene.frame_end,
        **{key: digest(args.bundle/name) for key, name in (
            ("trace_sha256", "trace.json"), ("positions_sha256", "positions.f32"), ("usd_sha256", "scene.usdc"),
        )},
    }
    args.report.write_text(json.dumps(report, indent=2)+"\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
