# Solver Lab: a launch with an analytic reference

Six independent CUDA recordings compare Genesis 1.4.1 `RigidSolver/Euler` and
Newton 1.6.0 `SolverXPBD` on an unconstrained ballistic flight. Each engine runs
with 1, 4 and 16 integration substeps per 1/30-second observation interval:
30, 120 and 480 integration steps per second. Every run retains the initial
state and 60 subsequent observations: **366 recorded states in total**.

## Scene and quantities

| Setting | Value |
| --- | --- |
| Position at t=0 | (0, 0, 1) m |
| Velocity at t=0 | (2, 0, 10) m/s |
| Gravity | (0, 0, −9.81) m/s² |
| Mass; radius used for display | 1 kg; 0.1 m |
| Angular velocity | Zero |
| Contacts, constraints, drag | None |
| Observation clock | 30 Hz, t=0 through t=2 s |
| Precision and device | float32, NVIDIA L40S / CUDA |

Newton uses one free body with explicitly authored mass and diagonal inertia
0.004 kg·m²; it needs no collision shape. Genesis uses a free sphere with density
chosen for 1 kg and collision detection disabled. The `.gs` scene saves the
authored scene; the launch velocity is applied after build. Use the `.gstraj`
trajectory to restore the recorded velocity as well as position.

For each observation time, the analytic reference is
`p(t) = p0 + v0*t + 0.5*g*t²` and `v(t) = v0 + g*t`.
Position/velocity error is the Euclidean distance to that reference. Specific
mechanical energy is `0.5*|v|² + 9.81*z`, initially 61.81 J/kg. Energy drift
subtracts that initial value. The analytical equations are computed separately
from engine outputs; they never supply a recorded position.

Both engines use a first-order velocity-before-position update in this simple
case. Their curves can overlap. Ideal-arithmetic position bias for that update
is `0.5*|g|*dt*t`, but displayed values are recomputed from the actual float32
recordings. The pilot's approximate maximum errors are 32.70, 8.17 and 2.05 cm
as integration frequency rises. Inspect source JSON for exact values.

These results isolate timestep and rounding effects. They do not compare
contact solvers, articulated robots, stability across scenes, real-world
accuracy or GPU throughput. Timings are not presented as a performance benchmark.
The page renders paths in the X/Z plane; the Y coordinate remains in the data.

## Reproduce the recordings

Use separate Python 3.12 environments so the two optional simulators do not
change an existing Robot Reel installation. A working NVIDIA CUDA device is
required for this particular recorder; it does not silently fall back to CPU.

```bash
python3.12 -m venv .venv-genesis
.venv-genesis/bin/pip install genesis-world==1.4.1 torch==2.11.0
.venv-genesis/bin/python scripts/record_solver_lab.py \
  --engine genesis --output artifacts/solver-genesis

python3.12 -m venv .venv-newton
.venv-newton/bin/pip install newton==1.6.0 warp-lang==1.17.0 usd-core==26.3
.venv-newton/bin/python scripts/record_solver_lab.py \
  --engine newton --output artifacts/solver-newton

.venv-newton/bin/python scripts/build_solver_lab.py \
  --genesis artifacts/solver-genesis --newton artifacts/solver-newton \
  --output artifacts/solver-lab
```

Each run records engine/runtime versions, device, GPU and driver. Genesis uses
its exact native trajectory recorder. The recorder reopens all three `.gstraj`
files with `Scene.load_trajectory`, seeks every sample and checks position,
velocity and clock. The builder writes USD, reopens it through `usd-core` and
checks all 366 positions and velocities. `native-check.json` binds these checks
to their input hashes. The upstream default velocity integration and unrelated
solver behavior may change; this adapter intentionally pins engine versions.

## Offline use and verification

Download `robot-reel-solver-experiment.zip` from the matching 0.10.0+ release,
extract it to `solver-lab`, and open `index.html`. No network, GPU or Python is
needed for the interactive replay. JSON and CSV exports include all six runs.
View links preserve engine, timestep and sample. Local file links need the
same extracted folder on the recipient's machine.

With the matching Robot Reel wheel installed:

```bash
robot-reel solver-lab --output solver-lab --verify
robot-reel solver-lab --export-from solver-lab --output solver-copy
```

Or verify from the checkout using only Python's standard library:

```bash
python3 -S -m robot_reel.cli solver-lab --output docs/solver-lab --verify
```

The verifier checks a fixed file inventory, hashes, scene and clock contracts,
all source states, derived metrics, embedded browser data, and saved native
readback receipts. Exit 0 reports `verified: true`; malformed or inconsistent
input exits 2. It executes no native archive and runs no simulation. Hashes
establish consistency, not producer authentication or independent recollection.
An individual input file is limited to 20 MiB; symlinks in input paths are
rejected. Generated archives have stable metadata and include every required file.

For a fresh USD readback, install `usd-core==26.3` and run:

```bash
robot-reel solver-lab --output solver-lab --verify --check-usd
```

Open `scene.usda` in Blender at **30 fps**. Frame 1 is source sample 0. The six
run parents are offset along Y by their zero-based run index for presentation;
local positions remain unchanged. `reel:velocity` preserves source velocity as
a custom USD attribute. This is recorded animation, not a new Blender simulation.

## Sources and rights

Checked 2026-09-14 against primary sources:

- Genesis 1.4.1 release, published September 12:
  <https://github.com/Genesis-Embodied-AI/genesis-world/releases/tag/v1.4.1>
- Pinned Genesis scene export and native trajectory API:
  <https://github.com/Genesis-Embodied-AI/genesis-world/blob/v1.4.1/genesis/engine/scene.py>
- Genesis trajectory format and exact/compressed mode:
  <https://github.com/Genesis-Embodied-AI/genesis-world/blob/v1.4.1/genesis/options/recorders.py>
- Newton 1.6.0 release:
  <https://github.com/newton-physics/newton/releases/tag/v1.6.0>

Original procedural scene, code and recorded outputs: Apache-2.0. No third-party
visual assets or generated images. Upstream engines are named to identify actual
dependencies; this experiment is not an upstream endorsement.
