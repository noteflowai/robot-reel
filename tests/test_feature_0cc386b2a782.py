"""Camera errors in LeRobot v3.0 exports name the camera, the file and a repair step.

Every dataset here is a small synthetic fixture built in a temporary directory.
"""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

REPOSITORY = Path(__file__).resolve().parents[1]
CLI_TIMEOUT = 120

HAS_READER = all(importlib.util.find_spec(m) for m in ("pyarrow", "numpy", "imageio_ffmpeg", "huggingface_hub"))
FPS, LENGTH = 10, 6
TOP = "observation.images.top"
VIDEO = f"videos/{TOP}/chunk-000/file-000.mp4"
DATA = "data/chunk-000/file-000.parquet"
EPISODES = "meta/episodes/chunk-000/file-000.parquet"


@unittest.skipUnless(HAS_READER, "Install robot-reel[lerobot] to read parquet datasets")
class CameraErrorTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.temporary = temporary.name
        self.root = Path(temporary.name)/"dataset"
        self.output = Path(temporary.name)/"replay"
        self.build()

    def build(self):
        """One synthetic v3.0 episode with one video camera."""
        import imageio_ffmpeg
        import pyarrow as pa
        import pyarrow.parquet as pq
        root = self.root
        for folder in ("meta/episodes/chunk-000", "data/chunk-000", f"videos/{TOP}/chunk-000"):
            (root/folder).mkdir(parents=True)
        motors = {"dtype": "float32", "shape": [2], "names": {"motors": ["lift", "grip"]}}
        scalar = {"dtype": "int64", "shape": [1]}
        (root/"meta/info.json").write_text(json.dumps({
            "codebase_version": "v3.0", "robot_type": "synthetic", "fps": FPS, "chunks_size": 1000,
            "total_episodes": 1, "data_path": "data/chunk-{chunk_index:03d}/file-{file_index:03d}.parquet",
            "video_path": "videos/{video_key}/chunk-{chunk_index:03d}/file-{file_index:03d}.mp4",
            "features": {TOP: {"dtype": "video", "shape": [48, 64, 3]}, "action": motors,
                         "timestamp": {"dtype": "float32", "shape": [1]}, "frame_index": scalar,
                         "episode_index": scalar, "index": scalar, "task_index": scalar}}))
        pq.write_table(pa.table({
            "action": pa.array([[float(i), -.5] for i in range(LENGTH)], pa.list_(pa.float32(), 2)),
            "timestamp": pa.array([i/FPS for i in range(LENGTH)], pa.float32()),
            "frame_index": list(range(LENGTH)), "episode_index": [0]*LENGTH,
            "index": list(range(LENGTH)), "task_index": [0]*LENGTH,
        }), root/DATA)
        frames = b"".join(bytes([20+14*i])*(64*48*3) for i in range(LENGTH))
        subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
                        "-s", "64x48", "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-qp", "0",
                        "-pix_fmt", "yuv444p", str(root/VIDEO)], input=frames, check=True)
        pq.write_table(pa.table({
            "episode_index": [0], "data/chunk_index": [0], "data/file_index": [0],
            f"videos/{TOP}/chunk_index": [0], f"videos/{TOP}/file_index": [0],
            f"videos/{TOP}/from_timestamp": [0.], f"videos/{TOP}/to_timestamp": [LENGTH/FPS],
            "tasks": [["lift the block"]], "length": [LENGTH],
        }), root/EPISODES)

    def cli(self, *args):
        """Run the LeRobot CLI in a child process with stdin closed and a time limit.

        A child process keeps ffmpeg away from the test runner's stdin. A hang or crash then
        shows up as an assertion failure, not as a stalled or killed test run.
        """
        paths = [str(REPOSITORY), os.environ.get("PYTHONPATH")]
        env = dict(os.environ, PYTHONPATH=os.pathsep.join(p for p in paths if p))
        try:
            return subprocess.run([sys.executable, "-m", "robot_reel.lerobot", *map(str, args)],
                                  stdin=subprocess.DEVNULL, capture_output=True, text=True,
                                  timeout=CLI_TIMEOUT, env=env, cwd=self.temporary)
        except subprocess.TimeoutExpired:
            self.fail(f"robot-reel lerobot did not finish within {CLI_TIMEOUT} s")

    def failed_export(self):
        """Run the export CLI, expect exit status 2 and return stderr."""
        result = self.cli(self.root, "--episode", "0", "--output", self.output)
        message = result.stderr
        self.assertEqual(result.returncode, 2, message)
        self.assertNotIn("Traceback", message)
        for local in {self.temporary, str(Path(self.temporary).resolve())}:
            self.assertNotIn(local, message)
        return message

    def test_corrupt_camera_video_names_camera_file_and_repair(self):
        (self.root/VIDEO).write_bytes(b"not a video")
        message = self.failed_export()
        self.assertIn(f"{TOP}: cannot read camera video {VIDEO} (", message)
        self.assertIn("re-download the dataset or re-encode this camera", message)
        self.assertNotIn("ffmpeg failed", message)

    def test_missing_per_camera_video_column_names_episodes_file(self):
        import pyarrow.parquet as pq
        column = f"videos/{TOP}/from_timestamp"
        table = pq.read_table(self.root/EPISODES)
        pq.write_table(table.remove_column(table.column_names.index(column)), self.root/EPISODES)
        message = self.failed_export()
        self.assertIn(f"{TOP}: {EPISODES} has no {column} for episode 0", message)
        self.assertIn("Re-run LeRobot's v3.0 conversion", message)
        self.assertFalse(self.output.exists())

    def test_declared_image_feature_without_column_is_reported_before_output(self):
        info = json.loads((self.root/"meta/info.json").read_text())
        info["features"]["observation.images.wrist"] = {"dtype": "image", "shape": [48, 64, 3]}
        (self.root/"meta/info.json").write_text(json.dumps(info))
        message = self.failed_export()
        self.assertIn("observation.images.wrist: meta/info.json declares an image feature but "
                      f"{DATA} has no observation.images.wrist column", message)
        self.assertNotIn("FieldRef", message)
        self.assertFalse(self.output.exists())

    def test_intact_export_still_verifies_and_missing_video_message_is_unchanged(self):
        for args in ([self.root, "--episode", "0", "--output", self.output],
                     [self.output, "--verify", "--check-media", "--check-source", "--dataset", self.root]):
            result = self.cli(*args)
            self.assertEqual(result.returncode, 0, result.stderr)
        trace = json.loads((self.output/"episode.json").read_text())
        self.assertEqual(set(trace), {"schema", "dataset", "episode", "fps", "length", "tasks", "timestamps",
                                      "series", "cameras", "skipped", "source_files", "exporter"})
        self.assertEqual(set(json.loads((self.output/"manifest.json").read_text())), {"schema", "sha256"})
        self.assertEqual(trace["cameras"][0]["source"], VIDEO)
        (self.root/VIDEO).unlink()
        self.output = Path(self.temporary)/"replay-again"
        self.assertIn("Missing dataset file: videos/", self.failed_export())


if __name__ == "__main__":
    unittest.main()
