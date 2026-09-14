"""Record real native edits and a rejected completion-claim control."""
import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path

from environment import SceneEdit, SceneEnvironment
from pydantic import ValidationError


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("blender", "repository", "source", "baseline", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("choose a new evidence directory")
    version = importlib.metadata.version("openenv")
    if version != "0.4.2":
        parser.error("this published pilot requires OpenEnv 0.4.2")
    env = SceneEnvironment(**vars(args))
    initial = env.reset(seed=195)
    invalid_rejected = False
    try:
        SceneEdit(terrain_z_scale=1.4, sun_azimuth_degrees=310, sun_energy=3, success=True)
    except ValidationError:
        invalid_rejected = True
    if not invalid_rejected or env.state.step_count != 0:
        raise AssertionError("invalid action must not create a rewarded step")
    observations = []
    for scale, expected in ((1.0, 0), (1.4, 1)):
        action = SceneEdit(terrain_z_scale=scale, sun_azimuth_degrees=310, sun_energy=3)
        observation = env.step(action, timeout_s=120)
        observations.append({"action": action.model_dump(), "observation": observation.model_dump()})
        if observation.reward != expected:
            raise AssertionError(f"native edit reward differs from control: {scale}")
    harness = args.output / "harness"
    harness.mkdir()
    for path in (
        Path(__file__), Path(__file__).with_name("environment.py"),
        args.repository / "scripts/build_scene_lab.py",
        args.repository / "scripts/check_scene_lab.py",
    ):
        (harness / path.name).write_bytes(path.read_bytes())
    result = {
        "schema": "robot-reel.openenv-creation-pilot.v1",
        "openenv_version": version, "initial": initial.model_dump(),
        "invalid_completion_claim_rejected": invalid_rejected,
        "steps": observations, "final_state": env.state.model_dump(),
        "harness": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in harness.iterdir()},
        "scope": "Real OpenEnv reset/step/state Python interface. No HTTP deployment, RL training or aesthetic reward claim.",
    }
    (args.output / "pilot.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
