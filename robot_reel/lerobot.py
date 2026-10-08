"""Replay one LeRobotDataset episode offline, with its source files on record.

    robot-reel lerobot lerobot/svla_so101_pickplace --episode 0 --output artifacts/so101
    robot-reel lerobot ~/datasets/my_so101_run --episode 3 --output artifacts/mine
    robot-reel lerobot artifacts/so101 --verify --check-media --check-source
    robot-reel lerobot artifacts/so101 --mark 239 --signal action/shoulder_pan.pos --note "What you saw"

--mark seals one frame/channel observation into a verified export as a hashed
finding.json and shows it in the page; --verify on any copy re-checks it against episode.json.

Reading a dataset needs the `lerobot` extra (pyarrow, huggingface_hub); the
LeRobot library itself is not imported. --verify alone uses only the standard
library; --check-media adds the bundled ffmpeg. Formats v2.0, v2.1 and v3.0 are supported.
"""
import argparse
from importlib import metadata
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unicodedata

from .compare import digest

SCHEMA = "robot-reel-lerobot-1"
FORMATS = ("v2.0", "v2.1", "v3.0")
# Bookkeeping columns every LeRobot frame carries; they are the timeline, not signals.
CLOCK = ("timestamp", "frame_index", "episode_index", "index", "task_index")
NUMERIC = {"float16", "float32", "float64", "int8", "int16", "int32", "int64", "uint8", "uint16", "uint32", "bool"}
MAX_DIMS = 64
MAX_FRAMES = 20_000
HUB = "https://huggingface.co/datasets/"
VISUALIZER = "https://huggingface.co/spaces/lerobot/visualize_dataset"
# One sealed frame/channel observation per export (RR-02).
FINDING = "finding.json"
FINDING_SCHEMA = "robot-reel-lerobot-finding-1"
FINDING_KEYS = ("schema", "episode", "frame", "timestamp", "signals", "note", "episode_sha256", "robot_reel", "limitations")
FINDING_LIMITATIONS = ("An observation at one recorded frame. It is not a failure label, a calibrated threshold "
                       "or a signature: the manifest hashes show the files are unchanged since marking, not who wrote them.")
MAX_FINDING_SIGNALS = 8
MAX_NOTE = 2000
# --mark also embeds the finding in index.html (offline pages cannot fetch finding.json).
EPISODE_MARKER = '<script id="episode-data" type="application/json">'
FINDING_MARKER = '<script id="finding-data" type="application/json">'


def finding_element(finding):
    """The one line --mark inserts into index.html: the finding as inert JSON, '<' escaped."""
    payload = json.dumps(finding, separators=(",", ":"), allow_nan=False).replace("<", "\\u003c")
    return f"{FINDING_MARKER}{payload}</script>\n"


def embed_finding(html, finding):
    """Insert the finding line directly after the episode-data element; removing it restores html exactly."""
    start = html.index(EPISODE_MARKER)
    end = html.index("</script>\n", start)+len("</script>\n")
    return html[:end]+finding_element(finding)+html[end:]


class Source:
    """A local dataset root or a Hugging Face dataset pinned to one commit."""

    def __init__(self, source, revision=None):
        path = Path(source).expanduser()
        if (path/"meta"/"info.json").is_file():
            if revision:
                raise ValueError("--revision applies only to Hugging Face datasets")
            self.root, self.repo_id, self.revision, self.license = path.resolve(), None, None, None
            return
        if not re.fullmatch(r"[\w.-]+/[\w.-]+", str(source)):
            raise ValueError(f"{source}: not a dataset directory (meta/info.json) or a Hub repo id")
        from huggingface_hub import HfApi
        self.api = HfApi()
        self.root, self.repo_id = None, str(source)
        info = self.api.dataset_info(self.repo_id, revision=revision)
        self.revision = info.sha
        license = getattr(info.card_data, "license", None) if info.card_data else None
        self.license = license if isinstance(license, str) else None

    def file(self, name):
        if self.root:
            path = self.root/name
            if not path.is_file():
                raise ValueError(f"Missing dataset file: {name}")
            return path
        from huggingface_hub import hf_hub_download
        return Path(hf_hub_download(self.repo_id, name, repo_type="dataset", revision=self.revision))

    def parquet(self, prefix):
        if self.root:
            names = [p.relative_to(self.root).as_posix() for p in (self.root/prefix).rglob("*.parquet")]
        else:
            names = [n for n in self.api.list_repo_files(self.repo_id, repo_type="dataset", revision=self.revision)
                     if n.startswith(prefix+"/") and n.endswith(".parquet")]
        return sorted(names)

    def describe(self):
        if self.root:
            return {"kind": "local", "name": self.root.name}
        return {"kind": "hub", "repo_id": self.repo_id, "revision": self.revision,
                "url": f"{HUB}{self.repo_id}/tree/{self.revision}"}


def channel_names(feature, count):
    names = feature.get("names")
    if isinstance(names, dict) and len(names) == 1:
        names = next(iter(names.values()))
    if isinstance(names, list) and len(names) == count and all(isinstance(n, str) for n in names):
        return names
    return [str(i) for i in range(count)]


def dims(feature):
    shape = feature.get("shape") or [1]
    return math.prod(shape) if all(type(n) is int and n > 0 for n in shape) else 0


def scalar(value, dtype):
    """The exact source value, written as the shortest decimal that round-trips."""
    if value is None:
        return None
    if dtype == "bool":
        return int(bool(value))
    if dtype.startswith(("int", "uint")):
        return int(value)
    if dtype == "float64":
        value = float(value)
    else:
        import numpy
        value = float(numpy.format_float_positional(numpy.dtype(dtype).type(value), unique=True, trim="-"))
    return value if math.isfinite(value) else None


def flatten(value):
    if isinstance(value, (list, tuple)):
        return [v for item in value for v in flatten(item)]
    return [value]


def locate(source, info, episode):
    """Return the episode's metadata row, data file and per-camera video spans."""
    version = info.get("codebase_version")
    if version not in FORMATS:
        raise ValueError(f"Unsupported LeRobotDataset version {version!r}; expected one of {', '.join(FORMATS)}")
    cameras = [k for k, f in info["features"].items() if f.get("dtype") == "video"]
    if version == "v3.0":
        import pyarrow.parquet as pq
        row = None
        for name in source.parquet("meta/episodes"):
            table = pq.read_table(source.file(name), filters=[("episode_index", "=", episode)])
            if table.num_rows:
                row = {k: v for k, v in table.slice(0, 1).to_pylist()[0].items() if not k.startswith("stats/")}
                break
        if row is None:
            raise ValueError(f"Episode {episode} is not in this dataset ({info.get('total_episodes')} episodes)")
        data = info["data_path"].format(chunk_index=row["data/chunk_index"], file_index=row["data/file_index"])
        videos = {k: (info["video_path"].format(video_key=k, chunk_index=row[f"videos/{k}/chunk_index"],
                                                file_index=row[f"videos/{k}/file_index"]),
                      float(row[f"videos/{k}/from_timestamp"])) for k in cameras}
        return row, data, videos, "meta/episodes"
    row = None
    for line in source.file("meta/episodes.jsonl").read_text().splitlines():
        if line.strip() and (item := json.loads(line)).get("episode_index") == episode:
            row = item
            break
    if row is None:
        raise ValueError(f"Episode {episode} is not in this dataset ({info.get('total_episodes')} episodes)")
    chunk = episode // info["chunks_size"]
    data = info["data_path"].format(episode_chunk=chunk, episode_index=episode)
    videos = {k: (info["video_path"].format(episode_chunk=chunk, video_key=k, episode_index=episode), 0.)
              for k in cameras}
    return row, data, videos, "meta/episodes.jsonl"


REPAIR = " Robot Reel does not reorder, fill or interpolate frames; repair or re-export the episode."


def frame_index_error(values, episode, data):
    """Describe the first frame_index that differs from its position (frame_index values, never file rows)."""
    where = f"Episode {episode} in {data}"
    for i, v in enumerate(values):
        if v == i:
            continue
        # Order comparisons run only on finite numbers, so None or strings cannot raise TypeError.
        numeric = type(v) in (int, float) and math.isfinite(v)
        if numeric and i > 0 and v == values[i-1]:
            return f"{where} repeats frame_index {v!r}; each frame must appear once."+REPAIR
        if numeric and v > i:
            return (f"{where} is missing frame_index {i} (next recorded frame_index is {v!r}); "
                    "frames must be 0..length-1 without gaps."+REPAIR)
        return f"{where} has frame_index {v!r} where {i} was expected."+REPAIR
    return None


def timestamp_error(timestamps, episode, data):
    """Name the first missing or non-increasing timestamp; position i is frame_index i."""
    where = f"Episode {episode} in {data}"
    for i, t in enumerate(timestamps):
        if t is None:
            return f"{where} has no finite timestamp at frame_index {i}."+REPAIR
    for i in range(1, len(timestamps)):
        if timestamps[i] <= timestamps[i-1]:
            return (f"{where}: timestamp at frame_index {i} ({timestamps[i]!r} s) is not after "
                    f"frame_index {i-1} ({timestamps[i-1]!r} s)."+REPAIR)
    return None


def read_episode(source, episode):
    """Read one episode into a JSON-ready trace; media are described, not encoded."""
    import pyarrow.parquet as pq
    info = json.loads(source.file("meta/info.json").read_text())
    if type(episode) is not int or episode < 0:
        raise ValueError("Episode index must be a nonnegative integer")
    row, data, videos, index_file = locate(source, info, episode)
    fps = info.get("fps")
    if type(fps) not in (int, float) or not 0 < fps <= 1000:
        raise ValueError("Dataset has no valid fps")
    table = pq.read_table(source.file(data), filters=[("episode_index", "=", episode)])
    if "frame_index" in table.column_names:
        table = table.sort_by("frame_index")
    length = table.num_rows
    if not 2 <= length <= MAX_FRAMES:
        raise ValueError(f"Episode has {length} frames; expected 2–{MAX_FRAMES}")
    columns = table.to_pydict()
    for name in ("timestamp", "frame_index"):
        if name not in columns:
            raise ValueError(f"Data file has no {name} column")
    timestamps = [scalar(v, info["features"].get("timestamp", {}).get("dtype", "float32")) for v in flatten(columns["timestamp"])]
    # Frame indices first, so a frame dropped mid-episode is named instead of reported as a count mismatch.
    if columns["frame_index"] != list(range(length)):
        raise ValueError(frame_index_error(columns["frame_index"], episode, data) or "Frame indices are not 0..length-1")
    if row.get("length") not in (None, length):
        raise ValueError(f"Episode metadata lists {row['length']} frames but {data} holds {length}")
    # With exactly one value per frame, position i is frame_index i; otherwise keep the generic message.
    problem = timestamp_error(timestamps, episode, data) if len(timestamps) == length else None
    if problem:
        raise ValueError(problem)
    if any(t is None for t in timestamps) or any(b <= a for a, b in zip(timestamps, timestamps[1:])):
        raise ValueError("Timestamps are missing or not increasing")
    series, cameras, skipped = [], [], []
    for key, feature in info["features"].items():
        dtype = feature.get("dtype")
        if key in CLOCK:
            continue
        if dtype in ("video", "image"):
            cameras.append({"key": key, "kind": dtype, "file": "cameras/"+re.sub(r"[^\w.-]+", "_", key.removeprefix("observation.images."))+".mp4",
                            "shape": feature.get("shape")})
            continue
        count = dims(feature)
        if dtype not in NUMERIC or not 1 <= count <= MAX_DIMS or key not in columns:
            skipped.append({"key": key, "dtype": dtype, "reason": "not in data file" if key not in columns else
                            f"{count} values per frame" if dtype in NUMERIC else "not numeric"})
            continue
        values = [[scalar(v, dtype) for v in flatten(frame)] for frame in columns[key]]
        if any(len(frame) != count for frame in values):
            raise ValueError(f"{key}: frames do not match the declared shape {feature.get('shape')}")
        series.append({"key": key, "dtype": dtype, "names": channel_names(feature, count), "values": values})
    for camera in cameras:
        if camera["kind"] == "video":
            camera["source"], camera["from_timestamp"] = videos[camera["key"]][0], scalar(videos[camera["key"]][1], "float64")
        else:
            camera["source"] = data
    tasks = row.get("tasks")
    if isinstance(tasks, str):
        tasks = [tasks]
    if not isinstance(tasks, list) or not all(isinstance(t, str) for t in tasks):
        tasks = []
    files = sorted({"meta/info.json", index_file if index_file.endswith(".jsonl") else None, data,
                    *(c["source"] for c in cameras)} - {None})
    return {
        "schema": SCHEMA,
        "dataset": {**source.describe(), "codebase_version": info["codebase_version"],
                    "robot_type": info.get("robot_type"), "total_episodes": info.get("total_episodes"),
                    "license": info.get("license") or source.license},
        "episode": episode, "fps": fps, "length": length, "tasks": tasks,
        "timestamps": timestamps, "series": series, "cameras": cameras, "skipped": skipped,
        "source_files": {name: digest(source.file(name)) for name in files},
    }


def ffmpeg():
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


def encode_video(source, camera, length, fps, output, crf):
    """Cut the episode's span out of a (possibly shared) source video as H.264."""
    # Seek half a frame early: accurate input seeking keeps frames at or after
    # the target, so the first frame at from_timestamp survives float rounding.
    start = max(0., camera["from_timestamp"]-.5/fps)
    run([ffmpeg(), "-v", "error", "-y", "-ss", f"{start:.6f}", "-i", str(source.file(camera["source"])),
         "-map", "0:v:0", "-frames:v", str(length), "-an", "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2",
         "-r", repr(fps), "-c:v", "libx264", "-preset", "medium", "-crf", str(crf), "-pix_fmt", "yuv420p",
         "-movflags", "+faststart", str(output)])


def encode_images(source, camera, length, fps, output, crf, episode):
    """Encode per-frame images stored inside the parquet data file."""
    import pyarrow.parquet as pq
    frames = pq.read_table(source.file(camera["source"]), columns=[camera["key"], "frame_index"],
                           filters=[("episode_index", "=", episode)]).sort_by("frame_index").column(camera["key"]).to_pylist()
    payloads, decoder = [], None
    for i, image in enumerate(frames):
        payload = image.get("bytes") if isinstance(image, dict) else None
        if not payload:
            raise ValueError(f"{camera['key']}: frame {i} has no embedded image bytes")
        # ffmpeg cannot reliably guess small images from a pipe, so name the decoder.
        kind = next((codec for magic, codec in IMAGE_MAGIC if payload.startswith(magic)), None)
        if kind is None or decoder not in (None, kind):
            raise ValueError(f"{camera['key']}: frame {i} is not a PNG or JPEG like the other frames")
        payloads.append(payload)
        decoder = kind
    run([ffmpeg(), "-v", "error", "-y", "-f", "image2pipe", "-framerate", repr(fps), "-c:v", decoder, "-i", "-",
         "-frames:v", str(length), "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2", "-c:v", "libx264",
         "-preset", "medium", "-crf", str(crf), "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(output)],
        b"".join(payloads))


IMAGE_MAGIC = ((b"\x89PNG\r\n\x1a\n", "png"), (b"\xff\xd8\xff", "mjpeg"))


def run(command, stdin=None):
    result = subprocess.run(command, input=stdin, capture_output=True)
    if result.returncode:
        lines = result.stderr.decode(errors="replace").strip().splitlines()
        raise ValueError("ffmpeg failed: "+(lines or ["no output"])[-1])


def export_viewer(trace, path):
    validate_trace(trace)
    payload = json.dumps(trace, separators=(",", ":"), allow_nan=False).replace("<", "\\u003c")
    template = Path(__file__).with_name("lerobot.html").read_text()
    Path(path).write_text(template.replace("__EPISODE_DATA__", payload))


def export(source, episode, output, revision=None, crf=23):
    output = Path(output)
    if output.exists() and any(output.iterdir()):
        raise ValueError(f"{output} is not empty; choose a fresh directory")
    source = Source(source, revision)
    trace = read_episode(source, episode)
    try:
        version = metadata.version("robot-reel")
    except metadata.PackageNotFoundError:
        version = None
    trace["exporter"] = {"robot_reel": version, "video": f"H.264 yuv420p crf {crf}, {trace['length']} frames per camera"}
    (output/"cameras").mkdir(parents=True, exist_ok=True)
    for camera in trace["cameras"]:
        target = output/camera["file"]
        if camera["kind"] == "video":
            encode_video(source, camera, trace["length"], trace["fps"], target, crf)
        else:
            encode_images(source, camera, trace["length"], trace["fps"], target, crf, episode)
    validate_trace(trace)
    (output/"episode.json").write_text(json.dumps(trace, indent=1, allow_nan=False)+"\n")
    export_viewer(trace, output/"index.html")
    files = ["episode.json", "index.html", *(c["file"] for c in trace["cameras"])]
    (output/"manifest.json").write_text(json.dumps({
        "schema": SCHEMA, "sha256": {name: digest(output/name) for name in sorted(files)},
    }, indent=2)+"\n")
    return check_media(output)


def finite(values):
    return all(v is None or (type(v) in (int, float) and math.isfinite(v)) for v in values)


def validate_trace(trace):
    if not isinstance(trace, dict) or trace.get("schema") != SCHEMA:
        raise ValueError("Unsupported LeRobot replay schema")
    dataset = trace.get("dataset")
    if not isinstance(dataset, dict) or dataset.get("codebase_version") not in FORMATS or dataset.get("kind") not in ("hub", "local"):
        raise ValueError("Invalid dataset description")
    if dataset["kind"] == "hub" and not re.fullmatch(r"[a-f0-9]{40}", str(dataset.get("revision"))):
        raise ValueError("Hub dataset is not pinned to a commit")
    length, fps = trace.get("length"), trace.get("fps")
    if type(length) is not int or not 2 <= length <= MAX_FRAMES or type(fps) not in (int, float) or not 0 < fps <= 1000:
        raise ValueError("Invalid episode length or frame rate")
    if type(trace.get("episode")) is not int or trace["episode"] < 0:
        raise ValueError("Invalid episode index")
    stamps = trace.get("timestamps")
    if not isinstance(stamps, list) or len(stamps) != length or not finite(stamps) or None in stamps \
            or any(b <= a for a, b in zip(stamps, stamps[1:])):
        raise ValueError("Timestamps must increase once per frame")
    series = trace.get("series")
    if not isinstance(series, list) or len({s.get("key") for s in series if isinstance(s, dict)}) != len(series):
        raise ValueError("Invalid signal list")
    for item in series:
        names, values = item.get("names"), item.get("values")
        if not isinstance(names, list) or not 1 <= len(names) <= MAX_DIMS or not isinstance(values, list) or len(values) != length:
            raise ValueError(f"{item.get('key')}: one value row per frame is required")
        if any(not isinstance(row, list) or len(row) != len(names) or not finite(row) for row in values):
            raise ValueError(f"{item['key']}: rows must hold {len(names)} finite values or null")
    cameras = trace.get("cameras")
    if not isinstance(cameras, list) or len({c.get("file") for c in cameras if isinstance(c, dict)}) != len(cameras):
        raise ValueError("Invalid camera list")
    for camera in cameras:
        if camera.get("kind") not in ("video", "image") or not re.fullmatch(r"cameras/[\w.-]+\.mp4", str(camera.get("file"))):
            raise ValueError("Invalid camera file")
        if camera["kind"] == "video" and (type(camera.get("from_timestamp")) not in (int, float) or camera["from_timestamp"] < 0):
            raise ValueError(f"{camera.get('key')}: missing source video offset")
    files = trace.get("source_files")
    if not isinstance(files, dict) or "meta/info.json" not in files or not all(re.fullmatch(r"[a-f0-9]{64}", str(v)) for v in files.values()):
        raise ValueError("Source files are not fingerprinted")
    if any(c["source"] not in files for c in cameras):
        raise ValueError("A camera's source file is not fingerprinted")
    return {"episode": trace["episode"], "frames": length, "fps": fps, "seconds": round(length/fps, 6),
            "signals": {s["key"]: len(s["names"]) for s in series}, "cameras": [c["key"] for c in cameras],
            "dataset": dataset.get("repo_id") or dataset.get("name"), "revision": dataset.get("revision")}


def verify(directory):
    directory = Path(directory)
    manifest = json.loads((directory/"manifest.json").read_text())
    trace = json.loads((directory/"episode.json").read_text())
    result = validate_trace(trace)
    expected = {"episode.json", "index.html", *(c["file"] for c in trace["cameras"])}
    listed = set(manifest.get("sha256", {}))
    if manifest.get("schema") != SCHEMA or listed not in (expected, expected | {FINDING}):
        raise ValueError("Incomplete LeRobot replay manifest")
    marked = FINDING in listed
    if marked and not (directory/FINDING).is_file():
        raise ValueError(f"manifest lists {FINDING} but the file is missing")
    if not marked and os.path.lexists(directory/FINDING):
        raise ValueError(f"{FINDING} is present but not listed in manifest.json; delete it or re-mark a fresh copy")
    for filename, value in manifest["sha256"].items():
        if digest(directory/filename) != value:
            raise ValueError(f"Hash mismatch: {filename}")
    html = (directory/"index.html").read_text()
    marker = EPISODE_MARKER
    if html.count(marker) != 1 or json.loads(html.split(marker)[1].split("</script>", 1)[0]) != trace:
        raise ValueError("Viewer differs from episode.json")
    embedded = html.count(FINDING_MARKER)
    if embedded > 1:
        raise ValueError("index.html embeds more than one finding; re-mark a fresh copy of the export")
    if embedded and not marked:
        raise ValueError(f"index.html embeds a finding but manifest.json lists no {FINDING}; re-mark a fresh copy of the export")
    if marked:
        result["finding"] = verify_finding(directory/FINDING, trace, manifest["sha256"]["episode.json"])
        if embedded:
            try:
                shown = json.loads(html.split(FINDING_MARKER)[1].split("</script>", 1)[0])
            except ValueError:
                raise ValueError("The finding embedded in index.html is not readable JSON") from None
            if shown != result["finding"]:
                raise ValueError(f"The finding embedded in index.html differs from {FINDING}")
        # Folders marked by 0.19.0 carry finding.json only; their page does not show it.
        result["finding_in_viewer"] = bool(embedded)
    return result


class FindingError(ValueError):
    """A finding input rule failed; field names the finding.json key at fault."""

    def __init__(self, field, message, disagrees=False):
        super().__init__(message)
        self.field = field
        self.disagrees = disagrees


def parse_signal(text):
    """Split KEY/NAME at the last slash, e.g. observation.state/shoulder_pan.pos."""
    key, slash, name = str(text).rpartition("/")
    if not slash or not key or not name:
        raise FindingError("signals", f"--signal {text!r} must be KEY/NAME, for example action/shoulder_pan.pos")
    return key, name


def validate_finding(trace, frame, signals, note):
    """Apply the input rules shared by --mark and verify; return each signal's recorded value at frame."""
    if not isinstance(note, str) or not 1 <= len(note) <= MAX_NOTE:
        raise FindingError("note", f"the note must have 1 to {MAX_NOTE} characters")
    if any(c != "\n" and unicodedata.category(c) == "Cc" for c in note):
        raise FindingError("note", "the note may not contain control characters other than newline")
    if not 1 <= len(signals) <= MAX_FINDING_SIGNALS:
        raise FindingError("signals", f"choose 1 to {MAX_FINDING_SIGNALS} signals; got {len(signals)}")
    for i, pair in enumerate(signals):
        if pair in signals[:i]:
            raise FindingError("signals", f"signal {pair[0]}/{pair[1]} is listed more than once")
    length = trace["length"]
    if type(frame) is not int:
        raise FindingError("frame", "the frame must be a whole number")
    if not 0 <= frame < length:
        raise FindingError("frame", f"frame {frame} is outside episode {trace['episode']}; choose 0..{length-1}", True)
    channels = {(s["key"], name): (s, i) for s in trace["series"] for i, name in enumerate(s["names"])}
    recorded = []
    for key, name in signals:
        if (key, name) not in channels:
            available = [f"{k}/{n}" for k, n in channels]
            shown = ", ".join(available[:40])+(f", ... ({len(available)-40} more)" if len(available) > 40 else "")
            raise FindingError("signals", f"{key}/{name} is not a channel in episode.json; available: {shown}", True)
        series, index = channels[(key, name)]
        recorded.append({"key": key, "name": name, "value": series["values"][frame][index]})
    return recorded


def verify_finding(path, trace, episode_sha256):
    """Check a listed finding.json against the input rules and the episode it was sealed from."""
    def invalid(field, detail):
        return ValueError(f"Invalid finding: {field} ({detail})")

    def disagrees(field, detail):
        return ValueError(f"Finding disagrees with episode.json: {field} ({detail})")

    try:
        finding = json.loads(path.read_text(encoding="utf-8"))
    except ValueError as exc:
        raise invalid("document", f"{FINDING} is not readable JSON") from exc
    if not isinstance(finding, dict):
        raise invalid("document", "expected a JSON object")
    odd = sorted(set(finding) ^ set(FINDING_KEYS))
    if odd:
        raise invalid(odd[0], "missing" if odd[0] in FINDING_KEYS else "unexpected key")
    if finding["schema"] != FINDING_SCHEMA:
        raise invalid("schema", f"expected {FINDING_SCHEMA}")
    if finding["limitations"] != FINDING_LIMITATIONS:
        raise invalid("limitations", "must be the fixed Robot Reel statement")
    if finding["robot_reel"] is not None and not isinstance(finding["robot_reel"], str):
        raise invalid("robot_reel", "must be a version string or null")
    if type(finding["episode"]) is not int:
        raise invalid("episode", "must be a whole number")
    signals = finding["signals"]
    if not isinstance(signals, list) or not all(
            isinstance(s, dict) and set(s) == {"key", "name", "value"} and isinstance(s["key"], str)
            and isinstance(s["name"], str) for s in signals):
        raise invalid("signals", "expected a list of {key, name, value} entries")
    try:
        recorded = validate_finding(trace, finding["frame"], [(s["key"], s["name"]) for s in signals], finding["note"])
    except FindingError as exc:
        raise (disagrees if exc.disagrees else invalid)(exc.field, str(exc)) from None
    frame = finding["frame"]
    if finding["episode"] != trace["episode"]:
        raise disagrees("episode", f"episode.json holds episode {trace['episode']}")
    if finding["episode_sha256"] != episode_sha256:
        raise disagrees("episode_sha256", "the finding was sealed against a different episode.json")
    stamp = finding["timestamp"]
    if type(stamp) not in (int, float) or stamp != trace["timestamps"][frame]:
        raise disagrees("timestamp", f"frame {frame} is at {trace['timestamps'][frame]} s")
    for given, expected in zip(signals, recorded):
        value, actual = given["value"], expected["value"]
        if (value is None) != (actual is None) or (
                value is not None and (type(value) not in (int, float) or value != actual)):
            raise disagrees("signals", f"{expected['key']}/{expected['name']} at frame {frame} is {actual} in episode.json")
    return finding


def package_version():
    try:
        return metadata.version("robot-reel")
    except metadata.PackageNotFoundError:
        return None


def replace_beside(path, text, mode_source, temporary):
    """Write text to a temporary file in path's folder, then rename it over path."""
    handle, name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    temporary.append(Path(name))
    with os.fdopen(handle, "w", encoding="utf-8") as stream:
        stream.write(text)
    shutil.copymode(mode_source, name)
    os.replace(name, path)


def mark(directory, frame, signals, note):
    """Seal one frame/channel observation into a verified, unmarked export as finding.json."""
    directory = Path(directory)
    verify(directory)
    manifest_path, target = directory/"manifest.json", directory/FINDING
    manifest = json.loads(manifest_path.read_text())
    if FINDING in manifest["sha256"]:
        raise ValueError(f"{target} already holds a finding and a bundle carries one; mark a fresh copy of the export instead")
    trace = json.loads((directory/"episode.json").read_text())
    recorded = validate_finding(trace, frame, [parse_signal(s) for s in signals], note)
    finding = {
        "schema": FINDING_SCHEMA, "episode": trace["episode"], "frame": frame,
        "timestamp": trace["timestamps"][frame], "signals": recorded, "note": note,
        "episode_sha256": manifest["sha256"]["episode.json"], "robot_reel": package_version(),
        "limitations": FINDING_LIMITATIONS,
    }
    text = json.dumps(finding, indent=2, allow_nan=False)+"\n"
    viewer_path = directory/"index.html"
    viewer = viewer_path.read_text()
    temporary, placed, rewritten, sealed = [], False, False, False
    try:
        replace_beside(target, text, manifest_path, temporary)
        placed = True
        replace_beside(viewer_path, embed_finding(viewer, finding), viewer_path, temporary)
        rewritten = True
        hashes = dict(manifest["sha256"])
        hashes[FINDING] = digest(target)
        hashes["index.html"] = digest(viewer_path)
        manifest["sha256"] = dict(sorted(hashes.items()))
        # The manifest is always replaced last; until then verify reports an unlisted finding.json.
        replace_beside(manifest_path, json.dumps(manifest, indent=2)+"\n", manifest_path, temporary)
        sealed = True
    except BaseException:
        for path in temporary:
            path.unlink(missing_ok=True)
        if rewritten and not sealed:
            replace_beside(viewer_path, viewer, viewer_path, [])
        if placed and not sealed:
            target.unlink(missing_ok=True)
        raise
    result = {"episode": finding["episode"], "frame": frame, "timestamp": finding["timestamp"],
              "signals": recorded, "output": str(target),
              # An export made before the viewer could show findings keeps its older page script.
              "viewer_shows_finding": "#finding-data" in viewer}
    missing = [f"{s['key']}/{s['name']}" for s in recorded if s["value"] is None]
    if missing:
        result["no_recorded_value"] = missing
    return result


def check_media(directory):
    import imageio_ffmpeg
    directory = Path(directory)
    result = verify(directory)
    trace = json.loads((directory/"episode.json").read_text())
    for camera in trace["cameras"]:
        count, duration = imageio_ffmpeg.count_frames_and_secs(str(directory/camera["file"]))
        if count != trace["length"] or abs(duration-count/trace["fps"]) > 1.5/trace["fps"]:
            raise ValueError(f"{camera['key']}: {count} video frames for {trace['length']} recorded frames")
    result["checked_video_frames"] = len(trace["cameras"])*trace["length"]
    return result


def check_source(directory, dataset=None):
    """Re-read the original dataset and require every exported value to match."""
    directory = Path(directory)
    trace = json.loads((directory/"episode.json").read_text())
    described = trace["dataset"]
    if dataset is None:
        if described["kind"] != "hub":
            raise ValueError("A local dataset export needs --dataset PATH to check its source")
        dataset = described["repo_id"]
    source = Source(dataset, described.get("revision") if described["kind"] == "hub" else None)
    fresh = read_episode(source, trace["episode"])
    for key in ("dataset", "fps", "length", "tasks", "timestamps", "series", "skipped", "source_files"):
        if fresh[key] != trace[key]:
            raise ValueError(f"Source dataset disagrees with the export: {key}")
    if [{k: v for k, v in c.items()} for c in fresh["cameras"]] != trace["cameras"]:
        raise ValueError("Source dataset disagrees with the export: cameras")
    result = verify(directory)
    result["checked_values"] = len(fresh["timestamps"])+sum(len(s["names"])*fresh["length"] for s in fresh["series"])
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(prog="robot-reel lerobot", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("source", help="Hub repo id (user/name), local dataset root, or an export with --verify")
    parser.add_argument("--episode", type=int, default=None, help="Episode index to export (default 0)")
    parser.add_argument("--revision", help="Hub branch, tag or commit; the export pins the resolved commit")
    parser.add_argument("--output", type=Path, help="Fresh directory for the replay (default artifacts/lerobot-<name>-<episode>)")
    parser.add_argument("--crf", type=int, default=None, help="H.264 quality for camera clips (default 23; lower is larger)")
    parser.add_argument("--verify", action="store_true", help="Check an existing export's manifest, schema and viewer")
    parser.add_argument("--check-media", action="store_true", help="With --verify: count every camera frame")
    parser.add_argument("--check-source", action="store_true", help="With --verify: re-read the dataset and compare every value")
    parser.add_argument("--dataset", help="With --check-source: local dataset root for a local export")
    parser.add_argument("--mark", type=int, metavar="FRAME",
                        help="Seal one observation at this zero-based frame into a verified export as finding.json")
    parser.add_argument("--signal", action="append", metavar="KEY/NAME",
                        help="With --mark: a series key and channel, e.g. action/shoulder_pan.pos (repeat, 1 to 8)")
    parser.add_argument("--note", metavar="TEXT", help="With --mark: what you observed (1 to 2000 characters)")
    args = parser.parse_args(argv)
    if args.mark is not None:
        combined = [flag for flag, given in (
            ("--verify", args.verify), ("--output", args.output is not None), ("--revision", args.revision is not None),
            ("--episode", args.episode is not None), ("--crf", args.crf is not None)) if given]
        if combined:
            parser.error(f"--mark edits an existing export in place; remove {', '.join(combined)}")
        if not args.signal:
            parser.error("--mark needs at least one --signal KEY/NAME, for example --signal action/shoulder_pan.pos")
        if args.note is None:
            parser.error("--mark needs --note TEXT describing what you observed (1 to 2000 characters)")
    elif args.signal or args.note is not None:
        parser.error("--signal and --note apply with --mark FRAME")
    args.episode = 0 if args.episode is None else args.episode
    args.crf = 23 if args.crf is None else args.crf
    if (args.check_media or args.check_source or args.dataset) and not args.verify:
        parser.error("--check-media, --check-source and --dataset apply with --verify")
    if not 0 <= args.crf <= 51:
        parser.error("--crf must be between 0 and 51")
    try:
        if args.mark is not None:
            result = mark(args.source, args.mark, args.signal, args.note)
        elif args.verify:
            result = verify(args.source)
            if args.check_media:
                result = check_media(args.source)
            if args.check_source:
                result |= check_source(args.source, args.dataset)
        else:
            try:
                import pyarrow  # noqa: F401
                import huggingface_hub  # noqa: F401
            except ImportError:
                parser.error("reading LeRobot datasets needs: pip install 'robot-reel[lerobot]'")
            output = args.output or Path("artifacts")/f"lerobot-{re.sub(r'[^\w.-]+', '-', Path(args.source).name)}-{args.episode}"
            result = export(args.source, args.episode, output, args.revision, args.crf)
            result["output"] = str(output/"index.html")
    except (ValueError, OSError, KeyError, TypeError) as exc:
        parser.error(str(exc))
    print(json.dumps(result, indent=2))
    if not args.verify and args.mark is None:
        print(f"Open {result['output']} in a browser; the folder works offline.")


if __name__ == "__main__":
    main()
