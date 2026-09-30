"""Record, model, check, render and publish the factory digital twin lab.

    python3 scripts/build_factory_twin.py --output docs/factory-twin --work artifacts/factory-twin \
        --blender ~/.local/opt/blender-5.2.1-linux-x64/blender

Steps: simulate every seed pair (standard library) -> build one animated Blender
project per loop mode -> check every frame and read back the OpenUSD export ->
render stills with Cycles -> write the page and seal the manifest and ZIP.
``--preview`` also renders the README time-lapse GIF. The Blender projects and
USD files stay in ``--work`` (release assets), not in the published site.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from robot_reel import factory_twin as ft  # noqa: E402

# (view, frame, file) — frames chosen from the closed-loop record of seed 10.
STILLS = (
    ("hall", 361, "poster.png"),              # 10:30, CNC 2 in planned service
    ("aerial", 361, "render-aerial.jpg"),
    ("hall", 361, "render-hall.jpg"),
    ("cnc", 361, "render-cnc.jpg"),
    ("energy", 1201, "render-energy.jpg"),    # 11:40, cloud over PV, EV chargers capped
)


def run(command, **kwargs):
    print("+", " ".join(str(c) for c in command[:6]), "...", flush=True)
    result = subprocess.run([str(c) for c in command], capture_output=True, text=True, **kwargs)
    if result.returncode:
        sys.stderr.write(result.stdout[-4000:] + result.stderr[-4000:])
        raise SystemExit(f"Command failed: {command[:4]}")
    return result.stdout


def marker(output, prefix):
    line = next(line for line in output.splitlines() if line.startswith(prefix))
    return json.loads(line[len(prefix):])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--blender", type=Path, required=True)
    parser.add_argument("--samples", type=int, default=160)
    parser.add_argument("--preview", action="store_true")
    parser.add_argument("--skip-record", action="store_true", help="Reuse WORK/source")
    parser.add_argument("--gif-only", action="store_true", help="Re-encode the GIF from WORK/preview renders")
    args = parser.parse_args()
    work = args.work.resolve()
    if args.gif_only:
        return preview(args, work, render=False)
    source = work / "source"
    if not args.skip_record:
        if source.exists():
            shutil.rmtree(source)
        print(json.dumps(ft.record(source)["seed_summary"]))
    lab = source / "lab.json"
    blender = [args.blender, "--background", "--factory-startup", "--python"]
    for mode in ft.MODES:
        print(run([*blender, ROOT / "scripts/build_factory_twin_blender.py", "--", "--lab", lab, "--mode", mode,
                   "--output", work / f"factory-twin-{mode}.blend"]).splitlines()[-3])
    checks = [subprocess.Popen([str(c) for c in (
        *blender, ROOT / "scripts/check_factory_twin_blender.py", "--", "--lab", lab, "--mode", mode,
        "--blend", work / f"factory-twin-{mode}.blend", "--usd", work / f"factory-twin-{mode}.usdc",
        "--report", work / f"check-{mode}.json")], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        for mode in ft.MODES]
    renders = work / "renders"
    stills = []
    for view, frame, name in STILLS:
        size = ("1600", "900") if name.endswith(".png") else ("1920", "1080")
        out = run([*blender[:2], "--python", ROOT / "scripts/render_factory_twin.py", "--",
                   "--blend", work / "factory-twin-closed.blend", "--view", view, "--frames", frame,
                   "--output", renders, "--prefix", name.split(".")[0] + "-", "--samples", args.samples,
                   "--width", size[0], "--height", size[1]])
        stills.append({**marker(out, "RENDER_RESULT "), "published_as": name})
    for process in checks:
        output = process.communicate()[0]
        if process.returncode:
            sys.stderr.write(output[-4000:])
            raise SystemExit("Blender check failed")
    reports = {mode: json.loads((work / f"check-{mode}.json").read_text()) for mode in ft.MODES}
    digest = hashlib.sha256(lab.read_bytes()).hexdigest()
    receipt = {
        "schema": ft.SCHEMA, "verified": all(r["verified"] for r in reports.values()),
        "frames_checked": ft.SAMPLES, "usd_frames_checked": min(r["usd_frames_checked"] for r in reports.values()),
        "inputs": {"lab.json": digest}, "blender_version": reports["closed"]["blender_version"],
        "modes": {mode: {k: v for k, v in r.items() if k != "problems"} for mode, r in reports.items()},
        "renders": stills,
        "note": "Produced by scripts/check_factory_twin_blender.py; robot-reel --verify checks this receipt's "
                "inputs but does not re-run Blender.",
    }
    from PIL import Image
    with tempfile.TemporaryDirectory(dir=args.output.resolve().parent, prefix=".factory-twin-") as temporary:
        stage = Path(temporary) / "lab"
        stage.mkdir()
        for mode in ft.MODES:
            shutil.copyfile(source / f"trace-{mode}.json", stage / f"trace-{mode}.json")
        for name in ("lab.json", "seeds.json"):
            shutil.copyfile(source / name, stage / name)
        (stage / "blender-check.json").write_text(json.dumps(receipt, indent=2) + "\n")
        for view, frame, name in STILLS:
            png = renders / f"{name.split('.')[0]}-{view}-{frame:04d}.png"
            image = Image.open(png).convert("RGB")
            if name.endswith(".png"):
                image.save(stage / name, optimize=True)
            else:
                image.save(stage / name, quality=86, optimize=True, progressive=True)
        shutil.copyfile(ROOT / "examples/factory-twin/METHODS.md", stage / "METHODS.md")
        shutil.copyfile(ROOT / "LICENSE", stage / "LICENSE")
        (stage / "index.html").write_text(ft.render_page(ft.decode((stage / "lab.json").read_bytes())))
        ft.seal(stage)
        if args.output.exists():
            shutil.rmtree(args.output)
        stage.rename(args.output)
    print(json.dumps(ft.verify(args.output), indent=2))
    if args.preview:
        preview(args, work)


def preview(args, work, render=True):
    """Time-lapse GIF over the whole closed-loop shift, one frame every 90 samples (7.5 min)."""
    frames = list(range(1, ft.SAMPLES + 1, 90))
    renders = work / "preview"
    if render:
        run([args.blender, "--background", "--python", ROOT / "scripts/render_factory_twin.py", "--",
             "--blend", work / "factory-twin-closed.blend", "--view", "hall", "--frames", ",".join(map(str, frames)),
             "--output", renders, "--samples", "48", "--width", "800", "--height", "450"])
    from PIL import Image, ImageDraw, ImageFont
    images = []
    try:
        font = ImageFont.truetype("DejaVuSans-Bold.ttf", 14)
    except OSError:
        font = ImageFont.load_default()
    lab = ft.decode((args.output / "lab.json").read_bytes())
    plant = lab["runs"]["closed"]["plant"]
    for frame in frames:
        image = Image.open(renders / f"hall-{frame:04d}.png").convert("RGB").resize((640, 360), Image.LANCZOS)
        draw = ImageDraw.Draw(image)
        k = frame - 1
        label = (f"{ft._clock(ft.START_CLOCK_S + k * ft.SAMPLE_S)} · closed loop · sample {k} · "
                 f"good {plant['good'][k]} · CNC 2 {lab['config']['state_names'][plant['state'][k][2]]}")
        draw.rectangle((0, 334, 640, 360), fill=(8, 14, 25))
        draw.text((10, 339), label, font=font, fill=(121, 239, 203))
        images.append(image.quantize(colors=128, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE))
    images[0].save(args.output / "preview.gif", save_all=True, append_images=images[1:], duration=450, loop=0,
                   optimize=True)
    manifest = {"frames": frames, "samples": [f - 1 for f in frames], "duration_ms": 450, "mode": "closed",
                "source": "factory-twin-closed.blend, camera 'Hall cutaway', Cycles 48 spp"}
    (args.output / "preview.json").write_text(json.dumps(manifest, indent=2) + "\n")


if __name__ == "__main__":
    main()
