# Examples

Three JSON inputs for the `robot-reel` command line. Two are four-shot arm plans
for the MuJoCo recorder; one is a director storyboard that only needs the
Python standard library.

| File | Consumed by | Runtime |
| --- | --- | --- |
| `close-up.json` | `robot-reel --shots` | MuJoCo (`pip install -e .`) |
| `orbit.json` | `robot-reel --shots` | MuJoCo (`pip install -e .`) |
| `contact-storyboard.json` | `robot-reel direct --plan` | Standard library only |

## Arm shot plans: `close-up.json`, `orbit.json`

Schema: `{"version": 1, "shots": [...]}` with exactly four shots. The first
three carry a `label` (1–64 characters) and nonempty `targets` mapping joint
names to finite radian values; unspecified joints keep their previous target.
The fourth shot must be `{"label": ..., "home": true}` and returns the arm to
the model's home pose. Validation lives in `robot_reel/plans.py`; unknown
joints, nonfinite or out-of-range targets and extra fields are rejected.

- `close-up.json`: small moves. Rotation -0.4, then Rotation 0.4 with Jaw 0.65,
  then Wrist_Roll 0.25 with Jaw 0.25, then home.
- `orbit.json`: wider sweep. Rotation -0.8, then Rotation 0.8, then Wrist_Roll
  0.6 with Jaw 0.5, then home. This is the same plan as `DEFAULT_PLAN` in
  `robot_reel/plans.py`, so it reproduces the credential-free studio demo.

These plans drive a simulated capture, so they need the full runtime
(MuJoCo, `strands-robots`, ffmpeg via `imageio-ffmpeg`), Python 3.12+ and a
GL backend (Linux defaults to EGL):

```bash
python -m pip install -e .
robot-reel --shots examples/close-up.json --output artifacts/close-up
robot-reel --shots examples/orbit.json --output artifacts/orbit
```

`--shots` is only valid for the default `studio` pack and cannot be combined
with `--agent` or `--render-only`. The browser replay's plan editor exports a
`shots.json` in this same format. See [docs/recording.md](../docs/recording.md).

## Director storyboard: `contact-storyboard.json`

Schema `robot-reel-director-1`, validated by `robot_reel/director.py`. Fields:
`brief` (1–1200 characters), `title` (1–80), `theme` (`midnight` or
`daylight`) and 1–8 `shots`. Each shot has `start`/`end` (exclusive source
frame indices that must cover every source frame once, in order), a `camera`
from `overview`, `tracking`, `impact`, `top`, a `rate` of `1` or `0.5` (slow
motion repeats samples; no motion is generated or dropped) and a `caption`
(1–100 characters).

The example turns the 180-frame braking comparison in `docs/compare/braking`
into four shots: overview 0–60, tracking 60–96, impact 96–126 at half speed,
top 126–180. The result is 210 output frames at 30 fps.

Standard library only:

```bash
# Frame count, cameras and events available to a storyboard.
python3 -m robot_reel.cli direct docs/compare/braking --inspect

# Export storyboard.json, film.json, the Blender build scripts and a manifest.
python3 -m robot_reel.cli direct docs/compare/braking \
  --plan examples/contact-storyboard.json --output artifacts/director

# Re-check an exported bundle against its hashes and source recording.
python3 -m robot_reel.cli direct artifacts/director --verify
```

Expected export output:

```json
{
  "frames": 210,
  "source_frames": 180,
  "fps": 30
}
```

Building and rendering the Blender project from that bundle is described in
[docs/director.md](../docs/director.md). The same storyboard is used by
`tests/test_director.py` and `scripts/check_director_mcp.py`.

## Microduck frame review

`microduck-frame.json` is a full-precision export of the original right-run
frame 120, left knee selected. [Verify it and load the agent review skill](../docs/agent-review.md).
The JSON preserves the original trace hash and model identity; no new simulation
or policy output is generated.
