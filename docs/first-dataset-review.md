# First dataset review and handoff

Inspect one recorded episode, locate a commanded-versus-measured difference,
and give a collaborator the files needed to check your observation. This is
the RR-01/RR-02 workflow in the [roadmap](../ROADMAP.md).

The example is a public LeRobot recording. It does not establish that a
particular robot failed or that a larger command/measurement difference is
unsafe; those conclusions need task context and calibrated units.

## Install and export

Use Python 3.12 or newer. The commands work from an empty directory; a source
checkout, GPU, model account and LeRobot installation are not required.

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install 'robot-reel[lerobot]==0.19.0'

robot-reel lerobot lerobot/svla_so101_pickplace \
  --revision f641879e22172be7e8161d5e6c1503c2d2feb657 \
  --episode 0 --output so101

robot-reel lerobot so101 --verify --check-media --check-source
```

The dataset declares Apache-2.0. Keep its source attribution and applicable
license/notice files when redistributing recordings or derived clips.

At this revision, verification should report:

| Recorded quantity | Expected value |
| --- | --- |
| Episode | 0 |
| Frames / rate / duration | 303 / 30 fps / 10.1 seconds |
| Cameras | `observation.images.up`, `observation.images.side` |
| Action / observed-state channels | 6 / 6 |
| Decoded video frames checked | 606 |
| Source values checked | 3,939 |

The source metadata says `robot_type: so100_follower`; retain the recorded
metadata when describing the episode instead of inferring hardware from the
repository name.

## Make one reviewable observation

Open `so101/index.html` in a browser.

1. Step through the two camera views on the same frame timeline.
2. Select a named command/measurement channel and inspect its largest
   displayed difference. Note the channel, the frame position and the two
   values. `--mark FRAME` takes a zero-based index into `episode.json`
   (0..length-1). The `--mark` output prints that frame's recorded timestamp
   and values, so compare them with what you saw before handing off.
3. Check the image at that frame. Decide what is visible, what the numeric
   record says and what remains unknown. Do not infer task success from the
   joint curve alone.
4. Seal that selection into the export. `--mark` needs robot-reel 0.19.0 or
   later. It edits the folder in place, so copy the folder first if the
   unmarked version must stay readable by older robot-reel releases.

```bash
robot-reel lerobot so101 --mark 239 \
  --signal action/shoulder_pan.pos --signal observation.state/shoulder_pan.pos \
  --note "Visible: gripper approaching the box. Command and measurement diverge in recorded units. Unknown: whether contact occurred. Next check: side camera around this frame."
```

`--mark` first runs the same checks as `--verify`. It then reads each value at
that frame from `episode.json` and writes `finding.json` with the episode,
frame, recorded timestamp, each `{key, name, value}`, your note, the
`episode.json` hash and the Robot Reel version. Finally it adds the
`finding.json` hash to `manifest.json`. No other manifest entry changes. At
this revision the printed values are 45.14706 (`action`) and 61.75649
(`observation.state`).

Use the note (1 to 2000 characters) for what the numbers cannot say: the
visible observation, your question and its limitations. Each `--signal` is a
series key and channel name from `episode.json`, split at the last slash. You
can give 1 to 8 distinct signals.

`--mark` exits with status 2 and writes nothing in these cases:

- The frame is out of range. The message gives the valid range.
- A channel is unknown. The message lists the available channels.
- The note is empty or invalid.
- The export fails verification.
- The export already carries a finding. Each bundle holds one finding.

## Hand off the complete folder

Copy or archive all of `so101/`, including `index.html`, `episode.json`,
`finding.json`, `manifest.json` and the camera clips. You do not need a
separate note or a `file://` link.

The recipient installs the same release and checks the folder from any path,
without contacting the Hub:

```bash
python -m pip install 'robot-reel[lerobot]==0.19.0'
robot-reel lerobot received/so101 --verify --check-media
```

The JSON output contains a `finding` object with the sealed episode, frame,
timestamp, signal values and note. To see the frame with 0.19.0, open
`received/so101/index.html`, step to the printed frame with the frame
controls and confirm the position against the printed timestamp; the 0.19.0
page does not show the finding.

Releases after 0.19.0 show it: a folder marked with one opens with a *Sealed
finding* panel giving the note, frame, timestamp and recorded values, and a
**Go to frame 239** button that moves both cameras and the charts to that frame,
offline. The panel compares the finding only with the page's own data; it is not
a substitute for the `--verify` run above.

robot-reel 0.18.x and earlier, including 0.17.1, report a marked folder as
`Incomplete LeRobot replay manifest`. Upgrading to 0.19.0 or later fixes this.

`--verify` exits with status 2 and names the problem in these cases:

- `finding.json` was edited without updating the manifest: `Hash mismatch: finding.json`.
- `episode.json` or a clip changed: `Hash mismatch: FILE`.
- A re-hashed finding contradicts the recorded data:
  `Finding disagrees with episode.json: FIELD`.
- A re-hashed finding breaks the input rules or the fixed schema:
  `Invalid finding: FIELD`.
- `finding.json` exists but is not listed in `manifest.json`, for example
  after an interrupted `--mark`. Delete `finding.json` and mark again, or
  re-mark a fresh copy of the export.

A finding records an observation. It is not a failure label, a calibrated
threshold or a signature. The hashes show that the files are unchanged since
they were marked. They do not show who wrote them. A rewrite that is re-hashed
and stays consistent with `episode.json` is not detected. Examples are another
valid note, another version string, or another frame with its matching
recorded values.

To return a folder marked by 0.19.0 to its unmarked form, delete
`finding.json` and remove its one entry from `manifest.json`. Old and new
releases then both verify it. Later releases also embed the finding in
`index.html`, so keep an unmarked copy from before marking.

`--check-source` additionally needs access to the pinned source files, through
the Hub/cache or a supplied local dataset. It compares exported values against
that source. The manifest checks file integrity; it is not a digital signature
or a guarantee that an interpretation is correct.

## Recorded maintainer check, 2026-09-29

On one Linux machine with a new Python 3.12 environment, installation took
164.6 seconds (existing pip cache), export 29.3 seconds (empty Hub cache), and
source/media verification 5.5 seconds. Copying the folder to a new path
preserved offline verification and browser frame stepping. Both camera clips
opened with network requests blocked. Changing the copied `episode.json`
without updating its manifest was rejected with exit code 2.

The [machine-readable check record](validation/first-use-2026-09-29.json) also
records one observation: at frame 239, `shoulder_pan.pos` has command 45.14706
and measurement 61.75649, in the dataset's recorded units. Their difference
is an observation to investigate, not a task-failure label.

This establishes reproducibility for this package/dataset pair. Independent
first-use trials, repeat use and a same-task Rerun/LeRobot comparison are still
needed to validate usability or comparative value.
