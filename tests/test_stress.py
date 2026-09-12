import copy
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from robot_reel.stress import canonical_hash, divergence, file_hash, summarize, validate_plan, validate_run, wilson
from robot_reel.stress_site import ARCHIVE_HREF, MARKER, load_collection, page, payload, verify_site
from robot_reel.vla import validate_trace

SITE = Path(__file__).resolve().parents[1]/"docs/stress"


class StressTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.plan, cls.attempts, cls.traces = load_collection(SITE)

    def test_published_pack_keeps_all_thirty_trials_and_attempt_history(self):
        from scripts.build_stress_showcase import verify_preview
        summary = verify_site(SITE)
        self.assertEqual(verify_preview(SITE)["source_trials"], 3)
        self.assertEqual(summary["planned_trials"], 30)
        self.assertEqual(summary["completed_trials"], 30)
        self.assertEqual(len(summary["pairs"]), 20)
        self.assertEqual([c["trials"] for c in summary["conditions"]], [10]*3)
        self.assertEqual(summary["attempts"], len(self.attempts))
        self.assertEqual(summary["execution_errors"], sum(a["status"] == "error" for a in self.attempts))
        self.assertEqual({t["initial_state_id"] for t in self.traces}, set(range(10)))
        self.assertEqual(self.plan["device"], "cuda")
        for condition in summary["conditions"]:
            self.assertEqual(condition["successes"]+condition["step_limits"]+condition["terminated"], 10)
        for trace in self.traces:
            self.assertEqual(trace["source"]["device"], "cuda")
            self.assertTrue(trace["source"]["gpu"])
            self.assertIs(trace["source"]["tf32"], False)

    def test_cli_verifies_the_published_experiment_without_site_packages(self):
        result = subprocess.run(
            [sys.executable, "-S", "-m", "robot_reel.cli", "stress", str(SITE)],
            cwd=SITE.parents[1], capture_output=True, text=True, timeout=60,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["completed_trials"], 30)

    def test_duplicate_missing_or_relabelled_trial_cannot_change_denominator(self):
        for runs in (self.traces[:-1], self.traces+[self.traces[0]]):
            with self.assertRaises(ValueError):
                summarize(self.plan, runs, self.attempts)
        trace = copy.deepcopy(self.traces[0])
        trace["initial_state_id"] = 1
        with self.assertRaisesRegex(ValueError, "paired initial state"):
            validate_run(trace, self.plan)

    def test_rehashed_initial_state_and_independent_policy_noise_break_pairing(self):
        for kind in ("physics", "noise", "checkpoint", "task", "device", "gpu", "tf32"):
            with self.subTest(kind=kind):
                traces = copy.deepcopy(self.traces)
                trace = traces[1]
                if kind == "physics":
                    trace["stress"]["initial_physics"]["qpos"][0] += .01
                    trace["stress"]["initial_physics_sha256"] = canonical_hash(trace["stress"]["initial_physics"])
                elif kind == "noise":
                    trace["inference_calls"][0]["noise_sha256"] = "0"*64
                elif kind == "checkpoint":
                    trace["source"]["checkpoint_sha256"] = "0"*64
                elif kind == "task":
                    trace["stress"]["task_bddl_sha256"] = "0"*64
                elif kind == "device":
                    trace["source"]["device"] = "cpu"
                elif kind == "gpu":
                    trace["source"]["gpu"] = "different device"
                else:
                    trace["source"]["tf32"] = True
                with self.assertRaises(ValueError):
                    summarize(self.plan, traces, self.attempts)

    def test_native_condition_and_refreshed_input_views_are_required(self):
        for kind in ("light", "camera", "unchanged", "image"):
            with self.subTest(kind=kind):
                traces = copy.deepcopy(self.traces)
                trace = traces[1]
                if kind == "light":
                    trace["stress"]["render_after"]["light_diffuse"][0][0] += .1
                elif kind == "camera":
                    trace["stress"]["render_after"]["camera_pos"][0] += .1
                elif kind == "unchanged":
                    trace["stress"]["physics_unchanged_by_condition"] = False
                else:
                    trace["frames"][0]["raw_camera_sha256"] = traces[0]["frames"][0]["raw_camera_sha256"]
                with self.assertRaises(ValueError):
                    summarize(self.plan, traces, self.attempts)

    def test_timing_terminal_and_input_hash_integrity(self):
        for kind in ("timing", "overlap", "terminal", "hash", "step"):
            with self.subTest(kind=kind):
                trace = copy.deepcopy(self.traces[0])
                if kind == "timing":
                    trace["inference_calls"][0]["policy_seconds"] += 1
                elif kind == "overlap":
                    trace["inference_calls"][1]["started_seconds"] = 0
                elif kind == "terminal":
                    trace["frames"][-1]["action"] = [0]*7
                elif kind == "hash":
                    trace["frames"][5]["raw_camera_sha256"]["main"] = "not-a-hash"
                else:
                    trace["frames"][0]["env_step_seconds"] += 1
                with self.assertRaises(ValueError):
                    validate_run(trace, self.plan)

    def test_wilson_intervals_retain_small_sample_uncertainty(self):
        self.assertIsNone(wilson(0, 0))
        self.assertAlmostEqual(wilson(0, 10)[1], .2775327999)
        self.assertAlmostEqual(wilson(10, 10)[0], .7224672001)
        self.assertAlmostEqual(wilson(5, 10)[0], .2365930905)
        self.assertAlmostEqual(wilson(5, 10)[1], .7634069095)

    def test_divergence_excludes_held_samples(self):
        reference = {"frames": [
            {"state": [0, 0, 0], "action": [0, 0]},
            {"state": [0, 0, 0]}, {"state": [100, 100, 100]},
        ]}
        other = {"frames": [{"state": [0, 0, 0], "action": [3, 4]}, {"state": [3, 4, 0]}]}
        self.assertEqual(divergence(reference, other), {
            "shared_observations": 2, "max_eef_distance_m": 5,
            "max_eef_frame": 1, "first_action_l2": 5,
        })

    def test_plan_is_locked_and_initial_states_have_real_bounds(self):
        for key, value in (("seeds", [False]+list(range(1, 10))), ("max_steps", 161), ("precision", "bfloat16")):
            changed = copy.deepcopy(self.plan)
            changed[key] = value
            if key == "max_steps":
                with self.assertRaisesRegex(ValueError, "locked experiment"):
                    validate_run(self.traces[0], changed)
            else:
                with self.assertRaises(ValueError):
                    validate_plan(changed)
        for initial_id in (False, -1, 50, .5):
            trace = copy.deepcopy(self.traces[0])
            trace["initial_state_id"] = initial_id
            with self.assertRaises(ValueError):
                validate_trace(trace)

    def test_unsafe_unfinished_or_duplicate_completed_attempt_is_rejected(self):
        for kind in ("path", "running", "duplicate", "outcome"):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                (root/"experiment.json").write_text(json.dumps(self.plan))
                attempts = copy.deepcopy(self.attempts)
                first = next(a for a in attempts if a["status"] == "completed")
                if kind == "path":
                    first["directory"] = "../elsewhere"
                elif kind == "running":
                    first["status"] = "running"
                elif kind == "duplicate":
                    attempts.insert(attempts.index(first)+1, copy.deepcopy(first))
                else:
                    first["outcome"] = "unrecorded"
                (root/"attempts.json").write_text(json.dumps(attempts))
                with patch("robot_reel.stress_site.verify_run", return_value=self.traces[0]):
                    with self.assertRaises(ValueError):
                        load_collection(root)

    def test_rehashed_viewer_and_summary_cannot_replace_source_results(self):
        for kind in ("viewer", "summary"):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)/"pack"
                shutil.copytree(SITE, root)
                if kind == "viewer":
                    name = "index.html"
                    head, rest = (root/name).read_text().split(MARKER)
                    encoded, tail = rest.split("</script>", 1)
                    changed = json.loads(encoded)
                    changed["traces"][0]["frames"][0]["state"][0] += 1
                    (root/name).write_text(head+MARKER+json.dumps(changed)+"</script>"+tail)
                    message = "Viewer payload"
                else:
                    name = "summary.json"
                    changed = json.loads((root/name).read_text())
                    changed["conditions"][0]["successes"] += 1
                    (root/name).write_text(json.dumps(changed))
                    message = "Published rates"
                manifest = json.loads((root/"manifest.json").read_text())
                manifest["files"][name] = file_hash(root/name)
                (root/"manifest.json").write_text(json.dumps(manifest))
                with self.assertRaisesRegex(ValueError, message):
                    verify_site(root)

    def test_published_page_is_reproducible_from_its_template(self):
        # The whole document, not only its payload: the offline-archive link used
        # to be patched into the published page by hand, so a rebuild silently
        # replaced it with a local path.
        self.assertEqual(page(payload(self.plan, self.attempts, self.traces)),
                         (SITE/"index.html").read_text())
        self.assertIn(ARCHIVE_HREF, (SITE/"index.html").read_text())
        self.assertIn("/releases/download/", ARCHIVE_HREF)
        with self.assertRaisesRegex(ValueError, "one archive link"):
            with patch("pathlib.Path.read_text", return_value="<html>__STRESS_DATA__</html>"):
                page({})

    def test_published_site_verifies_without_the_release_archive(self):
        # docs/stress/ ships the archive as a release asset, not as a tracked file.
        self.assertFalse((SITE/"experiment.zip").exists())
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)/"pack"
            shutil.copytree(SITE, root)
            summary = verify_site(root)
            self.assertEqual(summary, json.loads((SITE/"summary.json").read_text()))

    def test_offline_archive_omission_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)/"pack"
            shutil.copytree(SITE, root)
            with zipfile.ZipFile(root/"experiment.zip", "w") as archive:
                archive.write(root/"index.html", "index.html")
            with self.assertRaisesRegex(ValueError, "archive is incomplete"):
                verify_site(root)

    def test_completed_failed_trials_are_not_retried_on_resume(self):
        from scripts.record_stress import main
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in ("experiment.json", "attempts.json"):
                shutil.copyfile(SITE/name, root/name)
            by_id = {t["stress"]["trial_id"]: t for t in self.traces}
            with (
                patch("sys.argv", ["record_stress", "--output", str(root), "--resume",
                                   "--device", self.plan.get("device", "cpu")]),
                patch("scripts.record_stress.load_runtime") as runtime,
                patch("scripts.record_stress.collect") as collect,
                patch("scripts.record_stress.verify_run", side_effect=lambda p, d: by_id[p.parent.name]),
                patch("builtins.print"),
            ):
                main()
            runtime.assert_not_called()
            collect.assert_not_called()
            self.assertEqual(json.loads((root/"attempts.json").read_text()), self.attempts)

    def test_mcap_roundtrip_and_telemetry_mutation(self):
        try:
            import mcap  # noqa: F401
        except ImportError:
            self.skipTest("Install robot-reel[inspect] for MCAP round-trip verification")
        from robot_reel.stress_mcap import check_mcap
        result = check_mcap(self.traces, SITE/"telemetry.mcap")
        self.assertEqual(result["messages"], sum(len(t["frames"])+len(t["inference_calls"]) for t in self.traces))
        changed = copy.deepcopy(self.traces)
        changed[0]["frames"][0]["state"][0] += 1
        with self.assertRaisesRegex(ValueError, "provenance"):
            check_mcap(changed, SITE/"telemetry.mcap")
