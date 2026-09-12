# Installing and releasing Robot Reel

Python 3.12 or newer is required. The browser demos need no installation.
Published wheels and source distributions are available from
[GitHub Releases](https://github.com/noteflowai/robot-reel/releases).
PyPI publishing is optional and is not enabled for this release; do not assume
that `pip install robot-reel` resolves to this project's current version.

The release also includes `robot-reel-seed-09.rrd`: the verified native
[Rerun recording](telemetry.md#native-rerun-workspace), with six embedded videos
and the original evidence. Open it in Rerun 0.37.2.

Download the wheel and `SHA256SUMS` from the same release, then install the
downloaded file in a virtual environment:

```bash
# Run from the directory containing the downloaded release files.
sha256sum --check --ignore-missing SHA256SUMS
python3 -m venv .venv
source .venv/bin/activate
python -m pip install ./robot_reel-0.5.0-py3-none-any.whl
robot-reel --help
```

The package contains its viewer templates and Stress export notices, license and
methods. Recordings and model weights are separate inputs. For example, an
existing complete Stress collection can be exported from any working directory:

```bash
python -m pip install 'mcap==1.4.0'
python -m robot_reel.stress_site /path/to/recording /path/to/new-site
robot-reel stress /path/to/new-site --check-media --check-mcap
```

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
sources. It also runs the installed CLI on the VLA recording.

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
    "$reel_source/scripts/check_distribution.py" --source "$reel_source"
)
```

When updating `LICENSE`, `licenses/VLA-MEDIA-NOTICE.txt` or `docs/stress.md`,
refresh the corresponding `LICENSE.txt`, `NOTICE.txt` or `METHODS.txt` under
`robot_reel/resources/stress/`. A standard-library test rejects stale copies.

## Publishing

`Check` invokes six reusable validation jobs: core Python/MCP/media, browser,
native Rerun, Newton/OpenUSD, installed distributions and Docker. Only after all
six pass does a main-branch run invoke the Pages deployment. Manually rerunning
`Check` on main also performs the checks before deploying.

A `v*` tag must exactly match `pyproject.toml` and have a version section in
`CHANGELOG.md`. The release workflow runs the same six jobs and publishes their
tested wheel and source distribution with SHA-256 checksums. It does not rebuild
different artifacts after validation. The native Rerun recording is copied from
the same checked commit and included in those checksums.

PyPI publishing additionally requires the project's trusted publisher and the
GitHub `pypi` environment to be configured, then the repository variable
`PYPI_PUBLISH_ENABLED` set to `true`. Until then the PyPI job is skipped and
GitHub Releases remains the installation channel. Existing recorded-data
release assets retain their original versioned URLs.
