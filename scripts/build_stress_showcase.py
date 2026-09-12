"""Create a source-mapped, three-condition preview from sealed policy videos."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from robot_reel.stress import CONDITIONS, SCHEMA, file_hash, summarize, trial_id, write_json
from robot_reel.stress_site import load_collection, verify_site


def selection(document, attempts, traces):
    summary = summarize(document, traces, attempts)
    chosen = next((p for p in summary["pairs"] if p["reference_success"] and not p["condition_success"]), None)
    if chosen is None:
        chosen = next((p for p in summary["pairs"] if p["reference_success"] != p["condition_success"]), summary["pairs"][0])
    runs = [next(t for t in traces if t["stress"]["trial_id"] == trial_id(chosen["seed"], c["id"])) for c in CONDITIONS]
    maximum = max(t["result"]["actions"] for t in runs)
    samples = list(range(0, maximum+1, 3))
    if samples[-1] != maximum:
        samples.append(maximum)
    return chosen, runs, samples


def verify_preview(directory):
    directory = Path(directory)
    document, attempts, traces = load_collection(directory)
    chosen, runs, samples = selection(document, attempts, traces)
    report = json.loads((directory/"preview-manifest.json").read_text())
    paths = {a["trial_id"]: a["directory"] for a in attempts if a["status"] == "completed"}
    expected_sources = {"summary.json"}|{paths[t["stress"]["trial_id"]]+"/"+name for t in runs for name in ("trace.json", "main.mp4")}
    if (
        report.get("schema") != SCHEMA or report.get("seed") != chosen["seed"]
        or report.get("selection") != "first reference success / condition failure; otherwise first outcome change; otherwise first pair"
        or report.get("samples") != samples or report.get("poster_sample") != chosen["max_eef_frame"]
        or report.get("source_samples") != [[min(n, t["result"]["actions"]) for t in runs] for n in samples]
        or report.get("durations_ms") != [(b-a)*50 for a, b in zip(samples, samples[1:])]+[50]
        or set(report.get("sources", {})) != expected_sources
        or set(report.get("files", {})) != {"preview.gif", "poster.png"}
    ):
        raise ValueError("Stress preview mapping differs from the experiment")
    for name, expected in (report["sources"]|report["files"]).items():
        if file_hash(directory/name) != expected:
            raise ValueError(f"Stress preview hash mismatch: {name}")
    return {"seed": chosen["seed"], "frames": len(samples), "source_trials": len(runs)}


def build(directory):
    import imageio_ffmpeg
    from PIL import Image, ImageDraw, ImageFont
    directory = Path(directory)
    verify_site(directory)
    document, attempts, traces = load_collection(directory)
    chosen, runs, samples = selection(document, attempts, traces)
    paths = {a["trial_id"]: a["directory"] for a in attempts if a["status"] == "completed"}
    images = []
    for t in runs:
        reader = imageio_ffmpeg.read_frames(str(directory/paths[t["stress"]["trial_id"]]/"main.mp4"), output_params=["-threads", "1"])
        try:
            metadata = next(reader)
            if tuple(metadata["size"]) != (256, 256):
                raise ValueError("Expected policy camera dimensions")
            frames = [Image.frombytes("RGB", (256, 256), pixels) for pixels in reader]
            if len(frames) != len(t["frames"]):
                raise ValueError("Video length differs from source")
            images.append(frames)
        finally:
            reader.close()
    font = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")
    large = ImageFont.truetype(str(font), 29)
    small = ImageFont.truetype(str(font), 12)
    label_font = ImageFont.truetype(str(font), 15)
    summary = summarize(document, traces, attempts)

    def canvas(sample):
        image = Image.new("RGB", (816, 446), "#0b1016")
        draw = ImageDraw.Draw(image)
        draw.text((18, 12), "ROBOT REEL   /   STRESS LAB", font=small, fill="#83eac5")
        draw.text((18, 32), "Change the view. Check the policy.", font=large, fill="#e6e1ff")
        device_label = "CUDA" if document.get("device") == "cuda" else "CPU"
        draw.text((18, 74), f'{len(traces)} real rollouts  /  {len(document["seeds"])} paired seeds  /  one LIBERO task  /  {device_label} inference', font=small, fill="#acbac7")
        for i, (t, condition) in enumerate(zip(runs, CONDITIONS)):
            x = 12+i*268
            source = min(sample, t["result"]["actions"])
            image.paste(images[i][source], (x, 126))
            stat = summary["conditions"][i]
            draw.text((x+4, 104), condition["label"], font=label_font, fill="#83eac5" if i == 0 else "#c5afff")
            status = "SUCCESS" if t["result"]["outcome"] == "success" else "STEP LIMIT" if t["result"]["outcome"] == "step_limit" else "TERMINATED"
            suffix = " / HELD FINAL" if sample > source else ""
            draw.text((x+4, 388), f"Seed {t['seed']:02d} / {status}{suffix}", font=small, fill="#83eac5" if status == "SUCCESS" else "#ffc27d")
            draw.text((x+4, 408), f"Sample {source:03d} / {source/20:.2f}s", font=small, fill="#acbac7")
            draw.text((x+4, 426), f"All seeds: {stat['successes']}/{stat['trials']} success", font=small, fill="#acbac7")
        return image

    canvas(chosen["max_eef_frame"]).save(directory/"poster.png")
    frames = [canvas(n) for n in samples]
    contact = Image.new("RGB", (816, 446*5))
    for i in range(5):
        contact.paste(frames[round(i*(len(frames)-1)/4)], (0, i*446))
    palette = contact.quantize(colors=128, dither=Image.Dither.NONE)
    frames = [image.quantize(palette=palette, dither=Image.Dither.NONE) for image in frames]
    durations = [(b-a)*50 for a, b in zip(samples, samples[1:])]+[50]
    frames[0].save(directory/"preview.gif", save_all=True, append_images=frames[1:], duration=durations, loop=0, optimize=True, disposal=1)
    sources = {"summary.json"}|{paths[t["stress"]["trial_id"]]+"/"+name for t in runs for name in ("trace.json", "main.mp4")}
    write_json(directory/"preview-manifest.json", {
        "schema": SCHEMA, "seed": chosen["seed"],
        "selection": "first reference success / condition failure; otherwise first outcome change; otherwise first pair",
        "samples": samples, "source_samples": [[min(n, t["result"]["actions"]) for t in runs] for n in samples],
        "poster_sample": chosen["max_eef_frame"], "durations_ms": durations,
        "sources": {name: file_hash(directory/name) for name in sorted(sources)},
        "files": {name: file_hash(directory/name) for name in ("preview.gif", "poster.png")},
    })
    return verify_preview(directory)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    print(json.dumps(build(args.directory), indent=2))
