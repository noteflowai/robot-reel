# Try Robot Reel on your own episode (about 20 minutes)

We want to know whether Robot Reel helps you understand **your own** robot
recording, and where it gets in the way. This is roadmap milestone
[RR-01](../ROADMAP.md): we need first-use attempts by people who are not
maintainers. Failed and abandoned attempts count; please report them too.

Nothing is uploaded. Robot Reel runs on your machine, sends no telemetry and
writes one folder. You decide what to put in the report.

## 1. Pick an episode and a question

Use a LeRobotDataset (v3.0 or v2.x), either your own (local folder or Hub) or any
public one. Before you start, write down **one concrete question** you would
normally answer by looking at the recording, for example:

- Where does the gripper close later than it was commanded?
- Is the wrist camera in sync with the scene camera?
- At which frame does the arm stop following the command?

## 2. Install, export and verify, with timings

Linux or macOS, Python 3.12 or newer. Replace `YOUR/DATASET` with a Hub repo id
or a local dataset path, and `0` with your episode.

```bash
start=$(date +%s)
python3 -m venv rr-trial && . rr-trial/bin/activate
python -m pip install 'robot-reel[lerobot]==0.19.0'
installed=$(date +%s)
robot-reel lerobot YOUR/DATASET --episode 0 --output my-episode
exported=$(date +%s)
robot-reel lerobot my-episode --verify --check-media
echo "install $((installed - start)) s · export $((exported - installed)) s"
```

Private Hub datasets need `huggingface-cli login` (or `HF_TOKEN`) first.
For a local dataset, add `--dataset PATH` when you also run `--check-source`.
On Windows, note the times by hand.

If a command fails, stop and report the full message: that is a useful result.

## 3. Answer your question

Open `my-episode/index.html` in a browser (no server needed). Note when you
first have a replay you can use, then try to answer your question. The page
shows every camera on one clock, the language task and each recorded signal;
where `action` and `observation.state` share channel names it overlays command
and measurement and links to their largest difference.

## 4. Report

[Open a first-use trial report](https://github.com/noteflowai/robot-reel/issues/new?template=first_use_trial.yml).
It takes about five minutes. Questions before you start: the
[call for trials](https://github.com/noteflowai/robot-reel/discussions/104).
If you prefer not to use GitHub, the same questions can go in the
[pinned Hugging Face discussion](https://huggingface.co/spaces/glayguo/robot-reel/discussions/1).

## How reports are used

A bot replies to each report with exactly what it read from the form and whether
the attempt counts, so you can correct a misread answer by editing the issue.

`scripts/collect_first_use_trials.py` reads reports labelled `first-use-trial`
whose author confirmed they are not a maintainer and agreed to a public summary.
It writes [`validation/external-trials.json`](validation/external-trials.json):
whether the replay opened, minutes to the first useful replay, whether the
question was answered, the comparison tool and whether you would reuse it.
The RR-01 targets are three independent attempts, a first useful replay within
15 minutes, and at least two participants returning with another episode within
four weeks. The record shows progress against them as reported, nothing more.
