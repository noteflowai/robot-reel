"""No tracked file may exceed 25 MB.

Large bundles belong in release assets (see CONTRIBUTING.md). A 56 MB archive
once made every clone of this repository carry it forever; this keeps the next
one out before it lands in the history.
"""
from pathlib import Path
import shutil
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
LIMIT = 25 * 1024 * 1024


class TrackedFileSizeTest(unittest.TestCase):
    def test_tracked_files_stay_under_the_limit(self):
        if shutil.which("git") is None or not (ROOT/".git").exists():
            self.skipTest("not a git checkout")
        listed = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, check=True,
                                capture_output=True).stdout.split(b"\0")
        oversized = []
        for name in filter(None, listed):
            path = ROOT/name.decode()
            if path.is_file() and path.stat().st_size > LIMIT:
                oversized.append(f"{name.decode()} ({path.stat().st_size/1e6:.1f} MB)")
        self.assertEqual(oversized, [], "Move these to release assets: " + ", ".join(oversized))
