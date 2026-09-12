"""Turn a verified braking run and an agent's storyboard into a checkable film."""
import argparse
import json
from pathlib import Path
import shutil
import tempfile

from .blender import export_blender, verify_export
from .compare import digest

SCHEMA = "robot-reel-director-1"
CAMERAS = ("overview", "tracking", "impact", "top")
THEMES = ("midnight", "daylight")
EXPORT_FILES = ("storyboard.json", "film.json", "build_directed_scene.py", "base_scene.py")


def validate_storyboard(plan, frame_count):
    if not isinstance(plan, dict) or set(plan) != {"schema", "brief", "title", "theme", "shots"}:
        raise ValueError("Storyboard requires schema, brief, title, theme and shots")
    if plan["schema"] != SCHEMA or plan["theme"] not in THEMES:
        raise ValueError("Unsupported storyboard schema or theme")
    for key, maximum in (("brief", 1200), ("title", 80)):
        if not isinstance(plan[key], str) or not plan[key].strip() or len(plan[key]) > maximum:
            raise ValueError(f"{key} must contain 1–{maximum} characters")
    if not isinstance(plan["shots"], list) or not 1 <= len(plan["shots"]) <= 8:
        raise ValueError("Provide 1–8 shots")
    next_frame = 0
    for shot in plan["shots"]:
        if not isinstance(shot, dict) or set(shot) != {"start", "end", "camera", "rate", "caption"}:
            raise ValueError("Each shot requires start, end, camera, rate and caption")
        if (
            type(shot["start"]) is not int or type(shot["end"]) is not int
            or shot["start"] != next_frame or not shot["start"] < shot["end"] <= frame_count
        ):
            raise ValueError("Shots must cover every source frame once, in order, using exclusive end indices")
        if shot["camera"] not in CAMERAS:
            raise ValueError("Unsupported camera")
        if type(shot["rate"]) not in (int, float) or shot["rate"] not in (.5, 1):
            raise ValueError("Playback rate must be 0.5 or 1; slow motion repeats samples")
        if not isinstance(shot["caption"], str) or not shot["caption"].strip() or len(shot["caption"]) > 100:
            raise ValueError("Each caption must contain 1–100 characters")
        next_frame = shot["end"]
    if next_frame != frame_count:
        raise ValueError("Storyboard omits the end of the recording")
    return plan


def film_document(source, plan):
    validate_storyboard(plan, source["frame_count"])
    frames = []
    for shot_index, shot in enumerate(plan["shots"]):
        for index in range(shot["start"], shot["end"]):
            for _ in range(round(1 / shot["rate"])):
                frames.append({
                    "frame": len(frames), "source_frame": index, "shot": shot_index,
                    "sim_time": source["runs"][0]["frames"][index]["sim_time"],
                })
    return {
        "schema": SCHEMA, "fps": source["fps"], "source_frame_count": source["frame_count"],
        "frame_count": len(frames), "frames": frames,
        "editing": "Camera cuts and sample duplication only; no source motion is generated or dropped.",
    }


def inspect_source(source):
    """Expose facts and available presentation controls for a director agent."""
    source = Path(source)
    with tempfile.TemporaryDirectory() as temporary:
        directory = Path(temporary)/"source"
        if (source/"blender-manifest.json").exists():
            verify_export(source)
            document = json.loads((source/"scene.json").read_text())
        else:
            document = export_blender(source, directory)
    events = []
    for run in document["runs"]:
        for name, predicate in (
            ("braking", lambda f: f.get("brake_force_n", 0) != 0),
            ("contact", lambda f: f["collision"]),
        ):
            frame = next((f for f in run["frames"] if predicate(f)), None)
            if frame:
                events.append({"run": run["id"], "event": name, "frame": frame["frame"], "sim_time": frame["sim_time"]})
    return {
        "fps": document["fps"], "frames": document["frame_count"],
        "events": events, "cameras": list(CAMERAS), "themes": list(THEMES),
        "rates": [.5, 1], "storyboard_schema": SCHEMA,
        "rule": "Cover [0, frames) with consecutive shots. End indices are exclusive. Never alter recorded outcomes.",
        "runs": [{"id": r["id"], "label": r["label"], "outcome": r["outcome"]} for r in document["runs"]],
    }


def export_director(source, output, plan):
    source, output = Path(source).resolve(), Path(output).resolve()
    if source == output or source in output.parents:
        raise ValueError("Director output must be outside the source bundle")
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        raise ValueError("Director output must be empty")
    facts = inspect_source(source)
    validate_storyboard(plan, facts["frames"])
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".director-", dir=output.parent) as temporary:
        staging = Path(temporary)
        if (source/"blender-manifest.json").exists():
            original = json.loads((source/"blender-manifest.json").read_text())
            (staging/"source").mkdir()
            for filename in [*original["sha256"], "blender-manifest.json"]:
                shutil.copyfile(source/filename, staging/"source"/filename)
        else:
            export_blender(source, staging/"source")
        document = json.loads((staging/"source/scene.json").read_text())
        (staging/"storyboard.json").write_text(json.dumps(plan, indent=2, ensure_ascii=False)+"\n")
        (staging/"film.json").write_text(json.dumps(film_document(document, plan), indent=2)+"\n")
        shutil.copyfile(Path(__file__).with_name("director_scene.py"), staging/"build_directed_scene.py")
        shutil.copyfile(Path(__file__).with_name("blender_scene.py"), staging/"base_scene.py")
        (staging/"director-manifest.json").write_text(json.dumps({
            "schema": SCHEMA,
            "source_manifest_sha256": digest(staging/"source/blender-manifest.json"),
            "sha256": {name: digest(staging/name) for name in EXPORT_FILES},
        }, indent=2)+"\n")
        verify_director(staging)
        shutil.copytree(staging, output, dirs_exist_ok=True)
    return film_document(document, plan)


def verify_director(directory):
    directory = Path(directory)
    verify_export(directory/"source")
    manifest = json.loads((directory/"director-manifest.json").read_text())
    if manifest.get("schema") != SCHEMA or set(manifest.get("sha256", {})) != set(EXPORT_FILES):
        raise ValueError("Incomplete director manifest")
    if manifest.get("source_manifest_sha256") != digest(directory/"source/blender-manifest.json"):
        raise ValueError("Director source manifest changed")
    for name in EXPORT_FILES:
        if manifest["sha256"][name] != digest(directory/name):
            raise ValueError(f"Director hash mismatch: {name}")
    document = json.loads((directory/"source/scene.json").read_text())
    plan = json.loads((directory/"storyboard.json").read_text())
    film = json.loads((directory/"film.json").read_text())
    if film != film_document(document, plan):
        raise ValueError("Film mapping differs from its storyboard or source recording")
    return {"frames": film["frame_count"], "source_frames": film["source_frame_count"], "fps": film["fps"]}


def export_viewer(directory, output):
    directory = Path(directory)
    verify_director(directory)
    data = {
        "plan": json.loads((directory/"storyboard.json").read_text()),
        "film": json.loads((directory/"film.json").read_text()),
        "source": json.loads((directory/"source/scene.json").read_text()),
    }
    payload = json.dumps(data, separators=(",", ":"), allow_nan=False).replace("<", "\\u003c")
    Path(output).write_text(Path(__file__).with_name("director.html").read_text().replace("__DIRECTOR_DATA__", payload))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--inspect", action="store_true")
    mode.add_argument("--verify", action="store_true")
    parser.add_argument("--plan", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.inspect or args.verify:
            if args.plan or args.output:
                parser.error("Inspection and verification do not accept --plan or --output")
            result = inspect_source(args.source) if args.inspect else verify_director(args.source)
        else:
            if not args.plan or not args.output:
                parser.error("Export requires --plan and --output")
            export_director(args.source, args.output, json.loads(args.plan.read_text()))
            result = verify_director(args.output)
        print(json.dumps(result, indent=2))
    except (ValueError, OSError, KeyError, TypeError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
