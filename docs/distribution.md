# Installing and releasing Robot Reel

Python 3.12 or newer is required. The browser demos need no installation.
Published wheels and source distributions are available from
[GitHub Releases](https://github.com/noteflowai/robot-reel/releases).
PyPI publishing is optional and is not enabled for this release; do not assume
that `pip install robot-reel` resolves to this project's current version.

The release also includes `robot-reel-seed-09.rrd`: the verified native
[Rerun recording](telemetry.md#native-rerun-workspace), with six embedded videos
and the original evidence. Open it in Rerun 0.37.2.

Starting with 0.6.0, releases also carry the complete offline Stress Lab,
`robot-reel-seed-09-review.json` and `START-HERE.md`. Follow the
[offline lab guide](offline-lab.md) to open the experiment and import a review
without installing Python or using a GPU.

Starting with 0.7.0, releases also include `robot-reel-cloth-experiment.zip`
and its standalone USD scene. The installed CLI verifies and re-exports the
complete cloth experiment without Newton, Blender, a GPU or a source checkout.

Download the wheel and `SHA256SUMS` from the same release, then install the
downloaded file in a virtual environment:

```bash
# Run from the directory containing the downloaded release files.
sha256sum --check --ignore-missing SHA256SUMS
python3 -m venv .venv
source .venv/bin/activate
python -m pip install ./robot_reel-0.15.0-py3-none-any.whl
robot-reel --help
```

The package contains its viewer templates and the Stress/Cloth export methods
and licenses. Recordings and model weights are separate inputs. For example, an
existing complete Stress collection can be exported from any working directory:

```bash
python -m pip install 'mcap==1.4.0'
python -m robot_reel.stress_site /path/to/recording /path/to/new-site
robot-reel stress /path/to/new-site --check-media --check-mcap
```

Starting with 0.7.1, Stress exports validate the complete lab in a temporary
directory before publishing it at the requested path. Missing dependencies,
media errors or a Python interruption leave no partial export there, so fix the
cause and retry the same command. The input and output must be separate; existing
files and symlink destinations are protected. Earlier releases retain their
original behavior.

After extracting the cloth experiment, use a fresh destination:

```bash
robot-reel cloth --output /path/to/cloth-lab --verify
robot-reel cloth --export-from /path/to/cloth-lab --output /path/to/cloth-copy
```

The new folder includes an offline `experiment.zip`. Source data and saved
native reports remain unchanged. Optional `--check-usd` performs native readback
again after installing `usd-core==26.3`; plain export only verifies saved reports
and their source hashes. See the [cloth method](cloth.md#use-the-installed-package).

Starting with 0.8.0, both offline labs include the current inspection tools:
paired outcome groups and report export for Stress, and sample import plus
1080p figures for Cloth. The installed CLI independently checks both report
types. The release includes `robot-reel-paired-outcomes.json`, exported by
the tested wheel and compared with the offline browser at two screen sizes.

The VLA collector keeps its separately pinned GPU environment; installing the
main runtime there would conflict with its MuJoCo version. See the
[GPU guide](gpu-access.md) for recording, and [telemetry](telemetry.md) for the
optional Rerun environment.

## Containers and file ownership

The image installs a regular wheel and runs as `robotreel`, UID/GID 1000. It
includes the recorded VLA episode and braking comparison. New recordings and
exports go into `/app/artifacts`. Build and check the included episode:

```bash
docker build -t robot-reel .
docker run --rm robot-reel
```

For a bind mount, create the output directory first and use the host user's
UID/GID. This keeps generated files owned by the invoking user:

```bash
mkdir -p artifacts
docker run --rm --user "$(id -u):$(id -g)" \
  -v "$PWD/artifacts:/app/artifacts" robot-reel \
  robot-reel direct docs/compare/braking \
  --plan examples/contact-storyboard.json --output artifacts/director
```

The image uses writable temporary cache paths for arbitrary UIDs. It does not
include Blender, Newton or the separately pinned VLA GPU collector.
`bash scripts/check_container.sh robot-reel` checks the default command,
non-root execution, writable output, and a real export with UID/GID 12345.

## Distribution checks

CI builds the wheel from the source distribution, checks metadata with Twine,
and installs it in a clean environment. From outside the checkout it rebuilds
the complete thirty-trial Stress site, decodes all sixty videos, reads back
3,915 MCAP records and compares the archived notices with their maintained
sources. It also runs the installed CLI on the VLA recording and a sample review.
The installed cloth CLI exports all 42,471 vertex samples, checks the complete
archive, and preserves every source binary and native report. CI retains both
exact ZIPs; the browser job extracts them, blocks network access, checks playback,
source payloads, scene downloads and sharing at desktop and mobile sizes.

To reproduce that check from a source checkout:

```bash
python3 -m venv .venv
.venv/bin/pip install build twine
.venv/bin/python -m build
.venv/bin/python -m twine check dist/*
reel_source="$PWD"
reel_check="$(mktemp -d)"
python3 -m venv "$reel_check/installed"
"$reel_check/installed/bin/pip" install dist/*.whl 'mcap==1.4.0'
"$reel_check/installed/bin/pip" check
(
  cd "$reel_check"
  PYTHONPATH= "$reel_check/installed/bin/python" \
    "$reel_source/scripts/check_distribution.py" --source "$reel_source" \
    --release-assets "$reel_check/offline-assets"
)
# Use the repository's existing npm/Playwright environment for the browser check.
python3 -m zipfile -e "$reel_check/offline-assets/robot-reel-stress-experiment.zip" "$reel_check/lab"
node scripts/check_offline_release.cjs "$reel_check/lab" \
  "$reel_check/offline-assets/robot-reel-seed-09-review.json" \
  "$reel_check/offline-assets/robot-reel-paired-outcomes.json"
python3 -m zipfile -e "$reel_check/offline-assets/robot-reel-cloth-experiment.zip" "$reel_check/cloth"
node scripts/check_cloth_release.cjs "$reel_check/cloth"
```

When updating `LICENSE`, `licenses/VLA-MEDIA-NOTICE.txt` or `docs/stress.md`,
refresh the corresponding `LICENSE.txt`, `NOTICE.txt` or `METHODS.txt` under
`robot_reel/resources/stress/`. A standard-library test rejects stale copies.
Likewise, `robot_reel/resources/cloth/` contains copies of `LICENSE` and
`docs/cloth.md` named `LICENSE.txt` and `METHODS.txt`.

## Publishing

`Check` invokes six reusable validation jobs: core Python/MCP/media, browser,
native Rerun, Newton/OpenUSD, installed distributions and Docker. Only after all
six pass does a main-branch run invoke the Pages deployment. Manually rerunning
`Check` on main also performs the checks before deploying.

A `v*` tag must exactly match `pyproject.toml` and have a version section in
`CHANGELOG.md`. The release workflow runs the same six jobs and publishes their
tested wheel, source distribution, four offline ZIPs, cloth USD, sample reviews and start guide
with SHA-256 checksums. It does not rebuild different artifacts after validation.
The native Rerun recording is copied from the same checked commit and included
in those checksums. The release assembler rejects missing, stale or extra files.
Offline artifacts remain separate from Python distributions, so optional PyPI
publishing receives only the wheel and source distribution.
Files are uploaded to a draft first. The uploader validates the complete local
SHA256SUMS inventory, the tag's source commit, and every existing remote asset's
size and GitHub SHA-256 digest before uploading missing files. A lost upload
response triggers a state check before retrying, so an already completed upload
is retained. A missing upload gets at most three attempts. Only a complete,
verified draft reaches the separate publication step.

An existing public release or draft stops a new release workflow. To recover an
interrupted draft, download the **original** `dist` and `offline-lab` artifacts
from the run whose package/browser jobs passed. Use `prepare_release.py` with
that source revision to assemble the same files; do not rebuild a new wheel.
Then invoke the upload helper with that tag and its tested commit:

```bash
python scripts/upload_release_assets.py --repo OWNER/REPO --tag vX.Y.Z \
  --source-commit FULL_TESTED_COMMIT --assets release-assets
```

The helper never publishes or overwrites files. It rejects public releases,
changed local checksums, unknown/duplicate remote files, partial starter assets
and mismatching remote hashes. After a successful `verified: true` result,
publish the complete draft with `gh release edit TAG --draft=false --latest`,
then verify its public downloads. A mismatch requires investigation; preserve
the existing files. The 0.10.0 recovery is recorded in
[the publication receipts](../notes/outreach/publication-0.10.0.json).

PyPI publishing additionally requires the project's trusted publisher and the
GitHub `pypi` environment to be configured, then the repository variable
`PYPI_PUBLISH_ENABLED` set to `true`. Until then the PyPI job is skipped and
GitHub Releases remains the installation channel. Existing recorded-data
release assets retain their original versioned URLs.
