# Cloth Lab: recorded GPU deformation → OpenUSD → Blender

Three independent Newton 1.6.0 / SolverVBD simulations start from the same
horizontal sheet. Only the numerical bending coefficient, `edge_ke`, changes:
**0.01, 1.0 and 100.0**. The public recording ran on **NVIDIA L40S / CUDA**,
using Warp 1.17.0. The browser replays saved vertices; it does not simulate.

## Explore

Open the [Cloth Lab](https://noteflowai.github.io/robot-reel/cloth/).
It starts paused at the largest recorded RMS distance from the 0.01 case.
Press **Release all three**, scrub, step, orbit with the camera buttons or
drag sideways. Overlay compares the original coordinates. Side-by-side
presentation adds X offsets of −1.35, 0 and +1.35 m; metrics exclude them.
**Share sample** preserves the sample, selected case, presentation mode and
camera rotation. Older links without a camera angle open with the default view.

The current website and source export also offer **Figure PNG** and **Sample JSON**.
Figure PNG pauses at the selected sample and renders a **1920 × 1080** image
from original vertices with your camera angle, selected case, recorded clock,
RMS separation, free-edge drop, pin displacement and the positions SHA-256.
The image includes the full RMS curve and experiment limits, ready for a slide
or technical discussion. Its fixed layout is independent of the screen size.

Sample JSON uses schema `robot-reel-cloth-sample-1`. It preserves full-precision
measurements in metres, zero-based sample and case indices, time in seconds,
the one-based Blender frame, camera angles in radians, presentation offsets,
source recorder metadata and the positions fingerprint. Append its
`replay_fragment` to the matching lab's address to restore the view. It contains
no local filesystem path. Metrics use original positions; pin displacement
is the maximum over fixed vertices **in the selected case and sample**.
Save the PNG and JSON without changing the selection to keep them paired.
These are derived inspection exports, not a new simulation or signed evidence.
Both downloads work offline. The immutable **0.7.1** release archives predate
these two buttons; use this page's **Offline experiment** or export from the
current source to include them.

Download **Offline experiment**, extract it, and open `index.html`. The HTML
contains its positions and metadata, so replay also works from `file://`
without fetching data, fonts, libraries or a GPU service. Keep the entire
folder to retain the source downloads and USD scene. Navigation and method
links to GitHub are optional online links.

## Controlled setup

| Setting | Value |
| --- | --- |
| Grid | 12 × 8 cells, 117 vertices, 192 triangles |
| Cell size / sheet extent | 0.08 × 0.08 m / 0.96 × 0.64 m |
| Initial origin / velocity | (0, 0, 1.5) m / zero |
| Clamp | First **two** columns, 18 vertices, fixed position and zero inverse mass |
| Free vertices | 0.01 kg each |
| Gravity | (0, 0, −9.81) m/s² |
| Triangle coefficients | `tri_ke=10000`, `tri_ka=10000`, `tri_kd=0.02` |
| Edge coefficients | `edge_ke` as above; `edge_kd=0.01` |
| Time integration | 30 Hz recording, 10 substeps at 1/300 s, 10 VBD iterations |
| Collisions / self-contact | Both disabled; no ground/contact forces |
| Execution | Separate model/solver per case, direct device launches; no warm-up state reused |
| Public duration | 4 s; 121 samples including the untouched initial state |

The two-column clamp constrains the initial slope as well as position.
Fixing only one edge would permit the whole sheet to swing about that line.
The display grid is a visual reference, not a simulated collision surface.

The three cases contain **42,471 vertex samples**. Every point and velocity is
stored as its original float32 value. SHA-256 manifests detect changed files;
they do not authenticate a recorder or prove a material model.

## Measurements and limits

For each sample, RMS separation is
`sqrt(sum(||p_case[i] - p_reference[i]||²) / 117)` over corresponding
vertices, including the fixed vertices. Mean free-edge drop is `1.5 - mean(z)`
over the nine vertices in the last column. Maximum pin displacement,
peak vertex speed and the minimum/maximum mesh-edge length ratio are recorded
as numerical diagnostics. Edge ratios include every unique triangle edge,
including diagonals, relative to that case's initial edge length.

In this recording the largest RMS separation is **0.908000 m**, for `edge_ke=100`
at sample **29** (0.966667 s), relative to `edge_ke=0.01`. Maximum pin
displacement is zero. Mesh-edge lengths across all three cases range from
approximately **0.980× to 1.082×** their initial lengths. The page reports the
full timeline, not only this selected moment.

These are bounded, finite-step solver experiments. `edge_ke` is a Newton
coefficient, **not a calibrated fabric property or a Young's modulus**.
Colors identify cases; they do not depict stress. No contact/self-collision,
material calibration, convergence study, real-fabric validation, policy
inference or real-robot trial is included. A CPU rerun is a functional smoke
check; different hardware/solver execution need not reproduce GPU bytes.

## Source contract

`trace.json` records schema `robot-reel-cloth-1`, source versions/device,
settings, topology, fixed/free-edge vertex indices, summary and clock.

`positions.f32` and `velocities.f32` are headerless, **little-endian float32**,
C order, shape `[frame_count, 3, 117, 3]`; the last axis is X/Y/Z.
Units are metres and metres/second, Z up. Byte offset of coordinate `axis`
of vertex `i`, case `c`, sample `f`:

```text
4 * (((f * 3 + c) * 117 + i) * 3 + axis)
```

Sample `f` means simulation time `f / 30` s. USD/Blender frame `f + 1`
contains that sample. There is no dropped initial state, camera interpolation,
quantization or display spacing in the original binary coordinates.

After cloning the current repository, Python 3.12 and the standard library
can verify the published data, recompute all metrics and compare the browser
payload to its source:

```bash
python3 -m robot_reel.cli cloth --output docs/cloth --verify
```

The `cloth` command is included in Robot Reel **0.7.0+**. Earlier 0.6.0
packages do not include it. Download the wheel and the cloth experiment from
the same GitHub release; Python 3.12+ is required for the CLI.

## Use the installed package

After extracting `robot-reel-cloth-experiment.zip` into `cloth-lab`, install
the downloaded wheel in a virtual environment:

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install ./robot_reel-0.7.1-py3-none-any.whl
robot-reel cloth --output cloth-lab --verify

# Produce a fresh viewer, source files and complete experiment.zip.
robot-reel cloth --export-from cloth-lab --output cloth-copy
```

Verification and export use the standard library once the package is installed.
They need no source checkout, GPU, Newton or Blender. The export verifies the
original bytes and recomputes diagnostics, checks the saved native reports
against their source hashes, and preserves those reports. It does **not** claim
to rerun Blender or USD readback: `native_usd_checked` is false by default.
The source and destination must be separate; existing nonempty output is
rejected. A failed export leaves no partial site in the destination.

To additionally rerun native USD readback, install its pinned dependency:

```bash
python -m pip install 'usd-core==26.3'
robot-reel cloth --export-from cloth-lab --output cloth-with-native-check --check-usd
```

This checks the existing scene's points and velocities before writing output.
The Blender report still describes its original import of the same source bytes.
The standalone release file `robot-reel-cloth-scene.usdc` is identical to
`scene.usdc` inside the experiment ZIP.

## Record and export your own

From a source checkout (or install the downloaded 0.7.1 wheel with its
`[newton]` extra instead):

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -e '.[newton]'

# Uses CUDA explicitly; an unavailable CUDA device is an error.
robot-reel cloth --device cuda:0 --seconds 4 --output artifacts/my-cloth
robot-reel cloth --output artifacts/my-cloth --verify --check-usd

# Short CPU integration check; not a performance comparison.
robot-reel cloth --device cpu --seconds 0.1 --output artifacts/cloth-cpu
```

Recording requires a fresh output directory. It produces both source binaries,
metadata, a self-contained viewer, USD and the native USD readback report.
The offline ZIP is exported after the Blender check supplies its matching report.
The maintainer helper scripts below run from a source checkout; they are not
needed to verify or re-export the complete published experiment.
The duration is bounded to 10 s to keep this small demo's output predictable.

## Native USD and Blender checks

The USD contains three triangle meshes with time-sampled **points and
velocities**, not rigid transforms standing in for deformation. Local point
values retain the original solver frame. Each mesh has a fixed presentation
translation, no subdivision, and double-sided display. The scene is Z up,
metres, 30 fps, with no external layers/assets or physics resimulation.
The native reader checks every point, velocity, mesh index, time sample,
case color, affine presentation transform and scene clock.

In **Blender 5.2.1 LTS**, set the scene to **30 fps**, then use **File → Import →
Universal Scene Description** to open `scene.usdc`. Blender does not adopt
the USD frame rate automatically. Frame 1 is source sample 0. Mesh cache
modifiers provide recorded deformation; do not add a cloth simulation merely
to replay it. Add cameras, lights and your own materials as desired.

```bash
blender --background --python scripts/check_cloth_blender.py -- \
  --bundle artifacts/my-cloth --report artifacts/my-cloth/blender-check.json

python scripts/build_cloth_site.py --bundle artifacts/my-cloth \
  --destination artifacts/cloth-site
```

The Blender check evaluates every vertex at all recorded frames, checking
topology and world-space positions against source plus presentation offsets,
with a 1e-5 m tolerance. The report identifies the exact source and USD hashes.
The site builder requires matching native reports, reruns USD readback, and
builds an offline ZIP whose members must match the published files byte for byte.

## Upstream and licensing

This uses the procedural grid and VBD APIs from the official
[Newton 1.6.0 source](https://github.com/newton-physics/newton/tree/v1.6.0),
including the documented `ModelBuilder.add_cloth_grid`,
`ModelBuilder.color(include_bending=True)` and `SolverVBD` interfaces.
The September 10, 2026 [release](https://github.com/newton-physics/newton/releases/tag/v1.6.0)
is the pinned version; this is a small integration of its deformable workflow,
not a new solver or an upstream benchmark.

Robot Reel code, procedural grid and generated recordings are Apache-2.0.
No third-party mesh, texture, trained model or synthetic image asset is used.
Newton and Warp are Apache-2.0; OpenUSD is Apache-2.0 with its modified
trademark provision; Blender is GPL. Optional upstream software is installed
separately; its binaries are not redistributed inside the experiment ZIP.
