"""Verify every saved directed Blender frame against the source recording."""
import argparse
import hashlib
import json
from pathlib import Path
import sys


def main():
    import bpy
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from robot_reel.director import verify_director

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--blend", type=Path, required=True)
    parser.add_argument("--report", type=Path)
    argv = sys.argv[sys.argv.index("--")+1:] if "--" in sys.argv else sys.argv[1:]
    args = parser.parse_args(argv)
    verify_director(args.bundle)
    film = json.loads((args.bundle/"film.json").read_text())
    source = json.loads((args.bundle/"source/scene.json").read_text())
    plan = json.loads((args.bundle/"storyboard.json").read_text())
    bpy.ops.wm.open_mainfile(filepath=str(args.blend.resolve()), use_scripts=False)
    scene = bpy.context.scene
    if (
        scene.frame_start != 1 or scene.frame_end != film["frame_count"]
        or scene.render.fps != film["fps"] or scene.render.fps_base != 1
        or scene.rigidbody_world is not None or scene.render.use_motion_blur
        or json.loads(scene["film_mapping_json"]) != film or json.loads(scene["storyboard_json"]) != plan
    ):
        raise ValueError("Directed project metadata mismatch")
    names = {
        "overview": "Overview / both independent trials", "impact": "Impact / alternate angle",
        "tracking": "Director / tracking", "top": "Director / top",
    }
    maximum, checked = 0., 0
    for row in film["frames"]:
        scene.frame_set(row["frame"]+1)
        if scene.camera.name != names[plan["shots"][row["shot"]]["camera"]]:
            raise ValueError(f"Camera cut mismatch at output frame {row['frame']}")
        for run in source["runs"]:
            obj = bpy.data.objects[run["id"]+" / recorded vehicle"]
            expected = run["frames"][row["source_frame"]]
            error = abs(obj.location.x-expected["qpos"][2])
            if error > 1e-5 or obj["source_frame"] != row["source_frame"]:
                raise ValueError(f"Recorded motion changed at output frame {row['frame']}")
            if abs(obj["sim_time_s"]-expected["sim_time"]) > 1e-6 or obj["contact_recorded"] != int(expected["collision"]):
                raise ValueError("Directed telemetry mismatch")
            if (
                abs(obj["speed_mps"]-expected["qpos"][0]) > 1e-6
                or abs(obj["gap_m"]-expected["qpos"][1]) > 1e-6
                or abs(obj.location.y-run["lane_y"]) > 1e-6 or abs(obj.location.z) > 1e-6
            ):
                raise ValueError("Directed state or lane mismatch")
            maximum = max(maximum, error)
            checked += 1
        center = sum(run["frames"][row["source_frame"]]["qpos"][2] for run in source["runs"])/len(source["runs"])
        if abs(bpy.data.objects["Director / tracking"].location.x-center) > 1e-5:
            raise ValueError("Tracking camera diverges from measured motion")
        if row["frame"] < film["frame_count"]-1:
            scene.frame_set(row["frame"]+1, subframe=.5)
            for run in source["runs"]:
                if abs(bpy.data.objects[run["id"]+" / recorded vehicle"].location.x-run["frames"][row["source_frame"]]["qpos"][2]) > 1e-5:
                    raise ValueError("Unexpected pose interpolation")
    report = {
        "blender_version": bpy.app.version_string, "output_frames": film["frame_count"],
        "source_frames": source["frame_count"], "checked_vehicle_samples": checked,
        "maximum_position_error_m": maximum, "camera_cuts_checked": len(plan["shots"]),
        "constant_hold_checked": True,
        "tracking_camera_checked": True,
        "blend_sha256": hashlib.sha256(args.blend.read_bytes()).hexdigest(),
        "film_sha256": hashlib.sha256((args.bundle/"film.json").read_bytes()).hexdigest(),
        "source_sha256": hashlib.sha256((args.bundle/"source/scene.json").read_bytes()).hexdigest(),
    }
    if args.report:
        args.report.write_text(json.dumps(report, indent=2)+"\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
