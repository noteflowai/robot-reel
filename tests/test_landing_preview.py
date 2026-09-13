import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from scripts.build_landing_preview import MANIFEST, VIDEO, verify
from robot_reel.chaos import digest

ROOT = Path(__file__).resolve().parents[1]


class LandingPreviewTest(unittest.TestCase):
    def test_preview_retains_the_verified_recording_and_sample_mapping(self):
        metadata = verify()
        self.assertEqual(metadata["source_samples"], list(range(0, 601, 10)))
        self.assertEqual(metadata["fps"], 10)

    def test_relabelled_samples_cannot_survive_an_unchanged_video_hash(self):
        metadata = json.loads((ROOT/"docs/showcase"/MANIFEST).read_text())
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root/"docs/showcase"
            output.mkdir(parents=True)
            (output/VIDEO).symlink_to(ROOT/"docs/showcase"/VIDEO)
            changed = dict(metadata, source_samples=list(reversed(metadata["source_samples"])))
            (output/MANIFEST).write_text(json.dumps(changed))
            source = {key: value for key, value in metadata.items() if key != "video_sha256"}
            with patch("scripts.build_landing_preview.provenance", return_value=source):
                with self.assertRaisesRegex(ValueError, "source mapping"):
                    verify(root)

    @unittest.skipUnless(importlib.util.find_spec("imageio_ffmpeg") and importlib.util.find_spec("PIL"),
                         "Install rendering dependencies for decoded preview checks")
    def test_every_decoded_frame_and_its_clock_match_the_source_gif(self):
        verify(check_media=True)

    @unittest.skipUnless(importlib.util.find_spec("imageio_ffmpeg") and importlib.util.find_spec("PIL"),
                         "Install rendering dependencies for native clock checks")
    def test_retimed_video_is_rejected_even_after_its_hash_is_updated(self):
        import imageio_ffmpeg
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root/"docs/showcase"
            output.mkdir(parents=True)
            (root/"docs/chaos").symlink_to(ROOT/"docs/chaos", target_is_directory=True)
            # Remux the same encoded pictures with doubled timestamps. Hash
            # checks alone cannot detect a recording played on the wrong clock.
            subprocess.run(
                [imageio_ffmpeg.get_ffmpeg_exe(), "-loglevel", "error",
                 "-itsscale", "2", "-i", str(ROOT/"docs/showcase"/VIDEO),
                 "-c", "copy", str(output/VIDEO)],
                check=True, capture_output=True, timeout=30,
            )
            metadata = json.loads((ROOT/"docs/showcase"/MANIFEST).read_text())
            metadata["video_sha256"] = digest(output/VIDEO)
            (output/MANIFEST).write_text(json.dumps(metadata))
            with self.assertRaisesRegex(ValueError, "native clock"):
                verify(root, check_media=True)
