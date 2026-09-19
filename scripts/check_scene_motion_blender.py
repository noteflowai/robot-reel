"""Independently reopen a motion project and check all frames and camera projections."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import sys


def identity(path):
    with Path(path).open("rb") as stream:
        return {"sha256": hashlib.file_digest(stream, "sha256").hexdigest(),
                "bytes": Path(path).stat().st_size}


def check(root, check_renders=False):
    import bpy
    import numpy as np
    from mathutils import Vector
    from bpy_extras.object_utils import world_to_camera_view

    root = Path(root).resolve()
    project = json.loads((root / "project.json").read_text())
    files = dict(project["files"])
    render_files = project.get("render_files", {})
    if set(render_files) != {f"renders/frame_{frame+1:04}.png"
                             for frame in project["rendered_source_frames"]}:
        raise ValueError("render inventory differs from its source frames")
    if check_renders:
        files.update(render_files)
    for name, expected in files.items():
        path = root / name
        if not path.resolve().is_relative_to(root) or path.is_symlink() or identity(path) != expected:
            raise ValueError(f"project input changed: {name}")
    trace = json.loads((root / "trace.json").read_text())
    geometry = json.loads((root / "geometry.json").read_text())["geometries"]
    bpy.ops.wm.open_mainfile(filepath=str(root / "scene-motion.blend"), use_scripts=False)
    scene = bpy.context.scene
    if scene["robot_reel_motion_trace_sha256"] != identity(root / "trace.json")["sha256"]:
        raise ValueError("Blender project names another recording")
    if scene["robot_reel_motion_usd_sha256"] != identity(root / "motion.usdc")["sha256"]:
        raise ValueError("Blender project names another USD")
    if scene.unit_settings.scale_length != 1 or scene.render.fps != trace["plan"]["sample_hz"]:
        raise ValueError("native units or playback clock differ")
    if scene.frame_start != 1 or scene.frame_end != len(trace["frames"]):
        raise ValueError("native frame range differs")
    if not bpy.data.cache_files or any(Path(bpy.path.abspath(cache.filepath)).resolve() != root / "motion.usdc"
                                       for cache in bpy.data.cache_files):
        raise ValueError("animation cache is not the included USD")
    maximum = pixel_error = position_error = 0.
    projected = outside = 0
    camera = scene.camera
    width, height = trace["camera"]["width"], trace["camera"]["height"]
    if camera.name != "RecordedCamera" or (scene.render.resolution_x, scene.render.resolution_y) != (width, height):
        raise ValueError("native camera or output dimensions differ")
    if not math.isclose(camera.data.lens, 50, abs_tol=1e-4):
        raise ValueError("USD metre-stage lens units were not preserved")
    local_matrices = {}

    def pose_matrix(position, quaternion):
        w, x, y, z = quaternion
        matrix = np.eye(4, dtype=np.float64)
        matrix[:3, :3] = [
            [1-2*(y*y+z*z), 2*(x*y-z*w), 2*(x*z+y*w)],
            [2*(x*y+z*w), 1-2*(x*x+z*z), 2*(y*z-x*w)],
            [2*(x*z-y*w), 2*(y*z+x*w), 1-2*(x*x+y*y)],
        ]
        matrix[:3, 3] = position
        return matrix

    for item in geometry:
        obj = bpy.data.objects[item["name"]]
        mesh = obj.data
        points = np.empty(len(mesh.vertices)*3, dtype="<f4")
        mesh.vertices.foreach_get("co", points)
        indices = np.empty(len(mesh.loops), dtype="<i4")
        mesh.loops.foreach_get("vertex_index", indices)
        if (len(mesh.vertices) != item["vertices"] or len(mesh.polygons) != item["triangles"]
                or hashlib.sha256(points.tobytes()).hexdigest() != item["points_f32_le_sha256"]
                or hashlib.sha256(indices.tobytes()).hexdigest() != item["faces_i32_le_sha256"]):
            raise ValueError(f"native robot mesh differs: {item['name']}")
        local_matrices[item["name"]] = pose_matrix(item["position_m"], item["quaternion_wxyz"])
    for frame in trace["frames"]:
        scene.frame_set(frame["frame"] + 1)
        graph = bpy.context.evaluated_depsgraph_get()
        expected_bodies = {}
        for name, pose in zip(trace["bodies"], frame["body_poses"]):
            matrix = pose_matrix(pose[:3], pose[3:])
            expected_bodies[name] = matrix
            actual = bpy.data.objects[name].evaluated_get(graph).matrix_world
            maximum = max(maximum, float(np.max(np.abs(np.asarray(actual) - np.asarray(matrix)))))
            position_error = max(position_error, float(np.max(np.abs(
                np.asarray(actual)[:3, 3] - np.asarray(pose[:3])))))
            offset = np.asarray(pose[:3]) - trace["camera"]["position_m"]
            right, up, back = np.asarray(trace["camera"]["axes_world"])
            depth = -float(back @ offset)
            if depth <= 0:
                continue
            expected_x = width/2 + trace["camera"]["focal_px"][0] * float(right @ offset) / depth
            expected_y = height/2 - trace["camera"]["focal_px"][1] * float(up @ offset) / depth
            native = world_to_camera_view(scene, camera, Vector(pose[:3]))
            pixel_error = max(pixel_error, abs(native.x*width - expected_x),
                              abs((1-native.y)*height - expected_y))
            projected += 1
            outside += int(not (0 <= expected_x <= width and 0 <= expected_y <= height))
        for item in geometry:
            matrix = expected_bodies[item["body"]] @ local_matrices[item["name"]]
            actual = bpy.data.objects[item["name"]].evaluated_get(graph).matrix_world
            maximum = max(maximum, float(np.max(np.abs(np.asarray(actual) - np.asarray(matrix)))))
    if maximum > 3e-6 or pixel_error > .002:
        raise ValueError(f"native frame import differs: matrix={maximum}, pixels={pixel_error}")
    if not all(math.isfinite(x) for x in (maximum, pixel_error)):
        raise ValueError("non-finite native comparison")
    return {
        "schema": "robot-reel.scene-motion-blender-check.v1", "passed": True,
        "blender": bpy.app.version_string, "project": identity(root / "scene-motion.blend"),
        "source_trace": identity(root / "trace.json"), "usd": identity(root / "motion.usdc"),
        "frames": len(trace["frames"]), "body_transforms": len(trace["frames"])*15,
        "visual_geometry_transforms": len(trace["frames"])*len(geometry),
        "checked_local_vertices": sum(item["vertices"] for item in geometry),
        "max_world_matrix_error": maximum, "camera_projections": projected,
        "max_body_position_error_m": position_error,
        "virtual_camera_lens_mm": camera.data.lens,
        "checked_render_files": len(render_files) if check_renders else 0,
        "projections_outside_image": outside, "max_projection_error_px": pixel_error,
        "scope": "Every native body/visual transform and virtual-camera projection; no physical survey or real-camera calibration.",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--check-renders", action="store_true",
                        help="Also verify every producer PNG (not needed to reopen a portable project).")
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1:])
    if args.output.exists():
        raise ValueError("choose a new native-check output")
    result = check(args.project, args.check_renders)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2), flush=True)
