"""Build the Microduck Motion Lab from two original recordings, without simulation.

The small kinematic description comes from export_microduck_kinematics.py.
Forward kinematics is checked separately against MuJoCo for every measured and
target pose. No root attitude, contact state or new policy output is invented.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import shutil
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from robot_reel.microduck import MODEL_COMMIT, POLICY_REVISION, POLICY_SHA256
from robot_reel.pages import digest

SOURCE = ROOT/"docs/compare/microduck"
KINEMATICS = ROOT/"scripts/assets/microduck-kinematics.json"
FILES = ("index.html", "data.json", "kinematics.json", "kinematics-check.json",
         "left-trace.json", "right-trace.json", "left.mp4", "right.mp4",
         "MICRODUCK-MEDIA-NOTICE.txt", "METHODS.md", "LICENSE", "manifest.json")
JOINTS = ("left_hip_yaw", "left_hip_roll", "left_hip_pitch", "left_knee", "left_ankle",
          "neck_pitch", "head_pitch", "head_yaw", "head_roll", "right_hip_yaw",
          "right_hip_roll", "right_hip_pitch", "right_knee", "right_ankle")


def multiply(a, b):
    w, x, y, z = a
    v, i, j, k = b
    return [w*v-x*i-y*j-z*k, w*i+x*v+y*k-z*j,
            w*j-x*k+y*v+z*i, w*k+x*j-y*i+z*v]


def rotate(q, v):
    return multiply(multiply(q, [0, *v]), [q[0], -q[1], -q[2], -q[3]])[1:]


def poses(kinematics, angles):
    """Body-local transforms with the floating root fixed at identity."""
    result = []
    for body in kinematics["bodies"]:
        if body["parent"] == -1:
            result.append([0, 0, 0, 1, 0, 0, 0])
            continue
        parent = result[body["parent"]]
        position = [a+b for a, b in zip(parent[:3], rotate(parent[3:], body["position"]))]
        orientation = multiply(parent[3:], body["quaternion"])
        angle = angles[body["joint"]]-body["reference"]
        joint = multiply(orientation, [math.cos(angle/2), *[
            a*math.sin(angle/2) for a in body["axis"]]])
        before, after = rotate(orientation, body["offset"]), rotate(joint, body["offset"])
        result.append([p+a-b for p, a, b in zip(position, before, after)]+joint)
    return result


def validate_trace(trace, speed):
    if (trace.get("robot") != "microduck" or tuple(trace.get("joints", [])) != JOINTS
            or trace.get("requested_speed_mps") != speed or trace.get("fps") != 30
            or len(trace.get("frames", [])) != 300 or len(trace.get("policy_steps", [])) != 500
            or trace["policy"]["model_commit"] != MODEL_COMMIT
            or trace["policy"]["revision"] != POLICY_REVISION
            or trace["policy"]["sha256"] != POLICY_SHA256):
        raise ValueError("Unexpected Microduck source contract")
    previous_time = 0
    for index, frame in enumerate(trace["frames"]):
        if (type(frame["frame"]) is not int or frame["frame"] != index
                or not previous_time < frame["sim_time"] <= 10.001
                or type(frame["policy_step"]) is not int or not 0 <= frame["policy_step"] < 500):
            raise ValueError("Invalid Microduck sample clock")
        for key, length in (("qpos", 14), ("target", 14), ("base_position_m", 3)):
            values = frame[key]
            if len(values) != length or any(type(v) not in (float, int) or not math.isfinite(v) for v in values):
                raise ValueError("Invalid Microduck numeric sample")
        step = trace["policy_steps"][frame["policy_step"]]
        if frame["target"] != step["target"] or not 0 <= frame["sim_time"]-step["sim_time"] <= .021:
            raise ValueError("Sample target differs from the preceding policy step")
        previous_time = frame["sim_time"]


def make_data(source, kinematics):
    if (kinematics["model_commit"] != MODEL_COMMIT or kinematics["joints"] != list(JOINTS)
            or len(kinematics["bodies"]) != 15):
        raise ValueError("Unexpected Microduck kinematic description")
    runs = []
    for name, speed in (("left", .3), ("right", .5)):
        path = source/f"{name}-trace.json"
        trace = json.loads(path.read_text())
        validate_trace(trace, speed)
        frames = []
        for original in trace["frames"]:
            frames.append({**original, "measured_pose": poses(kinematics, original["qpos"]),
                           "target_pose": poses(kinematics, original["target"])})
        worst = max(((abs(f["qpos"][j]-f["target"][j]), f["frame"], j)
                     for f in frames for j in range(14)))
        runs.append({"id": name, "speed": speed, "trace_sha256": digest(path),
                     "video_sha256": digest(source/f"{name}.mp4"), "frames": frames,
                     "mean_walking_speed_mps": sum(f["measured_forward_speed_mps"] for f in frames
                         if f["commanded_forward_speed_mps"] > 0)/210,
                     "peak_error": {"radians": worst[0], "frame": worst[1], "joint": worst[2]}})
    return {"schema": "robot-reel-microduck-motion-1", "fps": 30,
            "coordinate_frame": "floating root fixed at origin, identity rotation",
            "joints": list(JOINTS), "kinematics": kinematics, "runs": runs}


def same_data(actual, expected):
    """Keep source values exact; allow platform libm roundoff only in derived FK."""
    try:
        for actual_run, expected_run in zip(actual["runs"], expected["runs"], strict=True):
            for actual_frame, expected_frame in zip(actual_run["frames"], expected_run["frames"], strict=True):
                for key in ("measured_pose", "target_pose"):
                    for actual_body, expected_body in zip(actual_frame[key], expected_frame[key], strict=True):
                        for a, b in zip(actual_body, expected_body, strict=True):
                            if type(a) not in (float, int) or not math.isfinite(a) or abs(a-b) > 1e-12:
                                return False
                    expected_frame[key] = actual_frame[key]
        # Python considers False == 0 and True == 1; source JSON must not.
        return json.dumps(actual, sort_keys=True, allow_nan=False) == json.dumps(
            expected, sort_keys=True, allow_nan=False)
    except (KeyError, TypeError, ValueError):
        return False


def verify_showcase(site, *, check_sources=False):
    site = Path(site)
    record = json.loads((site/"showcase-manifest.json").read_text())
    expected = {*FILES, "poster.png", "experiment.zip"}
    if record.get("schema") != "robot-reel-microduck-showcase-1" or set(record.get("files", {})) != expected:
        raise ValueError("Unexpected Microduck file inventory")
    if any(p.is_symlink() for p in site.rglob("*")):
        raise ValueError("Microduck lab contains a symlink")
    for name, checksum in record["files"].items():
        if digest(site/name) != checksum:
            raise ValueError(f"Changed Microduck file: {name}")
    bundle = json.loads((site/"manifest.json").read_text())
    if (bundle.get("schema") != "robot-reel-microduck-motion-bundle-1"
            or bundle.get("sha256") != {name: digest(site/name) for name in FILES if name != "manifest.json"}):
        raise ValueError("Microduck offline source inventory differs")
    with zipfile.ZipFile(site/"experiment.zip") as archive:
        if len(archive.namelist()) != len(FILES) or set(archive.namelist()) != set(FILES):
            raise ValueError("Unexpected Microduck offline archive")
        for name in FILES:
            if archive.read(name) != (site/name).read_bytes():
                raise ValueError(f"Changed offline Microduck file: {name}")
    kin = json.loads((site/"kinematics.json").read_text())
    data = json.loads((site/"data.json").read_text())
    if not same_data(data, make_data(site, kin)):
        raise ValueError("Microduck poses or metrics differ from original traces")
    report = json.loads((site/"kinematics-check.json").read_text())
    if (report["kinematics_sha256"] != digest(site/"kinematics.json")
            or report["trace_sha256"] != {name: digest(site/f"{name}-trace.json") for name in ("left", "right")}
            or report["checked_body_transforms"] != 18000
            or not 0 <= report["max_position_error_m"] < 1e-9
            or not 0 <= report["max_rotation_matrix_error"] < 1e-9):
        raise ValueError("Microduck native kinematic readback differs")
    html = (site/"index.html").read_text()
    embedded = html.split('<script id="lab-data" type="application/json">', 1)[1].split("</script>", 1)[0]
    if json.loads(embedded) != data:
        raise ValueError("Microduck viewer contains changed evidence")
    if check_sources:
        for name in ("left-trace.json", "right-trace.json", "left.mp4", "right.mp4"):
            if digest(site/name) != digest(SOURCE/name):
                raise ValueError(f"Microduck original source changed: {name}")
        if digest(KINEMATICS) != digest(site/"kinematics.json"):
            raise ValueError("Microduck model description changed")
    return {"runs": 2, "frames": 600, "joint_samples": 8400,
            "checked_body_transforms": 18000, "source_data_unchanged": check_sources}


def build(site):
    site = Path(site).absolute()
    if site.is_symlink() or any(p.is_symlink() for p in site.parents):
        raise ValueError("Choose a destination without symlinks")
    if site.exists() and any(site.iterdir()):
        raise ValueError("Choose an empty Microduck destination")
    kin = json.loads(KINEMATICS.read_text())
    data = make_data(SOURCE, kin)
    site.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".microduck-", dir=site.parent) as temporary:
        stage = Path(temporary)
        for name in ("left-trace.json", "right-trace.json", "left.mp4", "right.mp4",
                     "MICRODUCK-MEDIA-NOTICE.txt"):
            shutil.copyfile(SOURCE/name, stage/name)
        with (stage/"MICRODUCK-MEDIA-NOTICE.txt").open("a") as notice:
            notice.write("\nThe Motion Lab's simplified body envelopes and kinematic description "
                         "are derived from the same pinned model. They retain the upstream "
                         "noncommercial/share-alike terms too; the Apache-2.0 code license "
                         "does not relicense this geometry.\n")
        shutil.copyfile(KINEMATICS, stage/"kinematics.json")
        shutil.copyfile(KINEMATICS.with_name("microduck-kinematics-check.json"), stage/"kinematics-check.json")
        shutil.copyfile(ROOT/"LICENSE", stage/"LICENSE")
        shutil.copyfile(ROOT/"docs/microduck-lab.md", stage/"METHODS.md")
        payload = json.dumps(data, separators=(",", ":"), allow_nan=False)
        (stage/"data.json").write_text(payload+"\n")
        template = (ROOT/"scripts/microduck_lab.html").read_text()
        (stage/"index.html").write_text(template.replace("__LAB_DATA__", payload.replace("<", "\\u003c")))
        # The poster is captured from the actual viewer, then the bundle is sealed.
        if site.exists():
            site.rmdir()
        shutil.copytree(stage, site)
    return data


def seal(site):
    site = Path(site)
    (site/"manifest.json").write_text(json.dumps({
        "schema": "robot-reel-microduck-motion-bundle-1",
        "sha256": {name: digest(site/name) for name in FILES if name != "manifest.json"},
    }, indent=2)+"\n")
    with zipfile.ZipFile(site/"experiment.zip", "w", zipfile.ZIP_DEFLATED) as archive:
        for name in FILES:
            info = zipfile.ZipInfo(name, date_time=(2026, 9, 14, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, (site/name).read_bytes())
    (site/"showcase-manifest.json").write_text(json.dumps({
        "schema": "robot-reel-microduck-showcase-1", "poster": {"run": "right", "frame": 120, "joint": 3},
        "files": {name: digest(site/name) for name in (*FILES, "poster.png", "experiment.zip")},
    }, indent=2)+"\n")
    return verify_showcase(site, check_sources=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT/"docs/microduck-lab")
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--seal", action="store_true")
    args = parser.parse_args()
    print(json.dumps(verify_showcase(args.output, check_sources=True) if args.verify else
                     seal(args.output) if args.seal else {"runs": len(build(args.output)["runs"])}, indent=2))
