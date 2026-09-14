"""An OpenEnv 0.4.2 task with a bounded Blender edit and independent native checks.

The server operator supplies reviewed source, executable and script paths.
Agent actions contain numbers only; no shell, Python code, paths or URLs.
"""

from __future__ import annotations

import hashlib
import json
import math
import subprocess
import time
from pathlib import Path
from uuid import uuid4

from openenv.core.env_server.interfaces import Environment
from openenv.core.env_server.types import Action, Observation, State
from pydantic import Field, field_validator


class SceneEdit(Action):
    terrain_z_scale: float = Field(ge=0.5, le=2)
    sun_azimuth_degrees: float = Field(ge=0, le=360)
    sun_energy: float = Field(ge=0.1, le=5)

    @field_validator("terrain_z_scale", "sun_azimuth_degrees", "sun_energy", mode="before")
    @classmethod
    def finite_number(cls, value):
        if type(value) not in (int, float) or not math.isfinite(value):
            raise ValueError("edit values must be finite numbers, not booleans")
        return value


class SceneObservation(Observation):
    instruction: str
    checks: dict = Field(default_factory=dict)
    artifact: str | None = None


INSTRUCTION = (
    "Raise the captured terrain by 40% in Z while preserving its XY bounds and source. "
    "Set sun azimuth to 310 degrees and energy to 3. Deliver a packed native Blender "
    "scene, standard GLB, surface SPLAT and a separately identified collision heightfield. "
    "Acceptance requires independent native readback; a completion statement earns no reward."
)


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


class SceneEnvironment(Environment[SceneEdit, SceneObservation, State]):
    SUPPORTS_CONCURRENT_SESSIONS = False

    def __init__(self, *, blender: Path, repository: Path, source: Path, baseline: Path, output: Path):
        super().__init__()
        self.blender = blender.resolve()
        self.repository = repository.resolve()
        self.source = source.resolve()
        self.baseline = json.loads((baseline / "scene.json").read_text())
        self.output = output.resolve()
        self.output.mkdir(parents=True, exist_ok=True)
        self.pins = {
            "blender": sha(self.blender),
            "builder": sha(self.repository / "scripts/build_scene_lab.py"),
            "checker": sha(self.repository / "scripts/check_scene_lab.py"),
            "source": sha(self.source / "source-manifest.json"),
        }
        if self.pins["source"] != self.baseline["source_manifest_sha256"]:
            raise ValueError("baseline and reviewed source differ")
        self._state = State(episode_id=str(uuid4()), step_count=0)
        self._done = False

    @property
    def state(self):
        return self._state

    def reset(self, seed=None, episode_id=None, **kwargs):
        # Do not use a caller's episode ID as a filesystem path.
        self._state = State(episode_id=str(uuid4()), step_count=0)
        self._done = False
        (self.output / self._state.episode_id).mkdir()
        return SceneObservation(instruction=INSTRUCTION, reward=0, done=False, metadata={
            "pins": self.pins, "step_limit": 3, "seed": seed,
            "scope": "Verifiable creation pilot. No RL training or aesthetic quality score.",
        })

    def step(self, action, timeout_s=None, **kwargs):
        if not isinstance(action, SceneEdit):
            raise TypeError("expected a validated SceneEdit")
        if self._done or self._state.step_count >= 3:
            raise ValueError("reset before starting another episode")
        current = {
            "blender": sha(self.blender),
            "builder": sha(self.repository / "scripts/build_scene_lab.py"),
            "checker": sha(self.repository / "scripts/check_scene_lab.py"),
            "source": sha(self.source / "source-manifest.json"),
        }
        if current != self.pins:
            raise ValueError("reviewed build inputs changed during the episode")
        self._state.step_count += 1
        root = self.output / self._state.episode_id / f"step-{self._state.step_count}"
        root.mkdir()
        recipe = root / "edit.json"
        recipe.write_text(json.dumps({
            "schema": "robot-reel.scene-edit.v1",
            **action.model_dump(exclude={"metadata"}),
        }, indent=2) + "\n")
        result_dir = root / "scene"
        commands = [
            [str(self.blender), "--background", "--factory-startup", "--disable-autoexec",
             "--python-exit-code", "1", "--python", str(self.repository / "scripts/build_scene_lab.py"),
             "--", "--source", str(self.source), "--edit", str(recipe), "--output", str(result_dir)],
            [str(self.blender), "--background", "--factory-startup", "--disable-autoexec",
             "--python-exit-code", "1", "--python", str(self.repository / "scripts/check_scene_lab.py"),
             "--", "--scene", str(result_dir)],
        ]
        started = time.monotonic()
        budget = min(120.0, 120.0 if timeout_s is None else float(timeout_s))
        if not math.isfinite(budget) or budget <= 0:
            raise ValueError("choose a positive bounded step timeout")
        failure = None
        try:
            for index, command in enumerate(commands):
                remaining = budget - (time.monotonic() - started)
                if remaining <= 0:
                    raise subprocess.TimeoutExpired(command, budget)
                with (root / f"process-{index}.log").open("wb") as log:
                    subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=remaining)
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
            failure = type(error).__name__
        checks = {}
        if failure is None:
            native = json.loads((result_dir / "native-check.json").read_text())
            scene = json.loads((result_dir / "scene.json").read_text())
            base = self.baseline["geometry"]["bounds_m"]
            bounds = native["native_bounds_m"]
            checks = {
                "native_readback": native["passed"] is True,
                "source_preserved": scene["source_manifest_sha256"] == self.pins["source"],
                "xy_preserved": all(
                    math.isclose(bounds[i][axis], base[i][axis], abs_tol=1e-5)
                    for i in (0, 1) for axis in (0, 1)
                ),
                "height_increased_40_percent": math.isclose(
                    bounds[1][2] - bounds[0][2], 1.4 * (base[1][2] - base[0][2]), abs_tol=1e-5
                ),
                "sun_azimuth": math.isclose(native["native_sun_azimuth_degrees"], 310, abs_tol=1e-4),
                "sun_energy": math.isclose(native["native_sun_energy"], 3, abs_tol=1e-5),
                "packed_textures": len(native["packed_textures"]) >= 3,
                "separate_collision": "CollisionHeightfield" in native["glb_meshes"],
            }
        accepted = bool(checks) and all(checks.values())
        self._done = accepted or self._state.step_count >= 3 or failure is not None
        observation = SceneObservation(
            instruction=INSTRUCTION, checks=checks, reward=int(accepted), done=self._done,
            artifact=str(result_dir.relative_to(self.output)) if failure is None else None,
            metadata={
                "failure": failure, "elapsed_seconds": time.monotonic() - started,
                "scene_sha256": sha(result_dir / "scene.blend") if failure is None else None,
                "reward_semantics": "All independent native requirements pass; not aesthetic quality.",
            },
        )
        (root / "observation.json").write_text(observation.model_dump_json(indent=2) + "\n")
        return observation
