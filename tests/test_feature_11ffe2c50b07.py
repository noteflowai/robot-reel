"""Sealing one frame/channel finding into a LeRobot replay bundle (RR-02).

Every test works on a temporary copy of the published SO-101 example in
docs/lerobot (episode 0, 303 frames); docs/lerobot itself is never modified.
"""
import contextlib
import io
import json
import os
import re
import shutil
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

from robot_reel import lerobot
from robot_reel.compare import digest

EXAMPLE = Path(__file__).resolve().parents[1]/"docs"/"lerobot"
NOTE = "Command and measurement diverge while the gripper approaches the box"
SIGNALS = ("action/shoulder_pan.pos", "observation.state/shoulder_pan.pos")


def run_cli(*argv):
    """Run robot-reel lerobot in-process; return (exit code, stdout, stderr)."""
    out, err = io.StringIO(), io.StringIO()
    code = 0
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            lerobot.main([str(a) for a in argv])
        except SystemExit as exc:
            code = exc.code
    return code, out.getvalue(), err.getvalue()


def mark_args(directory, frame=239, signals=SIGNALS, note=NOTE):
    args = [directory, "--mark", frame]
    for signal in signals:
        args += ["--signal", signal]
    return args+["--note", note]


def snapshot(directory):
    return {p.relative_to(directory).as_posix(): p.read_bytes()
            for p in sorted(Path(directory).rglob("*")) if p.is_file()}


def rehash(directory, edit):
    """Edit finding.json and update its manifest entry, as a careful tamperer would."""
    path, manifest_path = directory/"finding.json", directory/"manifest.json"
    finding = json.loads(path.read_text())
    edit(finding)
    path.write_text(json.dumps(finding, indent=2))
    manifest = json.loads(manifest_path.read_text())
    manifest["sha256"]["finding.json"] = digest(path)
    manifest_path.write_text(json.dumps(manifest, indent=2))


class FindingTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="robot-reel-finding-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.bundle = self.copy(EXAMPLE, "so101")
        self.trace = json.loads((self.bundle/"episode.json").read_text())

    def copy(self, source, name):
        target = self.tmp/name
        shutil.copytree(source, target)
        return target

    def mark(self, directory):
        code, out, err = run_cli(*mark_args(directory))
        self.assertEqual(code, 0, err)
        return json.loads(out)

    def assert_rejected(self, directory, message):
        with self.assertRaisesRegex(ValueError, re.escape(message)):
            lerobot.verify(directory)
        code, _, err = run_cli(directory, "--verify")
        self.assertEqual(code, 2)
        self.assertIn(message, err)

    def test_mark_seals_the_observed_frame_and_survives_a_move(self):
        example_before = snapshot(EXAMPLE)
        hashes_before = json.loads((self.bundle/"manifest.json").read_text())["sha256"]
        unmarked = lerobot.verify(self.bundle)
        self.assertNotIn("finding", unmarked)
        self.assertEqual(unmarked, lerobot.verify(EXAMPLE))

        printed = self.mark(self.bundle)
        expected_values = {("action", "shoulder_pan.pos"): 45.14706,
                           ("observation.state", "shoulder_pan.pos"): 61.75649}
        self.assertEqual(printed["episode"], 0)
        self.assertEqual(printed["frame"], 239)
        self.assertEqual(printed["timestamp"], self.trace["timestamps"][239])
        self.assertEqual({(s["key"], s["name"]): s["value"] for s in printed["signals"]}, expected_values)
        self.assertEqual(Path(printed["output"]), self.bundle/"finding.json")

        finding = json.loads((self.bundle/"finding.json").read_text())
        self.assertEqual(finding["schema"], "robot-reel-lerobot-finding-1")
        self.assertEqual(finding["episode"], 0)
        self.assertEqual(finding["frame"], 239)
        self.assertEqual(finding["timestamp"], self.trace["timestamps"][239])
        self.assertEqual({(s["key"], s["name"]): s["value"] for s in finding["signals"]}, expected_values)
        self.assertEqual(finding["note"], NOTE)
        self.assertIn("not a failure label", finding["limitations"])

        hashes_after = json.loads((self.bundle/"manifest.json").read_text())["sha256"]
        self.assertEqual(finding["episode_sha256"], hashes_before["episode.json"])
        self.assertEqual(hashes_after["finding.json"], digest(self.bundle/"finding.json"))
        # Only finding.json is added and index.html gains one embedded line; removing it restores the page exactly.
        self.assertEqual({k: v for k, v in hashes_after.items() if k not in ("finding.json", "index.html")},
                         {k: v for k, v in hashes_before.items() if k != "index.html"})
        page = (self.bundle/"index.html").read_text()
        self.assertEqual(page.replace(lerobot.finding_element(finding), "", 1), (EXAMPLE/"index.html").read_text())
        self.assertEqual(hashes_after["index.html"], digest(self.bundle/"index.html"))
        self.assertEqual((printed["finding_embedded"], printed["viewer_reader_signature"]), (True, True))
        self.assertNotIn("viewer_shows_finding", printed)
        self.assertEqual(snapshot(EXAMPLE), example_before)
        self.assertEqual(list(self.bundle.glob(".*.tmp")), [])

        moved = self.tmp/"elsewhere"/"received"
        shutil.copytree(self.bundle, moved)
        shutil.rmtree(self.bundle)
        result = lerobot.verify(moved)
        self.assertEqual(result["finding"], finding)
        self.assertIs(result.pop("viewer_reader_signature"), True)
        self.assertIs(result.pop("finding_embedded"), True)
        self.assertNotIn("finding_in_viewer", result)
        self.assertEqual({k: v for k, v in result.items() if k != "finding"}, unmarked)
        code, out, err = run_cli(moved, "--verify")
        self.assertEqual(code, 0, err)
        self.assertEqual(json.loads(out)["finding"], finding)

    def test_verify_rejects_tampered_or_unlisted_findings(self):
        marked = self.copy(EXAMPLE, "marked")
        self.mark(marked)

        unhashed = self.copy(marked, "unhashed")
        path = unhashed/"finding.json"
        path.write_text(path.read_text().replace(NOTE, "A different story"))
        self.assert_rejected(unhashed, "Hash mismatch: finding.json")

        episode_edit = self.copy(marked, "episode-edit")
        with open(episode_edit/"episode.json", "a") as stream:
            stream.write("\n")
        self.assert_rejected(episode_edit, "Hash mismatch: episode.json")

        stray = self.copy(EXAMPLE, "stray")
        shutil.copyfile(marked/"finding.json", stray/"finding.json")
        self.assert_rejected(stray, "finding.json is present but not listed in manifest.json")

        unlisted = self.copy(marked, "unlisted")
        manifest = json.loads((unlisted/"manifest.json").read_text())
        del manifest["sha256"]["finding.json"]
        (unlisted/"manifest.json").write_text(json.dumps(manifest, indent=2))
        self.assert_rejected(unlisted, "finding.json is present but not listed in manifest.json")

        cases = [
            ("episode", lambda f: f.update(episode=5), "Finding disagrees with episode.json: episode ("),
            ("value", lambda f: f["signals"][0].update(value=0.5), "Finding disagrees with episode.json: signals ("),
            ("timestamp", lambda f: f.update(timestamp=f["timestamp"]+1), "Finding disagrees with episode.json: timestamp ("),
            ("empty-signals", lambda f: f.update(signals=[]), "Invalid finding: signals ("),
            ("duplicate", lambda f: f["signals"].append(dict(f["signals"][0])), "Invalid finding: signals ("),
            ("empty-note", lambda f: f.update(note=""), "Invalid finding: note ("),
            ("extra-key", lambda f: f.update(extra=True), "Invalid finding: extra ("),
            ("limitations", lambda f: f.update(limitations="A verified failure label."), "Invalid finding: limitations ("),
        ]
        for name, edit, message in cases:
            with self.subTest(name):
                case = self.copy(marked, f"rehashed-{name}")
                rehash(case, edit)
                self.assert_rejected(case, message)

    def test_embedded_finding_must_match_finding_json(self):
        marked = self.copy(EXAMPLE, "marked")
        self.mark(marked)
        finding = json.loads((marked/"finding.json").read_text())

        def rewrite_page(directory, edit):
            """Edit index.html and re-hash it, as a careful tamperer would."""
            path, manifest_path = directory/"index.html", directory/"manifest.json"
            path.write_text(edit(path.read_text()))
            manifest = json.loads(manifest_path.read_text())
            manifest["sha256"]["index.html"] = digest(path)
            manifest_path.write_text(json.dumps(manifest, indent=2))

        other = dict(finding, note="A different story shown in the page")
        cases = [
            ("differs", lambda html: html.replace(lerobot.finding_element(finding), lerobot.finding_element(other)),
             "The finding embedded in index.html differs from finding.json"),
            ("unreadable", lambda html: html.replace(lerobot.finding_element(finding),
                                                     lerobot.FINDING_MARKER+"{not json</script>\n"),
             "The finding embedded in index.html is not readable JSON"),
            ("twice", lambda html: html.replace(lerobot.finding_element(finding), lerobot.finding_element(finding)*2),
             "index.html embeds more than one finding"),
        ]
        for name, edit, message in cases:
            with self.subTest(name):
                case = self.copy(marked, f"page-{name}")
                rewrite_page(case, edit)
                self.assert_rejected(case, message)

        # A page that shows a finding the manifest does not list is not a valid unmarked export.
        orphan = self.copy(marked, "orphan")
        (orphan/"finding.json").unlink()
        manifest = json.loads((orphan/"manifest.json").read_text())
        del manifest["sha256"]["finding.json"]
        (orphan/"manifest.json").write_text(json.dumps(manifest, indent=2))
        self.assert_rejected(orphan, "index.html embeds a finding but manifest.json lists no finding.json")

    def test_a_folder_marked_by_0_19_0_still_verifies(self):
        """0.19.0 wrote finding.json and its manifest entry but left index.html unchanged."""
        legacy = self.copy(EXAMPLE, "legacy")
        self.mark(legacy)
        manifest = json.loads((legacy/"manifest.json").read_text())
        shutil.copyfile(EXAMPLE/"index.html", legacy/"index.html")
        manifest["sha256"]["index.html"] = digest(legacy/"index.html")
        (legacy/"manifest.json").write_text(json.dumps(manifest, indent=2))
        self.old_page(legacy)  # 0.19.0 pages also lack the reader script
        result = lerobot.verify(legacy)
        self.assertIs(result["finding_embedded"], False)
        self.assertIs(result["viewer_reader_signature"], False)
        self.assertEqual(result["finding"]["frame"], 239)

    def old_page(self, directory):
        """An export whose page script predates the finding reader (as from 0.19.0), re-hashed in its manifest."""
        path, manifest_path = directory/"index.html", directory/"manifest.json"
        page = path.read_text()
        self.assertEqual(page.count(lerobot.FINDING_READER), 1)
        path.write_text(page.replace(lerobot.FINDING_READER, "null"))
        manifest = json.loads(manifest_path.read_text())
        manifest["sha256"]["index.html"] = digest(path)
        manifest_path.write_text(json.dumps(manifest, indent=2))

    def test_mark_and_verify_agree_on_an_old_page(self):
        # A note quoting the reader sits in the embedded JSON, outside the script, and cannot match.
        quoting = f"Note mentions {lerobot.FINDING_READER} on purpose"
        for name, note in (("plain", NOTE), ("quoting", quoting)):
            with self.subTest(name):
                old = self.copy(EXAMPLE, f"old-page-{name}")
                self.old_page(old)
                code, out, err = run_cli(*mark_args(old, note=note))
                self.assertEqual(code, 0, err)
                printed = json.loads(out)
                result = lerobot.verify(old)
                for fields in (printed, result):
                    self.assertEqual((fields["finding_embedded"], fields["viewer_reader_signature"]), (True, False))
        current = self.mark(self.bundle)
        result = lerobot.verify(self.bundle)
        self.assertEqual((current["viewer_reader_signature"], result["finding_embedded"], result["viewer_reader_signature"]),
                         (True, True, True))

    def test_reader_signature_is_only_a_static_text_check(self):
        """R2 review probe: an inert comment quoting the reader matches the signature without adding a reader.

        The output must therefore not claim display: no finding_in_viewer / viewer_shows_finding key,
        and the docs must call the field a static check. The browser test shows such a page has no panel."""
        old = self.copy(EXAMPLE, "old-page-comment")
        self.old_page(old)
        path, manifest_path = old/"index.html", old/"manifest.json"
        page = path.read_text()
        path.write_text(page.replace("<script>\n", f"<script>\n/* {lerobot.FINDING_READER} */\n", 1))
        manifest = json.loads(manifest_path.read_text())
        manifest["sha256"]["index.html"] = digest(path)
        manifest_path.write_text(json.dumps(manifest, indent=2))
        code, out, err = run_cli(*mark_args(old))
        self.assertEqual(code, 0, err)
        printed, result = json.loads(out), lerobot.verify(old)
        for fields in (printed, result):
            self.assertIs(fields["viewer_reader_signature"], True)
            self.assertFalse({"finding_in_viewer", "viewer_shows_finding"} & set(fields))
        docs = (Path(__file__).resolve().parents[1]/"docs"/"lerobot.md").read_text()
        self.assertIn("`viewer_reader_signature`", docs)
        self.assertIn("does not show that the reader runs", docs)
        # The draft names appear only in the sentence explaining their replacement.
        self.assertEqual(docs.count("finding_in_viewer"), 1)
        self.assertIn("were replaced because they implied display", docs)

    def test_a_second_io_failure_can_leave_files_that_verify_rejects(self):
        """Documented limit: rollback is best effort, not crash atomicity."""
        real_replace = os.replace

        def failing_replace(src, dst, *args, **kwargs):
            # Writing the marked page succeeds; the manifest and the page restore both fail.
            if Path(dst).name == "manifest.json" or (Path(dst).name == "index.html" and failing_replace.page_written):
                raise OSError("simulated I/O failure")
            if Path(dst).name == "index.html":
                failing_replace.page_written = True
            return real_replace(src, dst, *args, **kwargs)
        failing_replace.page_written = False

        with mock.patch.object(lerobot.os, "replace", failing_replace):
            code, _, err = run_cli(*mark_args(self.bundle))
        self.assertEqual(code, 2)
        self.assertIn("simulated I/O failure", err)
        # finding.json and the marked page remain; the manifest is the old one.
        self.assertTrue((self.bundle/"finding.json").exists())
        self.assertNotEqual((self.bundle/"index.html").read_bytes(), (EXAMPLE/"index.html").read_bytes())
        self.assert_rejected(self.bundle, "finding.json is present but not listed in manifest.json")
        (self.bundle/"finding.json").unlink()
        self.assert_rejected(self.bundle, "Hash mismatch: index.html")

    def crlf(self, directory):
        """Convert the page to CRLF line endings, a valid export as far as the manifest is concerned."""
        path, manifest_path = directory/"index.html", directory/"manifest.json"
        path.write_bytes(path.read_bytes().replace(b"\n", b"\r\n"))
        manifest = json.loads(manifest_path.read_text())
        manifest["sha256"]["index.html"] = digest(path)
        manifest_path.write_text(json.dumps(manifest, indent=2))
        lerobot.verify(directory)
        return path.read_bytes()

    def test_crlf_page_is_marked_in_its_own_line_endings(self):
        original = self.crlf(self.bundle)
        self.mark(self.bundle)
        page = (self.bundle/"index.html").read_bytes()
        finding = json.loads((self.bundle/"finding.json").read_text())
        inserted = lerobot.finding_element(finding, "\r\n").encode("utf-8")
        self.assertEqual(page.count(inserted), 1)
        self.assertEqual(page.replace(inserted, b"", 1), original)
        self.assertNotIn(b"\n", page.replace(b"\r\n", b""))
        self.assertIs(lerobot.verify(self.bundle)["viewer_reader_signature"], True)

    def test_failed_mark_restores_a_crlf_page_byte_for_byte(self):
        original = self.crlf(self.bundle)
        manifest = (self.bundle/"manifest.json").read_bytes()
        unmarked = lerobot.verify(self.bundle)
        real_replace = os.replace

        def failing_replace(src, dst, *args, **kwargs):
            if Path(dst).name == "manifest.json":
                raise OSError("simulated failure while replacing manifest.json")
            return real_replace(src, dst, *args, **kwargs)

        with mock.patch.object(lerobot.os, "replace", failing_replace):
            code, _, err = run_cli(*mark_args(self.bundle))
        self.assertNotEqual(code, 0)
        self.assertIn("simulated failure", err)
        self.assertEqual((self.bundle/"index.html").read_bytes(), original)
        self.assertEqual((self.bundle/"manifest.json").read_bytes(), manifest)
        self.assertFalse((self.bundle/"finding.json").exists())
        self.assertEqual(list(self.bundle.glob(".*.tmp")), [])
        self.assertEqual(lerobot.verify(self.bundle), unmarked)

    def test_hostile_note_and_names_stay_inert_text(self):
        hostile = "</script><script>window.pwned=1</script><img src=x onerror=alert(1)> https://evil.example/?$(rm -rf ~)"
        code, out, err = run_cli(*mark_args(self.bundle, note=hostile))
        self.assertEqual(code, 0, err)
        page = (self.bundle/"index.html").read_text()
        self.assertEqual(page.count("</script>"), (EXAMPLE/"index.html").read_text().count("</script>")+1)
        self.assertNotIn("<script>window.pwned", page)
        self.assertNotIn("<img src=x", page)
        self.assertEqual(lerobot.verify(self.bundle)["finding"]["note"], hostile)

    def test_cli_errors_write_nothing(self):
        pairs = [f"{s['key']}/{n}" for s in self.trace["series"] for n in s["names"]]
        self.assertGreaterEqual(len(pairs), 9)
        last = self.trace["length"]-1

        def tamper_clip(directory):
            with open(directory/self.trace["cameras"][0]["file"], "ab") as stream:
                stream.write(b"tampered")

        cases = [
            ("out-of-range", mark_args("{dir}", frame=last+1), f"choose 0..{last}", None),
            ("negative", mark_args("{dir}", frame=-1), f"choose 0..{last}", None),
            ("unknown", mark_args("{dir}", signals=["action/elbow_twist"]), "available: action/shoulder_pan.pos", None),
            ("malformed", mark_args("{dir}", signals=["shoulder_pan.pos"]), "must be KEY/NAME", None),
            ("duplicate", mark_args("{dir}", signals=[SIGNALS[0], SIGNALS[0]]), "listed more than once", None),
            ("nine", mark_args("{dir}", signals=pairs[:9]), "choose 1 to 8 signals; got 9", None),
            ("empty-note", mark_args("{dir}", note=""), "the note must have 1 to 2000 characters", None),
            ("control-note", mark_args("{dir}", note="bell\u0007"), "control characters", None),
            ("with-verify", mark_args("{dir}")+["--verify"], "remove --verify", None),
            ("with-output", mark_args("{dir}")+["--output", "elsewhere"], "remove --output", None),
            ("signal-alone", ["{dir}", "--verify", "--signal", SIGNALS[0]], "--signal and --note apply with --mark FRAME", None),
            ("tampered-clip", mark_args("{dir}"), "Hash mismatch: cameras/", tamper_clip),
        ]
        for name, args, message, prepare in cases:
            with self.subTest(name):
                case = self.copy(EXAMPLE, f"cli-{name}")
                if prepare:
                    prepare(case)
                manifest = (case/"manifest.json").read_bytes()
                code, _, err = run_cli(*[case if a == "{dir}" else a for a in args])
                self.assertEqual(code, 2)
                self.assertIn(message, err)
                self.assertFalse((case/"finding.json").exists())
                self.assertEqual((case/"manifest.json").read_bytes(), manifest)
                self.assertEqual((case/"index.html").read_bytes(), (EXAMPLE/"index.html").read_bytes())
                self.assertEqual(list(case.glob(".*.tmp")), [])

    def test_an_already_marked_copy_is_not_marked_again(self):
        self.mark(self.bundle)
        finding = (self.bundle/"finding.json").read_bytes()
        manifest = (self.bundle/"manifest.json").read_bytes()
        code, _, err = run_cli(*mark_args(self.bundle, frame=10, note="Second look"))
        self.assertEqual(code, 2)
        self.assertIn("already holds a finding", err)
        self.assertEqual((self.bundle/"finding.json").read_bytes(), finding)
        self.assertEqual((self.bundle/"manifest.json").read_bytes(), manifest)

    def test_check_media_output_keeps_finding(self):
        try:
            import imageio_ffmpeg  # noqa: F401
        except ImportError:
            self.skipTest("--check-media needs imageio-ffmpeg (robot-reel[lerobot])")
        self.mark(self.bundle)
        moved = self.tmp/"received"/"so101"
        moved.parent.mkdir()
        shutil.move(str(self.bundle), str(moved))
        code, out, err = run_cli(moved, "--verify", "--check-media")
        self.assertEqual(code, 0, err)
        result = json.loads(out)
        self.assertEqual(result["checked_video_frames"], 606)
        finding = result["finding"]
        self.assertEqual(finding, lerobot.verify(moved)["finding"])
        self.assertEqual(finding["frame"], 239)
        self.assertEqual(finding["note"], NOTE)
        self.assertEqual([s["value"] for s in finding["signals"]], [45.14706, 61.75649])

    def recorded_source(self, directory):
        """Patch the dataset reader to return the exported episode, as an unchanged source would."""
        trace = json.loads((directory/"episode.json").read_text())
        return (mock.patch.object(lerobot, "Source"),
                mock.patch.object(lerobot, "read_episode", return_value=trace))

    def fake_decoder(self, directory):
        """A synthetic decoder that reports exactly the recorded frame count for every clip."""
        trace = json.loads((directory/"episode.json").read_text())
        decoder = types.SimpleNamespace(
            count_frames_and_secs=lambda path: (trace["length"], trace["length"]/trace["fps"]))
        return mock.patch.dict(sys.modules, {"imageio_ffmpeg": decoder})

    def received(self):
        self.mark(self.bundle)
        moved = self.tmp/"received"/"so101"
        moved.parent.mkdir()
        shutil.move(str(self.bundle), str(moved))
        return moved

    def assert_sealed(self, result, directory):
        finding = result["finding"]
        self.assertEqual(finding, lerobot.verify(directory)["finding"])
        self.assertEqual(finding["episode"], 0)
        self.assertEqual(finding["frame"], 239)
        self.assertEqual(finding["note"], NOTE)
        self.assertEqual([f"{s['key']}/{s['name']}" for s in finding["signals"]], list(SIGNALS))
        self.assertEqual([s["value"] for s in finding["signals"]], [45.14706, 61.75649])

    def test_check_source_output_keeps_finding(self):
        moved = self.received()
        source, reader = self.recorded_source(moved)
        with source, reader as read:
            code, out, err = run_cli(moved, "--verify", "--check-source", "--dataset", "recorded-source")
        self.assertEqual(code, 0, err)
        read.assert_called_once()
        result = json.loads(out)
        self.assertEqual(result["checked_values"], 3939)
        self.assert_sealed(result, moved)

    def test_check_media_output_keeps_finding_with_synthetic_decoder(self):
        moved = self.received()
        with self.fake_decoder(moved):
            code, out, err = run_cli(moved, "--verify", "--check-media")
        self.assertEqual(code, 0, err)
        result = json.loads(out)
        self.assertEqual(result["checked_video_frames"], 606)
        self.assert_sealed(result, moved)

    def test_check_media_and_source_together_keep_finding(self):
        moved = self.received()
        source, reader = self.recorded_source(moved)
        with self.fake_decoder(moved), source, reader:
            code, out, err = run_cli(moved, "--verify", "--check-media", "--check-source",
                                     "--dataset", "recorded-source")
        self.assertEqual(code, 0, err)
        result = json.loads(out)
        self.assertEqual(result["checked_video_frames"], 606)
        self.assertEqual(result["checked_values"], 3939)
        self.assert_sealed(result, moved)

    def test_unmarked_check_flags_report_no_finding(self):
        source, reader = self.recorded_source(self.bundle)
        with self.fake_decoder(self.bundle), source, reader:
            code, out, err = run_cli(self.bundle, "--verify", "--check-media", "--check-source",
                                     "--dataset", "recorded-source")
        self.assertEqual(code, 0, err)
        self.assertNotIn("finding", json.loads(out))

    def test_failed_manifest_replacement_rolls_back(self):
        unmarked = lerobot.verify(self.bundle)
        manifest = (self.bundle/"manifest.json").read_bytes()
        real_replace = os.replace

        def failing_replace(src, dst, *args, **kwargs):
            if Path(dst).name == "manifest.json":
                raise OSError("simulated failure while replacing manifest.json")
            return real_replace(src, dst, *args, **kwargs)

        with mock.patch.object(lerobot.os, "replace", failing_replace):
            code, _, err = run_cli(*mark_args(self.bundle))
        self.assertNotEqual(code, 0)
        self.assertIn("simulated failure", err)
        self.assertFalse((self.bundle/"finding.json").exists())
        self.assertEqual((self.bundle/"manifest.json").read_bytes(), manifest)
        self.assertEqual((self.bundle/"index.html").read_bytes(), (EXAMPLE/"index.html").read_bytes())
        self.assertEqual(list(self.bundle.glob(".*.tmp")), [])
        self.assertEqual(lerobot.verify(self.bundle), unmarked)


if __name__ == "__main__":
    unittest.main()
