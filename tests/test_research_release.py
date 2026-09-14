import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from scripts.research_release_assets import fetch_assets


class ResearchReleaseTests(unittest.TestCase):
    def test_native_identity_and_immutable_download_are_checked(self):
        native = b"independently checked native scene"
        checksum = hashlib.sha256(native).hexdigest()
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("METHODS.md", "fixed native experiment")
            for variant in ("baseline", "edited"):
                archive.writestr(f"{variant}/scene.blend", native)
                archive.writestr(f"{variant}/scene.json", json.dumps({
                    "files": {"scene.blend": {"sha256": checksum, "bytes": len(native)}},
                }))
                archive.writestr(f"{variant}/native-check.json", json.dumps({
                    "passed": True, "scene_sha256": checksum,
                }))
                archive.writestr(f"{variant}/edit.json", "{}")
        records = io.BytesIO()
        with zipfile.ZipFile(records, "w") as archive:
            archive.writestr("trial.json", '{"resolved": false}')
        data = {"scene-lab-native.zip": buffer.getvalue(), "research-records.zip": records.getvalue()}
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root/"requirements").mkdir()
            spec = {
                "dataset": "glayguo/noteflow-research-pilots", "revision": "a"*40,
                "files": {name: {"sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}
                          for name, raw in data.items()},
            }
            (root/"requirements/research-release-assets.json").write_text(json.dumps(spec))
            def open_file(url, timeout):
                self.assertIn("/resolve/"+"a"*40+"/artifacts/", url)
                return io.BytesIO(data[url.rsplit("/", 1)[1]])
            files = fetch_assets(root, root/"good", opener=open_file)
            self.assertEqual({p.name: p.read_bytes() for p in files}, data)
            data["scene-lab-native.zip"] += b"unreviewed"
            with self.assertRaisesRegex(ValueError, "asset changed"):
                fetch_assets(root, root/"bad", opener=open_file)
