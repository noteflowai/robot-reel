"""Create source-mapped cloth preview frames using the actual browser renderer."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from robot_reel.cloth import digest, load
from scripts.build_cloth_site import verify_site


def verify_showcase(site):
    site = Path(site)
    result = verify_site(site)
    trace, _, _ = load(site)
    manifest = json.loads((site/"showcase-manifest.json").read_text())
    if (manifest.get("schema") != "robot-reel-cloth-showcase-1"
            or manifest.get("positions_sha256") != digest(site/"positions.f32")
            or manifest.get("trace_sha256") != digest(site/"trace.json")
            or manifest.get("preview_source_samples") != list(range(0, trace["frame_count"], 3))
            or manifest.get("preview_fps") != 10 or manifest.get("view") != "separate"
            or manifest.get("poster_source_sample") != result["peak"]["frame"]
            or manifest.get("selected_case") != result["peak"]["case"]
            or set(manifest.get("files", {})) != {"poster.png", "preview.gif", "index.html"}):
        raise ValueError("Cloth showcase mapping differs from source")
    for name, expected in manifest["files"].items():
        if digest(site/name) != expected:
            raise ValueError(f"Changed cloth showcase: {name}")
    return result


def build(site):
    from PIL import Image, ImageDraw, ImageFont

    site = Path(site)
    result = verify_site(site)
    trace, _, _ = load(site)
    samples = list(range(0, trace["frame_count"], 3))
    with tempfile.TemporaryDirectory() as temporary:
        output = Path(temporary)
        subprocess.run(["node", str(ROOT/"scripts/render_cloth_preview.cjs"), str(site), str(output)], check=True)
        if json.loads((output/"samples.json").read_text()) != samples:
            raise ValueError("Cloth preview samples differ from requested mapping")
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 26)
        mono = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf", 12)

        def compose(path, sample):
            source = Image.open(path).convert("RGB")
            source.thumbnail((900, 480), Image.Resampling.LANCZOS)
            image = Image.new("RGB", (900, source.height+120), "#09121b")
            draw = ImageDraw.Draw(image)
            draw.text((22, 12), "SAME SHEET. THREE WAYS TO FALL.", font=font, fill="#edf4ef")
            draw.text((22, 52), "CLOTH LAB / NEWTON VBD / NVIDIA L40S / THREE INDEPENDENT RUNS", font=mono, fill="#79dfc3")
            image.paste(source, ((900-source.width)//2, 80))
            draw.text((22, image.height-26), f"SOURCE SAMPLE {sample:03d} / {sample/30:.3f} s / BENDING k = 0.01, 1, 100", font=mono, fill="#c1b1ff")
            return image

        compose(output/"poster.png", result["peak"]["frame"]).save(site/"poster.png", optimize=True)
        images = []
        for i, sample in enumerate(samples):
            image = compose(output/f"{i:03d}.png", sample)
            image.thumbnail((720, 480), Image.Resampling.LANCZOS)
            images.append(image.quantize(colors=128, dither=Image.Dither.NONE))
        images[0].save(site/"preview.gif", save_all=True, append_images=images[1:], duration=100,
                       loop=0, optimize=False, disposal=2)
        with Image.open(site/"preview.gif") as image:
            if image.n_frames != len(samples) or image.info["duration"] != 100:
                raise ValueError("Encoded cloth preview lost its source clock")
    (site/"showcase-manifest.json").write_text(json.dumps({
        "schema": "robot-reel-cloth-showcase-1", "trace_sha256": digest(site/"trace.json"),
        "positions_sha256": digest(site/"positions.f32"), "preview_source_samples": samples,
        "preview_fps": 10, "poster_source_sample": result["peak"]["frame"],
        "selected_case": result["peak"]["case"], "view": "separate",
        "files": {name: digest(site/name) for name in ("poster.png", "preview.gif", "index.html")},
    }, indent=2)+"\n")
    return verify_showcase(site)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--site", type=Path, default=ROOT/"docs/cloth")
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    print(json.dumps((verify_showcase if args.verify else build)(args.site), indent=2))
