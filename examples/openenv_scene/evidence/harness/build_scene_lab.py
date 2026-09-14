"""Run with Blender to turn a checked photogrammetry asset into an editable scene.

Produces a standard glTF mesh, texture-sampled surface Gaussians, a separately
identified heightfield collision proxy and a native .blend file. The Gaussians
are derived from the mesh; this is not a trained multi-view 3DGS reconstruction.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import struct
import sys
from pathlib import Path


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def write_json(path, data):
    Path(path).write_text(json.dumps(data, indent=2, allow_nan=False) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--edit", type=Path)
    parser.add_argument("--gaussians", type=int, default=25000)
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1:])
    source = args.source.resolve()
    output = args.output.resolve()
    manifest = json.loads((source / "source-manifest.json").read_text())
    for name, row in manifest["files"].items():
        path = source / name
        if path.is_symlink() or not path.resolve().is_relative_to(source):
            raise ValueError("asset path must stay inside the checked source")
        if path.stat().st_size != row["bytes"] or sha(path) != row["sha256"]:
            raise ValueError(f"source asset changed: {name}")
    if manifest.get("asset_id") != "coast_rocks_02" or manifest.get("license") != "CC0-1.0":
        raise ValueError("this checked scene recipe requires Coast Rocks 02 under CC0")
    edit = {"terrain_z_scale": 1.0, "sun_azimuth_degrees": 135.0, "sun_energy": 2.0}
    if args.edit:
        supplied = json.loads(args.edit.read_text())
        if set(supplied) != {"schema", *edit} or supplied["schema"] != "robot-reel.scene-edit.v1":
            raise ValueError("unexpected scene edit schema or fields")
        edit.update({key: supplied[key] for key in edit})
    for key, low, high in (
        ("terrain_z_scale", 0.5, 2.0), ("sun_azimuth_degrees", 0, 360), ("sun_energy", 0.1, 5.0),
    ):
        value = edit[key]
        if type(value) not in (int, float) or not math.isfinite(value) or not low <= value <= high:
            raise ValueError(f"edit field {key} is outside its supported range")
    if not 1000 <= args.gaussians <= 100000:
        raise ValueError("choose 1000..100000 surface Gaussians")
    output.mkdir(parents=True, exist_ok=False)

    import bpy
    import numpy as np
    from mathutils import Matrix, Vector
    from mathutils.bvhtree import BVHTree

    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    bpy.ops.import_scene.gltf(filepath=str(source / "coast_rocks_02_1k.gltf"))
    meshes = [obj for obj in bpy.context.scene.objects if obj.type == "MESH"]
    if len(meshes) != 1:
        raise ValueError("expected one scanned terrain mesh")
    terrain = meshes[0]
    terrain.name = "ScanTerrain"
    original_polygons = len(terrain.data.polygons)
    bpy.context.view_layer.objects.active = terrain
    terrain.select_set(True)
    if original_polygons > 120000:
        modifier = terrain.modifiers.new("BrowserMeshReduction", "DECIMATE")
        modifier.ratio = 120000 / original_polygons
        bpy.ops.object.modifier_apply(modifier=modifier.name)
    # Centre the scene for inspection while retaining metres.
    corners = [terrain.matrix_world @ Vector(point) for point in terrain.bound_box]
    minimum = Vector(tuple(min(point[axis] for point in corners) for axis in range(3)))
    maximum = Vector(tuple(max(point[axis] for point in corners) for axis in range(3)))
    recenter = Vector((-(minimum.x + maximum.x) / 2, -(minimum.y + maximum.y) / 2, -minimum.z))
    terrain.matrix_world.translation += recenter
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    terrain.scale.z *= edit["terrain_z_scale"]
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    bpy.context.view_layer.update()
    mesh = terrain.data
    mesh.calc_loop_triangles()
    world_vertices = np.array([tuple(terrain.matrix_world @ vertex.co) for vertex in mesh.vertices])
    low = world_vertices.min(axis=0)
    high = world_vertices.max(axis=0)
    triangles = np.array([triangle.vertices[:] for triangle in mesh.loop_triangles], dtype=np.int32)
    points = world_vertices[triangles]
    normals = np.cross(points[:, 1] - points[:, 0], points[:, 2] - points[:, 0])
    double_areas = np.linalg.norm(normals, axis=1)
    valid = double_areas > 1e-10
    areas = np.where(valid, double_areas / 2, 0)
    rng = np.random.default_rng(20260914)
    sampled = rng.choice(len(triangles), size=args.gaussians, p=areas / areas.sum())
    a = np.sqrt(rng.random(args.gaussians))
    b = rng.random(args.gaussians)
    weights = np.stack([1 - a, a * (1 - b), a * b], axis=1)
    positions = (points[sampled] * weights[:, :, None]).sum(axis=1)
    sampled_normals = normals[sampled] / double_areas[sampled, None]
    uv_layer = mesh.uv_layers.active
    if uv_layer is None:
        raise ValueError("the scanned source needs texture coordinates")
    loop_indices = np.array([triangle.loops[:] for triangle in mesh.loop_triangles])
    uv = np.array([tuple(loop.uv) for loop in uv_layer.data])
    sampled_uv = (uv[loop_indices[sampled]] * weights[:, :, None]).sum(axis=1)
    texture = bpy.data.images.load(str(source / "textures/coast_rocks_02_diff_1k.jpg"))
    width, height = texture.size[:]
    pixels = np.array(texture.pixels[:], dtype=np.float32).reshape(height, width, 4)
    cols = np.floor(sampled_uv[:, 0] * width).astype(int) % width
    rows = np.floor(sampled_uv[:, 1] * height).astype(int) % height
    rgb = np.clip(pixels[rows, cols, :3] * 255, 0, 255).astype(np.uint8)
    radius = float(math.sqrt(areas.sum() / args.gaussians) * 0.55)
    to_browser = Matrix.Rotation(-math.pi / 2, 4, "X")
    rotation_to_browser = to_browser.to_quaternion()
    with (output / "terrain.splat").open("wb") as stream:
        for position, normal, color in zip(positions, sampled_normals, rgb):
            location = to_browser @ Vector(position)
            rotation = rotation_to_browser @ Vector(normal).to_track_quat("Z", "Y")
            packed_rotation = bytes(
                max(0, min(255, round(component * 128 + 128))) for component in rotation
            )
            stream.write(struct.pack(
                "<6f4B", *location, radius, radius, radius * 0.15, *color, 220
            ) + packed_rotation)

    # Heightfield approximation is a distinct physical representation. It fills
    # scan holes with a base plane and cannot reproduce overhangs or caves.
    graph = bpy.context.evaluated_depsgraph_get()
    bvh = BVHTree.FromObject(terrain, graph)
    inverse = terrain.matrix_world.inverted()
    resolution = 65
    vertices = []
    missing = 0
    for y in np.linspace(low[1], high[1], resolution):
        for x in np.linspace(low[0], high[0], resolution):
            origin = inverse @ Vector((float(x), float(y), float(high[2] + 10)))
            direction = inverse.to_3x3() @ Vector((0, 0, -1))
            hit, _, _, _ = bvh.ray_cast(origin, direction)
            if hit is None:
                z = float(low[2])
                missing += 1
            else:
                z = float((terrain.matrix_world @ hit).z)
            vertices.append((float(x), float(y), z))
    faces = []
    for y in range(resolution - 1):
        for x in range(resolution - 1):
            i = y * resolution + x
            faces.extend([(i, i + 1, i + resolution), (i + 1, i + resolution + 1, i + resolution)])
    collision_data = bpy.data.meshes.new("CollisionHeightfield")
    collision_data.from_pydata(vertices, [], faces)
    collision = bpy.data.objects.new("CollisionHeightfield", collision_data)
    bpy.context.collection.objects.link(collision)
    material = bpy.data.materials.new("CollisionProxyMint")
    material.diffuse_color = (0.08, 0.8, 0.6, 1)
    collision.data.materials.append(material)
    collision.hide_render = True
    collision.display_type = "WIRE"
    write_json(output / "collision-heightfield.json", {
        "schema": "robot-reel.heightfield.v1", "unit": "metre", "up_axis": "Z",
        "resolution": resolution, "bounds": [low.tolist(), high.tolist()],
        "heights_m": [row[2] for row in vertices], "filled_samples": missing,
        "scope": "Single-valued heightfield proxy; scan holes filled at the base height.",
    })
    # Export both named representations in standard glTF Y-up coordinates.
    bpy.ops.object.select_all(action="DESELECT")
    terrain.select_set(True)
    collision.select_set(True)
    bpy.ops.export_scene.gltf(
        filepath=str(output / "scene.glb"), export_format="GLB",
        use_selection=True, export_yup=True, export_apply=True,
    )
    scene = bpy.context.scene
    bpy.ops.object.light_add(type="SUN", location=(0, 0, float(high[2] + 15)))
    sun = bpy.context.object
    sun.name = "ReviewSun"
    sun.rotation_euler = (math.radians(25), math.radians(-25), math.radians(edit["sun_azimuth_degrees"]))
    sun.data.energy = edit["sun_energy"]
    sun.data.angle = math.radians(8)
    span = max(high[0] - low[0], high[1] - low[1])
    target = Vector((0, 0, float((low[2] + high[2]) / 2)))
    bpy.ops.object.camera_add(location=(span * 0.72, -span * 0.85, span * 0.63))
    camera = bpy.context.object
    camera.name = "ReviewCamera"
    camera.rotation_euler = (target - camera.location).to_track_quat("-Z", "Y").to_euler()
    camera.data.type = "ORTHO"
    camera.data.ortho_scale = span * 1.32
    camera.data.clip_end = 1000
    scene.camera = camera
    scene.world.color = (0.16, 0.19, 0.23)
    scene.render.engine = "CYCLES"
    preferences = bpy.context.preferences.addons["cycles"].preferences
    preferences.compute_device_type = "OPTIX"
    preferences.get_devices()
    devices = []
    for device in preferences.devices:
        device.use = device.type == "OPTIX"
        if device.use:
            devices.append(device.name)
    if not devices:
        raise ValueError("the declared OptiX GPU renderer is unavailable")
    scene.cycles.device = "GPU"
    scene.cycles.samples = 32
    scene.cycles.use_denoising = True
    scene.render.resolution_x = 1200
    scene.render.resolution_y = 720
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.filepath = str(output / "preview.png")
    scene.view_settings.view_transform = "AgX"
    scene["robot_reel_source_sha256"] = sha(source / "source-manifest.json")
    scene["robot_reel_edit"] = json.dumps(edit, sort_keys=True)
    bpy.ops.file.pack_all()
    bpy.ops.wm.save_as_mainfile(filepath=str(output / "scene.blend"), compress=True)
    bpy.ops.render.render(write_still=True)
    write_json(output / "edit.json", {"schema": "robot-reel.scene-edit.v1", **edit})
    write_json(output / "scene.json", {
        "schema": "robot-reel.scene-lab.v1", "source": manifest,
        "source_manifest_sha256": sha(source / "source-manifest.json"),
        "edit": edit, "blender_version": bpy.app.version_string,
        "renderer": {"engine": "Cycles", "backend": "OptiX", "devices": devices, "samples": 32},
        "geometry": {
            "source_polygons": original_polygons, "display_triangles": len(triangles),
            "world_unit": "metre", "native_up": "Z", "browser_up": "Y",
            "recentre_translation_m": list(recenter), "bounds_m": [low.tolist(), high.tolist()],
        },
        "representations": {
            "mesh": "Decimated photogrammetry surface with source texture coordinates.",
            "gaussians": {
                "count": args.gaussians, "seed": 20260914,
                "method": "Area-weighted mesh samples with sampled texture colour and surface normals.",
                "trained_3dgs": False, "radius_m": radius,
            },
            "collision": {
                "kind": "65x65 top-surface heightfield proxy", "filled_samples": missing,
                "limitations": "Does not preserve overhangs; absent surface samples become base plane.",
            },
        },
        "files": {
            path.name: {"sha256": sha(path), "bytes": path.stat().st_size}
            for path in sorted(output.iterdir()) if path.is_file()
        },
    })


if __name__ == "__main__":
    main()
