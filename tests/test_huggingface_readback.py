"""A successful upload must also deliver the original artifact to public readers."""
import hashlib
import io
from pathlib import Path
import tempfile
import types
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError

from scripts.verify_huggingface import LABS, MANIFEST, served_bytes, verify_live, verify_objects, verify_publication


class HuggingFaceReadbackTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        names = [MANIFEST, "index.html", *(f"{lab}/index.html" for lab in LABS), "thumbnail.png"]
        self.entries = []
        for index, name in enumerate(names):
            path = self.root/name
            path.parent.mkdir(parents=True, exist_ok=True)
            data = f"verified artifact {index}\n".encode()
            path.write_bytes(data)
            self.entries.append(SimpleNamespace(
                path=name, size=len(data),
                blob_id=hashlib.sha1(b"blob "+str(len(data)).encode()+b"\0"+data).hexdigest(),
                lfs=SimpleNamespace(sha256=hashlib.sha256(data).hexdigest()) if name.endswith(".png") else None,
            ))
        self.record = {"files": {name: {} for name in names if name != MANIFEST}}

    def test_readback_requires_every_managed_git_and_lfs_object(self):
        extra = SimpleNamespace(path="maintainer-note.txt", blob_id="outside-the-artifact")
        folder = SimpleNamespace(path="cloth", tree_id="directory")
        report = verify_objects(self.root, self.record, [*self.entries, extra, folder])
        self.assertEqual(report["verified_files"], len(LABS)+3)
        self.assertEqual(report["unmanaged_files"], ["maintainer-note.txt"])
        with self.assertRaisesRegex(ValueError, "Missing"):
            verify_objects(self.root, self.record, self.entries[1:])
        for index in (0, len(self.entries)-1):
            entry = self.entries[index]
            with self.subTest(path=entry.path), patch.object(entry, "size", entry.size+1):
                with self.assertRaisesRegex(ValueError, "size differs"):
                    verify_objects(self.root, self.record, self.entries)
            target, field = (entry.lfs, "sha256") if entry.lfs else (entry, "blob_id")
            with self.subTest(path=entry.path), patch.object(target, field, "changed"):
                with self.assertRaisesRegex(ValueError, "content differs"):
                    verify_objects(self.root, self.record, self.entries)
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            verify_objects(self.root, self.record, [*self.entries, self.entries[0]])

    def test_public_readback_retries_old_cdn_bytes_and_transient_errors(self):
        requests, calls = [], {}

        def fetch(request, **kwargs):
            name = request.full_url.removeprefix("https://demo.static.hf.space/")
            requests.append(request)
            calls[name] = calls.get(name, 0)+1
            if name == MANIFEST and calls[name] == 1:
                return io.BytesIO(b"older deployment")
            if name == "index.html" and calls[name] == 1:
                raise HTTPError(request.full_url, 503, "building", {}, None)
            return io.BytesIO((self.root/name).read_bytes())

        with patch("scripts.verify_huggingface.urlopen", side_effect=fetch), \
                patch("scripts.verify_huggingface.time.sleep") as sleep:
            files = verify_live(self.root, "https://demo.static.hf.space", timeout=10)
        self.assertEqual(len(files), len(LABS)+3)
        self.assertEqual(calls[MANIFEST], 2)
        self.assertEqual(calls["index.html"], 2)
        self.assertEqual(calls["cloth/index.html"], 1)
        sleep.assert_called_once()
        self.assertTrue(all(not r.has_header("Authorization") for r in requests))

    def test_only_the_known_platform_variable_is_normalized(self):
        original = b'<html><head><title>Recorded experiment</title></head></html>'
        injection = (b'<script>window.huggingface={variables:'
                     b'{"SPACE_CREATOR_USER_ID":"0123456789abcdef01234567"}};</script>')
        served = original.replace(b"<head>", b"<head>"+injection)
        self.assertEqual(served_bytes("index.html", served), original)
        self.assertEqual(served_bytes("trace.json", served), served)
        for changed in (
            served.replace(b'"SPACE_CREATOR_USER_ID"', b'"UNRECOGNIZED_VARIABLE"'),
            served.replace(b"</script>", b"alert(1);</script>"),
            served+b"<script>extra()</script>",
            served.replace(b"Recorded experiment", b"Changed result"),
            original.replace(b"</head>", injection+b"</head>"),
        ):
            with self.subTest(changed=changed):
                self.assertNotEqual(served_bytes("index.html", changed), original)

    def test_permanent_http_failure_and_stale_deployment_cannot_pass(self):
        error = HTTPError("https://demo.hf.space", 403, "not public", {}, None)
        with patch("scripts.verify_huggingface.urlopen", side_effect=error), \
                self.assertRaisesRegex(ValueError, "HTTP 403"):
            verify_live(self.root, "https://demo.hf.space")
        with patch("scripts.verify_huggingface.time.monotonic", side_effect=[0, 0, 2, 2]), \
                patch("scripts.verify_huggingface.urlopen", return_value=io.BytesIO(b"old")), \
                self.assertRaisesRegex(ValueError, "deadline"):
            verify_live(self.root, "https://demo.hf.space", timeout=1)

    def test_host_and_deadline_are_checked_before_network_access(self):
        with patch("scripts.verify_huggingface.urlopen") as fetch:
            for host in ("http://demo.hf.space", "https://example.com", "https://demo.hf.space@localhost",
                         "https://demo.hf.space/path", "https://demo.hf.space?token=unrelated"):
                with self.subTest(host=host), self.assertRaisesRegex(ValueError, "HTTPS"):
                    verify_live(self.root, host)
            for timeout in (0, -1, 301):
                with self.assertRaisesRegex(ValueError, "timeout"):
                    verify_live(self.root, "https://demo.hf.space", timeout=timeout)
            fetch.assert_not_called()

    def test_publication_uses_anonymous_access_and_rejects_a_changed_head(self):
        info = SimpleNamespace(private=False, sdk="static", sha="a"*40,
                               host="https://demo.hf.space", runtime=SimpleNamespace(stage="RUNNING"))
        api = MagicMock()
        api.space_info.return_value = info
        api.list_repo_tree.return_value = self.entries
        hub = types.ModuleType("huggingface_hub")
        hub.HfApi = MagicMock(return_value=api)
        record = {**self.record, "source_dirty": False, "source_commit": "c"*40}
        with patch.dict("sys.modules", {"huggingface_hub": hub}), \
                patch("scripts.verify_huggingface.verify", return_value=record), \
                patch("scripts.verify_huggingface.verify_live", return_value=["index.html"]):
            report = verify_publication(self.root, "owner/demo", revision=info.sha)
            hub.HfApi.assert_called_once_with(token=False)
            self.assertTrue(report["anonymous_readback"])
            self.assertEqual(api.list_repo_tree.call_args.kwargs["revision"], info.sha)
            with self.assertRaisesRegex(ValueError, "differs from the uploaded commit"):
                verify_publication(self.root, "owner/demo", revision="b"*40)
            api.space_info.side_effect = [info, SimpleNamespace(sha="b"*40)]
            with self.assertRaisesRegex(ValueError, "changed during readback"):
                verify_publication(self.root, "owner/demo", revision=info.sha)
