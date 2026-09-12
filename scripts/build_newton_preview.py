"""Encode the browser's sampled PNG sequence as the Newton demo preview."""
import argparse
from pathlib import Path
import shutil


def main():
    from PIL import Image

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frames", type=Path, default=Path("artifacts/newton-preview"))
    parser.add_argument("--destination", type=Path, default=Path("docs/newton"))
    args = parser.parse_args()
    frames = []
    for path in sorted(args.frames.glob("[0-9][0-9][0-9][0-9].png")):
        with Image.open(path) as source:
            frame = source.convert("RGB")
            frame.thumbnail((780, 780), Image.Resampling.LANCZOS)
            frames.append(frame)
    if not frames:
        raise ValueError("Render the browser PNG sequence first")
    palette = frames[0].quantize(colors=128)
    indexed = [frame.quantize(palette=palette, dither=Image.Dither.NONE) for frame in frames]
    args.destination.mkdir(parents=True, exist_ok=True)
    indexed[0].save(
        args.destination/"preview.gif", save_all=True, append_images=indexed[1:],
        duration=100, loop=0, optimize=True, disposal=1,
    )
    shutil.copyfile(args.frames/"preview.png", args.destination/"preview.png")
    print(f"Encoded {len(frames)} preview samples at 10 Hz")


if __name__ == "__main__":
    main()
