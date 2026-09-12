"""Package a checked .blend and its rendered preview for GitHub Pages."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import zipfile

from robot_reel.blender import verify_export
from robot_reel.compare import digest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--video", type=Path, required=True)
    parser.add_argument("--poster", type=Path, required=True)
    parser.add_argument("--destination", type=Path, default=Path("docs/blender"))
    args = parser.parse_args()
    summary = verify_export(args.bundle)
    report = json.loads((args.bundle / "animation-check.json").read_text())
    if report["blend_sha256"] != digest(args.bundle / "replay.blend"):
        raise ValueError("Animation check does not match the supplied .blend")
    if report["scene_json_sha256"] != digest(args.bundle / "scene.json"):
        raise ValueError("Animation check does not match the exported scene")
    import imageio_ffmpeg
    count, duration = imageio_ffmpeg.count_frames_and_secs(str(args.video))
    if count != summary["frames"] or abs(duration-summary["frames"]/summary["fps"]) > .01:
        raise ValueError("Preview video must preserve the complete source frame count and duration")
    reader = imageio_ffmpeg.read_frames(str(args.video))
    try:
        if abs(next(reader)["fps"]-summary["fps"]) > .01:
            raise ValueError("Preview frame rate differs from its source")
    finally:
        reader.close()
    output = args.destination
    output.mkdir(parents=True, exist_ok=True)
    document = json.loads((args.bundle / "scene.json").read_text())
    template = Path(__file__).with_name("blender_demo.html").read_text()
    payload = json.dumps(document, separators=(",", ":")).replace("<", "\\u003c")
    (output / "index.html").write_text(template.replace("__SCENE_DATA__", payload))
    for name in ("replay.blend", "animation-check.json"):
        shutil.copyfile(args.bundle / name, output / name)
    shutil.copyfile(args.video, output / "replay.mp4")
    shutil.copyfile(args.poster, output / "poster.png")
    subprocess.run([
        imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-loglevel", "error",
        "-i", str(args.video), "-filter_complex",
        "fps=12,scale=640:-1:flags=lanczos,split[a][b];[a]palettegen[p];[b][p]paletteuse",
        "-loop", "0", str(output / "preview.gif"),
    ], check=True)
    source_manifest = json.loads((args.bundle / "blender-manifest.json").read_text())
    filenames = list(source_manifest["sha256"]) + ["blender-manifest.json", "replay.blend", "animation-check.json"]
    with zipfile.ZipFile(output / "robot-reel-blender.zip", "w", zipfile.ZIP_DEFLATED) as archive:
        for name in filenames:
            archive.write(args.bundle / name, name)
    files = [output / name for name in ("index.html", "replay.mp4", "poster.png", "preview.gif",
                                       "replay.blend", "animation-check.json", "robot-reel-blender.zip")]
    (output / "media-manifest.json").write_text(json.dumps({
        "schema": 1, "blender_version": report["blender_version"],
        "frames": count, "fps": summary["fps"],
        "sha256": {p.name: digest(p) for p in files},
    }, indent=2) + "\n")
    print(f"Built {output.resolve()}; {count} frames, {duration:g} seconds")


if __name__ == "__main__":
    main()
