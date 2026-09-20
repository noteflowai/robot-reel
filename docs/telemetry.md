# Open the recorded telemetry in Foxglove or Rerun

The Stress Lab ships its measurements as MCAP, so you can inspect the same runs
in tools you already use instead of only in the browser replay.

- Download: [`stress/telemetry.mcap`](https://noteflowai.github.io/robot-reel/stress/telemetry.mcap) (1.3 MB), or find it in the [offline lab archive](https://github.com/noteflowai/robot-reel/releases/latest)
- In the checkout: `docs/stress/telemetry.mcap`

The file holds 3915 messages on 60 topics: 3555 observations and 360 inference
calls across 30 trials. Messages are `json`, against a single `jsonschema`
schema named `robot-reel.telemetry`. Video, model weights and a saved viewer
layout are not part of the file.

## The clock

Log time and publish time are **episode-relative nanoseconds, and every trial
starts at zero** — they are not UTC. That is deliberate: the ten paired seeds and
three conditions line up on one timeline, so a reference trial and its dimmed or
shifted-camera counterpart can be read against each other directly. It also
means the file has no wall-clock meaning; `started_seconds` and
`finished_seconds` on the inference topic carry the recording-relative timing.

## Topics

Two topics per trial, named after the trial id:

| Topic | Messages per trial | What each message carries |
| --- | --- | --- |
| `/{trial}/observation` | one per applied control, plus the terminal observation | Measured state, the applied and proposed controls, reward, camera hashes |
| `/{trial}/inference` | one per policy call | Policy, environment-step and wall timings, and the noise hash |

Trial ids are `seed-NN-{reference,dim,camera}` for seeds `00`–`09`, for example
`/seed-04-camera/observation`. Every message also repeats its `trial_id` and
`kind` next to the `sample` payload, so a single merged plot stays attributable.

## Foxglove

Foxglove opens the file directly (**Open local file**) and reads JSON messages
without a schema install. Add a Plot panel and paste these
[FoxQL](https://docs.foxglove.dev/docs/visualization/foxql) expressions as
series.

Paired end-effector height, one line per condition on the same seed:

```
/seed-00-reference/observation.sample.state[2]
/seed-00-dim/observation.sample.state[2]
/seed-00-camera/observation.sample.state[2]
```

The applied control the policy actually issued, against what it proposed. The
seven channels are `delta_x`, `delta_y`, `delta_z`, `delta_rx`, `delta_ry`,
`delta_rz`, `gripper`; index `6` is the gripper:

```
/seed-00-reference/observation.sample.action[6]
/seed-00-reference/observation.sample.proposed_action[6]
```

To see all seven at once, use `sample.action[:]` with the series **Array
expansion** setting on **By index**. Controls are normalized to `[-1, 1]` and
are not joint angles; `sample.joint_position` holds the measured arm.

Inference cost per call, and the simulator step time beside it:

```
/seed-00-reference/inference.sample.policy_seconds
/seed-00-reference/inference.sample.env_step_seconds
```

Reward and the recorded task outcome as it develops:

```
/seed-00-reference/observation.sample.reward
```

`sample.next_success` and `sample.terminal` are booleans, so a State Transitions
panel reads them better than a plot. `sample.inference_frame` maps an
observation back to the policy call that produced its chunk, which is the same
mapping the browser replay uses.

## Rerun

The Rerun Viewer opens MCAP files, but its automatic visualization covers ROS 2
messages and Foxglove's Protobuf schemas, so this custom JSON schema arrives as
raw messages rather than plotted scalars. Use the native export below for a
ready-to-use layout with videos, spatial data and plots.

### Native Rerun workspace

[Open the recorded workspace in Rerun 0.37.2](https://app.rerun.io/version/0.37.2/?url=https%3A%2F%2Fnoteflowai.github.io%2Frobot-reel%2Frerun%2Fseed-09.rrd)
or [download its portable recording](rerun/seed-09.rrd) (4.3 MiB).
The online viewer loads on demand; a desktop browser with WebGL/WebGPU support
works best. The downloaded `.rrd` opens in the native Rerun application without
a video server.

The example contains the **three conditions at seed 09**, selected from the
original **30-trial** experiment. Reference succeeds in 82 actions; dim lighting
and the shifted camera each reach the 160-action budget. These selected outcomes
do not estimate general robustness. The workspace contains:

- Six original MP4s, embedded byte for byte, with a frame reference for every
  source observation. Switch between scene and wrist cameras.
- Three measured end-effector paths in simulator world coordinates, metres,
  Z up. Full paths are visible from the start and show the complete recording;
  they are not predictions or reconstructed robot geometry.
- Seven applied-control channels per condition, with step-after interpolation,
  and separate points for policy and environment-step timing at real calls.
- Exact observation and inference JSON, complete source traces, provenance and
  media/license notices. The saved blueprint opens on a shared `episode` clock.

Native readback checks cover **405 observations, 2,814 applied-control values,
41 inference calls and all six video assets**. Video presentation timestamps must
equal `sample / 20`; scalar values and JSON stay exact. Spatial visualization
components use float32 and are compared to source positions within `1e-6` metres.

Reference ends at 4.10 s; the other recordings end at 8.00 s. Camera panels hold
their final images and state their end times in their titles. Controls stop
before the terminal observation; the moving 3D marker clears one sample after
it. The `sample` and `episode` indexes are source clocks. Rerun's optional
`log_time` index records export time and must not be read as policy latency.

Build any recorded seed in an isolated optional environment:

```bash
python3 -m venv .venv-rerun
.venv-rerun/bin/python -m pip install -e '.[rerun]'
.venv-rerun/bin/python -m robot_reel.stress_rerun \
  docs/stress artifacts/rerun-seed-09.rrd --seed 9
.venv-rerun/bin/python -m robot_reel.stress_rerun \
  docs/stress artifacts/rerun-seed-09.rrd --seed 9 --verify
.venv-rerun/bin/rerun artifacts/rerun-seed-09.rrd
```

Choose a new output filename when exporting again. Omitting `--seed` selects
seed 0, including for custom experiments. The exporter verifies the source site,
writes a temporary file, reads native components back, and publishes the file
only after the comparison passes. Rerun is not a dependency of ordinary replay
or standard-library validation.

The integration targets [Rerun 0.37.2](https://github.com/rerun-io/rerun/releases/tag/0.37.2).
It uses the version's native `AssetVideo`, `VideoFrameReference`, `Points3D`,
`LineStrips3D` and `Scalars`, with its experimental RRD reader for independent
readback. The pin is intentional; SDK/reader upgrades require this check to pass.

To refresh the homepage example, export seed 09, open it in the pinned viewer,
pause at sample zero and capture the complete workspace as a PNG. After reviewing
the camera panels, paths and curves, package the checked recording and screenshot:

```bash
.venv-rerun/bin/python -m scripts.build_rerun_showcase \
  --recording artifacts/rerun-seed-09.rrd --preview artifacts/rerun-preview.png
.venv-rerun/bin/python -m unittest discover -s tests -p test_rerun.py -v
```

The package manifest records the screenshot, recording and original source hashes.
The preview is a viewer screenshot; it is not an additional policy rollout.

## Checking and rebuilding it

The export is verified by reading it back, not just by writing it:

```bash
python3 -m pip install -e '.[inspect]'
python3 -m robot_reel.stress_mcap docs/stress
```

That re-reads every message and compares its topic, sequence, log time, publish
time and serialized payload to the source trace, and checks the recorded
`traces_sha256` provenance. It prints the message and trial counts. CI runs the
same check. The expressions on this page are also checked against the real
telemetry by `tests/test_telemetry.py`, so they cannot drift from the data.
