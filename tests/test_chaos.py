import copy
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from robot_reel.chaos import digest, export_viewer, measure, validate_trace, verify
from scripts.build_chaos_showcase import verify_showcase
from scripts.build_chaos_site import check_report

SITE = Path(__file__).resolve().parents[1]/"docs/chaos"


class ChaosTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.trace = json.loads((SITE/"trace.json").read_text())

    def test_world_count_and_device_are_read_from_the_trace(self):
        """A GPU sweep records its own device and width; both are then enforced."""
        import copy
        from robot_reel.chaos import ANGLE_STEP_DEG, validate_trace, worlds
        published = json.loads((SITE/"trace.json").read_text())
        self.assertIn("body_samples", validate_trace(published))
        self.assertEqual(published["source"]["device"], "cpu")
        self.assertEqual(published["source"]["world_count"], len(published["worlds"]))

        # The sweep is parameterised, which is what lets a cuda:0 run widen it.
        for count in (12, 48, 256):
            sweep = worlds(count)
            self.assertEqual(len(sweep), count)
            self.assertAlmostEqual(sweep[1]["angle_offset_deg"] - sweep[0]["angle_offset_deg"],
                                   ANGLE_STEP_DEG, places=9)

        # Anything the recorder claims about width or device has to match the trace.
        for label, mutate in (
            ("device the recorder cannot produce", lambda d: d["source"].update({"device": "gpu"})),
            ("world_count disagreeing with the sweep", lambda d: d["source"].update({"world_count": 24})),
            ("world_count below the range", lambda d: d["source"].update({"world_count": 1})),
            ("world_count above the range", lambda d: d["source"].update({"world_count": 513})),
        ):
            broken = copy.deepcopy(published)
            mutate(broken)
            with self.subTest(label), self.assertRaises(ValueError):
                validate_trace(broken)

    def test_published_experiment_and_download_match_all_recorded_samples(self):
        result = verify_showcase(SITE)
        self.assertEqual(result["body_samples"], 14424)
        self.assertEqual(result["peak"]["frame"], 375)
        self.assertEqual(result["peak"]["world"], 3)
        self.assertAlmostEqual(result["peak"]["distance_m"], 6.260145, places=6)
        self.assertLess(result["initial_tip_distances_m"][3], .009)
        self.assertEqual(self.trace["frames"][-1]["sim_time"], 20)

    def short_metadata_fixture(self):
        # This relabelled subset tests export metadata, not real GPU execution.
        trace = copy.deepcopy(self.trace)
        trace["source"].update(world_count=4, device="cuda:0")
        trace["worlds"] = trace["worlds"][:4]
        trace["frames"] = trace["frames"][:2]
        for frame in trace["frames"]:
            frame["poses"] = frame["poses"][:8]
        trace["summary"] = measure(trace)
        return trace

    def test_exported_page_describes_the_recording_without_javascript(self):
        trace = self.short_metadata_fixture()
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary)/"index.html"
            export_viewer(trace, path)
            html = path.read_text().split('<script id="chaos-data"', 1)[0]
        self.assertIn('aria-label="4 recorded Newton worlds"', html)
        self.assertIn("4 isolated worlds on GPU (cuda:0)", html)
        self.assertIn("8 animated links", html)
        self.assertIn("full sweep spans 0.15°", html)
        self.assertNotIn("12 WORLDS", html)
        self.assertNotIn("__WORLD_COUNT__", html)

    def test_native_usd_preserves_device_count_and_centered_layout(self):
        try:
            from pxr import Gf, Usd, UsdGeom
        except ImportError:
            self.skipTest("OpenUSD runtime is optional")
        from robot_reel.chaos_usd import check_usd, export_usd
        trace = self.short_metadata_fixture()
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary)/"fixture.usdc"
            export_usd(trace, path)
            self.assertEqual(check_usd(trace, path)["checked_body_samples"], 16)
            stage = Usd.Stage.Open(str(path))
            self.assertIn("4 isolated GPU (cuda:0) worlds",
                          stage.GetRootLayer().customLayerData["source"])
            first = UsdGeom.Xform.Get(stage, "/World/world_00")
            last = UsdGeom.Xform.Get(stage, "/World/world_03")
            self.assertAlmostEqual(first.GetOrderedXformOps()[0].Get()[1], -.9)
            self.assertAlmostEqual(last.GetOrderedXformOps()[0].Get()[1], .9)
            source = dict(stage.GetRootLayer().customLayerData)
            wrong = {**source, "source": "12 isolated CPU worlds"}
            stage.GetRootLayer().customLayerData = wrong
            stage.GetRootLayer().Save()
            with self.assertRaisesRegex(ValueError, "source description"):
                check_usd(trace, path)
            stage.GetRootLayer().customLayerData = source
            first.GetOrderedXformOps()[0].Set(Gf.Vec3d(0, -3.3, 0))
            stage.GetRootLayer().Save()
            with self.assertRaisesRegex(ValueError, "pose differs"):
                check_usd(trace, path)

    def test_relabeling_the_actual_release_is_rejected_even_with_updated_metrics(self):
        trace = copy.deepcopy(self.trace)
        poses = trace["frames"][0]["poses"]
        poses[2:4], poses[4:6] = poses[4:6], poses[2:4]
        trace["summary"] = measure(trace)
        with self.assertRaisesRegex(ValueError, "Initial poses"):
            validate_trace(trace)

    def test_invalid_clock_quaternion_and_broken_hinge_are_rejected(self):
        for kind in ("clock", "quaternion", "hinge", "nonfinite"):
            with self.subTest(kind=kind):
                trace = copy.deepcopy(self.trace)
                if kind == "clock":
                    trace["frames"][30]["sim_time"] = 1.1
                elif kind == "quaternion":
                    trace["frames"][30]["poses"][0][6] = 3
                elif kind == "hinge":
                    trace["frames"][30]["poses"][0][0] += .05
                    trace["summary"] = measure(trace)
                else:
                    trace["frames"][30]["poses"][0][0] = float("nan")
                with self.assertRaises(ValueError):
                    validate_trace(trace)

    def test_rehashed_browser_payload_cannot_replace_the_source(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            for name in ("trace.json", "scene.usdc", "index.html", "manifest.json"):
                shutil.copyfile(SITE/name, output/name)
            html = (output/"index.html").read_text()
            marker = '<script id="chaos-data" type="application/json">'
            head, rest = html.split(marker)
            payload, tail = rest.split("</script>", 1)
            changed = json.loads(payload)
            changed["frames"][30]["poses"][0][0] += 1
            (output/"index.html").write_text(head+marker+json.dumps(changed)+"</script>"+tail)
            manifest = json.loads((output/"manifest.json").read_text())
            manifest["files"]["index.html"] = digest(output/"index.html")
            (output/"manifest.json").write_text(json.dumps(manifest))
            with self.assertRaisesRegex(ValueError, "browser data differs"):
                verify(output)

    def test_native_report_from_another_scene_cannot_be_published(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            for name in ("trace.json", "scene.usdc", "index.html", "manifest.json", "blender-check.json", "usd-check.json"):
                shutil.copyfile(SITE/name, output/name)
            report = json.loads((output/"blender-check.json").read_text())
            report["usd_sha256"] = "0"*64
            (output/"blender-check.json").write_text(json.dumps(report))
            with self.assertRaisesRegex(ValueError, "different scene.usdc"):
                check_report(output)
