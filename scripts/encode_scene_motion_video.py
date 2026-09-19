"""Encode every checked Blender frame, then independently decode and compare it."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from robot_reel.scene_motion import checked_file, identity, validate_trace, write_json


def encode(project_root, output):
    import imageio_ffmpeg
    import numpy as np
    from PIL import Image

    root, output = Path(project_root), Path(output)
    project = json.loads((root / "project.json").read_text())
    project_id = identity(root / "project.json")
    trace = json.loads(checked_file(root, "trace.json", project["source_trace"]).read_text())
    counts = validate_trace(trace)
    frames = list(range(counts["frames"]))
    if project["rendered_source_frames"] != frames:
        raise ValueError("encoding requires all recorded frames, in source order")
    for name, expected in project["render_files"].items():
        checked_file(root, name, expected)
    if output.exists():
        raise ValueError("choose a new video output directory")
    output.mkdir(parents=True)
    width, height, fps = trace["camera"]["width"], trace["camera"]["height"], trace["plan"]["sample_hz"]
    movie = output / "blender.mp4"
    writer = imageio_ffmpeg.write_frames(
        str(movie), (width, height), fps=fps, codec="libx264", pix_fmt_in="rgb24",
        pix_fmt_out="yuv420p", macro_block_size=1, quality=8,
        output_params=["-preset", "medium", "-movflags", "+faststart"],
    )
    writer.send(None)
    try:
        for frame in frames:
            with Image.open(root / f"renders/frame_{frame+1:04}.png") as image:
                if image.size != (width, height):
                    raise ValueError("render dimensions differ")
                writer.send(np.asarray(image.convert("RGB")))
    finally:
        writer.close()
    reader = imageio_ffmpeg.read_frames(str(movie), pix_fmt="rgb24")
    metadata = next(reader)
    if tuple(metadata["size"]) != (width, height) or metadata["fps"] != fps:
        raise ValueError("decoded video size or frame rate differs")
    minimum, maximum_mae, decoded = math.inf, 0., 0
    for decoded, pixels in enumerate(reader, 1):
        if decoded > len(frames):
            raise ValueError("video contains extra frames")
        with Image.open(root / f"renders/frame_{decoded:04}.png") as image:
            source = np.asarray(image.convert("RGB"), dtype=np.float64)
        actual = np.frombuffer(pixels, dtype=np.uint8).reshape(height, width, 3).astype(np.float64)
        difference = actual - source
        mse = float(np.mean(difference*difference))
        psnr = 100. if mse == 0 else 10*math.log10(255**2/mse)
        minimum, maximum_mae = min(minimum, psnr), max(maximum_mae, float(np.mean(np.abs(difference))))
    if decoded != len(frames) or minimum < 30:
        raise ValueError("video frame coverage or image agreement differs")
    # Check presentation timestamps, independently of the encoder API.
    result = subprocess.run(
        [imageio_ffmpeg.get_ffmpeg_exe(), "-i", str(movie), "-vf", "showinfo", "-f", "null", "-"],
        capture_output=True, text=True, check=True,
    )
    pts = [(int(n), float(t)) for n, t in re.findall(r"\bn:\s*(\d+).*?\bpts_time:([-\d.]+)", result.stderr)]
    if len(pts) != len(frames) or any(n != i or abs(t-i/fps) > .00001 for i, (n, t) in enumerate(pts)):
        raise ValueError("video timestamps differ from the source-frame mapping")
    if identity(root / "project.json") != project_id:
        raise ValueError("project changed during encoding")
    for name, expected in project["render_files"].items():
        checked_file(root, name, expected)
    record = {
        "schema": "robot-reel.scene-motion-video.v1", "source_project": project_id,
        "source_trace": project["source_trace"], "video": identity(movie),
        "codec": "libx264", "quality": 8, "crf": 10, "pixel_format": "yuv420p",
        "width": width, "height": height, "fps": fps, "decoded_frames": decoded,
        "source_frames": frames, "checked_presentation_timestamps": len(pts),
        "max_timestamp_error_s": max(abs(t-i/fps) for i, (_, t) in enumerate(pts)),
        "minimum_psnr_db": minimum, "maximum_mean_absolute_pixel_error": maximum_mae,
        "mapping": "video frame i corresponds to source frame i and Blender frame i+1; use trace sim_time_s for physics time",
        "ffmpeg": imageio_ffmpeg.get_ffmpeg_version(),
    }
    write_json(output / "video-check.json", record)
    return record


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(encode(args.project, args.output), indent=2))
