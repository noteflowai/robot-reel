import fnmatch
import hashlib
import json
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import MagicMock, patch

from scripts.build_huggingface import LABS, MANIFEST, ROOT, Navigation, build, verify
from scripts.publish_huggingface import publish


class HuggingFaceSpaceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.site = Path(cls.temporary.name)/"space"
        cls.result = build(cls.site, allow_dirty=True)

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def test_package_preserves_original_evidence_and_includes_no_private_workspace(self):
        manifest = verify(self.site)
        # Recorded labs include scene/native policy evidence and model review, loaded on demand.
        self.assertLess(self.result["bytes"], 160*1024*1024)
        self.assertNotIn(".git", {p.name for p in self.site.iterdir()})
        self.assertTrue(all(path.startswith(tuple(f"docs/{lab}/" for lab in LABS))
                            or path.startswith("huggingface/") or path in
                            ("LICENSE", "pyproject.toml", "docs/showcase/butterfly-preview.mp4",
                             "docs/assets/ai-first-review.mp4", "docs/assets/ai-first-review.png",
                             "docs/assets/ai-first-review.vtt", "docs/assets/ai-first-review-media.json")
                            for path in manifest["source_files"]))
        transformed = {f"{lab}/{name}" for lab in LABS for name in
                       ("index.html", "manifest.json", "showcase-manifest.json", "experiment.zip", "review.zip")}
        count = 0
        for original, checksum in manifest["source_files"].items():
            if not original.startswith("docs/") or original.startswith("docs/showcase/"):
                continue
            relative = original.removeprefix("docs/")
            if relative not in transformed:
                self.assertEqual(hashlib.sha256((self.site/relative).read_bytes()).hexdigest(), checksum, relative)
                count += 1
        self.assertGreater(count, 190)
        landing = (self.site/"index.html").read_text()
        self.assertIn(f"{len(LABS)} recorded experiments", landing)
        self.assertIn(f"<strong>{len(LABS)}</strong><span>labs hosted", landing)
        self.assertEqual(landing.count('class="card"'), len(LABS))
        self.assertNotIn("__LAB_COUNT__", landing)
        self.assertNotIn("__PACKAGE_VERSION__", landing)
        import tomllib
        version = tomllib.loads((ROOT/"pyproject.toml").read_text())["project"]["version"]
        self.assertIn(f"release {version}", landing)
        for lab in ("cloth", "stress", "chaos", "microduck-lab", "solver-lab"):
            text = (self.site/lab/"index.html").read_text()
            self.assertIn('id="share-url"', text)
            self.assertIn('id="share-open"', text)

    def test_binary_assets_have_explicit_lfs_rules_before_hub_upload(self):
        patterns = [line.split()[0] for line in (self.site/".gitattributes").read_text().splitlines()
                    if "filter=lfs" in line]
        checked = []
        for path in self.site.rglob("*"):
            if not path.is_file():
                continue
            with path.open("rb") as stream:
                binary = b"\0" in stream.read(4096)
            if binary:
                relative = path.relative_to(self.site).as_posix()
                self.assertTrue(any(fnmatch.fnmatchcase(relative, pattern) for pattern in patterns),
                                f"Hub would append an unrecorded LFS rule: {relative}")
                checked.append(path.suffix)
        self.assertIn(".glb", checked)
        self.assertIn(".splat", checked)

    def test_changed_or_extra_files_and_symlinks_are_rejected(self):
        extra = self.site/".env"
        extra.write_text("unrelated private configuration")
        try:
            with self.assertRaisesRegex(ValueError, "inventory"):
                verify(self.site)
        finally:
            extra.unlink()
        path = self.site/"index.html"
        original = path.read_bytes()
        try:
            path.write_bytes(original+b"changed")
            with self.assertRaisesRegex(ValueError, "Changed Space file"):
                verify(self.site)
        finally:
            path.write_bytes(original)
        linked = self.site/"unexpected"
        linked.symlink_to(ROOT/"docs", target_is_directory=True)
        try:
            with self.assertRaisesRegex(ValueError, "symlink"):
                verify(self.site)
        finally:
            linked.unlink()

    def test_destination_is_protected(self):
        with self.assertRaisesRegex(ValueError, "empty"):
            build(self.site, allow_dirty=True)
        for path in (ROOT, ROOT/"docs/cloth", ROOT/"huggingface/output"):
            with self.subTest(path=path), self.assertRaisesRegex(ValueError, "overlap"):
                build(path, allow_dirty=True)
        self.assertTrue((self.site/MANIFEST).is_file())

    def test_navigation_preserves_records_and_moves_only_unhosted_demos_outside(self):
        script = '<script type="application/json">{"html":"<a href=\\"../vla/\\">recorded</a>"}</script>'
        original = ('<a href="https://noteflowai.github.io/robot-reel/">Home</a>'
                    '<a href="../chaos/">Native</a><a href="../remix/#compare">External</a>'
                    '<a href="trace.json" download>Source</a>'+script)
        text = Navigation(original, "cloth", self.site).rewrite()
        self.assertIn('<a href="../">Home', text)
        self.assertIn('<a href="../chaos/">Native', text)
        self.assertIn('href="https://noteflowai.github.io/robot-reel/remix#compare" target="_blank"', text)
        self.assertIn('<a href="trace.json" download>Source', text)
        self.assertTrue(text.endswith(script))

    def test_thumbnail_is_mapped_to_the_actual_recorded_posters(self):
        record = json.loads((ROOT/"huggingface/thumbnail.json").read_text())
        for path, expected in record["source_posters_sha256"].items():
            self.assertEqual(hashlib.sha256((ROOT/path).read_bytes()).hexdigest(), expected)
        self.assertEqual(hashlib.sha256((ROOT/"huggingface/thumbnail.png").read_bytes()).hexdigest(),
                         record["thumbnail_sha256"])

    def sdk(self, api, download, card=None):
        hub = types.ModuleType("huggingface_hub")
        hub.HfApi = lambda: api
        hub.hf_hub_download = download
        hub.SpaceCard = card if card is not None else MagicMock()
        utils = types.ModuleType("huggingface_hub.utils")
        utils.validate_repo_id = lambda value: None
        return patch.dict("sys.modules", {"huggingface_hub": hub, "huggingface_hub.utils": utils})

    def test_dirty_preview_cannot_contact_the_hub(self):
        path = self.site/MANIFEST
        original = path.read_bytes()
        record = json.loads(original)
        record["source_dirty"] = True
        path.write_text(json.dumps(record))
        api = MagicMock()
        try:
            with self.sdk(api, MagicMock()), self.assertRaisesRegex(ValueError, "uncommitted"):
                publish(self.site, "example/preview")
            api.whoami.assert_not_called()
        finally:
            path.write_bytes(original)

    def test_invalid_hub_card_cannot_create_or_modify_a_space(self):
        path = self.site/MANIFEST
        original = path.read_bytes()
        record = json.loads(original)
        record["source_dirty"] = False
        path.write_text(json.dumps(record))
        api, card = MagicMock(), MagicMock()
        card.load.return_value.validate.side_effect = ValueError("Invalid Space metadata")
        try:
            with self.sdk(api, MagicMock(), card), self.assertRaisesRegex(ValueError, "metadata"):
                publish(self.site, "example/invalid-card")
            api.whoami.assert_not_called()
            api.create_repo.assert_not_called()
            api.upload_folder.assert_not_called()
        finally:
            path.write_bytes(original)

    def test_existing_unrelated_space_is_protected_and_updates_keep_the_original_parent(self):
        path = self.site/MANIFEST
        original = path.read_bytes()
        record = json.loads(original)
        record["source_dirty"] = False
        path.write_text(json.dumps(record))
        api = MagicMock()
        api.repo_exists.return_value = True
        api.space_info.return_value = types.SimpleNamespace(sdk="static", private=False, sha="a"*40)
        api.upload_folder.return_value = types.SimpleNamespace(oid="b"*40)
        try:
            with self.sdk(api, MagicMock(side_effect=FileNotFoundError)):
                with self.assertRaisesRegex(ValueError, "no Robot Reel manifest"):
                    publish(self.site, "example/unrelated")
            api.upload_folder.assert_not_called()
            api.reset_mock()
            with self.sdk(api, lambda *args, **kwargs: path):
                result = publish(self.site, "example/managed")
            self.assertEqual(result["hub_commit"], "b"*40)
            api.space_info.assert_called_once()
            self.assertEqual(api.upload_folder.call_args.kwargs["parent_commit"], "a"*40)
            self.assertEqual(set(api.upload_folder.call_args.kwargs["allow_patterns"]), set(record["files"])|{MANIFEST})
        finally:
            path.write_bytes(original)

    def test_failed_initial_upload_can_retry_only_the_space_created_here(self):
        path = self.site/MANIFEST
        original = path.read_bytes()
        record = json.loads(original)
        record["source_dirty"] = False
        path.write_text(json.dumps(record))
        api = MagicMock()
        api.repo_exists.side_effect = [False, True]
        api.space_info.return_value = types.SimpleNamespace(sdk="static", private=False, sha="a"*40)
        api.upload_folder.side_effect = [RuntimeError("interrupted upload"), types.SimpleNamespace(oid="b"*40)]
        try:
            with self.sdk(api, MagicMock(side_effect=FileNotFoundError)):
                with self.assertRaisesRegex(RuntimeError, "interrupted"):
                    publish(self.site, "example/retry")
                result = publish(self.site, "example/retry")
            self.assertEqual(result["hub_commit"], "b"*40)
            api.create_repo.assert_called_once()
            self.assertTrue(all(c.kwargs["parent_commit"] == "a"*40 for c in api.upload_folder.call_args_list))
        finally:
            path.write_bytes(original)
