import copy
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from robot_reel.compare import digest
from robot_reel.vla import REQUIRED, export_viewer, validate_trace, verify

SITE = Path(__file__).resolve().parents[1]/"docs/vla"


class VlaTest(unittest.TestCase):
    def setUp(self):
        self.trace = json.loads((SITE/"trace.json").read_text())

    def test_real_policy_episode_retains_terminal_observation_and_outcome(self):
        result = verify(SITE)
        self.assertEqual(result, {"actions": 76, "frames": 77, "fps": 20, "outcome": "success", "inference_calls": 8})
        self.assertTrue(self.trace["frames"][-2]["next_success"])
        self.assertIsNone(self.trace["frames"][-1]["action"])
        self.assertEqual(self.trace["frames"][-1]["episode_time"], 3.8)
        self.assertAlmostEqual(self.trace["frames"][-1]["sim_time"], 4.3)
        self.assertEqual([c["frame"] for c in self.trace["inference_calls"]], list(range(0, 76, 10)))

    def test_malformed_observations_actions_and_clocks_fail(self):
        for changes in (
            {"action": [float("nan")]*7}, {"action": [2.]*7},
            {"state": [0.]*7}, {"joint_position": [float("inf")]*7},
            {"episode_time": .01}, {"sim_time": 0}, {"frame": True},
            {"inference_frame": 1}, {"terminal": True}, {"next_success": "true"},
        ):
            with self.subTest(changes=changes):
                trace = copy.deepcopy(self.trace)
                trace["frames"][0].update(changes)
                with self.assertRaises(ValueError):
                    validate_trace(trace)

    def test_clipping_preserves_proposed_and_executed_control(self):
        trace = copy.deepcopy(self.trace)
        trace["frames"][0]["proposed_action"][0] = 1.2
        trace["frames"][0]["action"][0] = 1.
        self.assertEqual(validate_trace(trace)["actions"], 76)
        trace["frames"][0]["action"][0] = .9
        with self.assertRaisesRegex(ValueError, "clipping"):
            validate_trace(trace)

    def test_false_outcomes_extra_actions_and_missing_inferences_fail(self):
        trace = copy.deepcopy(self.trace)
        trace["frames"][-2]["next_success"] = False
        with self.assertRaisesRegex(ValueError, "outcome"):
            validate_trace(trace)
        trace = copy.deepcopy(self.trace)
        trace["frames"][0]["next_success"] = True
        with self.assertRaisesRegex(ValueError, "continued"):
            validate_trace(trace)
        trace = copy.deepcopy(self.trace)
        trace["frames"][-1]["action"] = [0.]*7
        with self.assertRaisesRegex(ValueError, "Terminal"):
            validate_trace(trace)
        trace = copy.deepcopy(self.trace)
        trace["inference_calls"].pop()
        with self.assertRaisesRegex(ValueError, "Missing inference"):
            validate_trace(trace)

    def test_episode_download_is_complete_and_viewer_rehash_cannot_hide_changes(self):
        with tempfile.TemporaryDirectory() as temporary:
            bundle = Path(temporary)
            with zipfile.ZipFile(SITE/"episode.zip") as archive:
                self.assertEqual(set(archive.namelist()), REQUIRED|{"manifest.json"})
                archive.extractall(bundle)
            self.assertEqual(verify(bundle)["actions"], 76)
            self.assertEqual(digest(bundle/"trace.json"), digest(SITE/"trace.json"))
            for name in ("main.mp4", "wrist.mp4"):
                self.assertEqual(digest(bundle/name), digest(SITE/name))
            html = (bundle/"index.html").read_text().replace('"seed":0', '"seed":99')
            (bundle/"index.html").write_text(html)
            manifest = json.loads((bundle/"manifest.json").read_text())
            manifest["sha256"]["index.html"] = digest(bundle/"index.html")
            (bundle/"manifest.json").write_text(json.dumps(manifest))
            with self.assertRaisesRegex(ValueError, "viewer differs"):
                verify(bundle)

    def test_language_text_is_embedded_as_data(self):
        with tempfile.TemporaryDirectory() as temporary:
            trace = copy.deepcopy(self.trace)
            trace["task"] = "</script><img src=x onerror=alert(1)>"
            path = Path(temporary)/"index.html"
            export_viewer(trace, path)
            payload = path.read_text().split('<script id="vla-data" type="application/json">')[1].split("</script>", 1)[0]
            self.assertNotIn("<", payload)
            self.assertEqual(json.loads(payload)["task"], trace["task"])
