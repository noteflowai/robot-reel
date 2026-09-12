import json
from pathlib import Path
import tempfile
import unittest

from robot_reel.pages import PAGES, check, digest, inline_script, refresh_hashes

ROOT = Path(__file__).resolve().parents[1]


class PublishedPageTest(unittest.TestCase):
    def test_published_pages_carry_their_template_script(self):
        self.assertEqual([page.relative_to(ROOT).as_posix() for page in check(ROOT)], [])

    def test_every_published_page_is_listed(self):
        found = {p.relative_to(ROOT).as_posix() for p in (ROOT/"docs").rglob("index.html")}
        self.assertEqual(found, set(PAGES))
        for template in set(PAGES.values()):
            self.assertTrue((ROOT/template).exists(), template)
            # scripts/check_viewer_js.cjs type-checks these two directories.
            self.assertIn(Path(template).parent.as_posix(), {"robot_reel", "scripts"}, template)

    def test_payload_blocks_are_not_mistaken_for_the_script(self):
        for template in sorted(set(PAGES.values())):
            script = inline_script(ROOT/template)[0]
            self.assertNotIn("<script", script, template)
            self.assertNotIn("__", script.split("\n")[0], template)

    def test_only_manifests_that_recorded_the_file_are_rewritten(self):
        # A comparison bundle also carries its source captures' manifests, and
        # those record a different index.html of their own.
        with tempfile.TemporaryDirectory() as temporary:
            docs = Path(temporary)/"docs"
            docs.mkdir()
            page = docs/"index.html"
            page.write_text("<html>original</html>")
            previous = digest(page)
            own = docs/"comparison-manifest.json"
            own.write_text(json.dumps({"sha256": {"index.html": previous}}, indent=2))
            other = docs/"left-source-manifest.json"
            unrelated = json.dumps({"sha256": {"index.html": "0"*64}}, indent=2)
            other.write_text(unrelated)
            page.write_text("<html>rebuilt</html>")

            updated = refresh_hashes(Path(temporary), {page.resolve(): previous})

            self.assertEqual(updated, [own])
            self.assertEqual(json.loads(own.read_text())["sha256"]["index.html"], digest(page))
            self.assertEqual(other.read_text(), unrelated)

    def test_hashes_are_refreshed_along_the_manifest_chain(self):
        with tempfile.TemporaryDirectory() as temporary:
            docs = Path(temporary)/"docs"
            (docs/"bundle").mkdir(parents=True)
            page = docs/"bundle/index.html"
            page.write_text("<html>original</html>")
            previous = digest(page)
            bundle = docs/"bundle/comparison-manifest.json"
            bundle.write_text(json.dumps({"sha256": {"index.html": previous}}, indent=2) + "\n")
            downstream = docs/"remix-manifest.json"
            downstream.write_text(json.dumps(
                {"inputs": {"bundle/comparison-manifest.json": digest(bundle)}}, indent=2))
            page.write_text("<html>rebuilt</html>")

            updated = refresh_hashes(Path(temporary), {page.resolve(): previous})

            self.assertEqual(updated, [bundle, downstream])
            self.assertEqual(json.loads(downstream.read_text())["inputs"]
                             ["bundle/comparison-manifest.json"], digest(bundle))
            # The writers differ in their trailing newline; keep each file's own.
            self.assertTrue(bundle.read_text().endswith("}\n"))
            self.assertTrue(downstream.read_text().endswith("}"))
