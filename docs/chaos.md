# The Butterfly Lab

[Open the interactive experiment](https://noteflowai.github.io/robot-reel/chaos/) ·
[Offline experiment](https://noteflowai.github.io/robot-reel/chaos/experiment.zip) ·
[Animated OpenUSD scene](https://noteflowai.github.io/robot-reel/chaos/scene.usdc)

Twelve double pendulums start with slightly different release angles. Their
recorded paths separate, then become an interactive time sculpture. This is a
new CPU Newton recording, not a recolored copy of the original single pendulum.

The scenario connects multi-world simulation, parameter sensitivity and creative
3D exports. Newton's
[1.6.0 release](https://github.com/newton-physics/newton/releases/tag/v1.6.0)
(September 10, 2026) includes expanded multi-world and OpenUSD workflows. This
demo uses its existing rigid-body XPBD solver and isolated world builder; it does
not claim to demonstrate the release's particle, deformable or GPU features.

## What to try

1. **Replay the experiment** starts at the initial state. The replay is paused
   when first opened, including when reduced motion is preferred.
2. **Time sculpture** maps each tip's physical X and Z onto the display and
   simulation time onto depth. Drag horizontally or use the camera buttons.
   **Motion overlay** puts the original trajectories on common physical axes.
3. Choose a world to compare against world 01. The readout and graph use
   Euclidean distances between original 3D tip positions, before presentation.
   The graph shows the full recording; trails stop at the selected sample.
4. **Start together**, **Largest separation**, sample stepping and the timeline
   help explain how the paths separate. Playback speed only changes viewing time.
5. **Share this view** preserves sample, world and presentation mode in the URL.
   World indices in the URL are zero-based; displayed world numbers start at 01.
   Camera rotation resets to the chosen mode's default when opening a link.

The source is embedded in `index.html`; playback needs neither a web server nor
an external JavaScript library. Unzip `experiment.zip` and open `index.html`
offline. Links to other Robot Reel demos require the website.

## Recorded experiment

| Setting | Value |
| --- | --- |
| Simulator | Newton 1.6.0, Warp 1.17.0, CPU |
| Solver | XPBD, default solver settings |
| World isolation | 12 `ModelBuilder.begin_world/end_world` scopes |
| Bodies | Two 1.6 × 0.18 × 0.18 m box links per world |
| Hinges | Y-axis revolute joints; fixed pivot at [0, 0, 3.8] m |
| Initial state | Collinear links, zero joint velocity |
| Reference release | −1.3 radians around Y |
| Sweep | +0.00° through +0.55°, in +0.05° increments |
| Gravity | [0, 0, −9.81] m/s² |
| Actuation | None; no policy, inference or applied control |
| Clock | 300 physics steps/s, recorded at 30 samples/s |
| Duration | 20 s; 601 samples including the initial state |
| Coordinates | Z up, meters, XYZW quaternions |

The largest distance **from world 01**, across every world and source sample,
is **6.260145 m** at **12.5 s**, between worlds **04 and 01**. Their initial
angle difference is **0.15°**, with **0.0083775 m** of initial tip separation.
This metric is not the maximum over all possible world pairs.

The source contains all 14,424 body poses. The maximum measured anchor and
hinge deviations are about 2.80 mm and 1.69 mm; validators enforce a 1 cm bound.
This is an illustration of sensitivity in a finite-step, finite-precision
simulation. Separation is not a Lyapunov estimate, a robustness benchmark,
a policy evaluation or a prediction of exact physical hardware.

## Reproduce

From a checkout, using Python 3.12+:

```bash
python3 -m venv .venv
.venv/bin/pip install -e '.[newton]'
.venv/bin/python -m robot_reel.chaos --output artifacts/chaos
.venv/bin/python -m robot_reel.chaos \
  --output artifacts/chaos --verify --check-usd
```

Choose an empty output directory. A fresh 20-second CPU run records all 12
worlds together. `--seconds 1` makes a short smoke run; it does not reproduce
the full public experiment. Platform and numerical differences can change
later trajectories; verify each newly recorded bundle against its own source.

To record a wider GPU sweep with the same 0.05° spacing:

```bash
.venv/bin/python -m robot_reel.chaos --output artifacts/chaos-gpu \
  --device cuda:0 --worlds 48 --seconds 3
.venv/bin/python -m robot_reel.chaos --output artifacts/chaos-gpu \
  --verify --check-usd
```

The recorder supports 2–512 worlds on `cpu` or `cuda:0`. New viewer descriptions,
USD metadata, centered presentation offsets and preview notices follow that
recording's world count and device. This command produces a separate experiment;
the public recording described above remains the original twelve-world CPU run.
Check each new USD in Blender before building its downloadable showcase.
The [48-world GPU export check](../examples/chaos-gpu-review/README.md) includes
a three-second recording, offline viewer and independent native checks.

The complete published bundle also validates with **only the standard library**:

```bash
python3 -S -m robot_reel.chaos --output docs/chaos --verify
python3 -S scripts/build_chaos_showcase.py --verify
```

These checks validate timestamps, normalized quaternions, actual initial
geometry against the declared perturbations, hinge constraints, recomputed
distance metrics, file hashes, embedded browser data, native-check report
provenance and the exact contents of the offline archive. They do not rerun
Newton or Blender.

## Open in Blender

Download `scene.usdc`, set Blender to **30 fps**, and use **File → Import →
Universal Scene Description**. Frame **1** is source sample **0** at time **0 s**.
Frame **601** is time **20 s**.

The scene contains 24 animated boxes under 12 world parents. Each parent's Y
translation is `(world_index − 5.5) × 0.6 m`, separating the worlds for viewing.
The local animated poses are unchanged; remove these parent offsets to overlay
the worlds. The USD exports the physical link animation, while the browser's
time sculpture is a separate presentation of recorded tip paths.

There are no physics schemas, external scene assets, inferred poses or USD
resimulation. The export checks every integer source frame. DCC interpolation
between those frames belongs to the importing application.

Native checks:

```bash
blender --background --python scripts/check_chaos_blender.py \
  -- --bundle artifacts/chaos
```

The script also runs in a Python environment containing `bpy`.
[OpenUSD check](chaos/usd-check.json) and
[Blender check](chaos/blender-check.json) cover every one of the **14,424**
body samples, using four affine-independent points per box to check position,
rotation, scale and the declared presentation offset. Both reports include the
USD hash; the Blender report also includes the trace hash.

## Build the public preview

After the native check succeeds:

```bash
.venv/bin/python scripts/build_chaos_site.py --bundle artifacts/chaos
npm ci
npx playwright install chromium
.venv/bin/python scripts/build_chaos_showcase.py
```

The showcase builder captures actual browser source samples through Playwright,
then makes the GIF and static poster with Pillow. Its font dependency is the
system DejaVu Sans family. No image generation model is used.

[The preview manifest](chaos/showcase-manifest.json) maps every GIF image to its
source sample: 0, 10, …, 600, played at 10 fps (3.33× source speed, followed by
one displayed final sample). The poster shows sample 375, world 04, in time
sculpture mode. The README uses a static image when reduced motion is preferred.
Hashes cover the published media, source files, check reports and offline ZIP.

Code, generated scene and data use Apache-2.0. No third-party visual assets are
used. [Media notice](chaos/NOTICE.txt).
