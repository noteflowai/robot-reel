"""Build a mapped preview and portable download from the checked chaos site."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from robot_reel.chaos import device_label, digest, verify
from scripts.build_chaos_site import check_report

BUNDLE_FILES = ("index.html", "trace.json", "scene.usdc", "manifest.json",
                "blender-check.json", "usd-check.json", "NOTICE.txt", "LICENSE")


def verify_showcase(site):
    site = Path(site)
    measured = check_report(site)
    manifest = json.loads((site/"showcase-manifest.json").read_text())
    trace = json.loads((site/"trace.json").read_text())
    expected_samples = list(range(0, len(trace["frames"]), 10))
    if (
        manifest.get("schema") != "robot-reel-chaos-showcase-1"
        or manifest.get("trace_sha256") != digest(site/"trace.json")
        or manifest.get("preview_source_samples") != expected_samples
        or manifest.get("preview_fps") != 10
        or manifest.get("poster_source_sample") != measured["peak"]["frame"]
        or manifest.get("selected_world") != measured["peak"]["world"]
        or manifest.get("view") != "sculpture"
        or set(manifest.get("files", {})) != {*BUNDLE_FILES, "poster.png", "preview.gif", "experiment.zip"}
    ):
        raise ValueError("Invalid chaos showcase mapping")
    for name, expected in manifest["files"].items():
        if digest(site/name) != expected:
            raise ValueError(f"Changed chaos showcase: {name}")
    with zipfile.ZipFile(site/"experiment.zip") as archive:
        if len(archive.namelist()) != len(BUNDLE_FILES) or set(archive.namelist()) != set(BUNDLE_FILES):
            raise ValueError("Unexpected files in chaos offline bundle")
        for name in BUNDLE_FILES:
            if archive.read(name) != (site/name).read_bytes():
                raise ValueError(f"Offline chaos file differs: {name}")
    return measured


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--site", type=Path, default=ROOT/"docs/chaos")
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    if args.verify:
        print(json.dumps(verify_showcase(args.site), indent=2))
        return
    from PIL import Image, ImageDraw, ImageFont
    verify(args.site)
    measured = check_report(args.site)
    trace = json.loads((args.site/"trace.json").read_text())
    samples = list(range(0, len(trace["frames"]), 10))
    with tempfile.TemporaryDirectory() as temporary:
        output = Path(temporary)
        subprocess.run(["node", str(ROOT/"scripts/render_chaos_preview.cjs"), str(args.site), str(output)], check=True)
        if json.loads((output/"samples.json").read_text()) != samples:
            raise ValueError("Captured samples differ from the preview mapping")
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 22)
        small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf", 12)

        def compose(path, motion=True):
            source = Image.open(path).convert("RGB")
            source.thumbnail((900, 530), Image.Resampling.LANCZOS)
            image = Image.new("RGB", (900, source.height+110), "#0b0f1b")
            draw = ImageDraw.Draw(image)
            draw.text((24, 16), "THE BUTTERFLY LAB", font=font, fill="#e9eeff")
            draw.text(
                (24, 48),
                f'{trace["source"]["world_count"]} NEWTON WORLDS / 0.05 DEG BETWEEN ADJACENT RELEASES',
                font=small, fill="#7cf5d3",
            )
            image.paste(source, ((900-source.width)//2, 76))
            stamp = "PREVIEW 3.33x" if motion else f"SOURCE SAMPLE {measured['peak']['frame']}"
            draw.text((24, image.height-25), f"RECORDED POSES / DEPTH = TIME / {stamp} / DRAG TO EXPLORE", font=small, fill="#a5adc8")
            return image

        compose(output/"poster.png", motion=False).save(args.site/"poster.png", optimize=True)
        frames = [compose(output/f"{i:04}.png") for i in range(len(samples))]
        # One shared palette keeps unchanged pixels identical between samples.
        # Disabling dithering preserves narrow trails without noisy backgrounds.
        palette = frames[-1].quantize(colors=96)
        images = [frame.quantize(palette=palette, dither=Image.Dither.NONE) for frame in frames]
        images[0].save(args.site/"preview.gif", save_all=True, append_images=images[1:],
                       duration=100, loop=0, optimize=True, disposal=1)
    (args.site/"LICENSE").write_bytes((ROOT/"LICENSE").read_bytes())
    (args.site/"NOTICE.txt").write_text(
        "Robot Reel / The Butterfly Lab\n\n"
        "Code, generated scene and recorded data: Apache-2.0.\n"
        "Procedural geometry; no third-party visual assets or AI-generated frames.\n"
        "Simulation: Newton 1.6.0 (Apache-2.0) and Warp 1.17.0 (Apache-2.0).\n"
        f'{trace["source"]["world_count"]} isolated {device_label(trace)} worlds; '
        "the browser renders previously recorded poses.\n"
        "Time sculpture maps time to presentation depth. USD parents space worlds along Y.\n"
        "Local source poses remain unchanged. Blender import: set the frame rate to 30 fps.\n"
        "Offline: open index.html. Links to other Robot Reel scenes need the full site.\n"
    )
    with zipfile.ZipFile(args.site/"experiment.zip", "w", zipfile.ZIP_DEFLATED) as archive:
        for name in BUNDLE_FILES:
            archive.write(args.site/name, name)
    files = (*BUNDLE_FILES, "poster.png", "preview.gif", "experiment.zip")
    (args.site/"showcase-manifest.json").write_text(json.dumps({
        "schema": "robot-reel-chaos-showcase-1", "trace_sha256": digest(args.site/"trace.json"),
        "preview_source_samples": samples, "preview_fps": 10,
        "poster_source_sample": measured["peak"]["frame"], "selected_world": measured["peak"]["world"],
        "view": "sculpture", "files": {name: digest(args.site/name) for name in files},
    }, indent=2) + "\n")
    print(json.dumps(verify_showcase(args.site), indent=2))


if __name__ == "__main__":
    main()
