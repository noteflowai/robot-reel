# Verifiable scene creation with OpenEnv

This small OpenEnv 0.4.2 environment accepts three bounded numeric edit fields,
builds a real captured scene in Blender, then reopens the native file in a second
process. Reward is one only when measured geometry, native lighting, source
identity, packed textures and a separate collision mesh satisfy the task.

It is an environment/integration pilot, **not a trained policy, an aesthetic
reward model or evidence of reinforcement-learning gains**. The fixed recipe
space deliberately keeps executable code outside the action interface.

Install `requirements.txt` in a separate environment. Supply the reviewed
Blender 4.5.13 executable, Robot Reel checkout, checked Poly Haven source and
baseline scene described in `docs/scene-lab/METHODS.md`:

```python
from pathlib import Path
from environment import SceneEdit, SceneEnvironment

env = SceneEnvironment(
    blender=Path("/tools/blender"),
    repository=Path("/work/robot-reel"),
    source=Path("/data/checked-source"),
    baseline=Path("/data/original"),
    output=Path("/data/openenv-runs"),
)
initial = env.reset(seed=195)
result = env.step(SceneEdit(
    terrain_z_scale=1.4, sun_azimuth_degrees=310, sun_energy=3,
), timeout_s=120)
print(result.reward, result.checks)
```

The operator fixes all paths and executable hashes. An agent cannot choose a
shell command or artifact location. Episodes allow at most three attempts and
one GPU session at a time. Runtime errors terminate the episode with zero reward;
unsatisfied requirements are a task failure and remain visible. Extra fields
such as `success: true` are rejected by the action schema.

The public experiment includes a valid but incorrect edit, a correct edit and
an invalid completion-claim control. Logs and native checks accompany outcomes.
This follows OpenEnv's standard reset/step/state interface; no modified OpenEnv
fork, third-party session history or remote code execution service is required.
