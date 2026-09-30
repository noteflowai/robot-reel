import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from scripts.research_release_assets import fetch_assets


class ResearchReleaseTests(unittest.TestCase):
    def test_resealed_download_cannot_replace_native_motion_inputs(self):
        def make_archive(changed=False):
            output = io.BytesIO()
            original = b"checked native motion"
            native_id = {"sha256": hashlib.sha256(original).hexdigest(), "bytes": len(original)}
            with zipfile.ZipFile(output, "w") as archive:
                for name in ("README.md", "LICENSE", "check_scene_motion_blender.py"):
                    archive.writestr(name, "reviewed bundle")
                for variant in ("baseline", "edited"):
                    archive.writestr(f"{variant}/scene-motion.blend", b"replaced" if changed else original)
                    archive.writestr(f"{variant}/project.json", json.dumps({
                        "schema": "robot-reel.scene-motion-blender.v1",
                        "files": {"scene-motion.blend": native_id},
                        "source_trace": {"sha256": "b"*64, "bytes": 1},
                        "rendered_source_frames": [0, 1],
                    }))
                    archive.writestr(f"{variant}/producer-native-check.json", json.dumps({
                        "passed": True, "project": native_id,
                        "source_trace": {"sha256": "b"*64, "bytes": 1}, "frames": 2,
                    }))
            return output.getvalue()

        # Reuse the original archive test's two mandatory public assets; only
        # this new optional artifact is fetched before a deliberate stop.
        for changed in (False, True):
            with self.subTest(changed=changed), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                (root / "requirements").mkdir()
                raw = make_archive(changed)
                files = {
                    "scene-motion-native.zip": {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()},
                    "scene-lab-native.zip": {"bytes": 1, "sha256": "a"*64},
                    "research-records.zip": {"bytes": 1, "sha256": "a"*64},
                }
                (root / "requirements/research-release-assets.json").write_text(json.dumps({
                    "dataset": "glayguo/noteflow-research-pilots", "revision": "a"*40, "files": files,
                }))
                def open_file(url, timeout):
                    if not url.endswith("/scene-motion-native.zip"):
                        raise RuntimeError("motion archive accepted; next asset requested")
                    return io.BytesIO(raw)
                if changed:
                    with self.assertRaisesRegex(ValueError, "motion project input differs"):
                        fetch_assets(root, root / "output", opener=open_file)
                else:
                    with self.assertRaisesRegex(RuntimeError, "motion archive accepted"):
                        fetch_assets(root, root / "output", opener=open_file)

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

    def test_factory_twin_projects_must_match_the_published_receipt(self):
        root = Path(__file__).resolve().parents[1]
        buffer = io.BytesIO()
        names = ("README.md", "lab.json", "LICENSE", "factory_twin_scene.py", "build_factory_twin_blender.py",
                 "check_factory_twin_blender.py", "render_factory_twin.py", "check-closed.json", "check-shadow.json",
                 *(f"factory-twin-{m}.{e}" for m in ("closed", "shadow") for e in ("blend", "usdc")))
        receipt = json.loads((root/"docs/factory-twin/blender-check.json").read_text())
        with zipfile.ZipFile(buffer, "w") as archive:
            for name in names:
                data = b"unreviewed replacement project"
                if name == "lab.json":
                    data = (root/"docs/factory-twin/lab.json").read_bytes()
                elif name.startswith("check-"):
                    data = json.dumps(receipt["modes"][name[6:-5]]).encode()  # passing reports, genuine hashes
                archive.writestr(name, data)
        raw = buffer.getvalue()
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary)
            (source/"requirements").mkdir()
            (source/"scripts").mkdir()
            (source/"docs").mkdir()
            (source/"docs/factory-twin").symlink_to(root/"docs/factory-twin")
            for script in ("package_factory_twin_blender.py",):
                (source/"scripts"/script).write_bytes((root/"scripts"/script).read_bytes())
            files = {"factory-twin-blender.zip": {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()},
                     "scene-lab-native.zip": {"bytes": 1, "sha256": "a"*64},
                     "research-records.zip": {"bytes": 1, "sha256": "a"*64}}
            (source/"requirements/research-release-assets.json").write_text(json.dumps({
                "dataset": "glayguo/noteflow-research-pilots", "revision": "a"*40, "files": files}))
            with self.assertRaisesRegex(ValueError, "factory-twin-closed.blend differs from the published receipt"):
                fetch_assets(source, source/"output", opener=lambda url, timeout: io.BytesIO(raw))
