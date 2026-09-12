"""Every recorded video must be encoded at the same quality.

imageio-ffmpeg maps `quality` to `-crf 51*(1 - quality/10)`, so a stray value
changes file size by multiples. Transcoding one published 256x256 trial camera
through this writer measures the spread against the current published clip:

    quality=8  (crf 10)   72% of the size, PSNR 47.8 dB, SSIM 0.998
    quality=7  (crf 15)   47%             , PSNR 46.5 dB, SSIM 0.996
    quality=6  (crf 20)   28%             , PSNR 44.3 dB, SSIM 0.993

Six writers already agreed on 8; the two recorders that drifted to 9 (crf 5)
produced the heaviest files in the repository. This keeps them together, so
changing the trade-off stays one deliberate edit rather than a per-file accident.
"""
import ast
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
QUALITY = 8


def writer_qualities():
    """Yield (location, quality) for every imageio-ffmpeg video writer call."""
    for path in sorted((ROOT/"robot_reel").glob("*.py")) + sorted((ROOT/"scripts").glob("*.py")):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                continue
            if node.func.attr != "write_frames":
                continue
            quality = next((word.value for word in node.keywords if word.arg == "quality"), None)
            location = f"{path.relative_to(ROOT)}:{node.lineno}"
            yield location, quality if quality is None else ast.literal_eval(quality)


class EncodingTest(unittest.TestCase):
    def test_every_writer_uses_the_same_quality(self):
        calls = list(writer_qualities())
        self.assertGreaterEqual(len(calls), 8, "no video writers found")
        self.assertEqual([call for call in calls if call[1] != QUALITY], [],
                         f"these writers disagree with quality={QUALITY}")
