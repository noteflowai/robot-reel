import json
from pathlib import Path
import shutil
import tempfile
import unittest

from scripts.build_factory_twin_film import verify

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "docs/factory-twin"


@unittest.skipUnless((SITE / "film.json").exists(), "film not published")
class FactoryTwinFilmTests(unittest.TestCase):
    def test_published_film_maps_every_frame_to_one_recorded_sample(self):
        result = verify(SITE)
        self.assertEqual(result["frames"], 577)
        self.assertEqual(result["seconds"], 24)
        film = json.loads((SITE / "film.json").read_text())
        self.assertEqual(film["rows"][0]["sample"], 0)
        self.assertEqual(film["rows"][-1]["sample"], 2160)
        samples = [r["sample"] for r in film["rows"]]
        self.assertEqual(samples, sorted(samples), "the film never runs the shift backwards")

    def test_changed_film_or_mapping_is_rejected(self):
        for mutate, message in (
            (lambda p: (p / "film.mp4").write_bytes((p / "film.mp4").read_bytes() + b"x"), "film.mp4"),
            (lambda p: self._edit(p, lambda f: f["rows"][100].update(sample=5)), "time map"),
            (lambda p: self._edit(p, lambda f: f["inputs"].update(blend="0" * 64)), "checked Blender"),
            (lambda p: self._edit(p, lambda f: f["rows"].pop()), "incomplete"),
        ):
            with self.subTest(message=message), tempfile.TemporaryDirectory() as directory:
                p = Path(directory) / "site"
                p.mkdir()
                for name in ("film.json", "film.mp4", "blender-check.json", "lab.json"):
                    shutil.copyfile(SITE / name, p / name)
                mutate(p)
                with self.assertRaisesRegex(ValueError, message):
                    verify(p)

    @staticmethod
    def _edit(path, change):
        film = json.loads((path / "film.json").read_text())
        change(film)
        (path / "film.json").write_text(json.dumps(film))


if __name__ == "__main__":
    unittest.main()
