"""Encode the Factory Twin flythrough and record its provenance, or verify a published film.

    python3 scripts/build_factory_twin_film.py --frames artifacts/factory-twin/film \
        --blend artifacts/factory-twin/factory-twin-closed.blend --output docs/factory-twin
    python3 scripts/build_factory_twin_film.py --verify docs/factory-twin

`film.json` pins the MP4, the Blender project it was rendered from (whose hash
is in `blender-check.json`), the lab payload, the camera keys and the mapping
from every film frame to exactly one recorded sample. Verification needs only
the standard library.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

SCHEMA = "robot-reel-factory-twin-film-1"
FPS = 24


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def sample_at(time_map, seconds):
    for a, b in zip(time_map, time_map[1:]):
        if seconds <= b["seconds"]:
            return round(a["sample"] + (b["sample"] - a["sample"]) * (seconds - a["seconds"])
                         / (b["seconds"] - a["seconds"]))
    return time_map[-1]["sample"]


def verify(site):
    site = Path(site)
    film = json.loads((site / "film.json").read_text())
    receipt = json.loads((site / "blender-check.json").read_text())
    lab = json.loads((site / "lab.json").read_text())
    samples = lab["config"]["samples"]
    if film.get("schema") != SCHEMA or film["fps"] != FPS:
        raise ValueError("Unexpected film record")
    if film["inputs"]["lab.json"] != digest(site / "lab.json"):
        raise ValueError("Film was rendered from a different lab.json")
    if film["inputs"]["blend"] != receipt["modes"][film["mode"]]["inputs"]["blend"]:
        raise ValueError("Film project is not the checked Blender project")
    mp4 = site / "film.mp4"
    if {"sha256": digest(mp4), "bytes": mp4.stat().st_size} != film["mp4"]:
        raise ValueError("film.mp4 differs from its record")
    times = film["time_map"]
    if (times[0] != {"seconds": 0.0, "sample": 0} or times[-1]["sample"] != samples - 1
            or any(b["seconds"] <= a["seconds"] or b["sample"] < a["sample"] for a, b in zip(times, times[1:]))):
        raise ValueError("Time map must run monotonically over the whole shift")
    rows = film["rows"]
    if [r["film_frame"] for r in rows] != list(range(film["frames"])) or film["frames"] != len(rows):
        raise ValueError("Film frame list is incomplete")
    for r in rows:
        if r["sample"] != sample_at(times, r["film_frame"] / FPS) or not 0 <= r["sample"] < samples:
            raise ValueError(f"Film frame {r['film_frame']} does not follow the time map")
    return {"verified": True, "frames": film["frames"], "seconds": round((film["frames"] - 1) / FPS, 3),
            "samples_shown": len({r["sample"] for r in rows}), "mp4_bytes": film["mp4"]["bytes"]}


def build(frames, blend, output, crf, width):
    plan = json.loads((frames / "plan.json").read_text())
    missing = [r["film_frame"] for r in plan["rows"] if not (frames / f"film-{r['film_frame']:04d}.png").exists()]
    if missing:
        raise ValueError(f"{len(missing)} frames are not rendered yet (first: {missing[0]})")
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise ValueError("ffmpeg is required to encode the film")
    mp4 = output / "film.mp4"
    subprocess.run([ffmpeg, "-y", "-loglevel", "error", "-framerate", str(FPS), "-i", str(frames / "film-%04d.png"),
                    "-vf", f"scale={width}:-2:flags=lanczos", "-c:v", "libx264", "-preset", "veryslow",
                    "-crf", str(crf), "-tune", "animation", "-pix_fmt", "yuv420p",
                    "-movflags", "+faststart", "-map_metadata", "-1", "-an", str(mp4)], check=True)
    record = {
        "schema": SCHEMA, "fps": FPS, "frames": plan["frames"], "mode": "closed",
        "resolution": plan["resolution"], "renderer": {"engine": "Cycles", "device": plan["device"],
                                                       "samples_per_pixel": plan["samples_per_pixel"],
                                                       "blender_version": plan["blender_version"]},
        "encoder": {"codec": "H.264 (libx264)", "crf": crf, "pixel_format": "yuv420p", "width": width},
        "note": "The camera path is cinematography, not recorded data. Frame k+1 of the project holds "
                "sample k; each film frame shows exactly the sample listed in rows.",
        "inputs": {"blend": digest(blend), "lab.json": digest(output / "lab.json")},
        "mp4": {"sha256": digest(mp4), "bytes": mp4.stat().st_size},
        "keys": plan["keys"], "time_map": plan["time_map"],
        "rows": [{"film_frame": r["film_frame"], "sample": r["sample"], "camera": r["camera"],
                  "target": r["target"], "lens_mm": r["lens_mm"]} for r in plan["rows"]],
    }
    (output / "film.json").write_text(json.dumps(record, separators=(",", ":")) + "\n")
    return verify(output)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frames", type=Path)
    parser.add_argument("--blend", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--crf", type=int, default=26)
    parser.add_argument("--width", type=int, default=1600, help="Encoded width; frames are rendered at 1080p")
    parser.add_argument("--verify", type=Path)
    args = parser.parse_args()
    try:
        if args.verify:
            result = verify(args.verify)
        elif args.frames and args.blend and args.output:
            result = build(args.frames, args.blend, args.output, args.crf, args.width)
        else:
            parser.error("use --frames/--blend/--output, or --verify")
    except (ValueError, OSError, KeyError, subprocess.CalledProcessError) as exc:
        print(json.dumps({"verified": False, "error": str(exc)}))
        return 2
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
