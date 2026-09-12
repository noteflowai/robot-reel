"""Standalone Blender builder, copied into every exported replay bundle.

blender --background --python build_scene.py -- --bundle DIR --output replay.blend
The Blender Python module can also execute this file directly.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import sys


def load_bundle(directory):
    manifest = json.loads((directory / "blender-manifest.json").read_text())
    required = {"scene.json", "build_scene.py", "left-trace.json", "right-trace.json",
                "left-source-manifest.json", "right-source-manifest.json"}
    if manifest.get("schema") != 1 or set(manifest.get("sha256", {})) != required:
        raise ValueError("Incomplete Blender export")
    for filename, expected in manifest["sha256"].items():
        if hashlib.sha256((directory / filename).read_bytes()).hexdigest() != expected:
            raise ValueError(f"Changed export file: {filename}")
    document = json.loads((directory / "scene.json").read_text())
    if document.get("schema") != 1 or document.get("kind") != "braking":
        raise ValueError("Unsupported Blender replay")
    return document, manifest


def build_scene(document, manifest, output, portrait=False):
    import bpy
    from mathutils import Vector

    # This script creates a new scene; launch it in a fresh/background Blender.
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.name = "Robot Reel — recorded braking"
    scene.render.engine = "CYCLES"
    scene.cycles.samples = 24
    scene.cycles.use_denoising = True
    scene.render.resolution_x, scene.render.resolution_y = (720, 1280) if portrait else (1280, 720)
    scene.render.resolution_percentage = 100
    scene.render.fps = document["fps"]
    scene.render.fps_base = 1
    scene.frame_start, scene.frame_end = 1, document["frame_count"]
    scene.unit_settings.system = "METRIC"
    scene.unit_settings.scale_length = 1
    scene.render.use_motion_blur = False
    scene["robot_reel_notice"] = document["notice"]
    scene["source_frame_offset"] = -1
    scene["scene_json_sha256"] = manifest["sha256"]["scene.json"]
    scene["animation_samples"] = document["frame_count"]
    for filename in ("scene.json", "blender-manifest.json"):
        datablock = bpy.data.texts.new(filename)
        datablock.write(json.dumps(document if filename == "scene.json" else manifest, indent=2))
    world = bpy.data.worlds.new("Midnight studio")
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (.07, .095, .16, 1)
    world.node_tree.nodes["Background"].inputs["Strength"].default_value = .45
    scene.world = world

    def material(name, color, metallic=0, roughness=.35, emission=0):
        mat = bpy.data.materials.new(name)
        mat.diffuse_color = color
        mat.use_nodes = True
        shader = mat.node_tree.nodes.get("Principled BSDF")
        shader.inputs["Base Color"].default_value = color
        shader.inputs["Metallic"].default_value = metallic
        shader.inputs["Roughness"].default_value = roughness
        if emission:
            shader.inputs["Emission Color"].default_value = color
            shader.inputs["Emission Strength"].default_value = emission
        return mat

    asphalt = material("Road / graphite", (.027, .037, .06, 1), .2, .6)
    stage = material("Stage / ink", (.01, .018, .035, 1), .25, .32)
    glass = material("Cabin / smoked glass", (.045, .10, .14, 1), .7, .17)
    rubber = material("Tires", (.012, .016, .023, 1), .1, .8)
    white = material("Warm white", (.85, .9, 1, 1), .25)
    barrier_mat = material("Obstacle / signal orange", (.92, .14, .035, 1), .4)

    def box(name, location, size, mat, parent=None, bevel=0):
        bpy.ops.mesh.primitive_cube_add(size=2, location=location)
        obj = bpy.context.object
        obj.name = name
        obj.scale = size
        bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
        obj.data.materials.append(mat)
        if parent:
            obj.parent = parent
        if bevel:
            modifier = obj.modifiers.new("Edge highlights", "BEVEL")
            modifier.width, modifier.segments = bevel, 3
            obj.modifiers.new("Weighted normals", "WEIGHTED_NORMAL")
        return obj

    def text(name, words, location, size, mat):
        curve = bpy.data.curves.new(name, "FONT")
        curve.body, curve.size, curve.extrude = words, size, .004
        obj = bpy.data.objects.new(name, curve)
        scene.collection.objects.link(obj)
        obj.location = location
        obj.data.materials.append(mat)
        return obj

    box("Presentation plinth", (15, 0, -.35), (19, 7, .3), stage, bevel=.2)
    for run in document["runs"]:
        side, lane, cfg = run["id"], run["lane_y"], run["config"]
        accent = material(side + " / accent", run["color"], .5, .26)
        luminous = material(side + " / light", run["color"], .15, .3, emission=2)
        box(side + " road", (15, lane, -.02), (18, 1.65, .03), asphalt, bevel=.06)
        for y in (-1.5, 1.5):
            box(side + " boundary", (15, lane+y, .035), (18, .025, .018), luminous)
        for x in range(-2, 35, 3):
            for y in (-1.1, 1.1):
                box(side + " markings", (x, lane+y, .035), (.35, .02, .012), white)
        box(side + " obstacle", (cfg["obstacle_x_m"], lane, .8),
            (cfg["obstacle_half_length_m"], 1, .8), barrier_mat, bevel=.025)
        contact_x = cfg["obstacle_x_m"] - cfg["obstacle_half_length_m"] - cfg["car_half_length_m"]
        trigger_x = contact_x - cfg["trigger_gap_m"]
        box(side + " trigger marker", (trigger_x, lane, .04), (.035, 1.45, .018), accent)
        text(side + " title", run["label"].upper(), (1, lane-2.05, .06), .48, accent)
        text(side + " trigger label", f'BRAKE AT {cfg["trigger_gap_m"]:g} m GAP',
             (trigger_x-1.2, lane+1.8, .06), .28, white)
        car = bpy.data.objects.new(side + " / recorded vehicle", None)
        scene.collection.objects.link(car)
        car["source_robot"] = run["robot"]
        car["display_lane_offset_m"] = lane
        car["motion_source"] = "recorded qpos[2]; constant sample hold"
        box(side + " chassis", (0, 0, .45), (cfg["car_half_length_m"], .6, .22),
            accent, car, .08)
        box(side + " cabin", (-.1, 0, .82), (.55, .5, .18), glass, car, .09)
        box(side + " headlight", (cfg["car_half_length_m"]+.01, 0, .51),
            (.015, .45, .035), white, car, .01)
        for x in (-.65, .65):
            for y in (-.65, .65):
                bpy.ops.mesh.primitive_cylinder_add(vertices=32, radius=.25, depth=.24,
                                                   location=(x, y, .33), rotation=(math.pi/2, 0, 0))
                wheel = bpy.context.object
                wheel.name = side + " decorative wheel"
                wheel.parent = car
                wheel.data.materials.append(rubber)
        contact_marked, brake_marked = False, False
        for index, frame in enumerate(run["frames"], 1):
            car.location = (frame["qpos"][2], lane, 0)
            car.keyframe_insert(data_path="location", frame=index)
            for key, value in {
                "source_frame": frame["frame"], "sim_time_s": frame["sim_time"],
                "speed_mps": frame["qpos"][0], "gap_m": frame["qpos"][1],
                "contact_recorded": int(frame["collision"]),
            }.items():
                car[key] = value
                car.keyframe_insert(data_path=f'["{key}"]', frame=index)
            if not brake_marked and frame.get("brake_force_n", 0) != 0:
                scene.timeline_markers.new(side + " / first recorded braking", frame=index)
                brake_marked = True
            if frame["collision"] and not contact_marked:
                scene.timeline_markers.new(side + " / first recorded contact frame", frame=index)
                contact_marked = True
        # Python key insertion does not consistently honor the UI preference.
        # Set every channel explicitly, including the telemetry properties.
        animation = car.animation_data
        for layer in animation.action.layers:
            for strip in layer.strips:
                bag = strip.channelbag(animation.action_slot)
                if bag:
                    for curve in bag.fcurves:
                        for key in curve.keyframe_points:
                            key.interpolation = "CONSTANT"
    text("Title", "SAME START. DIFFERENT STOP.", (1, 5.3, .08), .66, white)
    text("Subtitle", "ROBOT REEL  /  RECORDED MOTION, EDITABLE SCENE", (1, 4.65, .08), .29, white)
    text("Scale note", "TWO INDEPENDENT 1D TRIALS  /  METERS  /  30 FPS", (1, -6.4, .08), .26, white)
    for name, location, energy, size in [
        ("Key", (8, -12, 19), 9000, 15),
        ("Rim", (24, 10, 15), 11000, 12),
        ("Fill", (-4, 0, 10), 5000, 10),
    ]:
        data = bpy.data.lights.new(name, "AREA")
        data.energy, data.shape, data.size = energy, "DISK", size
        light = bpy.data.objects.new(name, data)
        scene.collection.objects.link(light)
        light.location = location
        light.rotation_euler = (Vector((15, 0, 0))-light.location).to_track_quat("-Z", "Y").to_euler()

    def camera(name, location, target, scale):
        data = bpy.data.cameras.new(name)
        obj = bpy.data.objects.new(name, data)
        scene.collection.objects.link(obj)
        obj.location = location
        obj.rotation_euler = (Vector(target)-obj.location).to_track_quat("-Z", "Y").to_euler()
        data.type, data.ortho_scale = "ORTHO", scale
        return obj

    overview = camera("Overview / both independent trials", (15, -24, 28), (15, 0, 0), 40)
    close = camera("Impact / alternate angle", (39, -12, 10), (25, 0, .4), 19)
    scene.camera = close if portrait else overview
    if portrait:
        close.data.ortho_scale = 22
    scene.frame_set(1)
    for area in bpy.context.screen.areas if bpy.context.screen else []:
        if area.type == "VIEW_3D":
            area.spaces.active.region_3d.view_perspective = "CAMERA"
    output.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(output))
    return scene


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--portrait", action="store_true")
    parser.add_argument("--render-frames", type=Path, help="Optional PNG sequence directory")
    parser.add_argument("--poster", type=Path, help="Optional PNG of the first contact frame")
    parser.add_argument("--samples", type=int, default=24)
    args = parser.parse_args(argv)
    if args.output.exists():
        parser.error("Output .blend already exists; choose a new filename")
    if args.samples < 1:
        parser.error("--samples must be positive")
    document, manifest = load_bundle(args.bundle.resolve())
    scene = build_scene(document, manifest, args.output.resolve(), args.portrait)
    import bpy
    scene.cycles.samples = args.samples
    scene.render.image_settings.file_format = "PNG"
    if args.poster:
        contacts = [f["frame"]+1 for run in document["runs"] for f in run["frames"] if f["collision"]]
        scene.frame_set(min(contacts) if contacts else scene.frame_end)
        scene.render.filepath = str(args.poster.resolve())
        bpy.ops.render.render(write_still=True)
    if args.render_frames:
        args.render_frames.mkdir(parents=True, exist_ok=True)
        scene.render.filepath = str(args.render_frames.resolve() / "frame-")
        bpy.ops.render.render(animation=True)
    print(f"Robot Reel Blender export complete; Blender {bpy.app.version_string}")


if __name__ == "__main__":
    argv = sys.argv[sys.argv.index("--")+1:] if "--" in sys.argv else sys.argv[1:]
    main(argv)
