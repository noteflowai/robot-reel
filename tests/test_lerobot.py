import copy
from contextlib import redirect_stderr, redirect_stdout
import importlib.util
import io
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from robot_reel.compare import digest
from robot_reel.lerobot import export_viewer, main, validate_trace, verify

SITE = Path(__file__).resolve().parents[1]/"docs/lerobot"
HAS_READER = all(importlib.util.find_spec(m) for m in ("pyarrow", "numpy", "imageio_ffmpeg"))
FPS, LENGTHS = 10, (6, 8)


def level(index):
    """Gray level that identifies a global source frame after lossy coding."""
    return 20+14*index


class PublishedEpisodeTest(unittest.TestCase):
    def setUp(self):
        self.trace = json.loads((SITE/"episode.json").read_text())

    def test_published_so101_episode_is_pinned_and_complete(self):
        result = verify(SITE)
        self.assertEqual(result["dataset"], "lerobot/svla_so101_pickplace")
        self.assertEqual(result["revision"], "f641879e22172be7e8161d5e6c1503c2d2feb657")
        self.assertEqual((result["frames"], result["fps"]), (303, 30))
        self.assertEqual(result["signals"], {"action": 6, "observation.state": 6})
        self.assertEqual(result["cameras"], ["observation.images.up", "observation.images.side"])
        self.assertEqual(self.trace["tasks"], ["pink lego brick into the transparent box"])
        self.assertEqual(set(self.trace["source_files"]), {
            "meta/info.json", "data/chunk-000/file-000.parquet",
            "videos/observation.images.up/chunk-000/file-000.mp4",
            "videos/observation.images.side/chunk-000/file-000.mp4"})

    def test_tampered_files_and_malformed_traces_fail(self):
        with tempfile.TemporaryDirectory() as temporary:
            copy_dir = Path(temporary)/"episode"
            shutil.copytree(SITE, copy_dir)
            (copy_dir/"cameras/up.mp4").write_bytes(b"not a video")
            with self.assertRaisesRegex(ValueError, "Hash mismatch"):
                verify(copy_dir)
        for change in (
            lambda t: t["timestamps"].__setitem__(5, t["timestamps"][4]),
            lambda t: t["series"][0]["values"].pop(),
            lambda t: t["series"][0]["values"][0].append(1.),
            lambda t: t["series"][0]["values"][0].__setitem__(0, "1"),
            lambda t: t["dataset"].__setitem__("revision", "main"),
            lambda t: t["cameras"][0].__setitem__("file", "../escape.mp4"),
            lambda t: t["source_files"].pop(t["cameras"][0]["source"]),
            lambda t: t.__setitem__("length", 1),
        ):
            trace = copy.deepcopy(self.trace)
            change(trace)
            with self.subTest(change=change), self.assertRaises(ValueError):
                validate_trace(trace)

    def test_viewer_must_embed_the_recorded_episode(self):
        with tempfile.TemporaryDirectory() as temporary:
            copy_dir = Path(temporary)/"episode"
            shutil.copytree(SITE, copy_dir)
            trace = copy.deepcopy(self.trace)
            trace["tasks"] = ["another task"]
            export_viewer(trace, copy_dir/"index.html")
            manifest = json.loads((copy_dir/"manifest.json").read_text())
            manifest["sha256"]["index.html"] = digest(copy_dir/"index.html")
            (copy_dir/"manifest.json").write_text(json.dumps(manifest))
            with self.assertRaisesRegex(ValueError, "Viewer differs"):
                verify(copy_dir)

    def test_media_and_source_flags_require_verify(self):
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            main([str(SITE), "--check-media"])


@unittest.skipUnless(HAS_READER, "Install robot-reel[lerobot] to read parquet datasets")
class SyntheticDatasetTest(unittest.TestCase):
    """Two episodes share one video file (v3.0) or have their own (v2.1)."""

    def encode(self, path, first, count):
        import imageio_ffmpeg
        path.parent.mkdir(parents=True, exist_ok=True)
        frames = b"".join(bytes([level(first+i)])*(64*48*3) for i in range(count))
        subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
                        "-s", "64x48", "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-qp", "0",
                        "-pix_fmt", "yuv444p", str(path)], input=frames, check=True)

    def frames(self, root, episode, start):
        import pyarrow as pa
        count = LENGTHS[episode]
        return pa.table({
            "action": pa.array([[float(start+i), -.5] for i in range(count)], pa.list_(pa.float32(), 2)),
            "observation.state": pa.array([[start+i+.25, -.5] for i in range(count)], pa.list_(pa.float32(), 2)),
            "next.done": [i == count-1 for i in range(count)],
            "timestamp": pa.array([i/FPS for i in range(count)], pa.float32()),
            "frame_index": list(range(count)), "episode_index": [episode]*count,
            "index": list(range(start, start+count)), "task_index": [0]*count,
        })

    def info(self, version, data_path, video_path):
        motors = {"dtype": "float32", "shape": [2], "names": {"motors": ["lift", "grip"]}}
        return {"codebase_version": version, "robot_type": "synthetic", "fps": FPS, "chunks_size": 1000,
                "total_episodes": 2, "data_path": data_path, "video_path": video_path, "features": {
                    "observation.images.top": {"dtype": "video", "shape": [48, 64, 3]},
                    "action": motors, "observation.state": motors,
                    "next.done": {"dtype": "bool", "shape": [1]},
                    "timestamp": {"dtype": "float32", "shape": [1]},
                    "frame_index": {"dtype": "int64", "shape": [1]}, "episode_index": {"dtype": "int64", "shape": [1]},
                    "index": {"dtype": "int64", "shape": [1]}, "task_index": {"dtype": "int64", "shape": [1]},
                    "language_embedding": {"dtype": "float32", "shape": [512]}}}

    def v3(self, root):
        import pyarrow as pa
        import pyarrow.parquet as pq
        (root/"meta/episodes/chunk-000").mkdir(parents=True)
        (root/"data/chunk-000").mkdir(parents=True)
        (root/"meta/info.json").write_text(json.dumps(self.info(
            "v3.0", "data/chunk-{chunk_index:03d}/file-{file_index:03d}.parquet",
            "videos/{video_key}/chunk-{chunk_index:03d}/file-{file_index:03d}.mp4")))
        pq.write_table(pa.concat_tables([self.frames(root, 0, 0), self.frames(root, 1, LENGTHS[0])]),
                       root/"data/chunk-000/file-000.parquet")
        self.encode(root/"videos/observation.images.top/chunk-000/file-000.mp4", 0, sum(LENGTHS))
        pq.write_table(pa.table({
            "episode_index": [0, 1], "data/chunk_index": [0, 0], "data/file_index": [0, 0],
            "videos/observation.images.top/chunk_index": [0, 0], "videos/observation.images.top/file_index": [0, 0],
            "videos/observation.images.top/from_timestamp": [0., LENGTHS[0]/FPS],
            "videos/observation.images.top/to_timestamp": [LENGTHS[0]/FPS, sum(LENGTHS)/FPS],
            "tasks": [["lift the block"], ["lift the block"]], "length": list(LENGTHS),
            "stats/action/mean": [[0., 0.], [0., 0.]],
        }), root/"meta/episodes/chunk-000/file-000.parquet")

    def v21(self, root):
        import pyarrow.parquet as pq
        (root/"meta").mkdir(parents=True)
        (root/"data/chunk-000").mkdir(parents=True)
        (root/"meta/info.json").write_text(json.dumps(self.info(
            "v2.1", "data/chunk-{episode_chunk:03d}/episode_{episode_index:06d}.parquet",
            "videos/chunk-{episode_chunk:03d}/{video_key}/episode_{episode_index:06d}.mp4")))
        (root/"meta/episodes.jsonl").write_text("".join(json.dumps(
            {"episode_index": e, "tasks": ["lift the block"], "length": LENGTHS[e]})+"\n" for e in (0, 1)))
        for episode, start in ((0, 0), (1, LENGTHS[0])):
            pq.write_table(self.frames(root, episode, start), root/f"data/chunk-000/episode_{episode:06d}.parquet")
            self.encode(root/f"videos/chunk-000/observation.images.top/episode_{episode:06d}.mp4", start, LENGTHS[episode])

    def decoded_levels(self, path):
        import imageio_ffmpeg
        reader = imageio_ffmpeg.read_frames(str(path))
        try:
            next(reader)
            return [sum(frame)/len(frame) for frame in reader]
        finally:
            reader.close()

    def test_second_episode_is_cut_at_its_recorded_offset_and_checks_against_its_source(self):
        for layout in (self.v3, self.v21):
            with self.subTest(layout=layout.__name__), tempfile.TemporaryDirectory() as temporary:
                root, output = Path(temporary)/"dataset", Path(temporary)/"replay"
                layout(root)
                with redirect_stderr(io.StringIO()), redirect_stdout(io.StringIO()):
                    main([str(root), "--episode", "1", "--output", str(output), "--crf", "18"])
                trace = json.loads((output/"episode.json").read_text())
                self.assertEqual(trace["length"], LENGTHS[1])
                self.assertEqual(trace["tasks"], ["lift the block"])
                self.assertEqual(trace["series"][0]["key"], "action")
                self.assertEqual(trace["series"][0]["names"], ["lift", "grip"])
                self.assertEqual([row[0] for row in trace["series"][0]["values"]], list(range(6, 14)))
                self.assertEqual(trace["series"][1]["values"][0], [6.25, -.5])
                self.assertEqual(trace["series"][2]["values"], [[0]]*7+[[1]])
                self.assertEqual(trace["timestamps"][:3], [0., .1, .2])
                self.assertEqual(trace["skipped"], [{"key": "language_embedding", "dtype": "float32", "reason": "not in data file"}])
                # Every clip frame must come from the second episode, in order.
                levels = self.decoded_levels(output/trace["cameras"][0]["file"])
                self.assertEqual(len(levels), LENGTHS[1])
                for i, value in enumerate(levels):
                    self.assertLess(abs(value-level(LENGTHS[0]+i)), 4, f"clip frame {i}")
                with redirect_stderr(io.StringIO()), redirect_stdout(io.StringIO()):
                    main([str(output), "--verify", "--check-media", "--check-source", "--dataset", str(root)])
                # A changed source value is caught by the source check.
                import pyarrow as pa
                import pyarrow.parquet as pq
                name = next(n for n in trace["source_files"] if n.endswith(".parquet"))
                table = pq.read_table(root/name)
                rows = table.column("action").to_pylist()
                rows[-1] = [99., 99.]
                table = table.set_column(table.column_names.index("action"), "action",
                                         pa.array(rows, table.schema.field("action").type))
                pq.write_table(table, root/name)
                stderr = io.StringIO()
                with redirect_stderr(stderr), self.assertRaises(SystemExit):
                    main([str(output), "--verify", "--check-source", "--dataset", str(root)])
                self.assertIn("disagrees with the export: series", stderr.getvalue())

    def test_missing_episode_and_unsupported_version_fail_clearly(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)/"dataset"
            self.v3(root)
            for argv, message in (([str(root), "--episode", "7"], "Episode 7 is not in this dataset"),):
                stderr = io.StringIO()
                with redirect_stderr(stderr), self.assertRaises(SystemExit):
                    main(argv+["--output", str(Path(temporary)/"out")])
                self.assertIn(message, stderr.getvalue())
            info = json.loads((root/"meta/info.json").read_text())
            (root/"meta/info.json").write_text(json.dumps(info | {"codebase_version": "v1.6"}))
            stderr = io.StringIO()
            with redirect_stderr(stderr), self.assertRaises(SystemExit):
                main([str(root), "--output", str(Path(temporary)/"out2")])
            self.assertIn("Unsupported LeRobotDataset version", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
