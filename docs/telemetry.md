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
raw messages rather than plotted scalars. Nothing here is Rerun-specific yet: a
native Rerun view means converting the samples into Rerun archetypes, which is
still a proposal in the [roadmap](roadmap.zh-CN.md).

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
