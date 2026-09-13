"""Build and verify an offline, paired policy stress experiment."""
from __future__ import annotations

import argparse
import csv
import html
import io
from importlib.resources import files
import json
from pathlib import Path
import re
import shutil
import tempfile
import zipfile

from .stress import CONDITIONS, MEDIA, SCHEMA, file_hash, summarize, trial_id, validate_plan, verify_run, write_json

MARKER = '<script id="stress-data" type="application/json">'
# Only the published experiment uses this release asset. Custom builds link to
# their own local archive unless the caller explicitly supplies another location.
PUBLISHED_ARCHIVE_HREF = ("https://github.com/noteflowai/robot-reel/releases/download/"
                          "v0.7.0/robot-reel-stress-experiment.zip")


def page(data, archive_href="experiment.zip"):
    """Render the replay page for a verified payload."""
    encoded = json.dumps(data, separators=(",", ":"), allow_nan=False).replace("<", "\\u003c")
    template = Path(__file__).with_name("stress.html").read_text()
    if template.count("__ARCHIVE_HREF__") != 1 or template.count("__STRESS_DATA__") != 1:
        raise ValueError("The stress template must carry one archive link and one payload")
    replacements = {"__STRESS_DATA__": encoded, "__ARCHIVE_HREF__": html.escape(archive_href, quote=True)}
    return re.sub(r"__STRESS_DATA__|__ARCHIVE_HREF__", lambda match: replacements[match[0]], template)


def load_collection(directory):
    directory = Path(directory)
    document = json.loads((directory/"experiment.json").read_text())
    validate_plan(document)
    attempts = json.loads((directory/"attempts.json").read_text())
    expected = {trial_id(seed, c["id"]) for seed in document["seeds"] for c in CONDITIONS}
    seen, completed, traces = {}, set(), []
    if not isinstance(attempts, list):
        raise ValueError("Expected an attempt ledger")
    for attempt in attempts:
        if not isinstance(attempt, dict):
            raise ValueError("Invalid attempt ledger entry")
        key = attempt.get("trial_id")
        number = seen.get(key, 0)+1
        relative = f"runs/{key}/attempt-{number:03d}"
        if (
            key not in expected or key in completed or type(attempt.get("attempt")) is not int
            or attempt["attempt"] != number or attempt.get("directory") != relative
            or attempt.get("status") not in ("completed", "error")
            or not isinstance(attempt.get("started_utc"), str)
            or not re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", attempt["started_utc"])
        ):
            raise ValueError("Invalid, duplicate, unfinished or unsafe attempt")
        seen[key] = number
        if attempt["status"] == "error":
            if not isinstance(attempt.get("error"), str) or not attempt["error"]:
                raise ValueError("Execution errors must remain visible")
            continue
        path = directory/relative
        if path.is_symlink() or not path.resolve().is_relative_to(directory.resolve()):
            raise ValueError("Run path escapes the collection")
        trace = verify_run(path, document)
        if trace["stress"]["trial_id"] != key or trace["result"]["outcome"] != attempt.get("outcome"):
            raise ValueError("Ledger outcome or trial differs from the trace")
        completed.add(key)
        traces.append(trace)
    summarize(document, traces, attempts)
    order = {trial_id(seed, c["id"]): (seed, i) for seed in document["seeds"] for i, c in enumerate(CONDITIONS)}
    traces.sort(key=lambda t: order[t["stress"]["trial_id"]])
    return document, attempts, traces


def csv_text(traces):
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(("trial_id", "seed", "initial_state_id", "condition", "outcome", "actions", "simulation_seconds", "inference_calls", "mean_policy_seconds", "wall_seconds"))
    for trace in traces:
        calls = trace["inference_calls"]
        writer.writerow((
            trace["stress"]["trial_id"], trace["seed"], trace["initial_state_id"], trace["stress"]["condition"],
            trace["result"]["outcome"], trace["result"]["actions"], trace["result"]["simulation_seconds"],
            len(calls), sum(c["policy_seconds"] for c in calls)/len(calls), trace["result"]["wall_seconds"],
        ))
    return output.getvalue()


def payload(document, attempts, traces):
    return {"experiment": document, "attempts": attempts, "traces": traces, "summary": summarize(document, traces, attempts)}


def required_files(attempts):
    names = {
        "index.html", "experiment.json", "attempts.json", "summary.json", "results.csv",
        "telemetry.mcap", "media-checks.json", "NOTICE.txt", "LICENSE", "METHODS.md",
    }
    for attempt in attempts:
        if attempt["status"] == "completed":
            names.update(f'{attempt["directory"]}/{name}' for name in ("trace.json", "run-manifest.json", *MEDIA))
    return names


def verify_site(directory):
    directory = Path(directory)
    document, attempts, traces = load_collection(directory)
    expected = required_files(attempts)
    manifest = json.loads((directory/"manifest.json").read_text())
    if manifest.get("schema") != SCHEMA or set(manifest.get("files", {})) != expected:
        raise ValueError("Incomplete experiment manifest")
    for name, digest in manifest["files"].items():
        path = directory/name
        if path.is_symlink() or not path.resolve().is_relative_to(directory.resolve()) or file_hash(path) != digest:
            raise ValueError(f"Experiment hash mismatch: {name}")
    summary = summarize(document, traces, attempts)
    if json.loads((directory/"summary.json").read_text()) != summary:
        raise ValueError("Published rates differ from all planned trials")
    if (directory/"results.csv").read_text() != csv_text(traces):
        raise ValueError("CSV differs from recorded results")
    html = (directory/"index.html").read_text()
    if html.count(MARKER) != 1 or json.loads(html.split(MARKER)[1].split("</script>", 1)[0]) != payload(document, attempts, traces):
        raise ValueError("Viewer payload differs from source evidence")
    checks = json.loads((directory/"media-checks.json").read_text())
    if set(checks) != {t["stress"]["trial_id"] for t in traces}:
        raise ValueError("Incomplete camera checks")
    by_id = {t["stress"]["trial_id"]: t for t in traces}
    for attempt in attempts:
        if attempt["status"] != "completed":
            continue
        trace = by_id[attempt["trial_id"]]
        for camera in ("main", "wrist"):
            checked = checks[attempt["trial_id"]].get(camera, {})
            if checked != {
                "frames": len(trace["frames"]), "fps": 20.0, "size": [256, 256],
                "mp4_sha256": file_hash(directory/attempt["directory"]/f"{camera}.mp4"),
                "first_raw_pixels_sha256": trace["frames"][0]["raw_camera_sha256"][camera],
            }:
                raise ValueError("Camera check is stale or differs from the trace")
    # A build writes experiment.zip beside the site. The published copy under docs/
    # does not ship it -- the archive is a release asset, so it stays out of the
    # repository history -- and is verified from the manifest and files instead.
    if (directory/"experiment.zip").exists():
        with zipfile.ZipFile(directory/"experiment.zip") as archive:
            names = archive.namelist()
            if len(names) != len(set(names)) or set(names) != expected|{"manifest.json"}:
                raise ValueError("Offline archive is incomplete")
            for name in names:
                if archive.read(name) != (directory/name).read_bytes():
                    raise ValueError(f"Offline archive differs: {name}")
    return summary


def check_media(directory):
    import hashlib
    import imageio_ffmpeg
    from PIL import Image
    directory = Path(directory)
    _, attempts, traces = load_collection(directory)
    by_id = {t["stress"]["trial_id"]: t for t in traces}
    checks = {}
    for attempt in attempts:
        if attempt["status"] != "completed":
            continue
        key = attempt["trial_id"]
        trace, path = by_id[key], directory/attempt["directory"]
        checks[key] = {}
        for camera in ("main", "wrist"):
            reader = imageio_ffmpeg.read_frames(str(path/f"{camera}.mp4"), output_params=["-threads", "1"])
            try:
                meta = next(reader)
                count = sum(1 for _ in reader)
            finally:
                reader.close()
            with Image.open(path/f"{camera}-poster.png") as image:
                if image.size != (256, 256) or image.mode != "RGB":
                    raise ValueError("Expected a raw RGB initial policy view")
                pixels_hash = hashlib.sha256(image.tobytes()).hexdigest()
            if count != len(trace["frames"]) or meta["fps"] != 20 or tuple(meta["size"]) != (256, 256) or pixels_hash != trace["frames"][0]["raw_camera_sha256"][camera]:
                raise ValueError(f"Recorded camera differs from trace: {key}/{camera}")
            checks[key][camera] = {
                "frames": count, "fps": meta["fps"], "size": list(meta["size"]),
                "mp4_sha256": file_hash(path/f"{camera}.mp4"), "first_raw_pixels_sha256": pixels_hash,
            }
    return checks


def build(recording, output, archive_href="experiment.zip"):
    """Publish a complete, verified export without changing the input collection."""
    recording, output = Path(recording).resolve(), Path(output)
    target = output.resolve()
    if output.is_symlink() or target.is_relative_to(recording) or recording.is_relative_to(target):
        raise ValueError("Stress input and output directories must be separate")
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        raise ValueError("Choose an empty output directory")
    document, attempts, traces = load_collection(recording)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".stress-export-", dir=output.parent) as temporary:
        staging = Path(temporary)/"site"
        staging.mkdir()
        result = _write_site(recording, staging, document, attempts, traces, archive_href)
        # Keep staging on the destination filesystem for the final rename.
        # rmdir also refuses an empty placeholder populated by another writer.
        if output.is_dir():
            output.rmdir()
        staging.replace(output)
    return result


def _write_site(recording, output, document, attempts, traces, archive_href):
    from .stress_mcap import export_mcap
    # Resolve the optional MCAP dependency before copying the camera recordings.
    export_mcap(traces, output/"telemetry.mcap")
    for name in ("experiment.json", "attempts.json"):
        shutil.copyfile(recording/name, output/name)
    for attempt in attempts:
        if attempt["status"] != "completed":
            continue
        destination = output/attempt["directory"]
        destination.mkdir(parents=True)
        for name in ("trace.json", "run-manifest.json", *MEDIA):
            shutil.copyfile(recording/attempt["directory"]/name, destination/name)
    data = payload(document, attempts, traces)
    write_json(output/"summary.json", data["summary"])
    (output/"results.csv").write_text(csv_text(traces))
    write_json(output/"media-checks.json", check_media(output))
    resources = files("robot_reel").joinpath("resources", "stress")
    for source, name in (("NOTICE.txt", "NOTICE.txt"), ("LICENSE.txt", "LICENSE"), ("METHODS.txt", "METHODS.md")):
        (output/name).write_bytes(resources.joinpath(source).read_bytes())
    (output/"index.html").write_text(page(data, archive_href))
    write_json(output/"manifest.json", {"schema": SCHEMA, "files": {name: file_hash(output/name) for name in sorted(required_files(attempts))}})
    with zipfile.ZipFile(output/"experiment.zip", "w", zipfile.ZIP_DEFLATED) as archive:
        for name in sorted(required_files(attempts)|{"manifest.json"}):
            archive.write(output/name, name)
    return verify_site(output)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("recording", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--archive-href", default="experiment.zip",
                        help="Download location for this experiment (default: local experiment.zip)")
    args = parser.parse_args(argv)
    print(json.dumps(build(args.recording, args.output, archive_href=args.archive_href), indent=2))


if __name__ == "__main__":
    main()
