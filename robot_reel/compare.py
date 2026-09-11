"""Compare compatible, verified Microduck or braking captures on one clock."""
import argparse
import hashlib
import json
import math
import shutil
from pathlib import Path

from .verify import verify, verify_trace


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def family(trace):
    if trace["robot"] == "microduck":
        return "microduck"
    if trace["robot"] in ("braking_late", "braking_early"):
        return "braking"
    raise ValueError("Comparison currently supports Microduck and braking captures")


def compatible(left, right):
    kind = family(left)
    if family(right) != kind:
        raise ValueError("Cannot compare different scene families")
    for key in ("fps", "joints", "home", "timestep"):
        if left[key] != right[key]:
            raise ValueError(f"Capture {key} must match")
    units = lambda trace: trace.get("units", ["rad"]*len(trace["joints"]))
    if units(left) != units(right):
        raise ValueError("Channel units must match")
    if len(left["frames"]) != len(right["frames"]):
        raise ValueError("Capture lengths must match; no frames are silently truncated")
    for a, b in zip(left["frames"], right["frames"]):
        if not math.isclose(a["sim_time"], b["sim_time"], abs_tol=1e-6, rel_tol=0):
            raise ValueError("Simulation timestamps must match")
    if kind == "microduck":
        for key in ("model_commit", "sha256", "control_hz", "actuators"):
            if left["policy"][key] != right["policy"][key]:
                raise ValueError(f"Microduck {key} must match")
    else:
        config = lambda trace: {k: v for k, v in trace["config"].items() if k != "trigger_gap_m"}
        if config(left) != config(right):
            raise ValueError("Vehicle configurations must match apart from the brake trigger")
    return kind


def metrics(trace):
    if family(trace) == "braking":
        return [
            ["Brake trigger", f'{trace["config"]["trigger_gap_m"]:.2f} m'],
            ["Contact in trial", "Recorded" if trace["outcome"]["collision"] else "None recorded"],
            ["Minimum gap", f'{min(f["qpos"][1] for f in trace["frames"]):.3f} m'],
            ["Final gap", f'{trace["frames"][-1]["qpos"][1]:.3f} m'],
        ]
    commands = [s["command"][0] for s in trace["policy_steps"]]
    walking = [f for f in trace["frames"] if f.get("commanded_forward_speed_mps", 0) > 0]
    measured = (
        f'{sum(f["measured_forward_speed_mps"] for f in walking)/len(walking):.3f} m/s'
        if walking and all("measured_forward_speed_mps" in f for f in walking) else "Not recorded"
    )
    end = trace["frames"][-1]["base_position_m"]
    return [
        ["Forward command", f"{max(commands):.2f} m/s"],
        ["Mean forward speed while commanded", measured],
        ["Final world x displacement", f"{end[0]:.3f} m"],
        ["Final lateral offset", f"{end[1]:.3f} m"],
        ["Minimum base height", f'{trace["outcome"]["minimum_base_height_m"]:.3f} m'],
    ]


def payload(left, right, labels):
    kind = compatible(left, right)
    return {
        "schema": 1, "family": kind, "fps": left["fps"],
        "duration": len(left["frames"])/left["fps"],
        "labels": list(labels), "metrics": [metrics(left), metrics(right)],
        "traces": [{k: v for k, v in t.items() if k != "policy_steps"} for t in (left, right)],
    }


def check_label(value):
    if not isinstance(value, str) or not value.strip() or len(value) > 48:
        raise ValueError("Comparison labels must contain 1–48 characters")
    return value


def verify_comparison(directory):
    manifest = json.loads((directory/"comparison-manifest.json").read_text())
    hashes = manifest.get("sha256", {})
    required = {
        "left.mp4", "right.mp4", "left-trace.json", "right-trace.json",
        "left-source-manifest.json", "right-source-manifest.json",
        "comparison.json", "comparison.mp4", "index.html", "poster.png",
    }
    if manifest.get("schema") != 1 or not required <= hashes.keys():
        raise ValueError("Incomplete comparison manifest")
    for filename, expected in hashes.items():
        if Path(filename).name != filename or digest(directory/filename) != expected:
            raise ValueError(f"Comparison hash mismatch: {filename}")
    traces = []
    versions = []
    for side in ("left", "right"):
        trace = json.loads((directory/f"{side}-trace.json").read_text())
        source = json.loads((directory/f"{side}-source-manifest.json").read_text())
        name = trace["robot"]
        for original, copied in [(f"{name}-trace.json", f"{side}-trace.json"),
                                 (f"{name}-raw.mp4", f"{side}.mp4")]:
            if source["sha256"].get(original) != digest(directory/copied):
                raise ValueError("Copied input does not match its source manifest")
        verify_trace(trace, source["arm_director"])
        traces.append(trace)
        versions.append(source["versions"])
    if versions[0] != versions[1]:
        raise ValueError("Capture engine versions must match")
    document = json.loads((directory/"comparison.json").read_text())
    if len(document.get("labels", [])) != 2:
        raise ValueError("Exactly two labels are required")
    if family(traces[0]) == "microduck" and "MICRODUCK-MEDIA-NOTICE.txt" not in hashes:
        raise ValueError("Microduck media notice is required")
    if document != payload(*traces, [check_label(x) for x in document["labels"]]):
        raise ValueError("Comparison summary disagrees with its input traces")
    return {"family": document["family"], "frames_per_side": len(traces[0]["frames"]),
            "duration": document["duration"]}


def render_film(output, document):
    import imageio_ffmpeg
    import numpy as np
    from PIL import Image, ImageDraw
    from .film import BG, CYAN, MUTED, WHITE, font, text
    readers, sizes = [], []
    writer = imageio_ffmpeg.write_frames(str(output/"comparison.mp4"), (1280, 720),
        fps=document["fps"], codec="libx264", pix_fmt_out="yuv420p", quality=8,
        macro_block_size=2, output_params=["-movflags", "+faststart"], ffmpeg_log_level="error")
    writer.send(None)
    count = len(document["traces"][0]["frames"])
    try:
        for side in ("left", "right"):
            reader = imageio_ffmpeg.read_frames(str(output/f"{side}.mp4"), pix_fmt="rgb24")
            metadata = next(reader)
            if not math.isclose(metadata["fps"], document["fps"], abs_tol=.01):
                raise ValueError("Raw video frame rate differs from the trace")
            readers.append(reader)
            sizes.append(metadata["size"])
        for i in range(count):
            image = Image.new("RGB", (1280, 720), BG)
            draw = ImageDraw.Draw(image)
            text(draw, (32, 20), "ROBOT REEL / ONE CLOCK. TWO RUNS.", 19, CYAN, True)
            text(draw, (1000, 22), f"{i/document['fps']:05.2f} / {document['duration']:.2f} s", 17, MUTED)
            for side, (reader, size) in enumerate(zip(readers, sizes)):
                try:
                    raw = next(reader)
                except StopIteration as exc:
                    raise ValueError("Raw video ended before its trace") from exc
                raw_image = Image.fromarray(np.frombuffer(raw, dtype=np.uint8).reshape(size[1], size[0], 3))
                raw_image.thumbnail((596, 520), Image.Resampling.LANCZOS)
                x = 24+side*640
                image.paste(raw_image, (x+(596-raw_image.width)//2, 110))
                label_size = 27
                while draw.textlength(document["labels"][side], font=font(label_size, True)) > 585:
                    label_size -= 1
                text(draw, (x+12, 65), document["labels"][side], label_size, WHITE, True)
                trace = document["traces"][side]
                frame = trace["frames"][i]
                if document["family"] == "braking":
                    readout = f"Speed {frame['qpos'][0]:.2f} m/s  /  Gap {frame['qpos'][1]:.2f} m"
                    state = "CONTACT RECORDED" if frame["collision"] else "NO CONTACT YET"
                else:
                    speed = frame.get("measured_forward_speed_mps")
                    measured = f"{speed:.2f} m/s" if speed is not None else "not recorded"
                    readout = f"Measured forward speed: {measured}"
                    state = f"World x: {frame['base_position_m'][0]:.2f} m / Official ONNX policy"
                text(draw, (x+12, 634), readout, 19, WHITE)
                text(draw, (x+12, 664), state, 13, CYAN)
            note = ("1D physics surrogate / scripted controllers" if document["family"] == "braking"
                    else "MuJoCo PD approximation / Microduck model media: upstream BY-SA-NC terms")
            text(draw, (32, 695), note, 12, MUTED)
            draw.rectangle((0, 716, int(1280*(i+1)/count), 720), fill=CYAN)
            writer.send(np.asarray(image))
            if i == int(count*.75):
                image.save(output/"poster.png")
        for reader in readers:
            if next(reader, None) is not None:
                raise ValueError("Raw video has frames not present in its trace")
    finally:
        writer.close()
        for reader in readers:
            reader.close()


def create_comparison(left_path, right_path, output, labels=("Left run", "Right run")):
    labels = tuple(check_label(label) for label in labels)
    if len(labels) != 2:
        raise ValueError("Exactly two labels are required")
    if output.exists() and any(output.iterdir()):
        raise ValueError("Comparison output must be empty; choose a new directory")
    paths = [left_path.resolve(), right_path.resolve()]
    traces, source_manifests = [], []
    for directory in {path.parent for path in paths}:
        verify(directory)
    for path in paths:
        trace = json.loads(path.read_text())
        if path.name != f'{trace["robot"]}-trace.json':
            raise ValueError("Expected a recorded scene trace filename")
        source = json.loads((path.parent/"manifest.json").read_text())
        if source["sha256"].get(path.name) != digest(path):
            raise ValueError("Trace is not covered by its source manifest")
        traces.append(trace)
        source_manifests.append(source)
    if source_manifests[0]["versions"] != source_manifests[1]["versions"]:
        raise ValueError("Capture engine versions must match")
    document = payload(*traces, labels)
    output.mkdir(parents=True, exist_ok=True)
    for side, path, trace in zip(("left", "right"), paths, traces):
        shutil.copyfile(path, output/f"{side}-trace.json")
        shutil.copyfile(path.parent/"manifest.json", output/f"{side}-source-manifest.json")
        shutil.copyfile(path.parent/f'{trace["robot"]}-raw.mp4', output/f"{side}.mp4")
    if document["family"] == "microduck":
        notice = paths[0].parent/"MICRODUCK-MEDIA-NOTICE.txt"
        if not notice.exists():
            raise ValueError("Microduck comparisons require the original media notice")
        shutil.copyfile(notice, output/notice.name)
    (output/"comparison.json").write_text(json.dumps(document, indent=2))
    serialized = json.dumps(document, separators=(",", ":"), ensure_ascii=True).replace("<", "\\u003c")
    template = Path(__file__).with_name("comparison.html").read_text()
    (output/"index.html").write_text(template.replace("__COMPARISON_DATA__", serialized))
    render_film(output, document)
    hashes = {p.name: digest(p) for p in sorted(output.iterdir()) if p.is_file()}
    (output/"comparison-manifest.json").write_text(json.dumps({"schema": 1, "sha256": hashes}, indent=2))
    verify_comparison(output)
    return document


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--left", type=Path, required=True, help="A recorded scene's *-trace.json")
    parser.add_argument("--right", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--left-label", default="Left run")
    parser.add_argument("--right-label", default="Right run")
    args = parser.parse_args(argv)
    try:
        create_comparison(args.left, args.right, args.output, (args.left_label, args.right_label))
    except (ValueError, OSError, KeyError) as exc:
        parser.error(str(exc))
    print(f"Comparison saved: {args.output.resolve()}")


if __name__ == "__main__":
    main()
