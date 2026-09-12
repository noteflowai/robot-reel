"""Package two recorded policy-input videos and a validated action trace."""
import argparse
import json
from pathlib import Path
import shutil
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from robot_reel.vla import REQUIRED, check_media, seal, validate_trace


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--recording", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--font", type=Path, default=Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"))
    args = parser.parse_args()
    import imageio_ffmpeg
    from PIL import Image, ImageDraw, ImageFont

    trace = json.loads((args.recording/"trace.json").read_text())
    validate_trace(trace)
    if args.output.exists() and any(args.output.iterdir()):
        raise ValueError("Choose an empty site output directory")
    args.output.mkdir(parents=True, exist_ok=True)
    for name in REQUIRED-{"index.html", "NOTICE.txt", "LICENSE"}:
        shutil.copyfile(args.recording/name, args.output/name)
    shutil.copyfile(ROOT/"licenses/VLA-MEDIA-NOTICE.txt", args.output/"NOTICE.txt")
    shutil.copyfile(ROOT/"LICENSE", args.output/"LICENSE")
    seal(args.output)
    result = check_media(args.output)
    readers = [imageio_ffmpeg.read_frames(str(args.output/f"{name}.mp4")) for name in ("main", "wrist")]
    metadata = [next(reader) for reader in readers]
    if any(tuple(meta["size"]) != (256, 256) for meta in metadata):
        raise ValueError("Expected two 256px policy input views")
    font = ImageFont.truetype(str(args.font), 22)
    small = ImageFont.truetype(str(args.font), 14)
    previews = []
    try:
        for index, pixels in enumerate(zip(*readers)):
            if index % 2:
                continue
            image = Image.new("RGB", (768, 500), "#101923")
            for side, raw in enumerate(pixels):
                camera = Image.frombytes("RGB", (256, 256), raw).resize((368, 368))
                image.paste(camera, (12+side*376, 64))
            draw = ImageDraw.Draw(image)
            draw.text((20, 15), "SmolVLA  /  WORDS INTO MOTION", font=font, fill="#c1b1ff")
            draw.text((20, 442), f'OBSERVATION {index:03d}  /  EPISODE {index/20:.2f}s  /  SCENE + WRIST', font=small, fill="#cfdbdf")
            draw.text((20, 467), "One real CPU policy rollout in LIBERO. Inspect every applied action.", font=small, fill="#7be2c5")
            previews.append(image)
    finally:
        for reader in readers:
            reader.close()
    previews[len(previews)//2].save(args.output/"preview.png")
    previews = [image.resize((576, 375)).quantize(colors=96, dither=Image.Dither.NONE) for image in previews]
    previews[0].save(args.output/"preview.gif", save_all=True, append_images=previews[1:], duration=100, loop=0)
    with zipfile.ZipFile(args.output/"episode.zip", "w", zipfile.ZIP_DEFLATED) as archive:
        for name in sorted(REQUIRED|{"manifest.json"}):
            archive.write(args.output/name, name)
    print(json.dumps({**result, "output": str(args.output)}, indent=2))


if __name__ == "__main__":
    main()
