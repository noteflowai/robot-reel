# Robot Reel 0.8.0 — choose an offline lab

Download these files from the same Robot Reel GitHub release:

| File | Use |
| --- | --- |
| `robot-reel-cloth-experiment.zip` | GPU cloth replay, original positions/velocities, native reports and editable USD |
| `robot-reel-cloth-scene.usdc` | The same cloth scene as in the ZIP; import into Blender at 30 fps |
| `robot-reel-stress-experiment.zip` | Complete offline Stress Lab: 30 trials, 60 videos, telemetry and review tools |
| `robot-reel-seed-09-review.json` | A sample review to import into the lab |
| `robot-reel-paired-outcomes.json` | Complete outcome report: ten paired seeds for each changed condition |
| `SHA256SUMS` | SHA-256 checksums for the release files |
| `robot_reel-0.8.0-py3-none-any.whl` | Optional Python installation for independent checks and exports |
| `robot-reel-seed-09.rrd` | Optional native Rerun workspace; open in Rerun 0.37.2 |

Both ZIPs open in a browser without Python, a GPU or a network connection.
They contain recorded runs; opening them does not execute policy inference or
cloth simulation. Keep the two experiments in separate extracted folders.

## Compare every paired outcome

In the 0.8.0+ Stress Lab, open **Same starts. Which outcomes changed?** Choose
the camera condition, then **Success lost** to inspect seed 09. Choose **Success
gained** to inspect seeds 03, 04 and 05. The net gain of two contains three gains
and one loss; all thirty recorded trials remain available.

**Export all paired outcomes** always includes both changed conditions and all
seed groups, even when the view is filtered. It matches the release's
`robot-reel-paired-outcomes.json`. With the 0.8.0+ wheel installed, verify it:

```bash
robot-reel stress stress-lab --paired-report robot-reel-paired-outcomes.json
```

Expect `paired_report_verified: true`. This checks consistency with the complete
recording, not statistical significance or general policy robustness.

## Explore GPU cloth

1. Extract `robot-reel-cloth-experiment.zip` into `cloth-lab`, keeping all files
   together, and open `index.html`.
2. Press **Release all three**, step or scrub, and switch between side-by-side
   and overlay. Colors identify three numerical bending coefficients.
3. Share a sample by keeping the URL fragment with the folder. Positions and
   velocities retain all 42,471 vertex samples from the original L40S run.
4. To edit the scene, import `scene.usdc` in Blender and set **30 fps**.
   Blender frame 1 is source sample 0; no new cloth simulation is needed.
5. In 0.8.0+, export a 1080p figure or sample JSON. **Open sample JSON** checks
   a received file against the original vertices before restoring the same
   sample and camera. These controls work offline.

The experiment changes only a Newton solver coefficient. It does not calibrate
real fabric, model collisions/self-contact or measure material stress.
The included `METHODS.md` describes its scope and native checks.

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
viewer; use an archive from 0.6.0 or newer for these review tools.

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
python -m pip install ./robot_reel-0.8.0-py3-none-any.whl
robot-reel stress stress-lab --review robot-reel-seed-09-review.json
```

On Windows with Python 3.12 installed, PowerShell can invoke the environment
directly without changing its activation policy:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install .\robot_reel-0.8.0-py3-none-any.whl
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

To regenerate a complete Stress Lab with the installed package:

```bash
python -m robot_reel.stress_site stress-lab stress-copy
```

Version 0.7.1 validates this export before publishing the output directory.
If a dependency is missing or validation fails, fix that cause and retry the
same command. It protects the source collection and existing output files;
choose an empty destination outside the input folder.

Check or re-export the cloth recording from the same installed environment:

```bash
robot-reel cloth --output cloth-lab --verify
robot-reel cloth --export-from cloth-lab --output cloth-copy
```

The second command produces a new viewer and complete `experiment.zip`,
preserving original geometry, velocities and native reports. It requires an
empty destination outside the input folder, and no Newton, Blender or GPU.
`native_usd_checked: false` means the command checked saved report hashes,
not a new USD import. Install `usd-core==26.3` and add `--check-usd` to perform
native readback again.

For the equivalent standard-library check from a source checkout, use
`python3 -m robot_reel.cli stress /path/to/stress-lab --review /path/to/review.json`.
The extracted lab's `METHODS.md`, `NOTICE.txt` and `LICENSE` retain the experiment
scope, clocks, model identities and upstream terms.
