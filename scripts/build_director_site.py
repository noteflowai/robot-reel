"""Package an actually rendered, checked Blender film as a portable replay."""
import argparse
import json
from pathlib import Path
import shutil
import sys
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from robot_reel.compare import digest
from robot_reel.director import EXPORT_FILES, export_viewer, verify_director


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--font", type=Path, default=Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"))
    args = parser.parse_args()
    import imageio_ffmpeg
    from PIL import Image, ImageDraw, ImageFont

    bundle, output = args.bundle, args.output
    verified = verify_director(bundle)
    plan = json.loads((bundle/"storyboard.json").read_text())
    film = json.loads((bundle/"film.json").read_text())
    source = json.loads((bundle/"source/scene.json").read_text())
    report = json.loads((bundle/"animation-check.json").read_text())
    if (
        report["blend_sha256"] != digest(bundle/"reel.blend")
        or report["film_sha256"] != digest(bundle/"film.json")
        or report["source_sha256"] != digest(bundle/"source/scene.json")
        or report["output_frames"] != verified["frames"]
        or report["source_frames"] != verified["source_frames"]
        or report["checked_vehicle_samples"] != verified["frames"]*len(source["runs"])
        or report["camera_cuts_checked"] != len(plan["shots"])
        or not report["constant_hold_checked"] or report["maximum_position_error_m"] > 1e-5
    ):
        raise ValueError("The saved Blender project must pass the native animation check first")
    images = [bundle/"frames"/f"frame-{i+1:04d}.png" for i in range(film["frame_count"])]
    if not all(path.is_file() for path in images):
        raise ValueError("Render all film frames before building the site")
    if output.exists() and any(output.iterdir()):
        raise ValueError("Choose an empty site output directory")
    output.mkdir(parents=True, exist_ok=True)
    font = ImageFont.truetype(str(args.font), 21)
    small = ImageFont.truetype(str(args.font), 13)
    with Image.open(images[0]) as first:
        width, height = first.size
    writer = imageio_ffmpeg.write_frames(
        str(output/"reel.mp4"), (width, height), fps=film["fps"], codec="libx264",
        pix_fmt_out="yuv420p", quality=8, macro_block_size=1, ffmpeg_log_level="error",
        output_params=["-movflags", "+faststart"],
    )
    writer.send(None)
    previews = []
    poster_index = next((row["frame"] for row in film["frames"] if row["shot"] == 2), 0)
    try:
        for row, path in zip(film["frames"], images):
            with Image.open(path) as raw:
                image = raw.convert("RGB")
            if image.size != (width, height):
                raise ValueError("Rendered frame dimensions differ")
            draw = ImageDraw.Draw(image)
            draw.rectangle((0, 0, width, 48), fill="#101923")
            draw.text((22, 14), "ROBOT REEL  /  AGENT DIRECTOR", font=small, fill="#ffca85")
            draw.text((width-250, 14), f'SHOT {row["shot"]+1}   /   {plan["shots"][row["shot"]]["rate"]:g}x', font=small, fill="#dbe6eb")
            draw.rectangle((0, height-82, width, height), fill="#101923")
            caption = plan["shots"][row["shot"]]["caption"]
            fitted = font
            while draw.textlength(caption, font=fitted) > width-44 and fitted.size > 10:
                fitted = ImageFont.truetype(str(args.font), fitted.size-1)
            draw.text((22, height-69), caption, font=fitted, fill="#f4f4ee")
            draw.text((22, height-30), f'SOURCE {row["source_frame"]:03d}  /  SIM {row["sim_time"]:.3f}s  /  RECORDED MUJOCO MOTION', font=small, fill="#a8bac7")
            writer.send(image.tobytes())
            if row["frame"] == poster_index:
                image.save(output/"poster.png")
            if row["frame"] % 3 == 0:
                previews.append(image.resize((640, round(height*640/width))).quantize(colors=96, dither=Image.Dither.NONE))
    finally:
        writer.close()
    count, duration = imageio_ffmpeg.count_frames_and_secs(str(output/"reel.mp4"))
    if count != film["frame_count"] or abs(duration-count/film["fps"]) > .01:
        raise ValueError("Encoded film length differs from the checked frame mapping")
    previews[0].save(output/"preview.gif", save_all=True, append_images=previews[1:], duration=100, loop=0)
    for name in ("storyboard.json", "film.json", "animation-check.json"):
        shutil.copyfile(bundle/name, output/name)
    export_viewer(bundle, output/"index.html")
    source_manifest = json.loads((bundle/"source/blender-manifest.json").read_text())
    files = [*EXPORT_FILES, "director-manifest.json", "reel.blend", "animation-check.json"]
    files += ["source/"+name for name in [*source_manifest["sha256"], "blender-manifest.json"]]
    with zipfile.ZipFile(output/"project.zip", "w", zipfile.ZIP_DEFLATED) as archive:
        archive.write(Path(__file__).resolve().parents[1]/"LICENSE", "LICENSE")
        for name in files:
            archive.write(bundle/name, name)
    (output/"media-manifest.json").write_text(json.dumps({
        **verified, "schema": "robot-reel-director-media-1", "width": width, "height": height,
        "sha256": {path.name: digest(path) for path in sorted(output.iterdir())},
    }, indent=2)+"\n")
    print(json.dumps({**verified, "output": str(output)}, indent=2))


if __name__ == "__main__":
    main()
