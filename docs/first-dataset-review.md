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
python -m pip install 'robot-reel[lerobot]==0.17.1'

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
   displayed difference. Record the channel, frame and two values.
3. Check the image at that frame. Write what is visible, what the numeric
   record says and what remains unknown. Do not infer task success from the
   joint curve alone.
4. Use the frame link to preserve the selection. A local `file://` URL needs
   the matching exported folder on the recipient's machine.

Example note template:

```text
Dataset and pinned revision:
Episode / frame:
Channel and recorded units:
Command / measurement:
Visible observation:
Question or proposed next check:
Limitations:
```

## Hand off the complete folder

Copy or archive all of `so101/`, including `index.html`, `episode.json`,
`manifest.json` and the camera clips. Send the note alongside it.

The recipient can open the folder from a different path and check the saved
files without contacting the Hub:

```bash
robot-reel lerobot received/so101 --verify --check-media
```

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
