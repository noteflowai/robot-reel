import base64
import copy
import importlib.util
import json
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from robot_reel.cloth import (
    CASES, FILES, VERTICES, export_viewer, floats, load, measurements, record,
    validate, verify, write_manifest,
)
from robot_reel.cloth_site import SOURCES, build, check_reports, verify_site
from scripts.build_cloth_showcase import verify_showcase

SITE = Path(__file__).resolve().parents[1]/"docs/cloth"


class ClothEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.trace, cls.q, cls.v = load(SITE)

    def test_published_gpu_recording_native_reports_and_offline_archive(self):
        result = verify_showcase(SITE)
        self.assertEqual(self.trace["source"]["device"], "cuda:0")
        self.assertEqual(self.trace["source"]["device_name"], "NVIDIA L40S")
        self.assertEqual(result["vertex_samples"], 42471)
        self.assertEqual(result["max_pin_error_m"], 0)
        self.assertEqual(result["peak"]["frame"], 29)
        self.assertEqual(result["peak"]["case"], 2)
        self.assertAlmostEqual(result["peak"]["rms_m"], .908000040, places=8)
        self.assertEqual((SITE/"METHODS.md").read_bytes(), (SITE.parent/"cloth.md").read_bytes())

    def test_contract_rejects_relabelled_setup_topology_clock_and_shape(self):
        mutations = [
            lambda t: t["source"].update(mode="kinematic"),
            lambda t: t["source"].update(independent_cases=1),
            lambda t: t["setup"].update(tri_ke=9000.),
            lambda t: t["setup"].update(self_contact=True),
            lambda t: t["cases"][1].update(edge_ke=2.),
            lambda t: t["clock"].update(initial_sample=1),
            lambda t: t["clock"].update(usd_frame_offset=True),
            lambda t: t.update(frame_count=True),
            lambda t: t["triangles"][0].__setitem__(0, 2),
            lambda t: t["units"].update(position="cm"),
            lambda t: t["storage"].update(dtype=">f4"),
        ]
        for mutation in mutations:
            trace = copy.deepcopy(self.trace)
            mutation(trace)
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                validate(trace, self.q, self.v)

    def test_truncated_nonfinite_and_false_summary_fail(self):
        for q, v in (
            (self.q[:-4], self.v), (self.q, self.v+b"\x00"*4),
            (struct.pack("<f", float("nan"))+self.q[4:], self.v),
            (self.q, self.v[:1404]+struct.pack("<f", float("inf"))+self.v[1408:]),
        ):
            with self.subTest(length=len(q)), self.assertRaises(ValueError):
                validate(self.trace, q, v)
        for field in ("rms", "boolean", "curve"):
            trace = copy.deepcopy(self.trace)
            if field == "rms":
                trace["summary"]["peak"]["rms_m"] = 99
            elif field == "boolean":
                trace["summary"]["max_pin_error_m"] = False
            else:
                trace["summary"]["cases"][0]["free_edge_drop_m"][0] = False
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, "summary"):
                validate(trace, self.q, self.v)

    def test_initial_state_and_fixed_vertices_are_checked_even_with_recomputed_metrics(self):
        for target, frame, index in (("q", 0, 3), ("v", 0, 3), ("q", 1, 0), ("v", 1, 0)):
            with self.subTest(target=target, frame=frame):
                q, v = bytearray(self.q), bytearray(self.v)
                position = (frame*len(CASES)*VERTICES+index)*3*4
                struct.pack_into("<f", q if target == "q" else v, position, 99)
                trace = copy.deepcopy(self.trace)
                trace["summary"] = measurements(trace, floats(q, len(q)//4), floats(v, len(v)//4))
                with self.assertRaises(ValueError):
                    validate(trace, q, v)

    def test_rehashed_browser_vertices_cannot_diverge_from_binary_source(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            for name in FILES:
                shutil.copyfile(SITE/name, output/name)
            text = (output/"index.html").read_text()
            marker = '<script id="cloth-data" type="application/json">'
            head, tail = text.split(marker)
            raw, end = tail.split("</script>", 1)
            payload = json.loads(raw)
            payload["positions_base64"] = base64.b64encode(self.q[:-4]+b"\x00"*4).decode()
            (output/"index.html").write_text(head+marker+json.dumps(payload)+"</script>"+end)
            write_manifest(output)
            with self.assertRaisesRegex(ValueError, "Browser cloth"):
                verify(output)

    def test_report_and_archive_changes_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)/"site"
            shutil.copytree(SITE, output)
            report_path = output/"blender-check.json"
            report = json.loads(report_path.read_text())
            report["positions_sha256"] = "0"*64
            report_path.write_text(json.dumps(report))
            with self.assertRaisesRegex(ValueError, "different positions"):
                check_reports(output)
            shutil.copyfile(SITE/"blender-check.json", report_path)
            (output/"METHODS.md").write_text("Changed")
            with self.assertRaisesRegex(ValueError, "archive differs"):
                verify_site(output)

    def test_recording_bounds_and_safe_embedded_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            for seconds in (0, True, .04, float("inf"), float("nan"), 10.1):
                with self.subTest(seconds=seconds), self.assertRaises(ValueError):
                    record(directory, seconds)
            trace = copy.deepcopy(self.trace)
            trace["source"]["recorded_at"] = "</script><script>alert(1)</script>"
            path = Path(directory)/"index.html"
            export_viewer(trace, self.q, self.v, path)
            self.assertNotIn("</script><script>alert", path.read_text())
            self.assertIn('id="download-archive" hidden', path.read_text())


class ClothExportTests(unittest.TestCase):
    def test_stdlib_cli_exports_complete_sources_reports_and_package_resources(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)/"export"
            output.mkdir()  # An empty, pre-created output is also supported.
            command = subprocess.run(
                [sys.executable, "-S", "-m", "robot_reel.cli", "cloth",
                 "--export-from", str(SITE), "--output", str(output)],
                cwd=SITE.parents[1], capture_output=True, text=True, check=True,
            )
            report = json.loads(command.stdout)
            self.assertFalse(report["native_usd_checked"])
            self.assertEqual(report["summary"], verify_site(output))
            for name in SOURCES:
                self.assertEqual((SITE/name).read_bytes(), (output/name).read_bytes())
            for original, target, resource in (
                (SITE.parent/"cloth.md", "METHODS.md", "METHODS.txt"),
                (SITE.parents[1]/"LICENSE", "LICENSE", "LICENSE.txt"),
            ):
                self.assertEqual(original.read_bytes(), (output/target).read_bytes())
                self.assertEqual(original.read_bytes(),
                    (SITE.parents[1]/"robot_reel/resources/cloth"/resource).read_bytes())

    def test_export_protects_input_existing_output_and_symlink_targets(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root/"source"
            shutil.copytree(SITE, source)
            protected = root/"occupied"
            protected.mkdir()
            (protected/"keep.txt").write_text("keep")
            link = root/"link"
            link.symlink_to(source, target_is_directory=True)
            for output in (source, source/"child", root, protected, link):
                with self.subTest(output=output), self.assertRaises(ValueError):
                    build(source, output)
            self.assertEqual((protected/"keep.txt").read_text(), "keep")
            self.assertEqual(check_reports(source)["vertex_samples"], 42471)

    def test_failure_never_publishes_a_partial_export(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)/"export"
            with patch("robot_reel.cloth_site.export_viewer", side_effect=RuntimeError("render failed")):
                with self.assertRaisesRegex(RuntimeError, "render failed"):
                    build(SITE, output)
            self.assertFalse(output.exists())
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_saved_native_reports_reject_mistyped_clocks_and_unaccepted_errors(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory)/"source"
            shutil.copytree(SITE, source)
            for name, field, value in (
                ("blender", "frame_start", True),
                ("blender", "checked_vertex_samples", 42471.0),
                ("usd", "maximum_position_error_m", 1e-6),
            ):
                report = json.loads((SITE/f"{name}-check.json").read_text())
                report[field] = value
                path = source/f"{name}-check.json"
                path.write_text(json.dumps(report))
                with self.subTest(field=field), self.assertRaises(ValueError):
                    build(source, Path(directory)/"output")
                self.assertFalse((Path(directory)/"output").exists())
                shutil.copyfile(SITE/path.name, path)


@unittest.skipUnless(importlib.util.find_spec("pxr"), "OpenUSD optional dependency")
class ClothNativeTests(unittest.TestCase):
    def test_requested_native_export_rejects_an_edited_scene_even_after_rehash(self):
        from pxr import Gf, Usd, UsdGeom
        from robot_reel.cloth import digest
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root/"source"
            shutil.copytree(SITE, source)
            stage = Usd.Stage.Open(str(source/"scene.usdc"))
            attr = UsdGeom.Mesh.Get(stage, "/World/bend_1").GetPointsAttr()
            points = attr.Get(20)
            points[2] = Gf.Vec3f(4, 5, 6)
            attr.Set(points, 20)
            stage.GetRootLayer().Save()
            for name in ("usd", "blender"):
                path = source/f"{name}-check.json"
                report = json.loads(path.read_text())
                report["usd_sha256"] = digest(source/"scene.usdc")
                path.write_text(json.dumps(report))
            write_manifest(source)
            # Hash agreement alone is not a new native inspection.
            self.assertEqual(check_reports(source)["vertex_samples"], 42471)
            with self.assertRaisesRegex(ValueError, "USD differs"):
                build(source, root/"export", check_native=True)
            self.assertFalse((root/"export").exists())

    def test_native_points_and_velocities_match_source(self):
        from robot_reel.cloth_usd import check_usd
        result = check_usd(*load(SITE), SITE/"scene.usdc")
        self.assertEqual(result["checked_vertex_samples"], 42471)
        self.assertEqual(result["maximum_position_error_m"], 0)
        self.assertEqual(result["maximum_velocity_error_m_s"], 0)

    def test_native_mutated_points_velocities_topology_clock_and_offsets_fail(self):
        from pxr import Gf, Usd, UsdGeom
        from robot_reel.cloth_usd import check_usd
        for kind in ("point", "velocity", "topology", "clock", "transform", "samples"):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as directory:
                path = Path(directory)/"scene.usdc"
                shutil.copyfile(SITE/"scene.usdc", path)
                stage = Usd.Stage.Open(str(path))
                mesh = UsdGeom.Mesh.Get(stage, "/World/bend_1")
                if kind in ("point", "velocity"):
                    attr = mesh.GetPointsAttr() if kind == "point" else mesh.GetVelocitiesAttr()
                    values = attr.Get(20)
                    values[2] = Gf.Vec3f(4, 5, 6)
                    attr.Set(values, 20)
                elif kind == "topology":
                    values = mesh.GetFaceVertexIndicesAttr().Get()
                    values[0] = 3
                    mesh.GetFaceVertexIndicesAttr().Set(values)
                elif kind == "clock":
                    stage.SetFramesPerSecond(60)
                elif kind == "transform":
                    mesh.GetOrderedXformOps()[0].Set(Gf.Vec3d(7, 0, 0))
                else:
                    mesh.GetPointsAttr().ClearAtTime(20)
                stage.GetRootLayer().Save()
                with self.assertRaises(ValueError):
                    check_usd(*load(SITE), path)
