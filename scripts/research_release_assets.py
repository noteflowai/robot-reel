"""Download immutable public experiment assets and verify every expected byte."""
import hashlib
import json
import re
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath


def fetch_assets(source, output, *, opener=urllib.request.urlopen):
    specification = Path(source) / "requirements/research-release-assets.json"
    if not specification.is_file():
        return []
    document = json.loads(specification.read_text())
    if (document.get("dataset") != "glayguo/noteflow-research-pilots"
            or not re.fullmatch(r"[0-9a-f]{40}", document.get("revision", ""))):
        raise ValueError("expected the reviewed immutable public dataset")
    files = document["files"]
    required = {"scene-lab-native.zip", "research-records.zip"}
    if set(files) not in (required, required | {"scene-motion-native.zip"}):
        raise ValueError("unexpected research release inventory")
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    for name, expected in files.items():
        if (type(expected.get("bytes")) is not int or not 0 < expected["bytes"] < 128*1024*1024
                or not re.fullmatch(r"[0-9a-f]{64}", expected.get("sha256", ""))):
            raise ValueError("invalid expected asset size or hash")
        url = (f"https://huggingface.co/datasets/{document['dataset']}/resolve/"
               f"{document['revision']}/artifacts/{name}")
        with opener(url, timeout=90) as response:
            raw = response.read(expected["bytes"] + 1)
        if (len(raw) != expected["bytes"]
                or hashlib.sha256(raw).hexdigest() != expected["sha256"]):
            raise ValueError(f"immutable research asset changed: {name}")
        path = output / name
        path.write_bytes(raw)
        with zipfile.ZipFile(path) as archive:
            entries = archive.infolist()
            if len(entries) != len({item.filename for item in entries}):
                raise ValueError("duplicate archive member")
            for entry in entries:
                relative = PurePosixPath(entry.filename)
                if (relative.is_absolute() or ".." in relative.parts or "\\" in entry.filename
                        or entry.file_size > 32*1024*1024):
                    raise ValueError("unsafe or oversized research member")
            if name == "scene-lab-native.zip":
                expected_names = {"METHODS.md"} | {
                    f"{variant}/{item}" for variant in ("baseline", "edited")
                    for item in ("scene.blend", "scene.json", "native-check.json", "edit.json")
                }
                if set(archive.namelist()) != expected_names:
                    raise ValueError("native archive inventory differs")
                for variant in ("baseline", "edited"):
                    scene = json.loads(archive.read(f"{variant}/scene.json"))
                    native = archive.read(f"{variant}/scene.blend")
                    check = json.loads(archive.read(f"{variant}/native-check.json"))
                    checksum = hashlib.sha256(native).hexdigest()
                    if (scene["files"]["scene.blend"] != {"sha256": checksum, "bytes": len(native)}
                            or check["scene_sha256"] != checksum or check["passed"] is not True):
                        raise ValueError("native scene differs from recorded independent check")
            elif name == "scene-motion-native.zip":
                expected_names = {"README.md", "LICENSE", "check_scene_motion_blender.py"}
                for variant in ("baseline", "edited"):
                    project = json.loads(archive.read(f"{variant}/project.json"))
                    check = json.loads(archive.read(f"{variant}/producer-native-check.json"))
                    if (project.get("schema") != "robot-reel.scene-motion-blender.v1"
                            or check.get("passed") is not True
                            or check["project"] != project["files"]["scene-motion.blend"]
                            or check["source_trace"] != project["source_trace"]
                            or check["frames"] != len(project["rendered_source_frames"])):
                        raise ValueError("motion archive differs from its native check")
                    expected_names.update({f"{variant}/project.json", f"{variant}/producer-native-check.json"})
                    for member, identity in project["files"].items():
                        filename = f"{variant}/{member}"
                        content = archive.read(filename)
                        if identity != {"sha256": hashlib.sha256(content).hexdigest(), "bytes": len(content)}:
                            raise ValueError("motion project input differs")
                        expected_names.add(filename)
                if set(archive.namelist()) != expected_names:
                    raise ValueError("motion archive inventory differs")
    return [output / name for name in sorted(files)]
