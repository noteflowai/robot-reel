import copy
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile

from robot_reel.solver_lab import (
    FILES, IDS, analytic, decode, digest, export, make_lab, metrics, seal, validate_run, verify,
)

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT/"docs/solver-lab"


class SolverLabTests(unittest.TestCase):
    def test_real_recordings_and_independent_analytic_calculation(self):
        result = verify(SOURCE)
        self.assertEqual(result["samples"], 366)
        self.assertFalse(result["native_readback_reexecuted"])
        lab = decode((SOURCE/"lab.json").read_bytes())
        for r in lab["runs"]:
            f = r["frames"][-1]
            self.assertEqual(f["time_s"], 2)
            self.assertAlmostEqual(analytic(2)["position_m"][2], 1.38)
            self.assertAlmostEqual(analytic(2)["velocity_m_s"][2], -9.62)
            self.assertAlmostEqual(metrics(r)["final_position_error_m"],
                                   ((f["position_m"][0]-4)**2 + f["position_m"][1]**2
                                    + (f["position_m"][2]-1.38)**2)**.5)
            expected_bias = 9.81 / (30*r["substeps"])
            self.assertAlmostEqual(metrics(r)["max_position_error_m"], expected_bias, delta=5e-5)
        self.assertEqual(len(lab["metrics"]), 6)

    def test_full_handoff_standard_library_cli(self):
        p = subprocess.run([sys.executable, "-S", "-m", "robot_reel.cli", "solver-lab",
                            "--output", str(SOURCE), "--verify"], cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertTrue(json.loads(p.stdout)["verified"])

    def test_missing_clock_scene_and_state_are_rejected(self):
        original = decode((SOURCE/"genesis-1.json").read_bytes())
        mutations = [
            lambda r: r["frames"].pop(),
            lambda r: r["frames"][4].update(time_s=0.2),
            lambda r: r["frames"][4].update(sample=True),
            lambda r: r["frames"][4]["position_m"].__setitem__(0, float("nan")),
            lambda r: r["frames"][4]["position_m"].__setitem__(0, True),
            lambda r: r["frames"][0]["velocity_m_s"].__setitem__(0, 3),
            lambda r: r.update(substeps=4),
            lambda r: r["scene"].update(drag=True),
            lambda r: r.update(measured_mass_kg=0),
            lambda r: r["source"].update(device="cpu"),
        ]
        for i, mutate in enumerate(mutations):
            with self.subTest(mutation=i):
                r = copy.deepcopy(original)
                mutate(r)
                with self.assertRaises(ValueError):
                    validate_run(r, "genesis-1")

    def test_input_inventory_and_duplicate_json_keys(self):
        with self.assertRaises(ValueError):
            decode('{"schema":1,"schema":2}')
        with self.assertRaises(ValueError):
            decode('{"x":NaN}')
        with self.assertRaises(ValueError):
            make_lab([])

    def test_source_metrics_payload_and_receipt_tampering(self):
        for name in ("lab.json", "index.html", "native-check.json", "genesis-1.gstraj"):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                p = Path(directory)/"lab"
                shutil.copytree(SOURCE, p)
                path = p/name
                path.write_bytes(path.read_bytes()+b"changed")
                with self.assertRaises(ValueError):
                    verify(p)
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory)/"lab"
            shutil.copytree(SOURCE, p)
            lab = decode((p/"lab.json").read_bytes())
            lab["metrics"]["genesis-1"]["max_position_error_m"] = 0
            (p/"lab.json").write_text(json.dumps(lab))
            manifest = decode((p/"manifest.json").read_bytes())
            data = (p/"lab.json").read_bytes()
            manifest["files"]["lab.json"] = {"sha256": digest(data), "bytes": len(data)}
            (p/"manifest.json").write_text(json.dumps(manifest))
            with self.assertRaisesRegex(ValueError, "Derived metrics"):
                verify(p)

    def test_export_is_complete_reproducible_and_preserves_inputs(self):
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory)
            export(SOURCE, p/"one")
            export(SOURCE, p/"two")
            self.assertEqual((p/"one/experiment.zip").read_bytes(), (p/"two/experiment.zip").read_bytes())
            with zipfile.ZipFile(p/"one/experiment.zip") as archive:
                self.assertEqual(set(archive.namelist()), {*FILES, "manifest.json"})
            for name in IDS:
                self.assertEqual((p/f"one/{name}.json").read_bytes(), (SOURCE/f"{name}.json").read_bytes())
            with self.assertRaisesRegex(ValueError, "empty"):
                export(SOURCE, p/"one")
            with self.assertRaisesRegex(ValueError, "overlap"):
                export(SOURCE, SOURCE/"copy")

    def test_symlinks_and_changed_archive_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory)/"lab"
            shutil.copytree(SOURCE, p)
            path = p/"lab.json"
            path.unlink()
            path.symlink_to(SOURCE/"lab.json")
            with self.assertRaisesRegex(ValueError, "Symlink"):
                verify(p)
            path.unlink()
            shutil.copyfile(SOURCE/"lab.json", path)
            with zipfile.ZipFile(p/"experiment.zip", "w") as archive:
                archive.writestr("../unexpected", b"bad")
            with self.assertRaisesRegex(ValueError, "archive"):
                verify(p)
            seal(p)
            self.assertTrue(verify(p)["verified"])


if __name__ == "__main__":
    unittest.main()
