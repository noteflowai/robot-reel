import copy
import hashlib
from pathlib import Path
import tempfile
import unittest

from scripts.upload_release_assets import inventory, upload


class Draft:
    tag = "v0.10.0"

    def __init__(self, expected):
        self.expected = expected
        self.document = {"draft": True, "tag_name": self.tag, "assets": []}
        self.calls = []
        self.failures = 0
        self.lose_response = False

    def state(self):
        return copy.deepcopy(self.document)

    def put(self, name):
        self.document["assets"].append({"name": name, "state": "uploaded", **self.expected[name]})

    def upload(self, path):
        self.calls.append(path.name)
        if self.failures:
            self.failures -= 1
            return False
        self.put(path.name)
        return not self.lose_response


class ReleaseUploadTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        (self.folder/"demo.zip").write_bytes(b"tested archive")
        checksum = hashlib.sha256(b"tested archive").hexdigest()
        (self.folder/"SHA256SUMS").write_text(f"{checksum}  demo.zip\n")
        self.expected = inventory(self.folder)

    def test_resumes_only_missing_asset_and_never_publishes(self):
        api = Draft(self.expected)
        api.put("demo.zip")
        result = upload(self.folder, api, sleep=lambda _: None)
        self.assertEqual(api.calls, ["SHA256SUMS"])
        self.assertTrue(result["verified"])
        self.assertTrue(api.document["draft"])
        self.assertEqual(result["unchanged"], ["demo.zip"])
        upload(self.folder, api, sleep=lambda _: None)
        self.assertEqual(api.calls, ["SHA256SUMS"])

    def test_lost_upload_response_does_not_duplicate_a_completed_upload(self):
        api = Draft(self.expected)
        api.lose_response = True
        upload(self.folder, api, sleep=lambda _: None)
        self.assertEqual(api.calls, ["SHA256SUMS", "demo.zip"])

    def test_missing_upload_retries_but_failure_preserves_draft(self):
        api = Draft(self.expected)
        api.failures = 2
        waits = []
        upload(self.folder, api, sleep=waits.append)
        self.assertEqual(waits, [1, 2])
        self.assertEqual(api.calls.count("SHA256SUMS"), 3)
        api = Draft(self.expected)
        api.failures = 99
        with self.assertRaisesRegex(RuntimeError, "draft preserved"):
            upload(self.folder, api, sleep=lambda _: None)
        self.assertEqual(len(api.calls), 3)
        self.assertTrue(api.document["draft"])

    def test_mismatched_remote_or_public_release_is_never_modified(self):
        for mutation in ("hash", "size", "starter", "extra", "duplicate", "public"):
            with self.subTest(mutation=mutation):
                api = Draft(self.expected)
                api.put("demo.zip")
                item = api.document["assets"][0]
                if mutation == "hash":
                    item["digest"] = "sha256:" + "0"*64
                elif mutation == "size":
                    item["size"] += 1
                elif mutation == "starter":
                    item["state"] = "starter"
                elif mutation == "extra":
                    item["name"] = "unrelated.zip"
                elif mutation == "duplicate":
                    api.document["assets"].append(copy.deepcopy(item))
                else:
                    api.document["draft"] = False
                with self.assertRaises(ValueError):
                    upload(self.folder, api, sleep=lambda _: None)
                self.assertEqual(api.calls, [])

    def test_local_checksum_drift_and_symlinks_fail_before_upload(self):
        api = Draft(self.expected)
        (self.folder/"demo.zip").write_bytes(b"changed")
        with self.assertRaises(ValueError):
            upload(self.folder, api)
        self.assertEqual(api.calls, [])
        (self.folder/"demo.zip").unlink()
        (self.folder/"demo.zip").symlink_to(self.folder/"SHA256SUMS")
        with self.assertRaises(ValueError):
            inventory(self.folder)
