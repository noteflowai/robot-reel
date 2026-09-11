"""Rebuild published replay pages from verified capture directories."""
import argparse
import shutil
from pathlib import Path

from robot_reel.viewer import export_viewer


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--studio", type=Path, required=True)
    parser.add_argument("--microduck", type=Path, required=True)
    parser.add_argument("--braking", type=Path, required=True)
    parser.add_argument("--destination", type=Path, default=Path("docs"))
    args = parser.parse_args()
    for pack in ("studio", "microduck", "braking"):
        source = getattr(args, pack)
        root = args.destination/pack
        media = args.destination/"media" if pack == "studio" else root/"media"
        media.mkdir(parents=True, exist_ok=True)
        prefix = "../media/" if pack == "studio" else "media/"
        export_viewer(source, root/"index.html", prefix)
        for name in ("robot-reel.mp4", "robot-reel-vertical.mp4", "poster.png"):
            shutil.copyfile(source/name, media/name)
        if pack == "microduck":
            shutil.copyfile(source/"MICRODUCK-MEDIA-NOTICE.txt", media/"MICRODUCK-MEDIA-NOTICE.txt")
    export_viewer(args.microduck, args.destination/"index.html", "microduck/media/")


if __name__ == "__main__":
    main()
