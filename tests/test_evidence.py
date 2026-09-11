import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from robot_reel.verify import REQUIRED_FILES, verify, verify_trace
from robot_reel.viewer import export_viewer


def trace_fixture():
    frames = [{"frame": i, "sim_time": (i+1)/30, "qpos": [0.0], "target": [0.0],
               "mode": "physics", "source": "scripted", "label": f"shot{i}"} for i in range(4)]
    actions = [{"label": f"shot{i}", "source": "scripted", "start_frame": i, "end_frame": i,
                "target": {"Rotation": 0.0}, "measured": {"Rotation": 0.0},
                "max_error_rad": 0.0} for i in range(4)]
    return {"robot": "so100", "fps": 30, "joints": ["Rotation"], "home": [0.0],
            "frames": frames, "actions": actions}


class EvidenceTest(unittest.TestCase):
    def test_consistent_action_measurements_pass(self):
        result = verify_trace(trace_fixture(), "scripted")
        self.assertEqual(result["home_error_rad"], 0)

    def test_summary_cannot_disagree_with_recorded_endpoint(self):
        trace = trace_fixture()
        trace["actions"][0]["measured"]["Rotation"] = .01
        trace["actions"][0]["max_error_rad"] = .01
        with self.assertRaisesRegex(ValueError, "recorded endpoint"):
            verify_trace(trace, "scripted")

    def test_rejects_action_gaps_and_overlaps(self):
        for first in (0, 2):
            trace = trace_fixture()
            trace["actions"][1]["start_frame"] = first
            with self.subTest(first=first), self.assertRaises(ValueError):
                verify_trace(trace, "scripted")

    def test_rejects_nonfinite_error_and_wrong_frame_provenance(self):
        trace = trace_fixture()
        trace["actions"][0]["max_error_rad"] = float("nan")
        with self.assertRaises(ValueError):
            verify_trace(trace, "scripted")
        trace = trace_fixture()
        trace["frames"][0]["source"] = "agent"
        with self.assertRaisesRegex(ValueError, "provenance"):
            verify_trace(trace, "scripted")

    def test_empty_hash_manifest_cannot_skip_integrity_checks(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            (path / "manifest.json").write_text(json.dumps({"schema": 1, "arm_director": "scripted", "sha256": {}}))
            with self.assertRaisesRegex(ValueError, "required"):
                verify(path)

    def test_tampered_required_file_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            hashes = {}
            for filename in REQUIRED_FILES:
                (path / filename).write_bytes(b"original")
                hashes[filename] = hashlib.sha256(b"original").hexdigest()
            (path / "so100-raw.mp4").write_bytes(b"changed")
            (path / "manifest.json").write_text(json.dumps({"schema": 1, "arm_director": "scripted", "sha256": hashes}))
            with self.assertRaisesRegex(ValueError, "Hash mismatch"):
                verify(path)

    def test_caption_cannot_escape_embedded_json_script(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            trace = trace_fixture()
            trace["frames"][0]["label"] = '</script><script>window.injected=1</script>'
            (path / "so100-trace.json").write_text(json.dumps(trace))
            other = copy.deepcopy(trace)
            other["robot"] = "unitree_g1"
            (path / "unitree_g1-trace.json").write_text(json.dumps(other))
            (path / "manifest.json").write_text(json.dumps({"arm_director": "scripted", "editing": "test", "versions": {}}))
            result = export_viewer(path, validate=False).read_text()
            self.assertNotIn('</script><script>window.injected', result)
            self.assertIn('\\u003c/script>', result)
