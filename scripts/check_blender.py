"""Check saved Blender transforms against every source sample (run with bpy).

blender --background --python scripts/check_blender.py -- --bundle DIR --blend FILE
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys


def main():
    import bpy
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--blend", type=Path, required=True)
    parser.add_argument("--report", type=Path)
    argv = sys.argv[sys.argv.index("--")+1:] if "--" in sys.argv else sys.argv[1:]
    args = parser.parse_args(argv)
    document = json.loads((args.bundle / "scene.json").read_text())
    bpy.ops.wm.open_mainfile(filepath=str(args.blend.resolve()))
    scene = bpy.context.scene
    assert scene.frame_start == 1 and scene.frame_end == document["frame_count"]
    assert scene.render.fps == document["fps"] and scene.render.fps_base == 1
    assert scene.rigidbody_world is None
    assert not scene.render.use_motion_blur
    maximum_error = 0
    checked = 0
    for run in document["runs"]:
        car = bpy.data.objects[run["id"] + " / recorded vehicle"]
        assert car.rigid_body is None
        for index, frame in enumerate(run["frames"], 1):
            scene.frame_set(index)
            error = abs(car.location.x-frame["qpos"][2])
            maximum_error = max(maximum_error, error)
            assert error < 1e-5, (index, error)
            assert abs(car.location.y-run["lane_y"]) < 1e-6
            assert car["source_frame"] == frame["frame"]
            assert abs(car["sim_time_s"]-frame["sim_time"]) < 1e-6
            assert abs(car["speed_mps"]-frame["qpos"][0]) < 1e-5
            assert abs(car["gap_m"]-frame["qpos"][1]) < 1e-5
            assert car["contact_recorded"] == int(frame["collision"])
            if index < scene.frame_end:
                scene.frame_set(index, subframe=.5)
                assert abs(car.location.x-frame["qpos"][2]) < 1e-5, "Unexpected interpolation"
            checked += 1
    report = {
        "blender_version": bpy.app.version_string, "checked_vehicle_samples": checked,
        "frames_per_trial": document["frame_count"], "fps": document["fps"],
        "maximum_position_error_m": maximum_error,
        "between_samples": "constant hold checked",
        "physics": "no rigid-body simulation or motion blur",
        "blend_sha256": hashlib.sha256(args.blend.read_bytes()).hexdigest(),
        "scene_json_sha256": hashlib.sha256((args.bundle / "scene.json").read_bytes()).hexdigest(),
    }
    if args.report:
        args.report.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
