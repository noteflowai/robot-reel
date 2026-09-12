import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

from robot_reel.stress import file_hash
from robot_reel.stress_rerun import SDK_VERSION, blueprint, export, provenance, selection, verify

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT/"docs/stress"
SHOWCASE = ROOT/"docs/rerun"
HAS_RERUN = importlib.util.find_spec("rerun") is not None


class RerunScopeTest(unittest.TestCase):
    def test_selection_keeps_original_scope_and_terminal_observations(self):
        document, traces, paths = selection(SITE, 9)
        meta = provenance(document, traces)
        self.assertEqual((meta["selected_trials"], meta["experiment_trials"]), (3, 30))
        self.assertEqual([t["result"]["outcome"] for t in traces], ["success", "step_limit", "step_limit"])
        self.assertEqual([len(t["frames"]) for t in traces], [83, 161, 161])
        for trace in traces:
            self.assertIsNone(trace["frames"][-1]["action"])
            self.assertTrue((paths[trace["stress"]["trial_id"]]/"trace.json").is_file())

    def test_seed_must_belong_to_the_recording(self):
        for seed in (-1, 10, False, "9"):
            with self.subTest(seed=seed), self.assertRaisesRegex(ValueError, "Choose a seed"):
                selection(SITE, seed)

    def test_published_recording_and_preview_retain_source_hashes(self):
        manifest = json.loads((SHOWCASE/"manifest.json").read_text())
        document, traces, _ = selection(SITE, manifest["seed"])
        expected = provenance(document, traces)
        for key, value in expected.items():
            self.assertEqual(manifest[key], value, key)
        self.assertEqual(manifest["observations_checked"], 405)
        self.assertEqual(manifest["controls_checked"], 2814)
        self.assertEqual(manifest["inference_calls_checked"], 41)
        self.assertEqual(manifest["videos_checked"], 6)
        for key, base in (("inputs", ROOT/"docs"), ("sha256", SHOWCASE)):
            for name, digest in manifest[key].items():
                self.assertEqual(file_hash(base/name), digest, name)
        self.assertEqual(manifest["rrd_sha256"], file_hash(SHOWCASE/"seed-09.rrd"))
        self.assertLess((SHOWCASE/"seed-09.rrd").stat().st_size, 8*1024*1024)


@unittest.skipUnless(HAS_RERUN, "Install robot-reel[rerun] for native RRD readback checks")
class RerunNativeTest(unittest.TestCase):
    def test_every_published_native_component_matches_the_source(self):
        result = verify(SITE, SHOWCASE/"seed-09.rrd", 9)
        manifest = json.loads((SHOWCASE/"manifest.json").read_text())
        for key, value in result.items():
            self.assertEqual(manifest[key], value, key)

    def test_export_supports_a_different_seed_and_preserves_existing_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)/"seed-00.rrd"
            result = export(SITE, output, 0)
            self.assertEqual(result["seed"], 0)
            self.assertEqual(result["selected_trials"], 3)
            self.assertEqual(result["rerun_version"], SDK_VERSION)
            original = file_hash(output)
            with self.assertRaisesRegex(ValueError, "new .rrd"):
                export(SITE, output, 0)
            self.assertEqual(file_hash(output), original)

    def test_changed_native_controls_and_video_clocks_are_rejected(self):
        import pyarrow as pa
        import rerun as rr
        _, traces, _ = selection(SITE, 9)
        for kind in ("control", "video-clock"):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as temporary:
                output = Path(temporary)/"changed.rrd"
                stream = rr.RecordingStream("robot-reel-stress", recording_id=kind, send_properties=False)
                stream.save(output, default_blueprint=blueprint(traces))
                touched = False
                try:
                    for chunk in rr.experimental.RrdReader(SHOWCASE/"seed-09.rrd").stream().to_chunks():
                        target = "/controls/reference/gripper" if kind == "control" else "/cameras/reference/main"
                        field = "Scalars:scalars" if kind == "control" else "VideoFrameReference:timestamp"
                        batch = chunk.to_record_batch()
                        if not touched and chunk.entity_path == target and field in batch.schema.names:
                            index = batch.schema.get_field_index(field)
                            values = batch.column(index).to_pylist()
                            values[0][0] = 0.123 if kind == "control" else 25_000_000
                            batch = batch.set_column(index, batch.schema.field(index),
                                                     pa.array(values, type=batch.schema.field(index).type))
                            stream.send_chunks(rr.experimental.Chunk.from_record_batch(batch))
                            touched = True
                        else:
                            stream.send_chunks(chunk)
                    stream.flush()
                finally:
                    stream.disconnect()
                self.assertTrue(touched)
                with self.assertRaisesRegex(ValueError, "component differs from source"):
                    verify(SITE, output, 9)
