# Newton → OpenUSD → Blender

Record a double pendulum using **Newton 1.6.0 / SolverXPBD / CPU**, inspect its
measured rigid poses in an offline browser replay, and import the same animation
into Blender. No GPU, OpenGL context, external model asset, or model-service
account is needed for this command.

## Why this integration now

[Newton 1.6.0](https://github.com/newton-physics/newton/releases/tag/v1.6.0),
released September 10, 2026, expands OpenUSD workflows and moves mature APIs to
keyword-only options. Robot Reel uses its public builder and solver APIs to
produce a small, reproducible rigid-body example.

[Genesis 1.4.0](https://github.com/Genesis-Embodied-AI/Genesis/releases/tag/v1.4.0),
released September 6, introduces portable trajectory archives. That is another
useful example of making simulation runs shareable. This implementation records
Newton; it does not parse Genesis archives or implement Newton's particle and
deformable workflows.

## Record and inspect

From a checkout, with Python 3.12 and an activated virtual environment:

```bash
pip install -e '.[newton]'
robot-reel newton --output artifacts/newton
robot-reel newton --output artifacts/newton --verify --check-usd
```

The optional extra pins `newton==1.6.0`, `warp-lang==1.17.0` and `usd-core==26.3`;
the published run used Linux x86-64. The first run compiles Warp CPU kernels.
Warp may print that no CUDA device is available; this adapter explicitly uses
the CPU. Set `WARP_CACHE_PATH` to a writable directory if the default cache is
restricted.

Open `artifacts/newton/index.html` directly. The page works offline, including
frame stepping, body selection, front/orbit camera views, and the lower-tip
trajectory trail. A hosted replay also supports `#frame=30` sample links.
Use `--seconds 3` for a shorter capture; durations must be whole 30 Hz intervals
between 1/30 and 30 seconds. Choose an empty output directory.

| File | Contents |
| --- | --- |
| `trace.json` | Two box dimensions, engine/solver versions, all measured poses and summary |
| `scene.usda` | Self-contained OpenUSD geometry and integer-frame transform samples |
| `index.html` | Canvas view of those poses, with embedded source JSON |
| `manifest.json` | SHA-256 hashes binding the trace, USD and viewer |

To check the included bundle without installing any third-party Python packages:

```bash
python3 -S -m robot_reel.cli newton --output docs/newton --verify
```

This checks hashes, finite normalized poses, frame order, timestamps, units,
summary agreement and the embedded browser payload. `--check-usd` additionally
loads USD with `usd-core` and compares every body's transform against its source.
Hashes establish file consistency, not independent authenticity.

## The clock and coordinates

The default run advances 1,800 physics steps at 1/300 second, sampled every ten
steps. Both the initial state and final state are retained.

| Source sample | Simulation time | USD / Blender frame |
| --- | --- | --- |
| 0 | 0 seconds | 1 |
| 30 | 1 second | 31 |
| 180 | 6 seconds | 181 |

Positions are meters, Z is up, and the JSON quaternion order is **x, y, z, w**.
Each link is a 1.6 × 0.18 × 0.18 m box. Two revolute joints connect the links to
each other and to a fixed anchor at (0, 0, 3.8). Gravity is (0, 0, −9.81) m/s²;
the initial upper hinge is rotated 0.55 rad about Y. There is no motor command
or learned controller. The browser's grid, mounting marker and trail are visual
context; the USD exports the two measured links.

The USD uses a unit cube with an explicitly sampled affine transform for each
link. Transform checks compare the center and three independent local basis
points, covering translation, rotation and scale. Every recorded integer frame
is checked. Fractional-frame interpolation is left to the importing application.
This presentation export contains no USD physics schemas or solver checkpoint.

## Import into Blender

Tested with **Blender 5.2.1 LTS**:

1. Set **Output Properties → Frame Rate → 30 fps**. Blender does not automatically
   adopt the USD stage's frame rate during import.
2. Select **File → Import → Universal Scene Description** and open `scene.usda`.
3. Keep **Set Frame Range** enabled. The timeline should run from 1 to 181.
4. Add lights, cameras and materials as needed. Blender uses a transform cache
   referencing the USD; keep that file alongside a saved `.blend`.

Run the native import check from the repository root:

```bash
blender --background --python scripts/check_newton_blender.py -- \
  --bundle artifacts/newton --report artifacts/newton/blender-check.json
```

The script starts a fresh Blender scene, sets 30 fps, imports the real USD, then
compares every evaluated world transform against the JSON source. The published
check covers **362 body samples**; maximum transform error was
**1.627137754125032e-7 m**. Its SHA-256 values bind the result to the exact trace
and USD files in [the demo bundle](newton/).

The recorded pendulum's maximum anchor separation was about **0.536 mm** and
maximum inter-link hinge separation about **0.300 mm**. These are measured
constraint residuals from one CPU run, not cross-engine accuracy or performance
benchmarks.

## Rebuild the page and preview

After recording and completing the Blender check:

```bash
python -m scripts.build_newton_site --bundle artifacts/newton
npm ci
npx playwright install chromium
node scripts/render_newton_preview.cjs docs/newton artifacts/newton-preview
python -m scripts.build_newton_preview
```

The site builder requires the Blender report to match the source hashes and
checks the USD transforms again. The preview script draws every third recorded
sample into PNGs for a 10 Hz GIF. It also produces desktop and mobile screenshots.
The browser images are visualizations of recorded poses, not Newton-rendered
video.

The recorder deliberately supports this bounded rigid-body demo. It does not
yet import arbitrary Newton scenes, render particles, replay a policy, or resume
the physics engine. Procedural boxes and Robot Reel code are Apache-2.0; see
[third-party acknowledgments](../THIRD_PARTY.md) for the runtime libraries.
