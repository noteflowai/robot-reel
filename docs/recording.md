# Recording packs and development

Run commands from the repository root. For the visual overview and all demos, see the [project homepage](../README.md). The [VLA guide](vla.md), [MCP director guide](director.md) and [Newton guide](newton.md) describe their separate workflows.

## MuJoCo recording packs

| Pack | What actually runs | What you can inspect |
| --- | --- | --- |
| **Microduck** | Pollen Robotics' official walking ONNX policy, 50 Hz, in CPU MuJoCo | 14 joint targets and responses, every policy step, base motion, pinned policy checksum |
| **Braking** | Two scripted controllers in the same 1D rigid-body vehicle surrogate | Speed, obstacle gap, brake force, recorded contact; early versus late braking |
| **Studio** | SO-100 position actuators; optional live Strands agent. G1 is a scripted kinematic segment | Four arm moves, endpoint errors, asset-defined home, frame-by-frame traces |

All footage comes from the simulator. Titles and telemetry are drawn in code;
the soundtrack is originally synthesized. The replay includes shot navigation,
single-frame stepping, joint selection, measured/reference plots, and timestamp sharing.

**Limits are visible:** Microduck uses the upstream XML PD-actuator fallback,
not the BAM motor model used for official deployment. Braking is a toy longitudinal
scenario, not CARLA, AlpaSim, an Alpamayo inference run, or a road-safety validation.
G1 does not demonstrate walking or a learned balance policy.

## Quick start

Python 3.12+ and OpenGL. Tested on Linux / NVIDIA L40S / EGL.

```bash
git clone https://github.com/noteflowai/robot-reel.git
cd robot-reel
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e '.[microduck]'

# Official pretrained Microduck policy; no training or model-service account.
robot-reel --pack microduck --output artifacts/duck
python -m robot_reel.verify artifacts/duck
```

Open `artifacts/duck/index.html` directly. First run downloads the pinned upstream
model assets and policy. The policy runs on CPU; rendering needs OpenGL.
Set `ROBOT_REEL_CACHE` to choose the download cache.

Microduck model assets are identified upstream as **Creative Commons BY-SA-NC**
(the upstream README does not state a version). Its footage retains those asset
terms and attribution. Our recorder code is Apache-2.0; it does not relicense
Pollen's models. See [THIRD_PARTY.md](../THIRD_PARTY.md).

For the other packs, plain `pip install -e .` is enough:

```bash
# Two braking runs with identical initial conditions.
robot-reel --pack braking --output artifacts/braking

# Credential-free arm + humanoid demo.
robot-reel --output artifacts/studio

# Your own four-shot arm plan; final shot returns to the model's home pose.
robot-reel --shots examples/close-up.json --output artifacts/my-film
```

The browser's plan editor exports a `shots.json` compatible with `--shots`.
Editing that plan does not modify or simulate the video currently playing.
Unknown joints, nonfinite targets, out-of-range targets and unsupported plan fields
are rejected. The first three targets retain unspecified joints; the fourth shot
must use `"home": true`.

Linux defaults to EGL; software rendering can use `MUJOCO_GL=osmesa` after
installing your system's OSMesa library. macOS defaults to `glfw`, but is not yet
part of the tested platform matrix.

## Outputs

Each MuJoCo pack produces two H.264/AAC films, an interactive HTML replay, original
simulator recordings, per-frame JSON traces, a poster, and a SHA-256 manifest.
Microduck also records all 50 Hz policy actions and its policy/model revisions.
The separate Newton command produces an HTML pose replay, JSON trace, animated
USD scene, and checksum manifest; it does not render an MP4.

| Pack | Simulation footage | Edited film |
| --- | --- | --- |
| Microduck | 10 seconds / 300 frames | 15 seconds |
| Braking | 2 × 6 seconds / 360 frames | 17 seconds |
| Studio | 16-second arm + 10-second G1 / 780 frames | 31 seconds |

Landscape is 1280×720; portrait is 720×1280, both 30 fps. Share the MP4, or keep
`index.html` beside the videos for an interactive local replay.

```bash
# Re-edit an existing capture, including a Microduck or braking pack.
robot-reel --render-only --output artifacts/duck

# Add the latest replay UI to an existing compatible evidence bundle.
python -m robot_reel.viewer artifacts/duck
```

## Optional: let an agent direct the arm

Configure AWS SDK credentials and select a Bedrock model/inference profile that
is available to you. This is a billable model call:

```bash
robot-reel --agent --model YOUR_BEDROCK_MODEL_OR_INFERENCE_PROFILE \
  --region us-west-2 --output artifacts/agent-film
```

The agent inspects limits and home, then issues four constrained moves. Its prompt
and response are saved. Inference pauses are omitted; motion frames remain in order.
This is a bounded demonstration, not open-ended autonomous planning.

## Evidence, not a certification

The verifier requires hashes for every scene's raw video and trace plus both films.
It checks frame ordering, finite values, source labels, arm action/frame agreement,
policy-step/frame agreement, and braking contact-summary agreement. Arm endpoint
and home error must remain within a 0.05-radian demo tolerance.

Hashes detect changes relative to a manifest. They are not signatures, do not
prove independent authenticity, and do not certify physical safety or general
policy quality. Driving outcomes apply only to the documented surrogate.

## Why this exists

[Microduck](https://github.com/pollen-robotics/microduck) and
[Microduck RL](https://github.com/pollen-robotics/microduck_rl) provide the robot
and learned behavior. [Strands Robots](https://github.com/strands-labs/robots)
provides agent/robot integration. Robot Reel focuses on **turning a run into
something people can watch, inspect and reproduce**.

The automotive pack is a small starting point for recording comparable outcomes.
See [the automotive integration notes](automotive.md) for the relationship
to Alpamayo, AlpaSim and CARLA, and what is not integrated yet.

## Development

```bash
# Trace, plan and export tests run with the Python standard library.
python3 -m unittest discover -s tests -v
# For recording/rendering development, install the runtime in an isolated environment.
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[director,inspect]'
npm ci
npm run check:js
npx playwright install chromium
npm test
```

The Python suite covers plan rejection, VLA outcome/action consistency, evidence
bundles and Blender export agreement. Importing validators does not require
`imageio_ffmpeg`, MuJoCo, NumPy or ML libraries;
CI also runs the suite with third-party packages disabled. Browser checks
cover both camera clocks, seeking, stepping, downloads, mobile layout, local-file
playback and caption escaping. Stress Lab checks cover all thirty paired trials,
native scene changes, CPU/GPU separation, source-derived statistics and the
complete offline archive. The optional `inspect` extra enables MCAP readback;
without it, that one optional test is skipped. CI also exercises the real director MCP transport.
Real recording smoke runs require OpenGL and downloaded model assets.

`npm run check:js` type-checks the viewer scripts that live inline in the nine
templates under `robot_reel/` and `scripts/`. The exports stay single
self-contained HTML files, so the scripts
cannot move into modules or a bundler; the check extracts each template's script,
runs the TypeScript compiler over it in `checkJs` mode, and reports diagnostics at
their original HTML line. It reads the templates without modifying them, and it
does not add anything to the exported pages. `scripts/viewer-env.d.ts` records
what the templates assume about the DOM, so the check reports undeclared names,
typos, wrong arity and dead locals instead of a cast at every element access.

Because every published page carries a verbatim copy of its template's script, a
template change only reaches the site when the pages are rebuilt. The Python
suite fails while they disagree. A full rebuild needs the original capture
bundles and their videos; when only the script changed, copy it across instead:

```bash
python3 -m robot_reel.pages           # report pages behind their templates
python3 -m robot_reel.pages --write   # copy the templates into those pages
```

`--write` also re-records the affected hashes, following the manifest chain
outward -- a page, the bundle manifest that hashes it, and the remix manifest
that hashes that bundle manifest.
The Studio adapter uses private Strands Robots fields and pins version 0.5.1.

See [CONTRIBUTING.md](../CONTRIBUTING.md). Useful contributions include a public
backend adapter, measured policy comparisons, and an import adapter for an actual
AlpaSim/CARLA run. Do not describe planned integrations as shipped features.
