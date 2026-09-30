"""LeRobot timeline errors name the data file, episode and first bad frame_index (RR-01).

All fixtures are synthetic. FakeReaderTimelineTest swaps in a labeled stand-in
for pyarrow.parquet: each data file holds its columns as JSON, and rows are
filtered by episode_index and sorted by frame_index with nulls last, as pyarrow
does. That lets the whole export, --verify, --check-media and --check-source
path run without the lerobot extra. No camera is declared, so no media is
encoded. RealReaderTimelineTest repeats every case on real parquet files and is
skipped when pyarrow, numpy, huggingface_hub or imageio_ffmpeg is missing.
"""
from contextlib import contextmanager, nullcontext, redirect_stderr, redirect_stdout
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest

from robot_reel.lerobot import main

HAS_REAL_READER = all(importlib.util.find_spec(m) for m in ("pyarrow", "numpy", "huggingface_hub", "imageio_ffmpeg"))
FPS, LENGTH = 10, 6
DATA = "data/chunk-000/episode_000000.parquet"
REPAIR = "Robot Reel does not reorder, fill or interpolate frames; repair or re-export the episode."
FAKED = ("pyarrow", "pyarrow.parquet", "huggingface_hub", "imageio_ffmpeg")


def stamps(count):
    return [i/FPS for i in range(count)]


class FakeTable:
    """Synthetic stand-in for the pyarrow.Table members read_episode uses."""

    def __init__(self, columns):
        self.columns = columns
        self.column_names = list(columns)
        self.num_rows = len(columns["episode_index"])

    def sort_by(self, name):
        values = self.columns[name]
        order = sorted(range(self.num_rows), key=lambda r: (values[r] is None, 0 if values[r] is None else values[r]))
        return FakeTable({k: [v[r] for r in order] for k, v in self.columns.items()})

    def to_pydict(self):
        return {k: list(v) for k, v in self.columns.items()}


def fake_read_table(path, columns=None, filters=None):
    stored = json.loads(Path(path).read_text())
    rows = range(len(stored["episode_index"]))
    for name, op, value in filters or ():
        assert op == "="
        rows = [r for r in rows if stored[name][r] == value]
    return FakeTable({k: [v[r] for r in rows] for k, v in stored.items()})


@contextmanager
def fake_modules():
    parquet = types.ModuleType("pyarrow.parquet")
    parquet.read_table = fake_read_table
    pyarrow = types.ModuleType("pyarrow")
    pyarrow.parquet = parquet
    ffmpeg = types.ModuleType("imageio_ffmpeg")

    def no_media(*args, **kwargs):
        raise AssertionError("these fixtures declare no camera")
    ffmpeg.get_ffmpeg_exe = ffmpeg.count_frames_and_secs = no_media
    saved = {name: sys.modules.get(name) for name in FAKED}
    sys.modules.update({"pyarrow": pyarrow, "pyarrow.parquet": parquet,
                        "huggingface_hub": types.ModuleType("huggingface_hub"), "imageio_ffmpeg": ffmpeg})
    try:
        yield
    finally:
        for name, module in saved.items():
            if module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = module


class TimelineCases:
    """One synthetic local v2.1 episode of LENGTH frames, damaged per case."""

    def write(self, root, frame_index, timestamps, metadata_length=LENGTH, float_index=False):
        count = len(frame_index)
        (root/"meta").mkdir(parents=True)
        (root/"data/chunk-000").mkdir(parents=True)
        motors = {"dtype": "float64", "shape": [2], "names": {"motors": ["lift", "grip"]}}

        def one(dtype):
            return {"dtype": dtype, "shape": [1]}
        (root/"meta/info.json").write_text(json.dumps({
            "codebase_version": "v2.1", "robot_type": "synthetic", "fps": FPS, "chunks_size": 1000, "total_episodes": 1,
            "data_path": "data/chunk-{episode_chunk:03d}/episode_{episode_index:06d}.parquet",
            "video_path": "videos/chunk-{episode_chunk:03d}/{video_key}/episode_{episode_index:06d}.mp4",
            "features": {"action": motors, "next.done": one("bool"), "timestamp": one("float64"),
                         "frame_index": one("float64" if float_index else "int64"), "episode_index": one("int64"),
                         "index": one("int64"), "task_index": one("int64")}}))
        (root/"meta/episodes.jsonl").write_text(json.dumps(
            {"episode_index": 0, "tasks": ["lift the block"], "length": metadata_length})+"\n")
        self.store(root/DATA, {
            "action": [[float(i), -.5] for i in range(count)], "next.done": [i == count-1 for i in range(count)],
            "timestamp": list(timestamps),
            "frame_index": [None if v is None else float(v) if float_index else v for v in frame_index],
            "episode_index": [0]*count, "index": list(range(count)), "task_index": [0]*count}, float_index)

    def rejected(self, frame_index, timestamps=None, metadata_length=LENGTH):
        with tempfile.TemporaryDirectory() as temporary, self.reader():
            root, output = Path(temporary)/"dataset", Path(temporary)/"replay"
            self.write(root, frame_index, stamps(len(frame_index)) if timestamps is None else timestamps, metadata_length)
            stderr = io.StringIO()
            with redirect_stderr(stderr), redirect_stdout(io.StringIO()), self.assertRaises(SystemExit) as caught:
                main([str(root), "--episode", "0", "--output", str(output)])
            self.assertEqual(caught.exception.code, 2)
            self.assertFalse(output.exists(), "a rejected episode must write nothing")
            message = stderr.getvalue()
            self.assertIn(DATA, message)
            for text in (temporary, str(Path(temporary).resolve()), "Traceback", "TypeError", "not supported between"):
                self.assertNotIn(text, message)
            return message

    def test_mid_episode_gap_names_the_missing_frame_not_the_count(self):
        message = self.rejected([0, 1, 2, 4, 5], [0., .1, .2, .4, .5])
        self.assertIn(f"Episode 0 in {DATA} is missing frame_index 3 (next recorded frame_index is 4)", message)
        self.assertNotIn("Episode metadata lists", message)
        self.assertIn(REPAIR, message)
        self.assertIn("missing frame_index 0 (next recorded frame_index is 1)", self.rejected([1, 2, 3, 4, 5, 6]))

    def test_repeated_null_and_negative_frame_indices_are_named(self):
        for frames, text in (([0, 1, 2, 2, 4, 5], f"Episode 0 in {DATA} repeats frame_index 2;"),
                             ([0, 1, 2, 3, 4, None], f"Episode 0 in {DATA} has frame_index None where 5 was expected"),
                             ([-1, 1, 2, 3, 4, 5], f"Episode 0 in {DATA} has frame_index -1 where 0 was expected")):
            with self.subTest(frames=frames):
                message = self.rejected(frames)
                self.assertIn(text, message)
                self.assertIn(REPAIR, message)

    def test_missing_trailing_frame_keeps_the_length_message(self):
        self.assertIn(f"Episode metadata lists 6 frames but {DATA} holds 5", self.rejected([0, 1, 2, 3, 4]))

    def test_null_and_repeated_timestamps_are_named(self):
        message = self.rejected(list(range(LENGTH)), [0., .1, None, .3, .4, .5])
        self.assertIn(f"Episode 0 in {DATA} has no finite timestamp at frame_index 2.", message)
        self.assertIn(REPAIR, message)
        message = self.rejected(list(range(LENGTH)), [0., .1, .2, .3, .3, .5])
        self.assertIn(f"Episode 0 in {DATA}: timestamp at frame_index 4 (0.3 s) is not after frame_index 3 (0.3 s).", message)
        self.assertIn(REPAIR, message)

    def test_float_frame_indices_equal_to_positions_still_export_and_check(self):
        traces = {}
        with tempfile.TemporaryDirectory() as temporary, self.reader():
            for float_index in (False, True):
                root, output = Path(temporary)/f"dataset-{float_index}", Path(temporary)/f"replay-{float_index}"
                self.write(root, list(range(LENGTH)), stamps(LENGTH), float_index=float_index)
                with redirect_stderr(io.StringIO()), redirect_stdout(io.StringIO()):
                    main([str(root), "--episode", "0", "--output", str(output)])
                    main([str(output), "--verify", "--check-media", "--check-source", "--dataset", str(root)])
                traces[float_index] = json.loads((output/"episode.json").read_text())
        self.assertEqual(traces[True]["length"], LENGTH)
        self.assertEqual(traces[True]["timestamps"], stamps(LENGTH))
        for key in ("length", "timestamps", "series", "cameras", "skipped"):
            self.assertEqual(traces[True][key], traces[False][key], key)


class FakeReaderTimelineTest(TimelineCases, unittest.TestCase):
    reader = staticmethod(fake_modules)

    def store(self, path, columns, float_index):
        path.write_text(json.dumps(columns))


@unittest.skipUnless(HAS_REAL_READER, "Install robot-reel[lerobot] to repeat these cases on real parquet files")
class RealReaderTimelineTest(TimelineCases, unittest.TestCase):
    reader = staticmethod(nullcontext)

    def store(self, path, columns, float_index):
        import pyarrow as pa
        import pyarrow.parquet as pq
        pq.write_table(pa.table({
            "action": pa.array(columns["action"], pa.list_(pa.float64(), 2)),
            "next.done": pa.array(columns["next.done"], pa.bool_()),
            "timestamp": pa.array(columns["timestamp"], pa.float64()),
            "frame_index": pa.array(columns["frame_index"], pa.float64() if float_index else pa.int64()),
            "episode_index": pa.array(columns["episode_index"], pa.int64()),
            "index": pa.array(columns["index"], pa.int64()),
            "task_index": pa.array(columns["task_index"], pa.int64()),
        }), path)


if __name__ == "__main__":
    unittest.main()
