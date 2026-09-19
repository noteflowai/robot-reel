"""Package recorded scene motion and bind browser data to native evidence."""

from __future__ import annotations

import json
import math
from pathlib import Path
import shutil
import struct

from robot_reel.scene_motion import checked_file, identity, validate_trace, write_json

CASES = ("baseline", "edited")
CASE_FILES = (
    "trace.json", "native-check.json", "export-check.json", "blender-check.json",
    "project.json", "video-check.json", "simulation.mp4", "blender.mp4",
    "poster.png", "motion.usdc",
)
FILES = {"motion.json", "robot.glb", "body-bounds.json", "NOTICE.txt"} | {
    f"{case}/{name}" for case in CASES for name in CASE_FILES
}
NOTICE = """Scene motion media and geometry

Terrain: Poly Haven Coast Rocks 02, CC0-1.0. Photography and processing:
Rob Tuytel; cleanup: Rico Cilliers. Source identities remain in scene.json.

Robot: Pollen Robotics Microduck, source revision
53b8971b61baf5b7f3c16d135dd7cac37623de4b. Model-derived geometry and footage
retain upstream Creative Commons BY-SA-NC terms; the upstream README does
not specify a license version. The Robot Reel code license and terrain CC0
license do not relicense the robot or the combined robot footage.

These are simulations using XML position-actuator fallback on a captured
top-surface heightfield. They are not hardware trials. Both registered
outcomes are retained. Recorded camera calibration is virtual.
"""


def load_json(path):
    return json.loads(Path(path).read_text())


def glb_parts(content):
    """Read our bounded, uncompressed GLB without a graphics dependency."""
    if len(content) < 28 or struct.unpack_from("<4sII", content) != (b"glTF", 2, len(content)):
        raise ValueError("invalid robot GLB header")
    length, kind = struct.unpack_from("<II", content, 12)
    if kind != 0x4E4F534A:
        raise ValueError("missing GLB JSON chunk")
    document = json.loads(content[20:20 + length])
    size, kind = struct.unpack_from("<II", content, 20 + length)
    binary = content[28 + length:]
    if kind != 0x004E4942 or size != len(binary):
        raise ValueError("invalid GLB binary chunk")
    return document, binary


def rotated(point, quaternion):
    x, y, z, w = quaternion
    a, b, c = point
    tx, ty, tz = 2 * (y*c-z*b), 2 * (z*a-x*c), 2 * (x*b-y*a)
    return [a+w*tx+y*tz-z*ty, b+w*ty+z*tx-x*tz, c+w*tz+x*ty-y*tx]


def body_bounds(content, bodies):
    """Compute each body's actual visual bounds, including static attachments."""
    document, binary = glb_parts(content)
    nodes = document["nodes"]
    root = nodes[0]
    if root["name"] != "WorldToBrowser" or any(abs(a-b) > 1e-12 for a, b in zip(
        root["rotation"], [-math.sqrt(.5), 0, 0, math.sqrt(.5)], strict=True
    )):
        raise ValueError("robot GLB coordinate conversion differs")
    if [nodes[i]["name"] for i in root["children"]] != bodies:
        raise ValueError("robot GLB body order differs")
    rows = []
    for index in root["children"]:
        body = nodes[index]
        lower, upper, count = [math.inf]*3, [-math.inf]*3, 0
        for child in body["children"]:
            node = nodes[child]
            for primitive in document["meshes"][node["mesh"]]["primitives"]:
                accessor = document["accessors"][primitive["attributes"]["POSITION"]]
                view = document["bufferViews"][accessor["bufferView"]]
                if (accessor["componentType"], accessor["type"]) != (5126, "VEC3"):
                    raise ValueError("unsupported robot vertex storage")
                start = view.get("byteOffset", 0) + accessor.get("byteOffset", 0)
                stride = view.get("byteStride", 12)
                for i in range(accessor["count"]):
                    point = struct.unpack_from("<fff", binary, start + i*stride)
                    point = [a+b for a, b in zip(
                        rotated(point, node["rotation"]), node["translation"], strict=True)]
                    for k, value in enumerate(point):
                        if not math.isfinite(value):
                            raise ValueError("nonfinite robot vertex")
                        lower[k], upper[k] = min(lower[k], value), max(upper[k], value)
                    count += 1
        if count == 0:
            raise ValueError("robot body has no visual geometry")
        rows.append({"name": body["name"], "min_m": lower, "max_m": upper, "vertices": count})
    return {"schema": "robot-reel.scene-body-bounds.v1", "unit": "metre",
            "space": "body-local", "bodies": rows}


def checked_case(root, case, scene_root):
    """Validate source relationships, not merely a self-consistent file list."""
    root = Path(root)
    trace = load_json(root / "trace.json")
    counts = validate_trace(trace)
    trace_id = identity(root / "trace.json")
    if trace["case"] != case or trace["error"] is not None:
        raise ValueError("case label or recorded execution differs")
    for filename, expected in trace["plan"]["cases"][case]["files"].items():
        checked_file(scene_root, filename, expected)
    native = load_json(root / "native-check.json")
    if (native.get("schema") != "robot-reel.scene-motion-native-check.v1"
            or native.get("valid") is not True or native.get("trace") != trace_id
            or any(native.get(k) != counts[k] for k in ("frames", "policy_calls", "body_transforms"))
            or any(native.get(k) != 0 for k in (
                "max_body_pose_error", "max_camera_transform_error", "max_replayed_state_error",
                "max_policy_observation_error", "max_replayed_contact_error"))):
        raise ValueError("native motion check does not establish the recorded replay")
    export = load_json(root / "export-check.json")
    usd_id = identity(root / "motion.usdc")
    if (export.get("source_trace") != trace_id
            or export.get("schema") != "robot-reel.scene-motion-export.v1"
            or export["usd_check"]["usd"] != usd_id
            or export["usd_check"]["body_transforms"] != counts["body_transforms"]):
        raise ValueError("USD export identifies different motion")
    project = load_json(root / "project.json")
    blender = load_json(root / "blender-check.json")
    frames = list(range(counts["frames"]))
    if (project.get("schema") != "robot-reel.scene-motion-blender.v1"
            or project["source_trace"] != trace_id
            or project["source_scene"] != identity(Path(scene_root) / "scene.json")
            or project["files"]["trace.json"] != trace_id
            or project["files"]["motion.usdc"] != usd_id
            or project["rendered_source_frames"] != frames
            or set(project["render_files"]) != {f"renders/frame_{i+1:04}.png" for i in frames}):
        raise ValueError("native project does not retain the full recorded frame range")
    if (blender.get("schema") != "robot-reel.scene-motion-blender-check.v1"
            or blender.get("passed") is not True or blender["source_trace"] != trace_id
            or blender["usd"] != usd_id
            or blender["project"] != project["files"]["scene-motion.blend"]
            or blender["frames"] != counts["frames"]
            or blender["body_transforms"] != counts["body_transforms"]
            or blender["camera_projections"] != counts["body_transforms"]
            or blender["checked_render_files"] != counts["frames"]
            or blender["virtual_camera_lens_mm"] != 50
            or not 0 <= blender["max_projection_error_px"] <= .002
            or not 0 <= blender["max_world_matrix_error"] <= 3e-6):
        raise ValueError("Blender readback does not cover all frames and the recorded camera")
    checked_file(root, "simulation.mp4", trace["files"]["simulation.mp4"])
    checked_file(root, "poster.png", project["render_files"]["renders/frame_0001.png"])
    video = load_json(root / "video-check.json")
    if (video.get("schema") != "robot-reel.scene-motion-video.v1"
            or video["source_trace"] != trace_id
            or video["source_project"] != identity(root / "project.json")
            or video["video"] != identity(root / "blender.mp4")
            or video["decoded_frames"] != counts["frames"]
            or video["width"] != trace["camera"]["width"]
            or video["height"] != trace["camera"]["height"]
            or video["fps"] != trace["plan"]["sample_hz"]
            or video["source_frames"] != frames
            or video["checked_presentation_timestamps"] != counts["frames"]
            or not 0 <= video["max_timestamp_error_s"] <= .00001
            or not math.isfinite(video["minimum_psnr_db"])
            or video["minimum_psnr_db"] < 30):
        raise ValueError("encoded Blender video does not cover the source frames")
    return trace


def verify(root, scenes):
    root, scenes = Path(root), Path(scenes)
    record = load_json(root / "motion.json")
    if (record.get("schema") != "robot-reel.scene-motion-site.v1"
            or set(record.get("cases", {})) != set(CASES)
            or set(record.get("files", {})) != FILES - {"motion.json"}):
        raise ValueError("motion site inventory differs")
    for name, expected in record["files"].items():
        checked_file(root, name, expected)
    traces = {case: checked_case(root / case, case, scenes / case) for case in CASES}
    first = traces["baseline"]
    if any(trace["plan"] != first["plan"] or trace["bodies"] != first["bodies"]
           or trace["policy"] != first["policy"] for trace in traces.values()):
        raise ValueError("motion cases do not use the shared plan and policy")
    if record["plan"] != first["plan"] or record["policy"] != first["policy"]:
        raise ValueError("site summary differs from its recorded plan")
    for case, trace in traces.items():
        row = record["cases"][case]
        if row != {
            "trace": identity(root / case / "trace.json"),
            "frames": len(trace["frames"]), "policy_calls": len(trace["policy_calls"]),
            "camera": trace["camera"], "initial_root_m": trace["frames"][0]["qpos"][:3],
            "final_root_m": trace["frames"][-1]["qpos"][:3],
            "frames_with_terrain_contacts": sum(bool(f["terrain_contacts"]) for f in trace["frames"]),
        }:
            raise ValueError("displayed case summary differs from recorded motion")
    expected_glb = load_json(root / "baseline/export-check.json")["glb"]["file"]
    checked_file(root, "robot.glb", expected_glb)
    if load_json(root / "body-bounds.json") != body_bounds((root / "robot.glb").read_bytes(), first["bodies"]):
        raise ValueError("lightweight geometry bounds differ from the full model")
    return {"valid": True, "cases": list(CASES), "frames": sum(len(t["frames"]) for t in traces.values()),
            "body_transforms": sum(len(t["frames"])*len(t["bodies"]) for t in traces.values())}


def package(base, scenes, output, *, locations=None):
    """Package only completed, independently checked runs and encoded videos."""
    base, scenes, output = Path(base), Path(scenes), Path(output)
    if output.exists():
        raise ValueError("choose a new motion output directory")
    output.mkdir(parents=True)
    for case in CASES:
        destination = output / case
        destination.mkdir()
        paths = (locations or {}).get(case, {})
        native = base / paths.get("project", f"{case}-blender")
        export = base / paths.get("export", f"{case}-export")
        raw = base / paths.get("recording", case)
        video = base / paths.get("video", f"{case}-video")
        sources = {
            "trace.json": raw / "trace.json", "simulation.mp4": raw / "simulation.mp4",
            "native-check.json": base / paths.get("native_check", f"{case}-native-check.json"),
            "export-check.json": export / "export-check.json",
            "blender-check.json": base / paths.get("blender_check", f"{case}-blender-check.json"),
            "project.json": native / "project.json", "motion.usdc": native / "motion.usdc",
            "poster.png": native / "renders/frame_0001.png",
            "blender.mp4": video / "blender.mp4",
            "video-check.json": video / "video-check.json",
        }
        for name, source in sources.items():
            shutil.copyfile(source, destination / name)
        checked_case(destination, case, scenes / case)
    exports = {case: base / (locations or {}).get(case, {}).get("export", f"{case}-export") for case in CASES}
    shutil.copyfile(exports["baseline"] / "robot.glb", output / "robot.glb")
    traces = {case: load_json(output / case / "trace.json") for case in CASES}
    # Only the initial body poses and trace annotation may differ between GLBs.
    left, left_binary = glb_parts((exports["baseline"] / "robot.glb").read_bytes())
    right, right_binary = glb_parts((exports["edited"] / "robot.glb").read_bytes())
    for document in (left, right):
        document.pop("extras")
        for node_index in document["nodes"][0]["children"]:
            node = document["nodes"][node_index]
            node.pop("translation")
            node.pop("rotation")
    if left != right or left_binary != right_binary:
        raise ValueError("one shared robot GLB cannot represent both recorded models")
    write_json(output / "body-bounds.json", body_bounds(
        (output / "robot.glb").read_bytes(), traces["baseline"]["bodies"]))
    (output / "NOTICE.txt").write_text(NOTICE)
    rows = {}
    for case, trace in traces.items():
        rows[case] = {
            "trace": identity(output / case / "trace.json"),
            "frames": len(trace["frames"]), "policy_calls": len(trace["policy_calls"]),
            "camera": trace["camera"], "initial_root_m": trace["frames"][0]["qpos"][:3],
            "final_root_m": trace["frames"][-1]["qpos"][:3],
            "frames_with_terrain_contacts": sum(bool(f["terrain_contacts"]) for f in trace["frames"]),
        }
    write_json(output / "motion.json", {
        "schema": "robot-reel.scene-motion-site.v1", "plan": traces["baseline"]["plan"],
        "policy": traces["baseline"]["policy"], "cases": rows,
        "files": {name: identity(output / name) for name in sorted(FILES - {"motion.json"})},
    })
    return verify(output, scenes)


def verify_frame(root, record):
    """Check a received frame against the original trace, including its camera."""
    root = Path(root)
    required = {"schema", "case", "source_trace", "frame", "camera", "blender_frame", "browser_view", "world"}
    if (not isinstance(record, dict) or set(record) != required
            or record["schema"] != "robot-reel.scene-motion-frame.v1"
            or record["case"] not in CASES
            or record["browser_view"] not in ("recorded", "orbit", "scene")
            or not isinstance(record["frame"], dict)):
        raise ValueError("unsupported scene frame review")
    trace_path = root / record["case"] / "trace.json"
    trace = load_json(trace_path)
    validate_trace(trace)
    frame = record["frame"].get("frame")
    if type(frame) is not int or not 0 <= frame < len(trace["frames"]):
        raise ValueError("frame index lies outside the original recording")
    if (record["source_trace"] != identity(trace_path) or record["frame"] != trace["frames"][frame]
            or record["camera"] != trace["camera"] or record["world"] != trace["world"]
            or type(record["blender_frame"]) is not int or record["blender_frame"] != frame+1):
        raise ValueError("received frame facts differ from the original recording")
    return {"valid": True, "case": record["case"], "frame": frame,
            "blender_frame": frame+1, "source_trace": identity(trace_path)}
