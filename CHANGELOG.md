# Changelog

## Unreleased

- Hold every published page inside a compressed transfer budget, measured the
  way GitHub Pages serves them. The Stress Lab page is 1.26 MiB of the 1.50 MiB
  limit.

- Document opening the Stress Lab's MCAP telemetry in Foxglove, with FoxQL
  expressions for paired conditions, controls and inference timing, and record
  what Rerun decodes today. A test resolves every documented expression and
  message count against the real telemetry.

- Ship the Stress Lab's 56 MB offline archive as a release asset instead of a
  tracked file, verify a published site without it, and fail the tests when any
  tracked file exceeds 25 MB. The archive was removed from the repository
  history as well, so existing clones must be re-cloned or hard-reset.

- Check that every relative link and heading anchor in the Markdown docs and the
  landing page resolves, with the standard library.
- Add launch copy for the landing page, Stress Lab and Butterfly Lab to the
  maintainer notes.

- Publish a landing page at the site root that indexes all twelve recorded demos,
  with a stdlib quick start and a copy button; the Microduck replay keeps its
  own page. The landing template lives in `scripts/landing.html` and is covered
  by the viewer script check.
- Move the quick start to the top of both READMEs, add live-demo, Python and
  stars badges, a Colab notebook and a Dockerfile for the stdlib checks, and a
  section on how Robot Reel differs from LeRobot, MuJoCo Playground, Isaac Lab,
  Genesis, Newton, Rerun and Foxglove.
- Add a 1280×640 social preview built from the Butterfly Lab poster, issue and
  pull request templates, a code of conduct, a security policy, a citation file,
  an `examples/` guide and a tag-triggered release workflow that builds the
  package and publishes it to PyPI through trusted publishing.
- Move maintainer launch notes out of the published `docs/` tree into `notes/`.

- Type-check each replay template's inline viewer script, and check the published
  pages still carry it. Copying a template into its pages re-records the affected
  bundle hashes along the manifest chain.

- Add the Stress Lab: thirty closed-loop SmolVLA CUDA trials on NVIDIA L40S across ten paired
  initial states and three native lighting/camera conditions. Preserve the
  locked plan, every result and interruption history, input/noise hashes,
  initial physics and separate policy/simulation timings.
- Add synchronized paired replay, an all-trial outcome matrix, source-aware
  final-frame holding, inference/outcome navigation and measured end-effector
  separation on the shared recording prefix.
- Export the complete offline experiment, CSV and lossless JSON telemetry in
  MCAP; verify every message on readback, all sixty camera videos and published
  summary/HTML against the source traces.
- Add a source-mapped homepage preview and a dated Chinese research roadmap.

- Add the Butterfly Lab: twelve isolated CPU Newton worlds with a 0.05° release
  sweep, interactive motion overlays and time sculptures, source-derived
  separation metrics, a portable offline bundle and a native-checked OpenUSD
  animation retaining all 14,424 body samples.
- Feature the new experiment in both GitHub READMEs with a source-mapped GIF
  and a reduced-motion poster.
- Redesign the English and Chinese GitHub homepages around a recorded-motion
  cover, a reduced-motion fallback, scene cards and direct demo/download links.
- Add Physics → Cinema: an interactive divider between the original MuJoCo
  comparison and its Blender replay, with shared sample stepping, contact
  navigation and source consistency checks.
- Preserve detailed recording and development instructions in dedicated guides.

## 0.4.0 — Recorded policies and agent-directed films

- Record a real SmolVLA CPU rollout in LIBERO with pinned checkpoint, backbone
  and assets; publish the successful seeded bowl-to-plate episode with both
  policy-input camera views, all 76 applied controls and a terminal observation.
- Inspect language tasks, normalized actions, inference chunk provenance,
  measured robot state and task outcomes on a shared browser timeline.
- Export an agent's typed MCP storyboard into an editable Blender film with
  four camera choices, captions and sample-preserving half-speed playback.
- Check all 420 vehicle samples, camera cuts, tracking and constant sample
  holds in the saved director project; publish its seven-second rendered film.
- Add portable downloads, frame links, mobile/offline checks, MCP protocol
  checks and semantic validation beyond file hashes.
- Isolate the LeRobot/MuJoCo environment from the original recording packs.

- Record Newton 1.6 CPU rigid-body poses and export a self-contained animated
  OpenUSD scene, with an offline 3D browser replay and per-sample sharing.
- Check all 362 body samples through OpenUSD and actual Blender 5.2.1 import;
  explicitly preserve the 30 fps time base when importing into Blender.
- Export verified braking captures/comparisons into editable Blender 5.2 scenes
  with procedural geometry, two cameras, source-driven keyframes and telemetry.
- Check the exported JSON against source traces and the saved `.blend` against
  every vehicle sample, including constant interpolation between frames.
- Add a downloadable Blender scene and browser replay of its rendered motion.
- Keep simulation/video dependencies out of validator imports so the complete
  unit suite runs with only the Python standard library.

## 0.2.0 — Physical-AI replay packs

- Official Microduck ONNX policy recording in CPU MuJoCo, pinned model/policy
  revisions, all 50 Hz actions, and an explicitly labeled PD-actuator fallback.
- Repeatable early/late braking comparison with raw contact and state evidence.
- Browser replay with frame stepping, shot navigation, selectable telemetry,
  reference curves, local-file support and timestamp sharing.
- Four-shot JSON arm plans, including a browser plan exporter.
- Required evidence hashes and action/frame, policy/frame and contact-summary checks.
- Microduck media attribution and asset-license separation.

## 0.1.0 — Initial preview

- SO-100 agent-directed or scripted arm recording and G1 kinematic showcase.
- Landscape/portrait films, synthesized music, raw recordings and traces.
