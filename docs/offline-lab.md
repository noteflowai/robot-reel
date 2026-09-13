# Robot Reel 0.6.0 — start with the offline lab

Download these files from the same Robot Reel GitHub release:

| File | Use |
| --- | --- |
| `robot-reel-stress-experiment.zip` | Complete offline Stress Lab: 30 trials, 60 videos, telemetry and review tools |
| `robot-reel-seed-09-review.json` | A sample review to import into the lab |
| `SHA256SUMS` | SHA-256 checksums for the release files |
| `robot_reel-0.6.0-py3-none-any.whl` | Optional Python installation for independent checks and exports |
| `robot-reel-seed-09.rrd` | Optional native Rerun workspace; open in Rerun 0.37.2 |

The ZIP opens in a browser without Python, a GPU or a network connection.
It contains recorded runs; opening it does not execute policy inference.

## Open a real review

1. Extract `robot-reel-stress-experiment.zip` into a folder named `stress-lab`.
   Keep the entire folder together and open its `index.html` in a browser.
2. Scroll to **Turn a moment into a review**. Use **Open a review JSON** to select
   the downloaded `robot-reel-seed-09-review.json`.
3. The lab compares the review with its loaded records and restores seed 09,
   reduced light, the wrist camera and paired sample 100. The reference has
   already succeeded at source sample 82; its final observation is explicitly
   held. The reduced-light run is still applying recorded controls.
4. Write your own note and export JSON for checking or Markdown for discussion.
   Importing that JSON into the same lab restores the selection and note.
   Notes are not uploaded or saved between visits.

The sample note is a review prompt, not verified evidence. The experiment remains
one LIBERO task, ten paired initial states and three conditions: all 30 trials
remain visible. A selected pair is not a benchmark or a general robustness claim.
The earlier v0.4.0 archive contains the same recorded experiment with an older
viewer; use the 0.6.0 archive for these review tools.

## Check the downloaded files

On Linux, from the directory containing the downloaded files:

```bash
sha256sum --check --ignore-missing SHA256SUMS
```

On macOS, check an individual file and compare the printed hash with its entry
in `SHA256SUMS`:

```bash
shasum -a 256 robot-reel-stress-experiment.zip
```

On Windows PowerShell:

```powershell
Get-FileHash .\robot-reel-stress-experiment.zip -Algorithm SHA256
```

Checksums compare downloaded bytes with the release. They are not an external
attestation of the original collector.

## Independently check the recorded facts

Python 3.12+ and the release wheel enable local verification. From the directory
containing that wheel, the sample JSON and the extracted `stress-lab` folder,
on Linux/macOS:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install ./robot_reel-0.6.0-py3-none-any.whl
robot-reel stress stress-lab --review robot-reel-seed-09-review.json
```

On Windows with Python 3.12 installed, PowerShell can invoke the environment
directly without changing its activation policy:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install .\robot_reel-0.6.0-py3-none-any.whl
.\.venv\Scripts\robot-reel.exe stress stress-lab --review robot-reel-seed-09-review.json
```

Installing dependencies can require internet access. The installed command checks
the complete lab and compares the review with its source records. Expect
`recorded_facts_match: true`, `user_note_verified: false`, and
`planned_trials: 30`. Replacing the sample filename checks your own exported JSON.

Optional video and MCAP checks:

```bash
python -m pip install 'mcap==1.4.0'
robot-reel stress stress-lab --check-media --check-mcap
```

For the equivalent standard-library check from a source checkout, use
`python3 -m robot_reel.cli stress /path/to/stress-lab --review /path/to/review.json`.
The extracted lab's `METHODS.md`, `NOTICE.txt` and `LICENSE` retain the experiment
scope, clocks, model identities and upstream terms.
