# Changelog

## Unreleased

- Verify draft assets against local checksums and GitHub SHA-256 digests, retry
  missing uploads individually, and retain uploads whose response was lost.
  Preserve existing public releases and drafts; document recovery using the
  original tested CI artifacts. Record the completed 0.10.0 publication.

## 0.10.0 — One launch, six recorded futures

- Add Solver Lab: six independent L40S/CUDA ballistic flights from Genesis 1.4.1
  and Newton 1.6.0 at 30, 120 and 480 integration steps per second. Preserve all
  366 position/velocity samples, including each initial state.
- Compare recorded trajectories, velocity errors and specific-energy drift with
  the constant-gravity analytic solution. Inspect every run, scrub or replay,
  select the largest error, share a view and export full-precision JSON/CSV.
- Reopen all Genesis native trajectories and read back every recorded state;
  export all six trajectories to editable OpenUSD with native sample checks.
- Ship a self-contained offline ZIP and installed `solver-lab` verifier/exporter.
  Verification recomputes metrics and checks source files; native-check receipts
  describe earlier reads, with optional fresh USD validation.
- Add the fifth Hugging Face lab, a homepage showcase and bilingual methods.

This is a no-contact, no-drag integration experiment, not a benchmark ranking or
real-world validation. Existing policy, cloth and Microduck recordings are unchanged.

## 0.9.1 — A more usable Motion Lab

- Keep playback beside the schematic, with links between the recording and its
  controls, four keyboard-operable orbit buttons, larger touch targets and
  spoken frame/time values. Disable stepping past the first or last frame.
- Recover unavailable videos in place while preserving the selected frame and
  usable joint data. Ignore superseded playback promises after changing runs.
- Expose clipboard fallback focus and download failure feedback.
- Synchronize the complete Microduck template while preserving its embedded
  recording verbatim, then refresh manifests and the offline ZIP. Test markup
  drift as well as script drift so new controls reach every distribution.

The two original walks and their numerical evidence are unchanged.

## 0.9.0 — Microduck evidence you can hand off

- Ship `robot-reel microduck-review` in the wheel. Verify an extracted Motion Lab
  ZIP and optional browser frame JSON without a source checkout, GPU, simulation
  dependencies or model download. Reconstruct all derived poses and metrics from
  the two bundled raw recordings and check their manifests and frame facts.
- Publish the original Microduck experiment ZIP and a matching frame JSON with
  checksums alongside the existing Cloth and Stress labs. Test successful and
  altered frame inputs from an installed wheel outside the checkout.
- Share the verifier with the source builder; reject ambiguous JSON, non-finite
  numbers, symlink files and non-regular inputs with structured error output.
- Synchronize Microduck telemetry to the video clock on pause, including when
  browser animation frames are throttled. Exercise that case explicitly.
- Include the interactive Microduck Motion Lab, frame exchange and agent-review
  workflow developed since 0.8. The two original recordings remain unchanged.

Verification checks bundled evidence consistency, not producer authenticity,
a fresh MuJoCo run, physical hardware or the correctness of agent commentary.

## 0.8.0 — Portable outcome reports and sample exchange

- Ship the paired policy outcome explorer in the installed package and complete
  offline Stress Lab. Retain gains and losses, all seed groups and the full
  experiment denominator. Export and independently verify the complete report.
- Include `robot-reel-paired-outcomes.json` as a checksummed release asset.
  Generate it with the installed wheel outside the checkout, reject an altered
  report, and compare the offline browser's filtered-view export with those
  exact bytes at desktop and mobile sizes.
- Publish the descriptive 30-trial / 20-pair result tables on Hugging Face with
  a source manifest and a reproducible export script. The recorded experiment
  is unchanged; this release adds inspection and distribution tools.

- Preserve Space homepage symbols and the Chinese link with HTML entities after
  public readback caught a UTF-8 character damaged at the hosting boundary.
- Connect the Space and both READMEs to a curated Hugging Face model/data
  collection and the public feedback thread. Credit the exact recording sources.
- Verify uploads anonymously against the tested CI artifact: every Git/LFS
  object plus the public manifest, homepage, three viewers and thumbnail.
  Bound CDN retries, reject stale or changed deployments and preserve unrelated
  remote files.
- Host Cloth, Stress and Butterfly labs as a native Hugging Face static Space,
  with original recordings, a dedicated landing page and model/dataset credits.
  Publish the exact browser-tested artifact after the current main commit's
  checks pass; verify its full inventory and source identity before upload.
- Make sample links visible and directly openable when embedded browsers deny
  clipboard access. Preserve the selected frame, condition and camera.
- Open Cloth Lab sample JSON files, verify their source facts and restore their
  sample and camera offline. Reject changed or ambiguous files without moving
  the current view. Add `cloth --verify-sample` for independent standard-library
  checks against a verified source bundle.
- Export Cloth Lab samples as 1920 × 1080 PNG figures with original mesh geometry,
  measured deformation, source clocks and a positions fingerprint, plus portable
  JSON records with full-precision metrics. Both work offline. Shared links now
  preserve camera rotation; failed PNG encoding can be retried.
- Point the homepage, both READMEs and the published Stress viewer at the
  verified 0.7.1 downloads, installation guide and checksums.

## 0.7.1 — Reliable offline export recovery

- Stage Stress Lab exports beside their destination and publish only after media,
  telemetry, manifest and archive verification succeeds. Failed or interrupted
  exports can be retried without removing a partial output. Reject overlapping
  input/output paths, symlink destinations and occupied outputs; preserve files
  another writer creates before publication.
- Connect the homepage and both READMEs to the verified 0.7.0 release files,
  with direct downloads for both offline labs and the editable cloth scene.

## 0.7.0 — GPU cloth and portable deformable experiments

- Ship Cloth Lab in the installed package and release downloads. Export a checked
  recording and its complete offline ZIP without a source checkout, Newton or a
  GPU. Preserve the original data and native reports; request native USD readback
  separately. Package the method and license, protect existing input/output
  directories, and publish only a fully validated export.
- Test both installed-wheel archives offline at desktop and mobile sizes, and
  publish those exact files with checksums. Keep citation, package and release
  versions aligned. Existing recordings and earlier release assets are preserved.

- Add Cloth Lab: three independent Newton VBD cloth simulations recorded on
  NVIDIA L40S, with original float32 positions and velocities, shared-clock
  mesh comparison, orbit/overlay replay and a portable offline experiment.
  Check every deforming vertex and velocity through OpenUSD, and every imported
  mesh vertex through Blender. Publish a source-mapped preview and document
  the numerical settings, diagnostics and material-validation limits.

- Point the homepage, READMEs and published Stress Lab at the verified 0.6.0
  offline bundle. Add a homepage download section with the sample review, guide
  and checksums after the release assets are publicly available.

## 0.6.0 — Portable reviews and a complete offline lab

- Deliver the complete Stress Lab ZIP, a source-checked sample review and a
  start guide alongside the wheel, source distribution and native Rerun recording.
  Publish the exact archive exported by the installed wheel and tested offline
  in Chromium. Keep these assets separate from the Python distributions and
  include every downloadable file in SHA256SUMS.

- Export selected Stress Lab moments as portable JSON and readable Markdown with
  separate user notes. Import and compare facts before restoring a selection;
  verify reviews against a complete local collection with the standard-library
  CLI. Preserve source clocks, held/final observations, active inference records,
  checkpoint identity and the complete experiment's counts.

- Guide first-time visitors from a selected paired outcome to native inspection
  and full-experiment reproduction. Add purpose filters with shareable URLs,
  keyboard controls, browser history and offline/no-JavaScript fallbacks.
- Load homepage motion only after an explicit play action. Preserve the original
  Butterfly preview's 61 source samples and clock in a checked H.264 derivative;
  pause when the preview leaves view, the tab is hidden or reduced motion changes.
- Synchronize the complete static landing template, including its markup and
  styles, while retaining script-only synchronization for recorded replay pages.

## 0.5.0 — Paired policy inspection and verified distributions

- Bundle Stress export notices, license and methods as package resources. Build
  a wheel from the source distribution, install it in a fresh environment, and
  export all thirty trials outside the checkout, checking videos, MCAP records
  and the complete offline archive.
- Gate Pages and tagged releases on the same six validation jobs. Require
  matching tag, package and changelog versions; publish the tested distributions
  and native Rerun recording with SHA-256 checksums. PyPI publishing is opt-in
  after trusted-publisher setup.
- Run the Docker image as an unprivileged user with a regular package install.
  Check the default command, writable output, and an actual storyboard export
  through a bind mount using a different UID/GID.

- Add a native Rerun inspection workspace: select a paired seed, open six embedded
  videos alongside measured 3D paths, applied controls and inference timings, or
  download the portable RRD. Read back native poses, controls, source JSON, video
  byte streams and clocks; retain terminal semantics and the full experiment's
  denominator. Feature the verified seed-09 recording on the landing page and in
  both READMEs. Rerun 0.37.2 remains an isolated optional dependency.

- Synchronize replay scripts, matching offline ZIP members and dependent manifest
  hashes together. Integration tests update real VLA, Chaos and Stress packs,
  verify their evidence and archives, and check that repeated syncs change nothing.

- Keep the Stress Lab's offline-archive link in its template. Custom builds
  default to their own `experiment.zip`; `--archive-href` explicitly selects the
  published Release asset. Tests cover the complete published page, local build
  downloads and CLI overrides.

- Encode every recorded video at one quality. Two recorders had drifted to
  imageio-ffmpeg quality 9 (crf 5) and wrote the heaviest media in the
  repository; a test now holds all eight writers to the same value.

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
