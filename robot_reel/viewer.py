"""Export a browser replay that also works from a local file, without a server."""
import argparse
import html
import json
from pathlib import Path


def export_viewer(directory, destination=None, media_prefix="", validate=True):
    if validate:
        from .verify import verify
        verify(directory)
    manifest = json.loads((directory / "manifest.json").read_text())
    traces = [json.loads((directory / f"{robot}-trace.json").read_text())
              for robot in manifest.get("scenes", ("so100", "unitree_g1"))]
    offset = 2.0
    scenes = []
    for trace in traces:
        scene = {**trace, "start": offset}
        scene.pop("policy_steps", None)
        scenes.append(scene)
        offset += len(trace["frames"]) / trace["fps"]
    data = {"scenes": scenes, "duration": offset + 3, "pack": manifest.get("pack", "studio"),
            "provenance": {"director": manifest["arm_director"],
                           "editing": manifest["editing"],
                           "versions": manifest["versions"]}}
    # Embedded JSON must not close the script element, even with user captions.
    serialized = json.dumps(data, separators=(",", ":"), ensure_ascii=True).replace("<", "\\u003c")
    template = Path(__file__).with_name("replay.html").read_text()
    template = template.replace("__MEDIA_PREFIX__", html.escape(media_prefix, quote=True))
    template = template.replace("__REEL_DATA__", serialized)
    if data["pack"] == "microduck":
        template = template.replace("https://noteflowai.github.io/robot-reel/media/poster.png", "https://noteflowai.github.io/robot-reel/microduck/media/poster.png")
    destination = destination or directory / "index.html"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(template)
    return destination


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    # Standalone export refreshes the manifest after adding its HTML output.
    old = json.loads((args.directory / "manifest.json").read_text())
    print(export_viewer(args.directory))
    from .capture import manifest
    manifest(args.directory, old["arm_director"], old["model_id"], old["region"], old.get("scenes"), old.get("pack"))


if __name__ == "__main__":
    main()
