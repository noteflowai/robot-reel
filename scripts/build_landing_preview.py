"""Encode an on-demand homepage video from the verified Butterfly GIF."""
import argparse
from fractions import Fraction
import json
from pathlib import Path
import re
import struct
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from robot_reel.chaos import digest
from scripts.build_chaos_showcase import verify_showcase

VIDEO = "butterfly-preview.mp4"
MANIFEST = "butterfly-preview.json"


def provenance(root):
    site = root/"docs/chaos"
    verify_showcase(site)
    mapping = json.loads((site/"showcase-manifest.json").read_text())
    size = list(struct.unpack("<HH", (site/"preview.gif").read_bytes()[6:10]))
    return {
        "schema": "robot-reel-landing-preview-1",
        "source_gif_sha256": digest(site/"preview.gif"),
        "source_trace_sha256": digest(site/"trace.json"),
        "source_samples": mapping["preview_source_samples"],
        "fps": mapping["preview_fps"],
        "size": size,
        "view": mapping["view"],
        "selected_world": mapping["selected_world"],
        "presentation": "3.33x sampled replay; sculpture depth represents time",
    }


def source_frames(root, metadata):
    from PIL import Image
    with Image.open(root/"docs/chaos/preview.gif") as image:
        if image.n_frames != len(metadata["source_samples"]):
            raise ValueError("GIF frames differ from the recorded sample mapping")
        for i in range(image.n_frames):
            image.seek(i)
            if image.info.get("duration") != 1000/metadata["fps"]:
                raise ValueError("GIF duration differs from the preview clock")
            yield image.convert("RGB")


def verify(root=ROOT, check_media=False):
    root = Path(root)
    output = root/"docs/showcase"
    expected = provenance(root)
    expected["video_sha256"] = digest(output/VIDEO)
    if json.loads((output/MANIFEST).read_text()) != expected:
        raise ValueError("Landing preview differs from its source mapping or files")
    if (output/VIDEO).stat().st_size > 1024 * 1024:
        raise ValueError("Landing preview exceeds its 1 MiB download budget")
    if check_media:
        import imageio_ffmpeg
        from PIL import Image, ImageChops, ImageStat
        # Decode to a temporary stream so verification does not retain all RGB
        # frames in memory. showinfo reports native timestamps before output.
        with tempfile.TemporaryFile() as pixels:
            result = subprocess.run(
                [imageio_ffmpeg.get_ffmpeg_exe(), "-hide_banner", "-nostdin",
                 "-threads", "1", "-i", str(output/VIDEO),
                 "-vf", "format=rgb24,showinfo", "-fps_mode", "passthrough",
                 "-threads", "1", "-f", "rawvideo", "pipe:1"],
                stdout=pixels, stderr=subprocess.PIPE, check=True, timeout=60,
            )
            stamps = re.findall(
                r"\bn:\s*(\d+)\s+pts:\s*\d+\s+pts_time:(\S+).*?"
                r"duration_time:(\S+).*?\bs:(\d+)x(\d+)",
                result.stderr.decode(),
            )
            width, height = expected["size"]
            frame_bytes = width*height*3
            count = len(expected["source_samples"])
            if len(stamps) != count or pixels.tell() != count*frame_bytes:
                raise ValueError("Landing video frame count differs")
            pixels.seek(0)
            for i, original in enumerate(source_frames(root, expected)):
                number, stamp, duration, w, h = stamps[i]
                if (int(number) != i or [int(w), int(h)] != expected["size"]
                        or Fraction(stamp) != Fraction(i, expected["fps"])
                        or Fraction(duration) != Fraction(1, expected["fps"])):
                    raise ValueError("Landing video dimensions or native clock differ")
                frame = Image.frombytes("RGB", (width, height), pixels.read(frame_bytes))
                # H.264 is lossy: check every decoded frame against its mapped
                # GIF source, allowing small YUV/chroma compression differences.
                difference = ImageStat.Stat(ImageChops.difference(original, frame)).mean
                if max(difference) > 4:
                    raise ValueError("Landing video pixels differ from the mapped source")
    return expected


def build(root=ROOT):
    import imageio_ffmpeg
    root = Path(root)
    output = root/"docs/showcase"
    output.mkdir(parents=True, exist_ok=True)
    metadata = provenance(root)
    writer = imageio_ffmpeg.write_frames(
        str(output/VIDEO), tuple(metadata["size"]), fps=metadata["fps"],
        codec="libx264", pix_fmt_out="yuv420p", quality=8, macro_block_size=1,
        ffmpeg_log_level="error", output_params=["-movflags", "+faststart", "-threads", "2"],
    )
    try:
        writer.send(None)
        for frame in source_frames(root, metadata):
            writer.send(frame.tobytes())
    finally:
        writer.close()
    metadata["video_sha256"] = digest(output/VIDEO)
    (output/MANIFEST).write_text(json.dumps(metadata, indent=2)+"\n")
    return verify(root, check_media=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    print(json.dumps(verify(check_media=True) if args.verify else build(), indent=2))
