"""Published pages must stay inside a transfer budget.

The replays are single self-contained HTML files, so a page's recorded data is
part of its download. GitHub Pages serves them compressed -- the Stress Lab page
is 3.59 MB on disk but transfers as 1,327,339 bytes with `content-encoding:
gzip` -- and gzip level 6 reproduces that within 0.2%, so that is what this
measures. The budget leaves the current worst page (the Stress Lab, at 1.26 MiB)
about a fifth of headroom.

To buy room, drop fields the viewer never reads from the embedded payload while
keeping them in the downloadable trace and MCAP: `raw_camera_sha256`,
`proposed_action`, `sim_time`, `next_success` and `reward` account for about
1.36 MB of the 3.57 MB payload.
"""
import gzip
from pathlib import Path
import unittest

from robot_reel.pages import PAGES

ROOT = Path(__file__).resolve().parents[1]
LIMIT = 1536 * 1024
LEVEL = 6


class PageWeightTest(unittest.TestCase):
    def test_published_pages_stay_inside_the_transfer_budget(self):
        heavy = []
        for name in sorted(PAGES):
            transfer = len(gzip.compress((ROOT/name).read_bytes(), LEVEL))
            if transfer > LIMIT:
                heavy.append(f"{name} ({transfer/1024/1024:.2f} MiB gzipped)")
        self.assertEqual(heavy, [], "Over the "
                         f"{LIMIT/1024/1024:.2f} MiB budget: {', '.join(heavy)}")
