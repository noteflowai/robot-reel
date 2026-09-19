"""Create a portable Blender archive from checked motion projects."""

import argparse
import json
from pathlib import Path
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from robot_reel.scene_motion import checked_file, identity

README = """# Scene motion: portable Blender projects

Both six-second Microduck simulations retain all 181 recorded frames. Both
robots fall and slide. These are XML-actuator simulations, not hardware trials.
Source and Blender use metres and Z-up; source frame i is Blender frame i+1.

Extract the entire archive. Keep each scene-motion.blend beside its motion.usdc,
which supplies animation through a relative cache path. Open the Blender file,
select RecordedCamera and scrub frames 1 through 181. Blender 4.5.13 LTS was used.
The captured terrain's textures are packed in the project.

From the extracted root, independently reopen and check each complete motion:

    blender --background --factory-startup --disable-autoexec --python-exit-code 1 \\
      --python check_scene_motion_blender.py -- \\
      --project baseline --output baseline-reopened.json

Repeat for edited and a different output JSON. The included checker verifies
file identities, every robot mesh, every frame's body and visual transforms,
and virtual-camera projections. It does not render new frames.

Each project.json separates portable inputs (included here) from the producer's
PNG inventory (not included here). The retained producer-native-check.json
records the earlier all-PNG check. To use --check-renders, obtain the full
producer archive and restore the recorded renders/ directory.

Native geometry and robot footage retain Pollen Robotics' BY-SA-NC terms,
version unspecified upstream. The Poly Haven Coast Rocks 02 terrain is CC0.
Read each project's NOTICE.txt. Apache-2.0 applies to the Robot Reel checker.
Hashes identify bytes; they do not authenticate the producer or establish
physical scale accuracy of the original scan.
"""


def package(baseline, edited, output, checks):
    output = Path(output)
    entries = {"README.md": README.encode(),
               "check_scene_motion_blender.py": (ROOT / "scripts/check_scene_motion_blender.py").read_bytes(),
               "LICENSE": (ROOT / "LICENSE").read_bytes()}
    for case, root in (("baseline", Path(baseline)), ("edited", Path(edited))):
        project = json.loads((root / "project.json").read_text())
        if project.get("schema") != "robot-reel.scene-motion-blender.v1":
            raise ValueError("unsupported Blender project")
        check = json.loads(Path(checks[case]).read_text())
        if (check.get("passed") is not True
                or check["project"] != project["files"]["scene-motion.blend"]
                or check["source_trace"] != project["source_trace"]
                or check["checked_render_files"] != len(project["rendered_source_frames"])):
            raise ValueError("native check does not identify the complete project")
        entries[f"{case}/producer-native-check.json"] = Path(checks[case]).read_bytes()
        entries[f"{case}/project.json"] = (root / "project.json").read_bytes()
        for name, expected in project["files"].items():
            entries[f"{case}/{name}"] = checked_file(root, name, expected).read_bytes()
    with zipfile.ZipFile(output, "x", zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for name, data in sorted(entries.items()):
            info = zipfile.ZipInfo(name, date_time=(2026, 9, 19, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, data)
    return {"archive": identity(output), "files": len(entries)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", required=True, type=Path)
    parser.add_argument("--edited", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--baseline-check", required=True, type=Path)
    parser.add_argument("--edited-check", required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(package(args.baseline, args.edited, args.output, {
        "baseline": args.baseline_check, "edited": args.edited_check,
    }), indent=2))
