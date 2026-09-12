import copy
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from robot_reel.compare import digest
from robot_reel.director import export_director, export_viewer, inspect_source, validate_storyboard, verify_director
from robot_reel.director_mcp import inside_root

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT/"docs/compare/braking"
PLAN = json.loads((ROOT/"examples/contact-storyboard.json").read_text())


class DirectorTest(unittest.TestCase):
    def test_agent_can_inspect_actual_events_and_preserve_all_samples(self):
        facts = inspect_source(SOURCE)
        self.assertEqual(facts["frames"], 180)
        contact = [e for e in facts["events"] if e["event"] == "contact"]
        self.assertEqual(len(contact), 1)
        self.assertTrue(96 <= contact[0]["frame"] < 126)
        with tempfile.TemporaryDirectory() as temporary:
            bundle = Path(temporary)/"film"
            film = export_director(SOURCE, bundle, PLAN)
            self.assertEqual(verify_director(bundle), {"frames": 210, "source_frames": 180, "fps": 30})
            self.assertEqual([f["source_frame"] for f in film["frames"]][96:100], [96, 96, 97, 97])
            self.assertEqual(sorted({f["source_frame"] for f in film["frames"]}), list(range(180)))
            self.assertEqual(sum(f["source_frame"] == contact[0]["frame"] for f in film["frames"]), 2)
            source = json.loads((bundle/"source/scene.json").read_text())
            for frame in film["frames"]:
                self.assertEqual(frame["sim_time"], source["runs"][0]["frames"][frame["source_frame"]]["sim_time"])
            with self.assertRaisesRegex(ValueError, "empty"):
                export_director(SOURCE, bundle, PLAN)

    def test_gaps_overlaps_dropped_samples_and_unsupported_controls_fail(self):
        for change in (
            {"start": 1}, {"end": 59}, {"end": 61}, {"camera": "arbitrary-python"},
            {"rate": 2}, {"rate": True}, {"caption": ""}, {"start": False}, {"extra": 1},
        ):
            with self.subTest(change=change):
                plan = copy.deepcopy(PLAN)
                plan["shots"][0].update(change)
                with self.assertRaises(ValueError):
                    validate_storyboard(plan, 180)
        plan = copy.deepcopy(PLAN)
        plan["shots"][-1]["end"] = 179
        with self.assertRaisesRegex(ValueError, "omits"):
            validate_storyboard(plan, 180)
        with self.assertRaisesRegex(ValueError, "outside"):
            export_director(SOURCE, SOURCE/"new-film", PLAN)

    def test_rehashing_an_altered_film_mapping_does_not_make_it_valid(self):
        with tempfile.TemporaryDirectory() as temporary:
            bundle = Path(temporary)/"film"
            export_director(SOURCE, bundle, PLAN)
            film = json.loads((bundle/"film.json").read_text())
            film["frames"][0]["source_frame"] = 1
            (bundle/"film.json").write_text(json.dumps(film))
            with self.assertRaisesRegex(ValueError, "hash mismatch"):
                verify_director(bundle)
            manifest = json.loads((bundle/"director-manifest.json").read_text())
            manifest["sha256"]["film.json"] = digest(bundle/"film.json")
            (bundle/"director-manifest.json").write_text(json.dumps(manifest))
            with self.assertRaisesRegex(ValueError, "mapping differs"):
                verify_director(bundle)

    def test_mcp_paths_reject_parent_absolute_and_symlink_escapes(self):
        with tempfile.TemporaryDirectory() as temporary:
            parent = Path(temporary)
            root = parent/"workspace"
            root.mkdir()
            (root/"escape").symlink_to(parent, target_is_directory=True)
            for name in ("../outside", "/tmp/outside", ".", "escape/outside", ""):
                with self.subTest(name=name), self.assertRaises(ValueError):
                    inside_root(root, name)
            self.assertEqual(inside_root(root, "artifacts/new"), root/"artifacts/new")

    def test_caption_payload_is_escaped_and_round_trips(self):
        with tempfile.TemporaryDirectory() as temporary:
            bundle = Path(temporary)/"film"
            plan = copy.deepcopy(PLAN)
            plan["shots"][0]["caption"] = "</script><img onerror=alert(1)>"
            export_director(SOURCE, bundle, plan)
            html = Path(temporary)/"index.html"
            export_viewer(bundle, html)
            text = html.read_text()
            marker = '<script id="director-data" type="application/json">'
            payload = text.split(marker)[1].split("</script>", 1)[0]
            self.assertNotIn("<", payload)
            self.assertEqual(json.loads(payload)["plan"], plan)

    def test_published_film_project_and_native_check_agree(self):
        site = ROOT/"docs/director"
        media = json.loads((site/"media-manifest.json").read_text())
        self.assertEqual((media["frames"], media["source_frames"], media["fps"]), (210, 180, 30))
        self.assertEqual(set(media["sha256"]), {
            "reel.mp4", "poster.png", "preview.gif", "storyboard.json", "film.json",
            "animation-check.json", "index.html", "project.zip",
        })
        for name, checksum in media["sha256"].items():
            self.assertEqual(Path(name).name, name)
            self.assertEqual(digest(site/name), checksum, name)
        with tempfile.TemporaryDirectory() as temporary:
            bundle = Path(temporary)
            with zipfile.ZipFile(site/"project.zip") as archive:
                self.assertTrue(all(not Path(n).is_absolute() and ".." not in Path(n).parts for n in archive.namelist()))
                archive.extractall(bundle)
            self.assertEqual((bundle/"LICENSE").read_bytes(), (ROOT/"LICENSE").read_bytes())
            self.assertEqual(verify_director(bundle)["frames"], 210)
            report = json.loads((bundle/"animation-check.json").read_text())
            self.assertEqual(report["checked_vehicle_samples"], 420)
            self.assertEqual(report["camera_cuts_checked"], 4)
            self.assertTrue(report["tracking_camera_checked"])
            self.assertTrue(report["constant_hold_checked"])
            self.assertLess(report["maximum_position_error_m"], 1e-5)
            for key, name in (("blend_sha256", "reel.blend"), ("film_sha256", "film.json"), ("source_sha256", "source/scene.json")):
                self.assertEqual(report[key], digest(bundle/name))
            html = (site/"index.html").read_text()
            payload = json.loads(html.split('<script id="director-data" type="application/json">')[1].split("</script>", 1)[0])
            self.assertEqual(payload["source"], json.loads((bundle/"source/scene.json").read_text()))
            self.assertEqual(payload["film"], json.loads((bundle/"film.json").read_text()))
            self.assertEqual(payload["plan"], json.loads((bundle/"storyboard.json").read_text()))
