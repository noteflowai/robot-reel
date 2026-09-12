"""Build the GitHub showcase from published recordings, without new simulation."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from robot_reel.compare import digest
from robot_reel.newton import verify as verify_newton
from robot_reel.vla import verify as verify_vla


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT/"docs/showcase")
    parser.add_argument("--fonts", type=Path, default=Path("/usr/share/fonts/truetype/dejavu"))
    args = parser.parse_args()
    import imageio_ffmpeg
    from PIL import Image, ImageDraw, ImageFont, ImageOps

    verify_vla(ROOT/"docs/vla")
    verify_newton(ROOT/"docs/newton")
    media = json.loads((ROOT/"docs/director/media-manifest.json").read_text())
    for name, expected in media["sha256"].items():
        if Path(name).name != name or digest(ROOT/"docs/director"/name) != expected:
            raise ValueError(f"Director source changed: {name}")
    vla = json.loads((ROOT/"docs/vla/trace.json").read_text())
    film = json.loads((ROOT/"docs/director/film.json").read_text())
    inputs = [
        "docs/vla/trace.json", "docs/vla/main.mp4", "docs/vla/wrist.mp4",
        "docs/director/reel.mp4", "docs/director/film.json",
        "docs/newton/preview.gif", "docs/newton/trace.json",
    ]
    args.output.mkdir(parents=True, exist_ok=True)
    output_names = ("hero.gif", "hero.png", "vla.png", "director.png", "newton.png")
    colors = ("#c1b1ff", "#ffca85", "#79dfc3")
    fonts = {
        size: ImageFont.truetype(str(args.fonts/filename), size)
        for size, filename in (
            (13, "DejaVuSansMono.ttf"), (16, "DejaVuSans.ttf"),
            (18, "DejaVuSans-Bold.ttf"), (24, "DejaVuSans-Bold.ttf"),
            (40, "DejaVuSans-Bold.ttf"), (58, "DejaVuSans-Bold.ttf"),
        )
    }

    def video_frames(name, count, size):
        reader = imageio_ffmpeg.read_frames(str(ROOT/name))
        metadata = next(reader)
        frames = []
        try:
            for raw in reader:
                frame = Image.frombytes("RGB", metadata["size"], raw)
                if name.startswith("docs/director/"):
                    frame = frame.crop((0, 48, 960, 458))
                frames.append(ImageOps.contain(frame, size, Image.Resampling.LANCZOS))
        finally:
            reader.close()
        if len(frames) != count:
            raise ValueError(f"Unexpected source video length: {name}")
        return frames

    main_camera = video_frames("docs/vla/main.mp4", len(vla["frames"]), (360, 360))
    wrist_camera = video_frames("docs/vla/wrist.mp4", len(vla["frames"]), (360, 360))
    directed = video_frames("docs/director/reel.mp4", film["frame_count"], (768, 360))
    newton = []
    with Image.open(ROOT/"docs/newton/preview.gif") as image:
        # Crop the recorded browser canvas, excluding its surrounding inspector.
        if image.size != (780, 529) or image.n_frames != 61:
            raise ValueError("Newton preview layout changed; update the canvas crop")
        for index in range(image.n_frames):
            image.seek(index)
            newton.append(image.convert("RGB").crop((0, 34, 594, 429)))

    def camera_pair(index):
        image = Image.new("RGB", (744, 360), "#111c27")
        image.paste(main_camera[index], (0, 0))
        image.paste(wrist_camera[index], (384, 0))
        return image

    def fit(image, width, height):
        return ImageOps.pad(image, (width, height), color="#111c27", method=Image.Resampling.LANCZOS)

    base = Image.new("RGB", (1280, 640), "#09121b")
    draw = ImageDraw.Draw(base)
    for y in range(0, 640, 32):
        draw.line((0, y, 1280, y), fill="#10202b")
    for x in range(0, 1280, 32):
        draw.line((x, 0, x, 640), fill="#10202b")
    draw.rectangle((0, 0, 1280, 236), fill="#09121b")
    draw.line((40, 76, 1240, 76), fill="#30414d")
    draw.rounded_rectangle((40, 25, 77, 60), radius=9, fill="#79dfc3")
    draw.polygon(((53, 33), (53, 52), (67, 42)), fill="#0b2423")
    draw.text((91, 27), "ROBOT REEL", font=fonts[24], fill="#f1f5ef")
    draw.text((899, 36), "PHYSICAL AI / OPEN SOURCE", font=fonts[16], fill="#a7bac6")
    draw.text((40, 94), "Physical AI.", font=fonts[58], fill="#f1f5ef")
    draw.text((40, 162), "In motion. On record.", font=fonts[40], fill="#79dfc3")
    draw.text((810, 128), "Real policies. Editable scenes.", font=fonts[18], fill="#d3e0e5")
    draw.text((810, 160), "One frame away from the evidence.", font=fonts[16], fill="#a7bac6")
    headings = ("01  /  SMOLVLA", "02  /  AGENT DIRECTOR", "03  /  NEWTON → USD")
    subtitles = ("Language → applied actions", "MCP → Blender storyboard", "Physics → editable 3D")
    for side in range(3):
        x = 40+408*side
        draw.rounded_rectangle((x, 240, x+384, 546), radius=14, fill="#121e29", outline="#344553", width=2)
        draw.line((x+18, 241, x+366, 241), fill=colors[side], width=3)
        draw.text((x+18, 260), headings[side], font=fonts[18], fill=colors[side])
        draw.text((x+18, 290), subtitles[side], font=fonts[16], fill="#d0dce3")
    draw.rectangle((0, 566, 1280, 640), fill="#09121b")
    draw.text((40, 582), "PLAY  →  INSPECT  →  REUSE", font=fonts[18], fill="#e8efe9")
    draw.text((40, 612), "Independent recorded demos · preview montage · no new physics", font=fonts[13], fill="#98aeba")

    preview_frames = []
    samples = []
    for index in range(70):
        vi = min(index*2, len(vla["frames"])-1)
        di = min(index*3, len(directed)-1)
        ni = min(index, len(newton)-1)
        images = (camera_pair(vi), directed[di], newton[ni])
        image = base.copy()
        for side, source in enumerate(images):
            image.paste(fit(source, 360, 180), (52+408*side, 322))
        draw = ImageDraw.Draw(image)
        stamps = (
            f'OBS {vi:02d}  /  {vla["frames"][vi]["episode_time"]:.2f}s',
            f'FILM {di:03d}  /  SOURCE {film["frames"][di]["source_frame"]:03d}',
            f'SAMPLE {ni*3:03d}  /  {ni/10:.2f}s',
        )
        for side, stamp in enumerate(stamps):
            draw.text((58+408*side, 519), stamp, font=fonts[13], fill=colors[side])
        draw.line((872, 594, 1232, 594), fill="#324957", width=4)
        draw.line((872, 594, 872+360*index/69, 594), fill="#79dfc3", width=4)
        draw.ellipse((868+360*index/69, 590, 876+360*index/69, 598), fill="#79dfc3")
        preview_frames.append(image.resize((960, 480), Image.Resampling.LANCZOS))
        samples.append({"preview_frame": index, "vla_observation": vi, "director_frame": di, "newton_sample": ni*3})
        if index == 40:
            image.save(args.output/"hero.png", optimize=True)
            for name, source in zip(("vla", "director", "newton"), images):
                fit(source, 768, 432).save(args.output/f"{name}.png", optimize=True)
    palette = preview_frames[40].quantize(colors=128)
    indexed = [frame.quantize(palette=palette, dither=Image.Dither.NONE) for frame in preview_frames]
    indexed[0].save(
        args.output/"hero.gif", save_all=True, append_images=indexed[1:],
        duration=100, loop=0, optimize=True, disposal=1,
    )
    (args.output/"manifest.json").write_text(json.dumps({
        "purpose": "README preview montage; independent recordings, completed panels hold their last sample.",
        "fps": 10, "frames": len(preview_frames), "samples": samples,
        "inputs": {name: digest(ROOT/name) for name in inputs},
        "sha256": {name: digest(args.output/name) for name in output_names},
    }, indent=2)+"\n")
    print(f"Built 70 preview frames from published recordings: {args.output}")
    print(f"Animated cover: {(args.output/'hero.gif').stat().st_size/1024/1024:.2f} MiB")


if __name__ == "__main__":
    main()
