"""Show the same recorded samples in the original simulation and Blender."""
import argparse
import json
from pathlib import Path
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from robot_reel.blender import verify_export
from robot_reel.compare import digest, verify_comparison

INPUTS = (
    "compare/braking/comparison-manifest.json", "compare/braking/comparison.mp4",
    "compare/braking/left-trace.json", "compare/braking/right-trace.json",
    "blender/media-manifest.json", "blender/replay.mp4",
    "blender/robot-reel-blender.zip", "blender/animation-check.json",
)


def checked_scene(docs=ROOT/"docs"):
    docs = Path(docs)
    verify_comparison(docs/"compare/braking")
    media = json.loads((docs/"blender/media-manifest.json").read_text())
    for name, expected in media["sha256"].items():
        if Path(name).name != name or digest(docs/"blender"/name) != expected:
            raise ValueError(f"Changed Blender source: {name}")
    with tempfile.TemporaryDirectory() as temporary:
        bundle = Path(temporary)
        with zipfile.ZipFile(docs/"blender/robot-reel-blender.zip") as archive:
            if any(Path(name).name != name for name in archive.namelist()):
                raise ValueError("Unexpected path inside the Blender source bundle")
            archive.extractall(bundle)
        verify_export(bundle)
        scene = json.loads((bundle/"scene.json").read_text())
        report = json.loads((bundle/"animation-check.json").read_text())
        if (
            report["scene_json_sha256"] != digest(bundle/"scene.json")
            or report["blend_sha256"] != digest(docs/"blender/replay.blend")
            or report["checked_vehicle_samples"] != 2*scene["frame_count"]
            or report["maximum_position_error_m"] > 1e-5
        ):
            raise ValueError("The native Blender check differs from its source")
        for side, run in zip(("left", "right"), scene["runs"]):
            original = json.loads((docs/f"compare/braking/{side}-trace.json").read_text())
            if run["frames"] != original["frames"] or run["outcome"] != original["outcome"]:
                raise ValueError("Original simulation and Blender do not share the same recording")
    return scene


def verify_site(docs=ROOT/"docs"):
    docs = Path(docs)
    scene = checked_scene(docs)
    site = docs/"remix"
    manifest = json.loads((site/"manifest.json").read_text())
    if manifest.get("schema") != "robot-reel-remix-1" or set(manifest.get("inputs", {})) != set(INPUTS):
        raise ValueError("Incomplete remix source manifest")
    for name in INPUTS:
        if digest(docs/name) != manifest["inputs"][name]:
            raise ValueError(f"Changed remix input: {name}")
    if set(manifest.get("sha256", {})) != {"index.html", "poster.png", "preview.gif"}:
        raise ValueError("Incomplete remix media manifest")
    for name, expected in manifest["sha256"].items():
        if digest(site/name) != expected:
            raise ValueError(f"Changed remix output: {name}")
    payload = (site/"index.html").read_text().split('<script id="scene-data" type="application/json">')[1].split("</script>", 1)[0]
    if json.loads(payload) != scene:
        raise ValueError("Remix viewer differs from the source recording")
    return {"frames": scene["frame_count"], "fps": scene["fps"], "checked_vehicle_samples": 2*scene["frame_count"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--docs", type=Path, default=ROOT/"docs")
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    if args.verify:
        print(json.dumps(verify_site(args.docs), indent=2))
        return
    import imageio_ffmpeg
    from PIL import Image, ImageDraw, ImageFont

    scene = checked_scene(args.docs)
    output = args.docs/"remix"
    output.mkdir(parents=True, exist_ok=True)
    template = Path(__file__).with_name("remix_demo.html").read_text()
    payload = json.dumps(scene, separators=(",", ":"), allow_nan=False).replace("<", "\\u003c")
    (output/"index.html").write_text(template.replace("__SCENE_DATA__", payload))
    readers = [imageio_ffmpeg.read_frames(str(args.docs/name)) for name in ("compare/braking/comparison.mp4", "blender/replay.mp4")]
    metadata = [next(reader) for reader in readers]
    if any(abs(meta["fps"]-scene["fps"]) > .01 for meta in metadata):
        raise ValueError("Source video frame rates differ")
    font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 16)
    small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf", 12)
    previews = []
    try:
        for index in range(scene["frame_count"]):
            images = []
            for side, reader in enumerate(readers):
                try:
                    raw = next(reader)
                except StopIteration as exc:
                    raise ValueError("Missing source video samples") from exc
                images.append(Image.frombytes("RGB", metadata[side]["size"], raw).resize((768, 432)))
            if index % 3:
                continue
            image = Image.new("RGB", (768, 500), "#101923")
            # A moving divider reveals both views; it does not spatially register them.
            ratio = .15+.7*abs(1-2*index/(scene["frame_count"]-1))
            edge = round(768*ratio)
            image.paste(images[1], (0, 42))
            image.paste(images[0].crop((0, 0, edge, 432)), (0, 42))
            draw = ImageDraw.Draw(image)
            draw.text((18, 12), "RAW MUJOCO", font=font, fill="#79dfc3")
            draw.text((575, 12), "BLENDER REPLAY", font=font, fill="#ffca85")
            draw.line((edge, 42, edge, 474), fill="#ffffff", width=2)
            draw.ellipse((edge-18, 239, edge+18, 275), fill="#eef4f1")
            draw.text((edge-12, 246), "↔", font=font, fill="#142330")
            draw.text((18, 480), f'SAME SOURCE FRAME {index:03d}  /  SIM {scene["runs"][0]["frames"][index]["sim_time"]:.3f}s', font=small, fill="#c8d6df")
            previews.append(image)
            if index == 108:
                image.save(output/"poster.png", optimize=True)
        for reader in readers:
            if next(reader, None) is not None:
                raise ValueError("Unexpected extra source video samples")
    finally:
        for reader in readers:
            reader.close()
    palette = previews[36].quantize(colors=128)
    indexed = [image.quantize(palette=palette, dither=Image.Dither.NONE) for image in previews]
    indexed[0].save(output/"preview.gif", save_all=True, append_images=indexed[1:], duration=100, loop=0, optimize=True)
    (output/"manifest.json").write_text(json.dumps({
        "schema": "robot-reel-remix-1",
        "inputs": {name: digest(args.docs/name) for name in INPUTS},
        "sha256": {name: digest(output/name) for name in ("index.html", "poster.png", "preview.gif")},
        "preview": "10 Hz samples of both 30 fps videos; animated divider, no new motion.",
    }, indent=2)+"\n")
    print(json.dumps(verify_site(args.docs), indent=2))


if __name__ == "__main__":
    main()
