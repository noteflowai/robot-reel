"""Import checked motion USD into the captured Blender scene and render frames."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys


def identity(path):
    path = Path(path)
    with path.open("rb") as stream:
        return {"sha256": hashlib.file_digest(stream, "sha256").hexdigest(),
                "bytes": path.stat().st_size}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scene", type=Path, required=True)
    parser.add_argument("--recording", type=Path, required=True)
    parser.add_argument("--export", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--render-animation", action="store_true")
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1:])
    builder_identity = identity(Path(__file__))
    import bpy

    scene_source = json.loads((args.scene / "scene.json").read_text())
    if identity(args.scene / "scene.blend") != scene_source["files"]["scene.blend"]:
        raise ValueError("captured Blender source differs from its recorded identity")
    trace = json.loads((args.recording / "trace.json").read_text())
    export = json.loads((args.export / "export-check.json").read_text())
    if identity(args.recording / "trace.json") != export["source_trace"]:
        raise ValueError("motion export belongs to another recording")
    for name, expected in [("motion.usdc", export["usd_check"]["usd"]),
                           ("geometry.json", export["geometry"])]:
        if identity(args.export / name) != expected:
            raise ValueError("motion export changed")
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    for source, name in [(args.recording / "trace.json", "trace.json"),
                         (args.export / "motion.usdc", "motion.usdc"),
                         (args.export / "geometry.json", "geometry.json"),
                         (args.scene / "scene.json", "source-scene.json")]:
        shutil.copyfile(source, output / name)
    bpy.ops.wm.open_mainfile(filepath=str((args.scene / "scene.blend").resolve()), use_scripts=False)
    scene = bpy.context.scene
    scene.render.fps = trace["plan"]["sample_hz"]
    scene.render.fps_base = 1
    scene.unit_settings.system = "METRIC"
    scene.unit_settings.scale_length = 1
    bpy.ops.wm.usd_import(
        filepath=str(output / "motion.usdc"), set_frame_range=True, scale=1,
        import_cameras=True, import_meshes=True, import_materials=True,
        import_lights=False, import_subdiv=False, create_collection=True,
        merge_parent_xform=False, apply_unit_conversion_scale=True,
        validate_meshes=False,
    )
    scene.camera = bpy.data.objects["RecordedCamera"]
    bpy.data.objects["MotionCollisionProxy"].hide_render = True
    bpy.data.objects["MotionCollisionProxy"].display_type = "WIRE"
    scene.render.resolution_x = trace["camera"]["width"]
    scene.render.resolution_y = trace["camera"]["height"]
    scene.render.resolution_percentage = 100
    scene.render.pixel_aspect_x = scene.render.pixel_aspect_y = 1
    scene.frame_start = 1
    scene.frame_end = len(trace["frames"])
    scene.frame_set(1)
    scene["robot_reel_motion_trace_sha256"] = identity(output / "trace.json")["sha256"]
    scene["robot_reel_motion_usd_sha256"] = identity(output / "motion.usdc")["sha256"]
    scene["robot_reel_source_blend_sha256"] = scene_source["files"]["scene.blend"]["sha256"]
    scene["robot_reel_source_frame_mapping"] = "Blender frame = recorded source frame + 1"
    scene.render.engine = "CYCLES"
    scene.cycles.device = "GPU"
    scene.cycles.samples = 24
    scene.cycles.use_denoising = True
    scene.render.use_persistent_data = True
    preferences = bpy.context.preferences.addons["cycles"].preferences
    preferences.compute_device_type = "OPTIX"
    preferences.get_devices()
    devices = []
    for device in preferences.devices:
        device.use = device.type == "OPTIX"
        if device.use:
            devices.append(device.name)
    if not devices:
        raise ValueError("declared OptiX renderer is unavailable")
    for cache in bpy.data.cache_files:
        cache.filepath = "//motion.usdc"
    notice = (
        "Captured terrain: Coast Rocks 02, Poly Haven, CC0-1.0. Photography/processing: "
        "Rob Tuytel; cleanup: Rico Cilliers.\n"
        "Microduck model-derived geometry: Pollen Robotics / microduck_rl, commit "
        "53b8971b61baf5b7f3c16d135dd7cac37623de4b. Upstream identifies 3D models as "
        "Creative Commons BY-SA-NC without a version. Keep attribution and "
        "noncommercial/share-alike terms with model-derived geometry and footage.\n"
        "Robot Reel code is Apache-2.0 and does not relicense these assets.\n"
        "Robot motion is simulated on a sampled heightfield. Photogrammetry appearance "
        "does not establish contact fidelity. Frame mappings and original state are "
        "in trace.json; motion.usdc must remain beside this Blender project.\n"
    )
    (output / "NOTICE.txt").write_text(notice)
    text = bpy.data.texts.new("ROBOT_REEL_NOTICE.txt")
    text.write(notice)
    renders = output / "renders"
    renders.mkdir()
    scene.render.image_settings.file_format = "PNG"
    scene.render.filepath = "//renders/frame_"
    bpy.ops.file.pack_all()
    bpy.ops.wm.save_as_mainfile(filepath=str(output / "scene-motion.blend"), compress=True,
                              relative_remap=False)
    # Reopen the actual portable project before rendering. Relative cache paths
    # must resolve beside this file, not beside the captured source .blend.
    bpy.ops.wm.open_mainfile(filepath=str(output / "scene-motion.blend"), use_scripts=False)
    scene = bpy.context.scene
    if args.render_animation:
        scene.render.filepath = str(renders / "frame_")
        bpy.ops.render.render(animation=True)
    else:
        for frame in (0, 90, 180):
            scene.frame_set(frame + 1)
            scene.render.filepath = str(renders / f"frame_{frame+1:04}.png")
            bpy.ops.render.render(write_still=True)
    record = {
        "schema": "robot-reel.scene-motion-blender.v1", "blender": bpy.app.version_string,
        "source_trace": identity(output / "trace.json"), "source_scene": identity(args.scene / "scene.json"),
        "render": {"engine": "Cycles", "backend": "OptiX", "devices": devices, "samples": 24,
                   "width": trace["camera"]["width"], "height": trace["camera"]["height"]},
        "rendered_source_frames": (list(range(len(trace["frames"]))) if args.render_animation else [0, 90, 180]),
        "builder": builder_identity,
        "files": {p.relative_to(output).as_posix(): identity(p) for p in sorted(output.iterdir()) if p.is_file()},
        "render_files": {p.relative_to(output).as_posix(): identity(p)
                         for p in sorted(renders.iterdir()) if p.is_file()},
    }
    if identity(Path(__file__)) != builder_identity:
        raise ValueError("builder source changed during rendering")
    (output / "project.json").write_text(json.dumps(record, indent=2) + "\n")
    print(json.dumps({"project": str(output), "rendered_frames": len(record["rendered_source_frames"]),
                      "blender": record["blender"], "render": record["render"]}), flush=True)


if __name__ == "__main__":
    main()
