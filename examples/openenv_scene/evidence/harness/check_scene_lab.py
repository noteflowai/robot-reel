"""Reopen an exported Scene Lab project with Blender and inspect native data.

Run Blender with --background --disable-autoexec --python-exit-code 1 --python
this_file -- --scene DIRECTORY. Never use this to open an unreviewed .blend file.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import struct
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scene", type=Path, required=True)
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1:])
    root = args.scene.resolve()
    manifest = json.loads((root / "scene.json").read_text())
    for name, expected in manifest["files"].items():
        path = root / name
        if path.is_symlink() or not path.resolve().is_relative_to(root):
            raise ValueError("scene files must stay in the scene directory")
        with path.open("rb") as stream:
            actual = hashlib.file_digest(stream, "sha256").hexdigest()
        if actual != expected["sha256"] or path.stat().st_size != expected["bytes"]:
            raise ValueError(f"scene file changed: {name}")
    import bpy
    from mathutils import Vector

    bpy.ops.wm.open_mainfile(filepath=str(root / "scene.blend"), use_scripts=False)
    scene = bpy.context.scene
    terrain = bpy.data.objects["ScanTerrain"]
    collision = bpy.data.objects["CollisionHeightfield"]
    scene_edit = json.loads(scene["robot_reel_edit"])
    assert scene_edit == manifest["edit"], "native edit settings differ"
    assert scene["robot_reel_source_sha256"] == manifest["source_manifest_sha256"]
    assert scene.render.engine == "CYCLES" and scene.cycles.device == "GPU"
    assert scene.camera.name == "ReviewCamera"
    assert math.isclose(bpy.data.objects["ReviewSun"].data.energy, scene_edit["sun_energy"])
    actual_azimuth = math.degrees(bpy.data.objects["ReviewSun"].rotation_euler.z)
    assert math.isclose(actual_azimuth, scene_edit["sun_azimuth_degrees"], abs_tol=1e-4)
    vertices = [terrain.matrix_world @ v.co for v in terrain.data.vertices]
    bounds = [
        [operation(v[axis] for v in vertices) for axis in range(3)]
        for operation in (min, max)
    ]
    assert all(
        math.isclose(a, b, abs_tol=1e-5)
        for actual, expected in zip(bounds, manifest["geometry"]["bounds_m"])
        for a, b in zip(actual, expected)
    ), "native terrain bounds differ"
    heightfield = json.loads((root / "collision-heightfield.json").read_text())
    assert len(collision.data.vertices) == heightfield["resolution"] ** 2
    assert all(
        math.isclose((collision.matrix_world @ v.co).z, z, abs_tol=1e-5)
        for v, z in zip(collision.data.vertices, heightfield["heights_m"])
    ), "native collision heights differ"
    used_images = {
        node.image.name for material in terrain.data.materials
        for node in material.node_tree.nodes
        if node.type == "TEX_IMAGE" and node.image
    }
    assert used_images and all(bpy.data.images[name].packed_file for name in used_images)
    # Independently parse the standard GLB container and verify both named meshes.
    glb = (root / "scene.glb").read_bytes()
    magic, version, total = struct.unpack_from("<4sII", glb)
    length, kind = struct.unpack_from("<II", glb, 12)
    assert magic == b"glTF" and version == 2 and total == len(glb) and kind == 0x4E4F534A
    gltf = json.loads(glb[20:20 + length])
    names = {node["name"] for node in gltf["nodes"] if "mesh" in node}
    assert {"ScanTerrain", "CollisionHeightfield"} <= names
    splats = (root / "terrain.splat").read_bytes()
    count = manifest["representations"]["gaussians"]["count"]
    assert len(splats) == count * 32
    # Check coordinate conversion and finite positive scales in the actual bytes.
    for offset in range(0, len(splats), 32):
        x, y, z, sx, sy, sz = struct.unpack_from("<6f", splats, offset)
        native = Vector((x, -z, y))
        assert all(math.isfinite(n) for n in (x, y, z, sx, sy, sz))
        assert min(sx, sy, sz) > 0
        assert all(bounds[0][i] - 1e-4 <= native[i] <= bounds[1][i] + 1e-4 for i in range(3))
    result = {
        "schema": "robot-reel.scene-native-check.v1",
        "blender_version": bpy.app.version_string,
        "scene_sha256": manifest["files"]["scene.blend"]["sha256"],
        "native_bounds_m": bounds, "edit": scene_edit,
        "native_sun_azimuth_degrees": actual_azimuth,
        "native_sun_energy": float(bpy.data.objects["ReviewSun"].data.energy),
        "packed_textures": sorted(used_images), "glb_meshes": sorted(names),
        "checked_surface_gaussians": count,
        "checked_collision_samples": len(collision.data.vertices),
        "passed": True,
        "scope": "File identities and native scene data; no real-world collision fidelity claim.",
    }
    (root / "native-check.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result), flush=True)


if __name__ == "__main__":
    main()
