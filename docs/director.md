# Agent director: a brief, a checked storyboard, an editable film

[Open the director demo](https://noteflowai.github.io/robot-reel/director/).
The published seven-second film has four shots: overview, tracking, half-speed
contact and top view. It retains all 180 source samples in 210 output frames.
All 420 vehicle samples, four cuts and the tracking camera were checked in the
saved Blender 5.2.1 LTS project. The source is the existing pair of independent
one-dimensional MuJoCo braking trials.

## Build the example

The plan exporter and verifier use only the Python standard library:

```bash
python3 -m robot_reel.cli direct docs/compare/braking --inspect
python3 -m robot_reel.cli direct docs/compare/braking \
  --plan examples/contact-storyboard.json --output artifacts/director
python3 -m robot_reel.cli direct artifacts/director --verify
blender --background --python artifacts/director/build_directed_scene.py -- \
  --bundle artifacts/director --output artifacts/director/reel.blend
blender --background --python scripts/check_director_blender.py -- \
  --bundle artifacts/director --blend artifacts/director/reel.blend \
  --report artifacts/director/animation-check.json
blender --background --python scripts/render_blender_preview.py -- \
  --blend artifacts/director/reel.blend --frames artifacts/director/frames \
  --scale 100 --samples 6 --threads 2
```

Render with CPU Cycles. The checked example uses 960×540 at 30 fps, with
constant sample hold and no motion blur. The saved project contains procedural
materials, source telemetry, all camera bindings and embedded plan/mapping JSON.
Captions are burned into the MP4 during packaging and stored as timeline marker
labels in the native project; they are not animated text objects.

With the normal Robot Reel runtime installed:

```bash
python scripts/build_director_site.py --bundle artifacts/director \
  --output artifacts/director-site
```

The packager requires the native check report and all rendered frames before
encoding. It creates the video, poster, preview, interactive page, checksums
and `project.zip`. The default font is DejaVu Sans on Linux; use `--font PATH`
on another system. Open the resulting `index.html` next to its media.

## Connect an agent over MCP

Install `pip install -e '.[director]'` in the normal Robot Reel environment.
The MCP SDK is pinned to 2.1.1, compatible with the existing Strands runtime.
Configure an MCP client with this local stdio server; replace the two absolute
paths with your checkout and interpreter:

```json
{
  "mcpServers": {
    "robot-reel-director": {
      "command": "/absolute/path/robot-reel/.venv/bin/python",
      "args": ["-m", "robot_reel.cli", "mcp", "--root", "/absolute/path/robot-reel"]
    }
  }
}
```

Example request:

> Inspect docs/compare/braking. Start with both trials, follow the approach,
> slow down the recorded contact, and finish with both outcomes. Keep all
> source samples. Write the storyboard into artifacts/my-directed-film.

The connected language model interprets the brief. `inspect_recording` returns
actual event frames and outcome summaries. `create_storyboard` validates the
typed plan and writes a new bundle. The tools operate on paths relative to the
configured root, reject symlink/parent escapes and refuse nonempty outputs.
The server does not execute shell commands, arbitrary Python or Blender.
The build and render commands above are explicit subsequent steps for the
agent or user. No model call occurs merely by starting this MCP server.

The website shows a rendered example, without a hosted language model.
Its editor downloads a plan for a **new** render; edits do not change the
currently displayed film or its source metadata. The full stdio integration
test is `python scripts/check_director_mcp.py` and also runs in CI.

## Storyboard contract

Use schema `robot-reel-director-1`, a brief, title, theme (`midnight` or
`daylight`) and 1–8 shots. Each shot has `start`, exclusive `end`, `camera`,
`rate` and `caption`. Cameras are `overview`, `tracking`, `impact`, `top`.
Rates are 1 or 0.5; half speed duplicates each sample exactly once.
Shots must cover the entire source in order, with no gaps or overlaps.

`film.json` maps every output frame to its original source frame and simulator
timestamp. Output indices start at zero; Blender frames start at one.
Film time and simulation time intentionally differ during slow motion.
The validator recomputes this mapping rather than accepting a rehashed,
inconsistent JSON file. Source traces and their checksums remain in `source/`.

Captions are editorial language, not independently verified statements.
Checksums establish file consistency, not independent authenticity. This
director currently supports braking captures/comparisons only; it does not
direct arbitrary robots or synthesize new physics.
