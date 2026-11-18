"""--dataset must not be silently ignored by --verify without --check-source."""
from contextlib import redirect_stderr, redirect_stdout
import io
import os
from pathlib import Path
import tempfile
import unittest

from robot_reel.lerobot import main

NEW_MESSAGE = "--dataset applies with --check-source"
OLD_MESSAGE = "--check-media, --check-source and --dataset apply with --verify"


class DatasetNeedsCheckSourceTest(unittest.TestCase):
    def run_cli(self, *flags):
        """Run the CLI from an empty working directory on an export that does not exist."""
        previous = os.getcwd()
        with tempfile.TemporaryDirectory() as temporary:
            os.chdir(temporary)
            try:
                stdout, stderr = io.StringIO(), io.StringIO()
                with redirect_stdout(stdout), redirect_stderr(stderr), self.assertRaises(SystemExit) as caught:
                    main(["missing-export", *flags])
                created = sorted(p.name for p in Path(temporary).iterdir())
            finally:
                os.chdir(previous)
        return caught.exception.code, stdout.getvalue(), stderr.getvalue(), created

    def test_verify_with_dataset_but_no_source_check_is_rejected(self):
        for flags in (["--verify", "--dataset", "D"],
                      ["--verify", "--check-media", "--dataset", "D"]):
            with self.subTest(flags=flags):
                code, stdout, stderr, created = self.run_cli(*flags)
                self.assertEqual(code, 2)
                self.assertIn(NEW_MESSAGE, stderr)
                self.assertIn("add --check-source to compare the export with that dataset", stderr)
                self.assertEqual(stdout, "")
                self.assertEqual(created, [])

    def test_dataset_without_verify_keeps_the_existing_message(self):
        code, stdout, stderr, _ = self.run_cli("--dataset", "D")
        self.assertEqual(code, 2)
        self.assertIn(OLD_MESSAGE, stderr)
        self.assertNotIn(NEW_MESSAGE, stderr)
        self.assertEqual(stdout, "")

    def test_source_check_with_dataset_still_passes_argument_parsing(self):
        for flags in (["--verify", "--check-source", "--dataset", "D"],
                      ["--verify", "--check-media", "--check-source", "--dataset", "D"]):
            with self.subTest(flags=flags):
                code, stdout, stderr, _ = self.run_cli(*flags)
                # The export does not exist, so the run fails later, on the missing files.
                self.assertEqual(code, 2)
                self.assertNotIn(NEW_MESSAGE, stderr)
                self.assertNotIn(OLD_MESSAGE, stderr)
                self.assertEqual(stdout, "")


if __name__ == "__main__":
    unittest.main()
