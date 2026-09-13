import hashlib
from pathlib import Path
import tempfile
import tomllib
import unittest

from scripts.prepare_release import OFFLINE_FILES, prepare


class ReleaseTests(unittest.TestCase):
    def inputs(self, root):
        source, dist, offline = (root/name for name in ("source", "dist", "offline"))
        for path in (source/"docs/rerun", dist, offline):
            path.mkdir(parents=True)
        (source/"pyproject.toml").write_text('[project]\nversion = "0.7.0"\n')
        (source/"CHANGELOG.md").write_text("## Unreleased\n\n## 0.7.0 — Cloth\n\n- Export both labs.\n\n## 0.6.0 — Previous\n")
        (source/"docs/rerun/seed-09.rrd").write_bytes(b"checked native recording")
        for name in ("robot_reel-0.7.0-py3-none-any.whl", "robot_reel-0.7.0.tar.gz"):
            (dist/name).write_bytes(("checked "+name).encode())
        for name in OFFLINE_FILES:
            (offline/name).write_bytes(("checked "+name).encode())
        return source, dist, offline

    def test_tested_bytes_and_all_asset_checksums_are_preserved(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source, dist, offline = self.inputs(root)
            output = root/"release"
            notes = prepare(source, dist, offline, output)
            self.assertIn("Export both labs.", notes)
            self.assertNotIn("Previous", notes)
            self.assertEqual(len(list(output.iterdir())), 10)
            names = set()
            for line in (output/"SHA256SUMS").read_text().splitlines():
                digest, name = line.split("  ")
                names.add(name)
                self.assertEqual(digest, hashlib.sha256((output/name).read_bytes()).hexdigest())
            self.assertEqual(names, {p.name for p in output.iterdir()}-{"SHA256SUMS"})
            for directory in (dist, offline):
                for path in directory.iterdir():
                    self.assertEqual(path.read_bytes(), (output/path.name).read_bytes())
            self.assertEqual((source/"docs/rerun/seed-09.rrd").read_bytes(), (output/"robot-reel-seed-09.rrd").read_bytes())

    def test_missing_stale_or_extra_artifacts_cannot_be_published(self):
        for mutation in ("missing", "old version", "extra", "symlink", "nonempty output"):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as folder:
                root = Path(folder)
                source, dist, offline = self.inputs(root)
                if mutation == "missing":
                    (offline/"START-HERE.md").unlink()
                elif mutation == "old version":
                    (dist/"robot_reel-0.7.0.tar.gz").rename(dist/"robot_reel-0.6.0.tar.gz")
                elif mutation == "extra":
                    (offline/"unexpected.txt").write_text("not validated")
                elif mutation == "symlink":
                    (offline/"START-HERE.md").unlink()
                    (offline/"START-HERE.md").symlink_to(source/"CHANGELOG.md")
                else:
                    (root/"release").mkdir()
                    (root/"release/old.zip").write_bytes(b"old")
                with self.assertRaises(ValueError):
                    prepare(source, dist, offline, root/"release")

    def test_citation_and_release_notes_match_the_package_version(self):
        root = Path(__file__).resolve().parents[1]
        version = tomllib.loads((root/"pyproject.toml").read_text())["project"]["version"]
        citation = (root/"CITATION.cff").read_text().splitlines()
        self.assertIn(f"version: {version}", citation)
        self.assertTrue(any(line.startswith(f"## {version} — ")
                            for line in (root/"CHANGELOG.md").read_text().splitlines()))


if __name__ == "__main__":
    unittest.main()
