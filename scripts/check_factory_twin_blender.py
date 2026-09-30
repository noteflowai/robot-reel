"""Check a saved factory twin project against every recorded sample, then read back its OpenUSD export.

blender --background --factory-startup --python scripts/check_factory_twin_blender.py -- \
  --lab docs/factory-twin/lab.json --blend factory-twin-closed.blend --mode closed \
  --usd factory-twin-closed.usdc --report check-closed.json

Checks, at every frame:
  * each animated channel equals the value derived from lab.json (float32 tolerance);
  * independently of the channel mapping: AMR positions, the number of visible
    crates in every buffer, station beacon colours and the CNC 2 wear gauges;
  * values hold between frames (sub-frame 0.5) — Blender invents no motion.
The USD export is then opened with pxr and every animated prim's world
transform is compared with Blender's at every time code.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys

import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from robot_reel.factory_twin_scene import (  # noqa: E402
    GAUGE_HEIGHT_M, STATE_COLORS, channels,
)

TOLERANCE = 2e-4


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def value(owner, path, index):
    if owner.startswith("light:"):
        return bpy.data.lights[owner[6:]].energy
    o = bpy.data.objects[owner]
    if path.startswith('["'):
        return o[path[2:-2]]
    return getattr(o, path)[index]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lab", type=Path, required=True)
    parser.add_argument("--blend", type=Path, required=True)
    parser.add_argument("--mode", choices=("closed", "shadow"), required=True)
    parser.add_argument("--usd", type=Path, required=True, help="Write the USD export here and read it back")
    parser.add_argument("--report", type=Path, required=True)
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
    args = parser.parse_args(argv)
    lab = json.loads(args.lab.read_bytes())
    run = lab["runs"][args.mode]
    plant = run["plant"]
    n = lab["config"]["samples"]
    buffer_ids = list(lab["config"]["buffers"])
    bpy.ops.wm.open_mainfile(filepath=str(args.blend.resolve()))
    scene = bpy.context.scene
    problems = []

    def require(condition, message):
        if not condition and len(problems) < 50:
            problems.append(message)

    require(scene.frame_start == 1 and scene.frame_end == n, "frame range")
    require(scene.render.fps == 30 and scene.render.fps_base == 1, "frame rate")
    require(not scene.render.use_motion_blur, "motion blur must be off")
    require(scene.rigidbody_world is None, "no rigid-body world expected")
    require(scene.get("robot_reel_mode") == args.mode, "scene mode")
    require(scene.get("lab_json_sha256") == digest(args.lab), "project was built from a different lab.json")
    spec = channels(lab, args.mode)
    crates = {name: [bpy.data.objects[f"Buffer {name} / slot {i + 1:02d}"]
                     for i in range(lab["config"]["buffers"][name])] for name in buffer_ids}
    transform_objects = sorted({owner for (owner, path, _) in spec
                                if not owner.startswith("light:") and path in ("location", "rotation_euler", "scale")})
    world = {name: [] for name in transform_objects}
    max_error = 0.0
    checked = 0
    for k in range(n):
        frame = k + 1
        scene.frame_set(frame)
        for (owner, path, index), values in spec.items():
            error = abs(value(owner, path, index) - values[k])
            max_error = max(max_error, error)
            require(error <= TOLERANCE * max(1.0, abs(values[k])), f"{owner} {path}[{index}] frame {frame}: {error}")
            checked += 1
        # Independent of the channel mapping: re-derive the key quantities from the samples.
        for i in range(len(plant["amr"][k])):
            loc = bpy.data.objects[f"AMR {i + 1}"].matrix_world.translation
            x, y = plant["amr"][k][i][:2]
            require(abs(loc.x - x) < 1e-3 and abs(loc.y - y) < 1e-3, f"AMR {i + 1} position frame {frame}")
        for b, name in enumerate(buffer_ids):
            visible = sum(o.matrix_world.to_scale().z > 0.5 for o in crates[name])
            require(visible == plant["buffers"][k][b], f"buffer {name} frame {frame}: {visible}")
        for j, sid in enumerate(s["id"] for s in lab["config"]["stations"]):
            color = tuple(bpy.data.objects[f"Station {sid} / beacon"].color[:3])
            require(max(abs(a - c) for a, c in zip(color, STATE_COLORS[plant["state"][k][j]])) < 1e-4,
                    f"beacon {sid} frame {frame}")
        bar = bpy.data.objects["Twin overlay / wear truth"]
        require(abs(bar.dimensions.z - GAUGE_HEIGHT_M * max(1e-3, plant["wear"][k])) < 1e-3, f"wear gauge frame {frame}")
        for name in transform_objects:
            world[name].append([list(row) for row in bpy.data.objects[name].matrix_world])
        if frame < n and k % 60 == 0:
            scene.frame_set(frame, subframe=0.5)
            for (owner, path, index), values in spec.items():
                require(abs(value(owner, path, index) - values[k]) <= TOLERANCE * max(1.0, abs(values[k])),
                        f"interpolation {owner} frame {frame}.5")
    # OpenUSD export and readback.
    args.usd.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.usd_export(filepath=str(args.usd.resolve()), export_animation=True, export_custom_properties=True,
                          selected_objects_only=False, export_materials=True)
    from pxr import Usd, UsdGeom
    stage = Usd.Stage.Open(str(args.usd.resolve()))
    up = UsdGeom.GetStageUpAxis(stage)
    prims = {}
    for prim in stage.Traverse():
        attr = prim.GetAttribute("userProperties:rr_id")
        if attr and prim.IsA(UsdGeom.Xformable):
            # Animated objects author their user properties as time samples.
            name = attr.Get() if attr.HasAuthoredValue() and attr.Get() is not None else attr.Get(Usd.TimeCode(1))
            if name is not None:
                prims[name] = prim
    require(set(transform_objects) <= set(prims), f"USD is missing animated prims: {sorted(set(transform_objects) - set(prims))[:5]}")
    # Blender converts to the stage's up axis; compare in the stage frame via the root correction.
    usd_error = 0.0
    usd_frames = 0
    for k in range(n):
        cache_time = Usd.TimeCode(k + 1)
        cache = UsdGeom.XformCache(cache_time)
        for name in transform_objects:
            if name not in prims:
                continue
            m = cache.GetLocalToWorldTransform(prims[name])
            usd = [[m[c][r] for c in range(4)] for r in range(4)]  # transpose row-vector convention
            blender = world[name][k]
            if up == "Z":
                target = blender
            else:  # Y-up: Blender (x, y, z) -> USD (x, z, -y)
                target = [blender[0], blender[2], [-v for v in blender[1]], blender[3]]
            err = max(abs(usd[r][c] - target[r][c]) for r in range(3) for c in range(4))
            usd_error = max(usd_error, err)
            require(err < 1e-3, f"USD {name} time {k + 1}: {err}")
        usd_frames += 1
    report = {
        "schema": lab["schema"], "mode": args.mode, "verified": not problems, "problems": problems,
        "blender_version": bpy.app.version_string, "frames_checked": n, "channels": len(spec),
        "channel_values_checked": checked, "maximum_channel_error": max_error,
        "independent_checks": ["AMR positions", "visible crates per buffer", "station beacon colours",
                               "CNC 2 wear gauge height", "constant hold at sub-frame 0.5 (every 60th frame)"],
        "usd_up_axis": up, "usd_animated_prims": len(transform_objects), "usd_frames_checked": usd_frames,
        "maximum_usd_transform_error": usd_error,
        "inputs": {"lab.json": digest(args.lab), "blend": digest(args.blend), "usd": digest(args.usd)},
        "bytes": {"blend": args.blend.stat().st_size, "usd": args.usd.stat().st_size},
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + "\n")
    print("CHECK_RESULT " + json.dumps({k: v for k, v in report.items() if k != "problems"}))
    if problems:
        print("\n".join(problems[:20]))
        raise SystemExit(1)


if __name__ == "__main__":
    main()
