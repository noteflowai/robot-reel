import copy
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from robot_reel.cloth import FILES, load
from robot_reel.cloth_sample import MAX_BYTES, read_sample, verify_record

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "docs/cloth"
# A real browser export from the recorded GPU experiment, retained unchanged.
FIXTURE = Path(__file__).parent / "fixtures/cloth-sample.json"


class ClothSampleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.trace, cls.positions, _ = load(SITE)

    def sample(self):
        return read_sample(FIXTURE)

    def test_original_browser_record_matches_source_without_mutation(self):
        sample = self.sample()
        original = copy.deepcopy(sample)
        result = verify_record(self.trace, self.positions, sample)
        self.assertTrue(result["recorded_facts_match"])
        self.assertEqual((result["sample"], result["case_index"]), (29, 2))
        self.assertEqual(result["positions_sha256"], hashlib.sha256(self.positions).hexdigest())
        self.assertAlmostEqual(sample["metrics"]["rms_separation_m"], .9080000404747988, places=14)
        self.assertEqual(sample, original)
        sample["sample"] = 29.0
        sample["case"]["index"] = 2.0
        self.assertTrue(verify_record(self.trace, self.positions, sample)["recorded_facts_match"])

    def test_changed_facts_source_and_unknown_claims_are_rejected(self):
        mutations = [
            lambda r: r.update(schema="unknown"),
            lambda r: r.update(time_s=0),
            lambda r: r.update(blender_frame=29),
            lambda r: r.update(fps=60),
            lambda r: r["case"].update(edge_ke=1),
            lambda r: r["reference"].update(index=1),
            lambda r: r["metrics"].update(rms_separation_m=.909),
            lambda r: r["metrics"].update(mean_free_edge_drop_m=0),
            lambda r: r["metrics"].update(max_pin_displacement_m=True),
            lambda r: r["source"].update(positions_sha256="0"*64),
            lambda r: r["source"].update(device="cpu"),
            lambda r: r["source"].update(recorder_sha256="0"*64),
            lambda r: r["source"].update(independent_cases=1),
            lambda r: r["source"].update(vertex_count=116),
            lambda r: r["presentation"].update(display_offsets_x_m=[0, 0, 0]),
            lambda r: r.update(limits=[]),
            lambda r: r.update(verified=True),
        ]
        for change in mutations:
            with self.subTest(change=change):
                sample = self.sample()
                change(sample)
                with self.assertRaises(ValueError):
                    verify_record(self.trace, self.positions, sample)

    def test_untrusted_selection_is_never_clamped_or_coerced(self):
        for value in (True, -1, 121, 1.5, "29", None, float("nan"), float("inf"), 10**400):
            sample = self.sample()
            sample["sample"] = value
            with self.subTest(sample=value), self.assertRaises(ValueError):
                verify_record(self.trace, self.positions, sample)
        for value in (False, -1, 3, 2.5, "2", []):
            sample = self.sample()
            sample["case"]["index"] = value
            with self.subTest(case=value), self.assertRaises(ValueError):
                verify_record(self.trace, self.positions, sample)
        for field, value in (("yaw_rad", 4), ("yaw_rad", True), ("yaw_rad", float("nan")),
                             ("pitch_rad", 1), ("mode", "unknown")):
            sample = self.sample()
            sample["presentation"][field] = value
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                verify_record(self.trace, self.positions, sample)
        for value in ([], None, {}, {"case": [], "presentation": {}}):
            with self.subTest(value=value), self.assertRaises(ValueError):
                verify_record(self.trace, self.positions, value)

    def test_only_measured_floats_allow_documented_roundoff(self):
        sample = self.sample()
        sample["metrics"]["rms_separation_m"] += 5e-13
        self.assertTrue(verify_record(self.trace, self.positions, sample)["recorded_facts_match"])
        for value in (float("inf"), float("nan"), 10**400, False, ".9080000404747988"):
            sample["metrics"]["rms_separation_m"] = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                verify_record(self.trace, self.positions, sample)
        sample = self.sample()
        sample["time_s"] += 5e-13
        with self.assertRaises(ValueError):
            verify_record(self.trace, self.positions, sample)

    def test_fragment_must_describe_the_same_view_and_cannot_redirect(self):
        sample = self.sample()
        sample["replay_fragment"] = "#yaw=-4.8e-1&view=separate&case=2&frame=29"
        self.assertTrue(verify_record(self.trace, self.positions, sample)["recorded_facts_match"])
        for fragment in (
            "https://example.com/#frame=29", "file:///private", "#frame=29&case=2&view=separate&yaw=0",
            "#frame=30&case=2&view=separate&yaw=-0.48",
            "#frame=29&case=2&view=separate&yaw=-0.48&yaw=0",
            "#frame=29&case=2&view=separate&yaw=-0.48&url=elsewhere",
            "#frame=29&case=2&view=separate&yaw=true", "#"+"x"*513,
        ):
            sample["replay_fragment"] = fragment
            with self.subTest(fragment=fragment), self.assertRaises(ValueError):
                verify_record(self.trace, self.positions, sample)

    def test_reader_rejects_ambiguous_and_unbounded_json_but_accepts_utf8_bom(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "sample.json"
            for content in (
                b'{"sample":1,"sample":29}', b'{"sample":1,"\\u0073ample":29}',
                b'{"x":NaN}', b'{"x":1e999}', b'{"x":'+b"9"*400+b"}",
                b"x"*MAX_BYTES+b"x", b"\xff", b"["*2000+b"]"*2000, b"{",
            ):
                path.write_bytes(content)
                with self.subTest(content=content[:40]), self.assertRaises(ValueError):
                    read_sample(path)
            path.write_bytes(b"\xef\xbb\xbf"+FIXTURE.read_bytes())
            self.assertEqual(read_sample(path), self.sample())

    def test_stdlib_cli_checks_the_bundle_and_cannot_start_a_recording(self):
        with tempfile.TemporaryDirectory() as folder:
            lab = Path(folder) / "lab"
            lab.mkdir()
            for name in (*FILES, "manifest.json"):
                shutil.copyfile(SITE/name, lab/name)
            before = {p.name: p.read_bytes() for p in lab.iterdir()}
            command = [sys.executable, "-S", "-m", "robot_reel.cli", "cloth",
                       "--output", str(lab), "--verify-sample", str(FIXTURE)]
            result = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(json.loads(result.stdout)["recorded_facts_match"])
            self.assertEqual(before, {p.name: p.read_bytes() for p in lab.iterdir()})
            for extra in (["--seconds", "4"], ["--device", "cuda:0"], ["--verify"], ["--check-usd"]):
                result = subprocess.run(command+extra, capture_output=True, text=True)
                self.assertNotEqual(result.returncode, 0)
                self.assertNotIn("Traceback", result.stderr)
            (lab/"positions.f32").write_bytes(b"changed")
            result = subprocess.run(command, capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Hash mismatch", result.stderr)
