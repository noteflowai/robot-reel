from contextlib import chdir, redirect_stdout
import io
import json
from pathlib import Path
import shutil
import tempfile
import unittest
import zipfile

from robot_reel.pages import PAGES, check, digest, inline_script, main, refresh_hashes, sync

ROOT = Path(__file__).resolve().parents[1]


class PublishedPageTest(unittest.TestCase):
    def test_published_pages_carry_their_template_script(self):
        self.assertEqual([page.relative_to(ROOT).as_posix() for page in check(ROOT)], [])

    def test_landing_markup_changes_sync_even_when_the_script_does_not_change(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            page, template = root/"docs/index.html", root/"scripts/landing.html"
            page.parent.mkdir()
            template.parent.mkdir()
            script = '<script>\nconsole.log("same script");\n</script>'
            page.write_text("<h1>Before</h1>"+script)
            template.write_text("<h1>After</h1>"+script)
            self.assertEqual(check(root), [page])
            self.assertEqual(sync(root), [page])
            self.assertEqual(page.read_bytes(), template.read_bytes())
            self.assertEqual(check(root), [])
            self.assertEqual(sync(root), [])

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

    def test_script_sync_keeps_real_offline_packs_and_downstream_hashes_consistent(self):
        from robot_reel.stress_site import required_files, verify_site
        from robot_reel.vla import verify
        from scripts.build_chaos_showcase import verify_showcase

        for name, archive_name, validate in (
            ("vla", "episode.zip", verify),
            ("chaos", "experiment.zip", verify_showcase),
            ("stress", "experiment.zip", verify_site),
        ):
            with self.subTest(bundle=name), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                site = root/"docs"/name
                shutil.copytree(ROOT/"docs"/name, site)
                template = root/PAGES[f"docs/{name}/index.html"]
                template.parent.mkdir(parents=True)
                template.write_text((ROOT/PAGES[f"docs/{name}/index.html"]).read_text().replace(
                    "<script>\n", "<script>\n// Test the complete offline update.\n", 1))
                archive = site/archive_name
                if name == "stress":
                    # Release archives are untracked; local builds still contain one.
                    attempts = json.loads((site/"attempts.json").read_text())
                    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as bundle:
                        for member in sorted(required_files(attempts)|{"manifest.json"}):
                            bundle.write(site/member, member)
                before = validate(site)
                with zipfile.ZipFile(archive) as bundle:
                    original = {info.filename: (info.date_time, info.compress_type, info.external_attr)
                                for info in bundle.infolist()}
                    evidence = {member: digest(site/member) for member in original
                                if member not in {"index.html", "manifest.json"}}
                downstream = root/"docs/downstream-manifest.json"
                inputs = {f"{name}/{archive_name}": digest(archive),
                          f"docs/{name}/manifest.json": digest(site/"manifest.json")}
                downstream.write_text(json.dumps({"inputs": inputs}, indent=2)+"\n")

                updated = sync(root)

                self.assertIn(archive, updated)
                self.assertEqual(len(updated), len(set(updated)))
                self.assertEqual(check(root), [])
                self.assertEqual(validate(site), before)
                with zipfile.ZipFile(archive) as bundle:
                    self.assertEqual({info.filename: (info.date_time, info.compress_type, info.external_attr)
                                      for info in bundle.infolist()}, original)
                    for member in bundle.namelist():
                        self.assertEqual(bundle.read(member), (site/member).read_bytes(), member)
                self.assertEqual({member: digest(site/member) for member in evidence}, evidence)
                self.assertEqual(json.loads(downstream.read_text())["inputs"], {
                    f"{name}/{archive_name}": digest(archive),
                    f"docs/{name}/manifest.json": digest(site/"manifest.json"),
                })
                after = digest(archive)
                self.assertEqual(sync(root), [])
                self.assertEqual(digest(archive), after)

    def test_archived_source_with_the_same_name_is_not_replaced(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            docs = root/"docs"
            docs.mkdir()
            page = docs/"index.html"
            page.write_text("published viewer")
            previous = digest(page)
            archive = docs/"source.zip"
            with zipfile.ZipFile(archive, "w") as bundle:
                bundle.writestr("index.html", "a different source capture")
            source_hash = digest(archive)
            page.write_text("updated published viewer")

            self.assertEqual(refresh_hashes(root, {page.resolve(): previous}), [])
            self.assertEqual(digest(archive), source_hash)

    def test_cli_accepts_a_relative_checkout_root(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root/"docs").mkdir()
            (root/"scripts").mkdir()
            (root/"docs/index.html").write_text("<script>\nold();</script>")
            (root/"scripts/landing.html").write_text("<script>\nupdated();</script>")
            with chdir(root), redirect_stdout(io.StringIO()) as output:
                main(["--root", ".", "--write"])
            self.assertIn("Updated docs/index.html", output.getvalue())
            self.assertEqual(check(root), [])
