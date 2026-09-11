"""Editorial overlays on recorded simulator frames, plus a portrait export."""
import json
import math
from functools import lru_cache
from pathlib import Path

import imageio_ffmpeg
import numpy as np
from PIL import Image, ImageDraw, ImageFont

BG = "#080e1b"
MUTED = "#8699b5"
WHITE = "#edf5ff"
CYAN = "#57edcf"
BLUE = "#80aaff"


@lru_cache(maxsize=32)
def font(size, bold=False):
    candidates = [
        Path("/usr/share/fonts/truetype/dejavu") / ("DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"),
        Path("/System/Library/Fonts/Supplemental/Arial.ttf"),
    ]
    for path in candidates:
        if path.exists():
            return ImageFont.truetype(str(path), size)
    return ImageFont.load_default(size=size)


def text(draw, xy, value, size=20, fill=WHITE, bold=False):
    draw.text(xy, value, font=font(size, bold), fill=fill)


def wrap(draw, value, xy, size, width, fill=WHITE, bold=False):
    words, line, y = value.split(), "", xy[1]
    for word in words:
        trial = (line + " " + word).strip()
        if draw.textlength(trial, font=font(size, bold)) > width and line:
            text(draw, (xy[0], y), line, size, fill, bold)
            y += size + 9
            line = word
        else:
            line = trial
    text(draw, (xy[0], y), line, size, fill, bold)


def card(title, subtitle, index, total, outro=False):
    im = Image.new("RGB", (1280, 720), BG)
    d = ImageDraw.Draw(im)
    for x in range(0, 1280, 48):
        d.line((x, 0, x, 720), fill="#111d30")
    for y in range(0, 720, 48):
        d.line((0, y, 1280, y), fill="#111d30")
    # A code-native orbital motif, not a generated robot image.
    for radius in [120, 175, 235]:
        d.ellipse((1010-radius, 350-radius, 1010+radius, 350+radius), outline="#24425b", width=2)
    angle = index / 20
    x, y = 1010+175*math.cos(angle), 350+175*math.sin(angle)
    d.ellipse((x-8, y-8, x+8, y+8), fill=CYAN)
    text(d, (66, 65), "ROBOT REEL  /  001", 20, CYAN, True)
    for j, line in enumerate(title.split("\n")):
        text(d, (62, 195+j*84), line, 68, WHITE, True)
    text(d, (68, 485), subtitle, 23, MUTED)
    text(d, (68, 606), "PROMPT  >  MOTION  >  EVIDENCE  >  FILM" if not outro else
         "Recorded simulation / Robot Reel", 19, CYAN)
    d.rectangle((0, 714, int(1280*index/max(total, 1)), 720), fill=CYAN)
    return im


def compose(raw, trace, frame, index, total):
    im = Image.new("RGB", (1280, 720), BG)
    # Preserve the camera aspect ratio; the robot remains visible in both exports.
    view = Image.fromarray(raw).resize((768, 720), Image.Resampling.LANCZOS)
    im.paste(view, (512, 0))
    d = ImageDraw.Draw(im)
    d.rectangle((0, 0, 485, 720), fill=BG)
    text(d, (38, 30), "ROBOT REEL", 22, WHITE, True)
    text(d, (38, 69), "LANGUAGE BECOMES MOTION", 13, MUTED)
    is_arm = trace["robot"] == "so100"
    custom = "display_name" in trace
    driving = trace.get("kind") == "braking"
    text(d, (38, 125), trace.get("eyebrow", "01 / THE ARM" if is_arm else "02 / THE HUMANOID"), 15, CYAN, True)
    text(d, (36, 156), trace.get("display_name", "SO-100" if is_arm else "UNITREE G1"), 36 if custom else 44, WHITE, True)
    wrap(d, frame["label"], (38, 225), 28, 405, WHITE, True)
    source = "SCRIPTED CONTROLLER" if driving else ("OFFICIAL ONNX POLICY" if frame["source"] == "policy" else ("AGENT TOOL CALL" if frame["source"] == "agent" else "SCRIPTED DEMO"))
    text(d, (38, 324), source, 14, CYAN, True)
    text(d, (38, 351), trace.get("description", "Position actuators / physics steps" if is_arm else "Kinematic poses / fixed root"), 17, MUTED)
    text(d, (38, 389), "MEASURED TELEMETRY" if driving else "MEASURED JOINT POSITION", 12, MUTED)
    names = trace.get("display_joints") or (["Rotation", "Pitch", "Wrist_Roll"] if is_arm else [
        "right_shoulder_pitch_joint", "right_elbow_joint", "waist_yaw_joint"])
    for row, name in enumerate(names):
        j = trace["joints"].index(name)
        value = frame["qpos"][j]
        lo, hi = trace["limits"][j]
        y = 419 + row*55
        display = name.replace("_joint", "").replace("right_", "").replace("_", " ")
        text(d, (38, y), display, 15, WHITE)
        text(d, (340, y), f"{value:+.2f}", 16, CYAN)
        d.rounded_rectangle((38, y+27, 427, y+31), radius=2, fill="#203047")
        d.rounded_rectangle((38, y+27, 39+int(388*np.clip((value-lo)/(hi-lo), 0, 1)), y+31),
                            radius=2, fill=CYAN)
    text(d, (38, 612), "SIMULATION / 30 FPS", 14, MUTED)
    text(d, (38, 641), trace.get("disclaimer", "Inference pauses omitted" if is_arm else "No walking or balance policy"), 13, MUTED)
    d.rounded_rectangle((1010, 26, 1252, 67), radius=20, fill=BG)
    text(d, (1030, 36), "RECORDED SIMULATION", 14, CYAN, True)
    d.rectangle((0, 714, int(1280*index/max(total, 1)), 720), fill=CYAN)
    return im


def portrait(landscape, phase):
    im = Image.new("RGB", (720, 1280), BG)
    d = ImageDraw.Draw(im)
    text(d, (40, 66), "ROBOT REEL", 25, CYAN, True)
    text(d, (36, 135), "Words in.", 65, WHITE, True)
    text(d, (36, 213), "Motion out.", 65, WHITE, True)
    # Full landscape frame is retained, so provenance labels are never cropped.
    im.paste(landscape.resize((720, 405), Image.Resampling.LANCZOS), (0, 360))
    text(d, (40, 815), phase, 27, WHITE, True)
    text(d, (40, 877), "Real simulator frames.", 25, MUTED)
    text(d, (40, 919), "Inspectable motion traces.", 25, MUTED)
    text(d, (40, 961), "One reproducible command.", 25, MUTED)
    d.line((40, 1090, 680, 1090), fill="#284255", width=2)
    text(d, (40, 1131), "STRANDS ROBOTS + MuJoCo", 20, CYAN)
    text(d, (40, 1171), "Simulation demo / no real hardware", 18, MUTED)
    return im


def render(output: Path, names=("so100", "unitree_g1")):
    traces = [json.loads((output / f"{name}-trace.json").read_text())
              for name in names]
    total = 60+sum(len(t["frames"]) for t in traces)+90
    writers = []
    try:
        for filename, size in [("robot-reel.mp4", (1280, 720)), ("robot-reel-vertical.mp4", (720, 1280))]:
            w = imageio_ffmpeg.write_frames(str(output / filename), size, fps=30, codec="libx264",
                    pix_fmt_out="yuv420p", quality=8, macro_block_size=2,
                    output_params=["-movflags", "+faststart"], ffmpeg_log_level="error")
            w.send(None)
            writers.append(w)
        index = 0
        def emit(im, phase):
            nonlocal index
            writers[0].send(np.asarray(im))
            writers[1].send(np.asarray(portrait(im, phase)))
            index += 1
        for _ in range(60):
            emit(card("Words in.\nMotion out.", "A robot simulation you can inspect.", index, total),
                 "PROMPT > SIMULATION")
        for trace in traces:
            reader = imageio_ffmpeg.read_frames(str(output / f"{trace['robot']}-raw.mp4"), pix_fmt="rgb24")
            metadata = next(reader)
            width, height = metadata["size"]
            for frame in trace["frames"]:
                raw = np.frombuffer(next(reader), dtype=np.uint8).reshape(height, width, 3)
                im = compose(raw, trace, frame, index, total)
                if trace is traces[-1] and frame["frame"] == len(trace["frames"])//2:
                    im.save(output / "poster.png")
                emit(im, trace.get("display_name", "AGENT-DIRECTED ARM" if frame["source"] == "agent" else "SCRIPTED POSE SHOWCASE"))
            reader.close()
        for _ in range(90):
            emit(card("Show the run.\nKeep the proof.", "Robot Reel / open-source preview", index, total, True),
                 "VIDEO + MOTION TRACE")
    finally:
        for w in writers:
            w.close()

    from .audio import add_soundtrack
    add_soundtrack(output, total / 30)
