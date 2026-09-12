"""Build a directed Blender film using only recorded vehicle samples.

blender --background --python build_directed_scene.py -- --bundle DIR --output FILE
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys


def load(directory):
    manifest = json.loads((directory/"director-manifest.json").read_text())
    expected = {"storyboard.json", "film.json", "build_directed_scene.py", "base_scene.py"}
    if manifest.get("schema") != "robot-reel-director-1" or set(manifest.get("sha256", {})) != expected:
        raise ValueError("Incomplete director bundle")
    for name, checksum in manifest["sha256"].items():
        if hashlib.sha256((directory/name).read_bytes()).hexdigest() != checksum:
            raise ValueError(f"Changed director file: {name}")
    if hashlib.sha256((directory/"source/blender-manifest.json").read_bytes()).hexdigest() != manifest["source_manifest_sha256"]:
        raise ValueError("Changed source manifest")
    return json.loads((directory/"storyboard.json").read_text()), json.loads((directory/"film.json").read_text())


def build(directory, output):
    import bpy
    from mathutils import Vector

    plan, film = load(directory)
    # Use the packaged builder, never execute a script supplied by a source capture.
    spec = importlib.util.spec_from_file_location("source_scene", directory/"base_scene.py")
    builder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(builder)
    source, manifest = builder.load_bundle(directory/"source")
    # The source builder saves once. Keep its intermediate in the new output directory.
    scene = builder.build_scene(source, manifest, output)
    scene.name = "Robot Reel / directed recording"
    scene.frame_end = film["frame_count"]
    scene["storyboard_json"] = json.dumps(plan)
    scene["film_mapping_json"] = json.dumps(film)
    scene["director_notice"] = film["editing"]
    scene.timeline_markers.clear()
    scene.render.resolution_x, scene.render.resolution_y = 960, 540
    scene.cycles.samples = 8
    scene.cycles.denoising_prefilter = "FAST"
    scene.cycles.denoising_quality = "FAST"
    if plan["theme"] == "daylight":
        scene.world.node_tree.nodes["Background"].inputs["Color"].default_value = (.32, .4, .52, 1)
        scene.world.node_tree.nodes["Background"].inputs["Strength"].default_value = .8
    cameras = {
        "overview": bpy.data.objects["Overview / both independent trials"],
        "impact": bpy.data.objects["Impact / alternate angle"],
    }
    for name, location, target, scale in (
        ("top", (15, 0, 36), (15, 0, 0), 39),
        ("tracking", (0, -14, 15), (0, 0, .5), 20),
    ):
        data = bpy.data.cameras.new("Director / "+name)
        obj = bpy.data.objects.new(data.name, data)
        scene.collection.objects.link(obj)
        data.type, data.ortho_scale = "ORTHO", scale
        obj.location = location
        obj.rotation_euler = (Vector(target)-obj.location).to_track_quat("-Z", "Y").to_euler()
        cameras[name] = obj
    for index, row in enumerate(film["frames"], 1):
        frame_index = row["source_frame"]
        center = sum(r["frames"][frame_index]["qpos"][2] for r in source["runs"])/2
        tracking = cameras["tracking"]
        tracking.location = (center, -14, 15)
        tracking.keyframe_insert(data_path="location", frame=index)
    for run in source["runs"]:
        car = bpy.data.objects[run["id"]+" / recorded vehicle"]
        car.animation_data_clear()
        for row in film["frames"]:
            frame, index = run["frames"][row["source_frame"]], row["frame"]+1
            car.location = (frame["qpos"][2], run["lane_y"], 0)
            car.keyframe_insert(data_path="location", frame=index)
            for key, value in {
                "source_frame": frame["frame"], "sim_time_s": frame["sim_time"],
                "speed_mps": frame["qpos"][0], "gap_m": frame["qpos"][1],
                "contact_recorded": int(frame["collision"]),
            }.items():
                car[key] = value
                car.keyframe_insert(data_path=f'["{key}"]', frame=index)
    for obj in [cameras["tracking"], *(bpy.data.objects[r["id"]+" / recorded vehicle"] for r in source["runs"])]:
        animation = obj.animation_data
        for layer in animation.action.layers:
            for strip in layer.strips:
                bag = strip.channelbag(animation.action_slot)
                if bag:
                    for curve in bag.fcurves:
                        for key in curve.keyframe_points:
                            key.interpolation = "CONSTANT"
    last_shot = None
    for row in film["frames"]:
        if row["shot"] != last_shot:
            shot = plan["shots"][row["shot"]]
            marker = scene.timeline_markers.new(f'{row["shot"]+1:02d} / {shot["caption"]}', frame=row["frame"]+1)
            marker.camera = cameras[shot["camera"]]
            last_shot = row["shot"]
    scene.camera = cameras[plan["shots"][0]["camera"]]
    scene.frame_set(1)
    bpy.ops.wm.save_as_mainfile(filepath=str(output))
    backup = output.with_suffix(output.suffix+"1")
    if backup.exists():
        backup.unlink()
    return scene


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--frames", type=Path)
    parser.add_argument("--threads", type=int, default=2)
    argv = sys.argv[sys.argv.index("--")+1:] if "--" in sys.argv else sys.argv[1:]
    args = parser.parse_args(argv)
    if args.output.exists() or (args.frames and args.frames.exists() and any(args.frames.iterdir())):
        parser.error("Choose a fresh project path and frame directory")
    if not 1 <= args.threads <= 32:
        parser.error("--threads must be 1–32")
    scene = build(args.bundle.resolve(), args.output.resolve())
    if args.frames:
        import bpy
        args.frames.mkdir(parents=True, exist_ok=True)
        scene.render.threads_mode = "FIXED"
        scene.render.threads = args.threads
        scene.render.use_persistent_data = True
        scene.render.image_settings.file_format = "PNG"
        scene.render.filepath = str(args.frames.resolve()/"frame-")
        bpy.ops.render.render(animation=True)


if __name__ == "__main__":
    main()
