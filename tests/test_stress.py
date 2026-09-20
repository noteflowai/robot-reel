import copy
from contextlib import contextmanager
from html.parser import HTMLParser
from importlib.resources import files
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
from robot_reel.stress_site import PUBLISHED_ARCHIVE_HREF, MARKER, build, load_collection, main, page, payload, verify_site
from robot_reel.vla import validate_trace

SITE = Path(__file__).resolve().parents[1]/"docs/stress"


def archive_link(document):
    class Links(HTMLParser):
        href = None

        def handle_starttag(self, tag, attrs):
            attributes = dict(attrs)
            if tag == "a" and attributes.get("id") == "zip":
                self.href = attributes.get("href")

    parser = Links()
    parser.feed(document)
    return parser.href


@contextmanager
def saved_export_evidence():
    # Keep failure/packaging tests runnable under python -S. CI's installed
    # distribution check separately regenerates MCAP and decodes every video.
    with (
        patch("robot_reel.stress_site.check_media",
              return_value=json.loads((SITE/"media-checks.json").read_text())),
        patch("robot_reel.stress_mcap.export_mcap",
              side_effect=lambda traces, path: shutil.copyfile(SITE/"telemetry.mcap", path)),
    ):
        yield


class StressTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.plan, cls.attempts, cls.traces = load_collection(SITE)

    def test_published_methods_copy_matches_its_source(self) -> None:
        # stress_site.build copies docs/stress.md into the bundle as METHODS.md, so the
        # two drift apart whenever the source is edited without a rebuild -- which is
        # exactly what happened across two pull requests before this test existed.
        source = (SITE.parents[1]/"docs"/"stress.md").read_text(encoding="utf-8")
        published = (SITE/"METHODS.md").read_text(encoding="utf-8")
        self.assertEqual(published, source, "docs/stress/METHODS.md is a stale copy of docs/stress.md")

    def test_packaged_notices_and_methods_match_the_maintained_sources(self):
        root = SITE.parents[1]
        resources = files("robot_reel").joinpath("resources", "stress")
        for source, bundled in (
            ("licenses/VLA-MEDIA-NOTICE.txt", "NOTICE.txt"),
            ("LICENSE", "LICENSE.txt"),
            ("docs/stress.md", "METHODS.txt"),
        ):
            with self.subTest(source=source):
                self.assertEqual(
                    (root/source).read_bytes(), resources.joinpath(bundled).read_bytes(),
                    f"Refresh robot_reel/resources/stress/{bundled} from {source}",
                )

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

    def test_legacy_packs_without_taxonomy_still_verify_and_new_taxonomy_is_checked(self):
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary)/"legacy"
            shutil.copytree(SITE, target)
            manifest = json.loads((target/"manifest.json").read_text())
            manifest["files"].pop("reliability.json")
            (target/"reliability.json").unlink()
            (target/"manifest.json").write_text(json.dumps(manifest))
            self.assertEqual(verify_site(target)["completed_trials"], 30)
            # Once present and sealed, taxonomy is checked against the traces.
            forged = json.loads((SITE/"reliability.json").read_text())
            forged["counts"]["success"] += 1
            (target/"reliability.json").write_text(json.dumps(forged))
            manifest["files"]["reliability.json"] = file_hash(target/"reliability.json")
            (target/"manifest.json").write_text(json.dumps(manifest))
            with self.assertRaisesRegex(ValueError, "taxonomy differs"):
                verify_site(target)

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
        self.assertEqual(page(payload(self.plan, self.attempts, self.traces), PUBLISHED_ARCHIVE_HREF),
                         (SITE/"index.html").read_text())
        self.assertEqual(archive_link((SITE/"index.html").read_text()), PUBLISHED_ARCHIVE_HREF)
        self.assertIn("/releases/download/", PUBLISHED_ARCHIVE_HREF)
        with self.assertRaisesRegex(ValueError, "one archive link"):
            with patch("pathlib.Path.read_text", return_value="<html>__STRESS_DATA__</html>"):
                page({})

    def test_custom_archive_link_is_escaped_without_changing_the_payload(self):
        data = {"label": '__ARCHIVE_HREF__ __STRESS_DATA__ </script><img src="x">'}
        href = 'experiment.zip?label="a&b"&token=__STRESS_DATA__'
        document = page(data, href)
        self.assertEqual(archive_link(document), href)
        self.assertEqual(json.loads(document.split(MARKER)[1].split("</script>", 1)[0]), data)

    def test_build_downloads_its_own_archive_by_default(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)/"pack"
            output.mkdir()
            with saved_export_evidence():
                summary = build(SITE, output)
            document = (output/"index.html").read_text()
            self.assertEqual(archive_link(document), "experiment.zip")
            with zipfile.ZipFile(output/"experiment.zip") as archive:
                self.assertEqual(archive.read("index.html"), document.encode())
                self.assertEqual(json.loads(archive.read("summary.json")), summary)
            self.assertEqual(list(Path(temporary).iterdir()), [output])

    def test_export_rejects_overlapping_occupied_and_symlink_outputs_before_reading(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root/"source"
            source.mkdir()
            (source/"keep.txt").write_text("original recording")
            occupied = root/"occupied"
            occupied.mkdir()
            (occupied/"keep.txt").write_text("existing output")
            file = root/"file"
            file.write_text("existing file")
            empty = root/"empty"
            empty.mkdir()
            link = root/"link"
            link.symlink_to(empty, target_is_directory=True)
            missing_link = root/"missing-link"
            missing_link.symlink_to(root/"missing", target_is_directory=True)
            source_alias = root/"source-alias"
            source_alias.symlink_to(source, target_is_directory=True)
            for output in (source, source/"nested"/"output", root, occupied, file,
                           link, missing_link, source_alias/"output"):
                with self.subTest(output=output), patch("robot_reel.stress_site.load_collection") as load:
                    with self.assertRaises(ValueError):
                        build(source, output)
                    load.assert_not_called()
            self.assertEqual((source/"keep.txt").read_text(), "original recording")
            self.assertEqual((occupied/"keep.txt").read_text(), "existing output")
            self.assertEqual(file.read_text(), "existing file")
            self.assertEqual(list(empty.iterdir()), [])
            self.assertTrue(link.is_symlink())
            self.assertTrue(missing_link.is_symlink())
            self.assertFalse((source/"nested").exists())

    def test_missing_dependency_leaves_no_partial_export_and_can_be_retried(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)/"pack"
            result = subprocess.run(
                [sys.executable, "-S", "-m", "robot_reel.stress_site", str(SITE), str(output)],
                cwd=SITE.parents[1], capture_output=True, text=True, timeout=60,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("No module named 'mcap'", result.stderr)
            self.assertFalse(output.exists())
            self.assertEqual(list(Path(temporary).iterdir()), [])
            with saved_export_evidence():
                summary = build(SITE, output)
            self.assertEqual(summary["completed_trials"], 30)
            self.assertEqual(verify_site(output), summary)
            self.assertEqual(list(Path(temporary).iterdir()), [output])

    def test_media_failure_interruption_and_final_validation_preserve_empty_output(self):
        for operation, failure in (
            ("check_media", OSError("video decode failed")),
            ("check_media", KeyboardInterrupt("export interrupted")),
            ("verify_site", ValueError("archive validation failed")),
        ):
            with self.subTest(operation=operation, failure=type(failure).__name__), tempfile.TemporaryDirectory() as temporary:
                output = Path(temporary)/"pack"
                output.mkdir()
                with saved_export_evidence(), patch("robot_reel.stress_site."+operation, side_effect=failure):
                    with self.assertRaisesRegex(type(failure), str(failure)):
                        build(SITE, output)
                self.assertTrue(output.is_dir())
                self.assertEqual(list(output.iterdir()), [])
                self.assertEqual(list(Path(temporary).iterdir()), [output])

    def test_export_does_not_replace_output_populated_during_validation(self):
        for precreated in (False, True):
            with self.subTest(precreated=precreated), tempfile.TemporaryDirectory() as temporary:
                output = Path(temporary)/"pack"
                if precreated:
                    output.mkdir()

                def concurrent_writer(staging):
                    result = verify_site(staging)
                    output.mkdir(exist_ok=True)
                    (output/"keep.txt").write_text("written by another process")
                    return result

                with saved_export_evidence(), patch("robot_reel.stress_site.verify_site", side_effect=concurrent_writer):
                    with self.assertRaises(OSError):
                        build(SITE, output)
                self.assertEqual((output/"keep.txt").read_text(), "written by another process")
                self.assertEqual(list(output.iterdir()), [output/"keep.txt"])
                self.assertEqual(list(Path(temporary).iterdir()), [output])

    def test_cli_uses_local_archive_unless_publication_link_is_explicit(self):
        for options, expected in (([], "experiment.zip"), (["--archive-href", PUBLISHED_ARCHIVE_HREF], PUBLISHED_ARCHIVE_HREF)):
            with self.subTest(options=options), patch("robot_reel.stress_site.build", return_value={}) as builder:
                with patch("builtins.print"):
                    main(["recording", "output", *options])
                builder.assert_called_once_with(Path("recording"), Path("output"), archive_href=expected)

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
