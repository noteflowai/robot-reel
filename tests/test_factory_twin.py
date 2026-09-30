import copy
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile

from robot_reel import factory_twin as ft
from robot_reel.factory_twin_scene import STATE_COLORS, channels, slot_position

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "docs/factory-twin"


def load(name):
    return ft.decode((SOURCE / name).read_bytes())


class FactoryTwinRecordTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.runs = {mode: load(f"trace-{mode}.json") for mode in ft.MODES}
        cls.lab = load("lab.json")

    def test_published_lab_verifies_by_reexecution(self):
        result = ft.verify(SOURCE)
        self.assertTrue(result["plant_and_twin_reexecuted"])
        self.assertTrue(result["twin_replayed_from_telemetry"])
        self.assertEqual(result["samples_per_run"], 2161)
        self.assertEqual(result["cnc2_failures"], {"shadow": 1, "closed": 0})
        self.assertEqual(result["blender_frames_checked"], 2161)

    def test_standard_library_cli(self):
        p = subprocess.run([sys.executable, "-S", "-m", "robot_reel.cli", "factory-twin", "--output", str(SOURCE),
                            "--verify"], cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertTrue(json.loads(p.stdout)["verified"])

    def test_pairs_share_disturbances_until_the_first_actuated_command(self):
        closed, shadow = self.runs["closed"], self.runs["shadow"]
        first = min(d["t"] for d in closed["decisions"] if d.get("actuated"))
        # A command sent at sample k is applied 5 s later, i.e. after sample k is recorded.
        k = first // ft.SAMPLE_S
        self.assertEqual(closed["samples"]["telemetry"][:k + 1], shadow["samples"]["telemetry"][:k + 1])
        self.assertEqual(closed["samples"]["plant"][:k + 1], shadow["samples"]["plant"][:k + 1])
        self.assertNotEqual(closed["samples"]["plant"], shadow["samples"]["plant"])

    def test_shadow_twin_advises_but_never_actuates(self):
        shadow = self.runs["shadow"]
        commands = [d for d in shadow["decisions"] if "actuated" in d]
        self.assertTrue(commands, "the shadow twin should still issue advice")
        self.assertTrue(all(d["actuated"] is False for d in commands))
        plant = shadow["samples"]["plant"]
        self.assertEqual({row["setpoint_c"] for row in plant}, {ft.DEFAULT_SETPOINT})
        self.assertEqual({row["ev_cap"] for row in plant}, {1.0})
        self.assertEqual({row["pm_request"] for row in plant}, {0})
        self.assertEqual(shadow["kpis"]["commands_actuated"], 0)

    def test_closed_loop_commands_reach_the_plant_after_the_actuation_delay(self):
        closed = self.runs["closed"]
        service = next(d for d in closed["decisions"] if d.get("actuated") and d["kind"] == "maintenance")
        plant = closed["samples"]["plant"]
        k = service["t"] // ft.SAMPLE_S
        self.assertEqual(plant[k]["pm_request"], 0)
        self.assertEqual(plant[k + 1]["pm_request"], 0)  # sampled at t+5, just before the command lands
        self.assertTrue(plant[k + 2]["pm_request"] or plant[k + 2]["state"][2] == ft.MAINT)
        demand = next(d for d in closed["decisions"] if d.get("actuated") and d["kind"] == "demand")
        k = demand["t"] // ft.SAMPLE_S
        self.assertEqual(plant[k]["setpoint_c"], ft.DEFAULT_SETPOINT)
        self.assertNotEqual((plant[k + 2]["setpoint_c"], plant[k + 2]["ev_cap"]), (ft.DEFAULT_SETPOINT, 1.0))

    def test_twin_depends_only_on_telemetry(self):
        run = copy.deepcopy(self.runs["closed"])
        snapshots, decisions = ft.replay_twin(run)
        self.assertEqual(ft.normalize(snapshots), run["samples"]["twin"])
        self.assertEqual(ft.normalize(decisions), run["decisions"])
        # Hide the plant entirely: the replay does not need it.
        del run["samples"]["plant"]
        self.assertEqual(ft.normalize(ft.replay_twin(run)[0]), self.runs["closed"]["samples"]["twin"])
        # Changing one vibration reading changes the twin's estimate.
        k = next(i for i, p in enumerate(run["samples"]["telemetry"])
                 if "cnc" in p and "plc" in p and p["plc"]["state"][2] == ft.BUSY and i > 100)
        run["samples"]["telemetry"][k]["cnc"]["vibration_mm_s"][1] += 3.0
        self.assertNotEqual(ft.normalize(ft.replay_twin(run)[0]), self.runs["closed"]["samples"]["twin"])

    def test_estimator_tracks_hidden_wear(self):
        for mode in ft.MODES:
            fidelity = self.runs[mode]["fidelity"]
            self.assertLess(fidelity["wear_mae_busy"], 0.02)
            self.assertLess(fidelity["hall_mae_c"], 0.2)
            self.assertGreater(fidelity["telemetry_dropouts"], 0)
        twin0 = self.runs["closed"]["samples"]["twin"][0]
        self.assertNotEqual(twin0["wear"], self.runs["closed"]["samples"]["plant"][0]["wear"])

    def test_featured_outcome_and_seed_table(self):
        c, s = self.runs["closed"]["kpis"], self.runs["shadow"]["kpis"]
        self.assertGreater(c["good_units"], s["good_units"])
        self.assertEqual(c["intervals_over_limit"], 0)
        self.assertGreater(s["intervals_over_limit"], 0)
        self.assertLessEqual(c["max_hall_c"], ft.COMFORT_MAX_C)
        self.assertEqual(c["billing_intervals_kw"], [round(v, 2) for v in c["billing_intervals_kw"]])
        self.assertEqual(len(c["billing_intervals_kw"]), ft.DURATION_S // ft.BILLING_S)
        seeds = load("seeds.json")
        self.assertEqual([r["seed"] for r in seeds["seeds"]], list(ft.SEEDS))
        summary = seeds["summary"]
        self.assertEqual(summary["closed_failures"], 0)
        self.assertEqual(summary["closed_intervals_over_limit"], 0)
        self.assertEqual(summary["good_units_gain"]["pairs_improved"] + summary["good_units_gain"]["pairs_worse"]
                         + sum(r["closed"]["good_units"] == r["shadow"]["good_units"] for r in seeds["seeds"]), 12)

    def test_other_seed_reexecutes(self):
        seeds = load("seeds.json")
        row = next(r for r in seeds["seeds"] if r["seed"] == 3)
        run = ft.simulate(3, "closed", record=False)
        self.assertEqual({k: run["kpis"][k] for k in row["closed"]}, row["closed"])

    def test_random_streams_are_bounded_and_reproducible(self):
        values = [ft.uniform(1, "vib1", i) for i in range(2000)]
        self.assertTrue(all(0 <= v < 1 for v in values))
        self.assertAlmostEqual(sum(values) / len(values), 0.5, delta=0.03)
        normals = [ft.normal(4, "hall", i) for i in range(3000)]
        self.assertAlmostEqual(sum(normals) / len(normals), 0.0, delta=0.08)
        self.assertAlmostEqual(sum(v * v for v in normals) / len(normals), 1.0, delta=0.1)
        self.assertEqual(ft.uniform(9, "drop", 77), ft.uniform(9, "drop", 77))
        self.assertNotEqual(ft.uniform(9, "drop", 77), ft.uniform(9, "load", 77))

    def test_blender_channels_follow_the_samples(self):
        spec = channels(self.lab, "closed")
        plant = self.lab["runs"]["closed"]["plant"]
        for i in range(3):
            self.assertEqual(spec[(f"AMR {i + 1}", "location", 0)], [row[i][0] for row in plant["amr"]])
        for k in (0, 500, 1500, 2160):
            for b, name in enumerate(self.lab["config"]["buffers"]):
                visible = sum(spec[(f"Buffer {name} / slot {i + 1:02d}", "scale", 2)][k]
                              for i in range(self.lab["config"]["buffers"][name]))
                self.assertEqual(visible, plant["buffers"][k][b])
            state = plant["state"][k][2]
            self.assertEqual(tuple(spec[("Station cnc2 / beacon", "color", c)][k] for c in range(3)), STATE_COLORS[state])
        self.assertTrue(all(len(v) == ft.SAMPLES for v in spec.values()))
        slots = {tuple(slot_position(self.lab["layout"]["buffers"][n], i))
                 for n in self.lab["config"]["buffers"] for i in range(self.lab["config"]["buffers"][n])}
        self.assertEqual(len(slots), sum(self.lab["config"]["buffers"].values()), "crate slots overlap")

    def test_blender_receipt_covers_both_modes(self):
        check = load("blender-check.json")
        self.assertTrue(check["verified"])
        for mode in ft.MODES:
            report = check["modes"][mode]
            self.assertTrue(report["verified"])
            self.assertEqual(report["frames_checked"], ft.SAMPLES)
            self.assertEqual(report["usd_frames_checked"], ft.SAMPLES)
            self.assertLess(report["maximum_channel_error"], 1e-3)
            self.assertLess(report["maximum_usd_transform_error"], 1e-3)
            self.assertTrue(report["blender_version"].startswith("5.2"))


class FactoryTwinIntegrityTests(unittest.TestCase):
    def copy(self, directory):
        p = Path(directory) / "lab"
        shutil.copytree(SOURCE, p)
        return p

    def reseal_manifest(self, p, name):
        manifest = ft.decode((p / "manifest.json").read_bytes())
        data = (p / name).read_bytes()
        manifest["files"][name] = {"sha256": ft.digest(data), "bytes": len(data)}
        (p / "manifest.json").write_text(json.dumps(manifest))

    def test_changed_files_are_rejected(self):
        for name in ("lab.json", "index.html", "blender-check.json", "trace-closed.json", "render-cnc.jpg"):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                p = self.copy(directory)
                (p / name).write_bytes((p / name).read_bytes() + b" ")
                with self.assertRaisesRegex(ValueError, "hash"):
                    ft.verify(p, reexecute=False)

    def test_consistent_but_altered_record_is_rejected_by_reexecution(self):
        with tempfile.TemporaryDirectory() as directory:
            p = self.copy(directory)
            run = ft.decode((p / "trace-closed.json").read_bytes())
            run["kpis"]["good_units"] += 5
            (p / "trace-closed.json").write_text(ft.dumps(run))
            self.reseal_manifest(p, "trace-closed.json")
            with self.assertRaisesRegex(ValueError, "Re-executed"):
                ft.verify(p, check_archive=False)
            run["kpis"]["good_units"] -= 5
            run["decisions"][0]["action"] = "Invented decision"
            (p / "trace-closed.json").write_text(ft.dumps(run))
            self.reseal_manifest(p, "trace-closed.json")
            with self.assertRaisesRegex(ValueError, "telemetry alone"):
                ft.verify(p, check_archive=False)

    def test_receipt_must_match_lab(self):
        with tempfile.TemporaryDirectory() as directory:
            p = self.copy(directory)
            check = ft.decode((p / "blender-check.json").read_bytes())
            check["inputs"]["lab.json"] = "0" * 64
            (p / "blender-check.json").write_text(json.dumps(check))
            self.reseal_manifest(p, "blender-check.json")
            with self.assertRaisesRegex(ValueError, "receipt"):
                ft.verify(p, reexecute=False, check_archive=False)

    def test_json_guards_and_symlinks(self):
        with self.assertRaises(ValueError):
            ft.decode('{"a":1,"a":2}')
        with self.assertRaises(ValueError):
            ft.decode('{"a":NaN}')
        with tempfile.TemporaryDirectory() as directory:
            p = self.copy(directory)
            (p / "lab.json").unlink()
            (p / "lab.json").symlink_to(SOURCE / "lab.json")
            with self.assertRaisesRegex(ValueError, "Symlink"):
                ft.verify(p, reexecute=False)

    def test_export_is_reproducible_and_guarded(self):
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory)
            ft.export(SOURCE, p / "one")
            ft.seal(p / "one")
            first = (p / "one/experiment.zip").read_bytes()
            ft.seal(p / "one")
            self.assertEqual((p / "one/experiment.zip").read_bytes(), first)
            with zipfile.ZipFile(p / "one/experiment.zip") as archive:
                self.assertEqual(set(archive.namelist()), {*ft.FILES, "manifest.json"})
            self.assertEqual((p / "one/index.html").read_bytes(), (SOURCE / "index.html").read_bytes())
            with self.assertRaisesRegex(ValueError, "empty"):
                ft.export(SOURCE, p / "one")
            with self.assertRaisesRegex(ValueError, "overlap"):
                ft.export(SOURCE, SOURCE / "copy")
            with zipfile.ZipFile(p / "one/experiment.zip", "w") as archive:
                archive.writestr("../unexpected", b"bad")
            with self.assertRaisesRegex(ValueError, "archive"):
                ft.verify(p / "one", reexecute=False)


if __name__ == "__main__":
    unittest.main()
