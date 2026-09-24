"""Replay one LeRobotDataset episode offline, with its source files on record.

    robot-reel lerobot lerobot/svla_so101_pickplace --episode 0 --output artifacts/so101
    robot-reel lerobot ~/datasets/my_so101_run --episode 3 --output artifacts/mine
    robot-reel lerobot artifacts/so101 --verify --check-media --check-source

Reading a dataset needs the `lerobot` extra (pyarrow, huggingface_hub); the
LeRobot library itself is not imported. --verify alone uses only the standard
library; --check-media adds the bundled ffmpeg. Formats v2.0, v2.1 and v3.0 are supported.
"""
import argparse
from importlib import metadata
import json
import math
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

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
    if row.get("length") not in (None, length):
        raise ValueError(f"Episode metadata lists {row['length']} frames but {data} holds {length}")
    columns = table.to_pydict()
    for name in ("timestamp", "frame_index"):
        if name not in columns:
            raise ValueError(f"Data file has no {name} column")
    timestamps = [scalar(v, info["features"].get("timestamp", {}).get("dtype", "float32")) for v in flatten(columns["timestamp"])]
    if columns["frame_index"] != list(range(length)):
        raise ValueError("Frame indices are not 0..length-1")
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
    with tempfile.TemporaryDirectory() as temporary:
        for i, image in enumerate(frames):
            payload = image.get("bytes") if isinstance(image, dict) else None
            if not payload:
                raise ValueError(f"{camera['key']}: frame {i} has no embedded image bytes")
            Path(temporary, f"{i:06d}.img").write_bytes(payload)
        run([ffmpeg(), "-v", "error", "-y", "-framerate", repr(fps), "-i", str(Path(temporary, "%06d.img")),
             "-frames:v", str(length), "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2", "-c:v", "libx264",
             "-preset", "medium", "-crf", str(crf), "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(output)])


def run(command):
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode:
        raise ValueError("ffmpeg failed: "+(result.stderr.strip().splitlines() or ["no output"])[-1])


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
    if manifest.get("schema") != SCHEMA or set(manifest.get("sha256", {})) != expected:
        raise ValueError("Incomplete LeRobot replay manifest")
    for filename, value in manifest["sha256"].items():
        if digest(directory/filename) != value:
            raise ValueError(f"Hash mismatch: {filename}")
    html = (directory/"index.html").read_text()
    marker = '<script id="episode-data" type="application/json">'
    if html.count(marker) != 1 or json.loads(html.split(marker)[1].split("</script>", 1)[0]) != trace:
        raise ValueError("Viewer differs from episode.json")
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
    parser.add_argument("--episode", type=int, default=0)
    parser.add_argument("--revision", help="Hub branch, tag or commit; the export pins the resolved commit")
    parser.add_argument("--output", type=Path, help="Fresh directory for the replay (default artifacts/lerobot-<name>-<episode>)")
    parser.add_argument("--crf", type=int, default=23, help="H.264 quality for camera clips (default 23; lower is larger)")
    parser.add_argument("--verify", action="store_true", help="Check an existing export's manifest, schema and viewer")
    parser.add_argument("--check-media", action="store_true", help="With --verify: count every camera frame")
    parser.add_argument("--check-source", action="store_true", help="With --verify: re-read the dataset and compare every value")
    parser.add_argument("--dataset", help="With --check-source: local dataset root for a local export")
    args = parser.parse_args(argv)
    if (args.check_media or args.check_source or args.dataset) and not args.verify:
        parser.error("--check-media, --check-source and --dataset apply with --verify")
    if not 0 <= args.crf <= 51:
        parser.error("--crf must be between 0 and 51")
    try:
        if args.verify:
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
    if not args.verify:
        print(f"Open {result['output']} in a browser; the folder works offline.")


if __name__ == "__main__":
    main()
