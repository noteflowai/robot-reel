# Contributing

Keep the distinction between physics rollouts, kinematic animation, and agent
decisions explicit in code, telemetry, and video labels.

Public introductions should start with a user workflow and the files it produces.
Keep experiment counts and outcomes next to their scope; put detailed methods in
linked guides or named disclosure panels. Keep asset licenses visible. Naming
history and industry research belong in their own documents. Check the English
and Chinese READMEs, website and Hugging Face card together when changing claims.

Run `python3 -m unittest discover -s tests -v` directly from the checkout; these
tests require only the standard library. CI also runs them with `python -S`.
For capture/rendering development, follow the README virtual-environment setup
and install the declared dependencies with `python -m pip install -e .`.
Do not install only `imageio-ffmpeg`: MuJoCo and the remaining runtime dependencies
are required for recording too.
For capture changes, run the credential-free demo and verify its output.
Do not require a paid model or real hardware for ordinary tests.

Changes to a replay template's inline script should pass `npm run check:js`
before `npm test`. Keep the scripts inline: the exported pages must stay
self-contained enough to open from `file://`. The published pages under `docs/`
carry a copy of that script, so rebuild them, or run
`python3 -m robot_reel.pages --write`, and commit the refreshed hashes with the
template change. Synchronization also refreshes matching files in local offline
ZIPs and the manifests that hash those archives. It preserves the original
recorded media and source-capture manifests. Release assets are immutable
snapshots: publish an updated archive separately when releasing a new version.

Stress and cloth exports use separate input and output directories. Build in
a temporary directory on the destination filesystem, validate the complete site
and archive, and only then rename it into place. Validation errors or Python
interruptions must not leave a partial output, and exports must never remove
files another writer has added. Exercise failure and retry as well as a
successful installed-wheel build. Stress export recovery is included starting
with 0.7.1; the published 0.7.0 wheel retains its original behavior.

The static landing page is synchronized in full, so its markup, styles and
script travel together. Its on-demand Butterfly video is derived from the
verified GIF, retaining the source samples and clock. Rebuild with
`python scripts/build_landing_preview.py`; `--verify` checks provenance, the
1 MiB video budget, and every decoded frame against its mapped source with a
bounded allowance for lossy color compression. The original GIF and trace remain
the source of truth. Browser checks require no GIF/video request before play,
and cover filtering, history, keyboard, reduced motion, offline and no-JS use.

Blender changes should also pass the saved-project check in [docs/blender.md](docs/blender.md).
For the Newton adapter, install `.[newton]`, record a fresh CPU run and use
`--verify --check-usd`. The native Blender USD import check and page rebuild
commands are in [docs/newton.md](docs/newton.md).

Please include a short reproducible command and the observed result with fixes.
CI runs on pull requests and on pushes to `main`, so open a pull request to have
a branch checked. Pages and tagged releases wait for the same six validation
jobs, including a real installed-wheel export and a non-root container check.
See [distribution checks and publishing](docs/distribution.md) to reproduce
them locally and keep packaged notices synchronized.
Do not commit credentials, account-specific logs, downloaded robot meshes, or
large videos. Release assets are the place for shareable video bundles; no
tracked file may exceed 25 MB. A published page's recorded data is part of its
download, so each `docs/**/index.html` also has a compressed transfer budget
(see `tests/test_page_weight.py` for the current limit and how to buy room).

## Re-encoding published media

The trial videos under `docs/stress/runs/` have five downstream consumers. A re-encode
that stops early leaves the repository claiming things that are no longer true.

1. `run-manifest.json` per attempt records each MP4's hash.
2. `media-checks.json` and `manifest.json` — regenerate with `check_media()` and
   `file_hash()` over `required_files()`, then confirm with `stress_site.verify_site()`.
3. The preview: `docs/stress/preview-manifest.json` lists the seed-09 videos in
   `sources`; rebuild with `scripts/build_stress_showcase.py`.
4. The Rerun workspace: `docs/rerun/seed-09.rrd` *embeds* six of these videos.
   Refreshing the recorded hash without rebuilding would make it claim it embedded
   videos it does not contain. Export to a new temporary `.rrd` with
   `robot_reel.stress_rerun`, then package it with
   `scripts/build_rerun_showcase.py` and a reviewed viewer screenshot.
5. The Hugging Face Space thumbnail: `huggingface/thumbnail.json` records the hash of
   `docs/stress/poster.png`, which step 3 regenerates. Rebuild with
   `scripts/build_huggingface_thumbnail.py`.

Build a new offline archive from the verified folder, update
`PUBLISHED_ARCHIVE_HREF` and the published methodology, and publish it under a new
evidence tag. Keep historical release assets unchanged. Before merging, run
`python scripts/check_stress_download.py --archive /path/to/experiment.zip`,
then run the same command without `--archive` to verify the actual public download.
The main-branch deployment requires that public download to match the source.

The September 2026 re-encode at `quality=8` reduces the sixty MP4s from 46.7 MiB to
28.7 MiB and the portable Rerun recording from 6.61 MB to 4.48 MB. The MP4s are lossy
viewing derivatives; retain every frame and the original trace, policy-input
hashes, controls, telemetry and outcome records.
