# Replay a LeRobot dataset episode

`robot-reel lerobot` turns one episode of any
[LeRobotDataset](https://huggingface.co/docs/lerobot/lerobot-dataset-v3) into a
folder you can open offline, attach to an issue or publish on GitHub Pages. It
reads the dataset's own files and does not import or install LeRobot.

**[Open the SO-101 example ↗](https://noteflowai.github.io/robot-reel/lerobot/)**:
episode 0 of [`lerobot/svla_so101_pickplace`](https://huggingface.co/datasets/lerobot/svla_so101_pickplace),
the real SO-101 pick-and-place data used to fine-tune SmolVLA. Two cameras, six
joints, 303 frames at 30 fps.

[![Two SO-101 camera views on one clock above commanded versus measured joint curves.](lerobot/poster.png)](https://noteflowai.github.io/robot-reel/lerobot/)

## Quick start

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install 'robot-reel[lerobot]==0.18.4'

# Any public Hub dataset; only the files this episode needs are downloaded.
robot-reel lerobot lerobot/svla_so101_pickplace --episode 0 --output artifacts/so101

# Or a dataset on disk, e.g. one you just recorded with lerobot-record.
robot-reel lerobot ~/.cache/huggingface/lerobot/you/your_dataset --episode 3 --output artifacts/mine
```

Open `artifacts/so101/index.html` directly from disk. The SO-101 export above
took 29.3 seconds in a maintainer check on 2026-09-29 with an empty Hub cache;
package installation took another 164.6 seconds in a new Python 3.12 environment
using the host's existing pip cache. These are one-machine measurements, not
a prediction for other networks or datasets; no GPU is used for this workflow.
Private or gated Hub datasets use your existing `hf auth login` token.

For a pinned dataset revision, expected verification counts and an offline
collaborator handoff, follow [First dataset review](first-dataset-review.md).

## What the replay shows

- **Every camera on one clock.** Each `video` feature is cut from its source
  file at the episode's recorded offset (`from_timestamp` in v3.0 files that
  hold many episodes) and re-encoded to H.264, so the clip holds exactly the
  episode's frames and plays in any browser. `image` features stored inside the
  parquet file (PNG or JPEG) are encoded the same way.
- **Commanded versus measured.** When `action` and `observation.state` share
  channel names, as LeRobot follower arms do, each joint gets its own panel with
  both curves and a link to the frame with the largest recorded difference.
  When the names or channel counts differ (for example an end-effector delta
  `action` beside joint `observation.state`), both are plotted separately and
  the page says why; Robot Reel never guesses which channels correspond.
  Other numeric features (rewards, `next.done`, extra sensors up to 64 values
  per frame) are plotted on their own.
- **The language task**, episode length and frame rate, plus frame stepping,
  playback speed, keyboard control (← → Space Home End) and shareable
  `#frame=N` links.
- **Provenance.** `episode.json` holds every exported value, the Hub commit the
  export was pinned to (a branch or tag given with `--revision` is resolved to
  its commit) and the SHA-256 of each source file used. The folder's
  `manifest.json` fingerprints the page, the data and every clip.

Floating-point values are written as the shortest decimal that reads back to
the same source number, so `episode.json` can be compared with the parquet file
exactly. Features the viewer cannot plot are listed under `skipped` with the
reason. Units are the dataset's own; Robot Reel does not rescale them.

## Verify an export

```bash
# Standard library only: manifest, schema and the page's embedded data.
robot-reel lerobot artifacts/so101 --verify

# Count every decoded camera frame against the episode length.
robot-reel lerobot artifacts/so101 --verify --check-media

# Re-read the pinned source dataset and compare every exported value and file hash.
robot-reel lerobot artifacts/so101 --verify --check-source
robot-reel lerobot artifacts/mine --verify --check-source --dataset ~/path/to/your_dataset
```

CI runs all three checks against a fresh export of the published example, and
the unit tests cut the second episode out of a shared v3.0 video and a v2.1
per-episode video, then decode each clip frame to confirm it came from that
episode, in order.

## Supported datasets and limits

- LeRobotDataset **v3.0** (current) and **v2.0 / v2.1**. Older v1.x datasets
  should be converted with LeRobot's own conversion script first.
- One episode per export, up to 20,000 frames. Numeric features with more than
  64 values per frame (for example embeddings or depth arrays stored in parquet)
  are skipped and listed.
- Clips are lossy H.264 viewing copies (`--crf 23` by default; lower values are
  larger and closer to the source). The source videos' hashes are recorded,
  not their pixels.
- Checked beyond the SO-101 example on 2026-10-01: episode 0 of seven other
  public datasets (PushT, xArm, ALOHA sim and real, Unitree H1, Columbia PushT,
  Berkeley UR5; one to four cameras, 25 to 1,100 frames) exported and passed all
  three checks with 0.18.3. [Record](validation/first-use-2026-10-01.json).
- Tried it on your own data? [Report the attempt](first-use-trial.md), including failures.
- The replay shows what the dataset recorded. It does not judge success,
  calibrate units or infer contacts.

### Timeline errors

Every frame must carry `frame_index` 0..length-1 exactly once, with a finite
timestamp later than the previous frame's. A damaged episode stops the export
with exit status 2 before any file is written. The message names the data file
(relative to the dataset root), the episode and the first bad value:

- `Episode 3 in data/chunk-000/episode_000003.parquet is missing frame_index 57 (next recorded frame_index is 58); frames must be 0..length-1 without gaps.`
  A dropped final frame is still reported as `Episode metadata lists N frames but … holds N-1`.
- `Episode E in DATA repeats frame_index R; each frame must appear once.`
- `Episode E in DATA has frame_index R where I was expected.` (a negative,
  null, NaN or non-numeric value)
- `Episode E in DATA has no finite timestamp at frame_index I.`
- `Episode E in DATA: timestamp at frame_index I (B s) is not after frame_index I-1 (A s).`

The numbers are `frame_index` values, not row numbers in the file (v3.0 files
hold many episodes, and rows may be stored unsorted). Filter the episode for
that `frame_index` to find the frame. Float or boolean indices numerically
equal to 0..length-1 (0.0, 1.0, …) are still accepted. Only the first problem
is reported. Each of these messages ends with `Robot Reel does not reorder, fill
or interpolate frames; repair or re-export the episode.` Robot Reel refuses a
damaged episode; it never repairs one. Timestamp columns with more than one
value per frame keep the generic `Timestamps are missing or not increasing`.

Rerun 0.38 added a reader that streams LeRobot datasets into its native viewer; use that
for live, multi-episode exploration, and this export when you need a single
self-contained folder that opens anywhere and carries its own checksums. The
[Hugging Face LeRobot visualizer](https://huggingface.co/spaces/lerobot/visualize_dataset)
browses public Hub datasets online; each exported page links to its episode there.
