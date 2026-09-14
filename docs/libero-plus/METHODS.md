# Official LIBERO-Plus subset: same task, changed scene

Three episodes were selected before inference: the original spatial bowl task,
Camera Viewpoints official ID **609** (runtime index 608), and Light Conditions
official ID **2124** (runtime index 2123), difficulty 1. The plan, upstream commit,
BDDL hashes and initial-state hash are preserved in `plan.json`.

The environment is official `sylvestf/LIBERO-plus` at
`4976dc30028e805ff8094b55501d532c48fec182`. Its original wrapper applies the camera
and light perturbations. No post-render pixel manipulation is used.
All three initial qpos, qvel and simulation clocks match exactly after 10 settling
steps. Native camera/light arrays independently confirm the requested scene changes.

Policy: `HuggingFaceVLA/smolvla_libero`, revision
`6721902bc4d61e50a3bfdb11dfb4cb626f05d102`, NVIDIA L40S, float32, TF32 disabled.
LeRobot 0.6.1 runs in a separate local process from the original simulator stack.
Only bounded RGB observations, robot state and actions cross the local HTTP boundary.
LeRobot's actual LiberoProcessorStep performs the 180-degree image rotation and
quaternion-to-axis-angle conversion. Noise seed 195 is paired across conditions;
action horizon is 10, control frequency 20 Hz, maximum episode length 220 actions.

The recorded outcomes are original success at 77 actions, viewpoint condition
step limit at 220, light condition success at 87. This is **one task and one episode
per condition**, not a full 10,030-task evaluation, a model ranking or a general
robustness estimate. Wall time includes rendering and is not a throughput benchmark.

Success comes from the native environment's task completion signal. Local validators
check source identities, clocks, action clipping, terminal consistency, paired noise,
initial states and video frame counts. They do not independently authenticate a producer
or prove simulator task success from a video alone.

## Reproduce and verify

Use `robot-reel libero-plus plan --repository /path/to/reviewed/LIBERO-plus --output plan.json`.
Download the exact assets archive identified in that plan. The checked archive uses
a nested original directory prefix; strip that prefix only after validating entries,
and place the assets at the configured native assets path.

Run `scripts/smolvla_server.py --cache /path/to/vla-cache` in the pinned GPU LeRobot
environment. Run `scripts/record_libero_plus.py` in the official LIBERO-Plus environment
with `--libero-repo`, `--plan`, `--cache` and a fresh `--output`. Its source and the exact
executed policy server are preserved here as `recorder.py` and `policy-server.py`.
Both scripts require existing reviewed model/source revisions.

Verify the public recording offline:

```sh
robot-reel libero-plus verify --output docs/libero-plus --media
```

The page replays both videos on one 20 Hz source clock. An episode that ends earlier
holds its last frame and is explicitly marked ended; it is never extended as new data.
Runtime/library versions, checkpoint fingerprint, raw telemetry and native scene settings
remain downloadable. Simulation assets retain their upstream terms; see the source
dataset card (`Sylvest/LIBERO-plus`) and Robot Reel's third-party notices.
