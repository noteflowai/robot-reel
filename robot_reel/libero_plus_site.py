"""Verify and publish a preselected official LIBERO-Plus policy experiment."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import shutil
import tempfile

from robot_reel.libero_plus import DEFAULT_BASE, REVISION, make_plan
from robot_reel.solver_lab import decode, digest, read

CONDITIONS = ("baseline", "camera-viewpoints", "light-conditions")
RUN_FILES = ("run.json", "native-scene.json", "initial-state.json", "rollout.mp4", "poster.png")
COMMON_FILES = ("plan.json", "source.json", "recorder.py", "policy-server.py")


def inspect(root, *, media=False):
    root = Path(root)
    plan = decode(read(root, "plan.json"))
    source = decode(read(root, "source.json"))
    if (
        plan.get("schema") != "robot-reel.libero-plus-plan.v1"
        or plan.get("source", {}).get("revision") != REVISION
        or plan.get("base_task") != DEFAULT_BASE
        or [c["name"] for c in plan.get("conditions", [])] != list(CONDITIONS)
        or plan.get("max_steps") != 220
        or source.get("plan_sha256") != digest(read(root, "plan.json"))
        or source.get("recorder_sha256") != digest(read(root, "recorder.py"))
        or source.get("policy", {}).get("server_sha256") != digest(read(root, "policy-server.py"))
    ):
        raise ValueError("official plan or executable source identity differs")
    if [
        (row["official_task_id"], row["runtime_index"]) for row in plan["conditions"]
    ] != [(None, None), (609, 608), (2124, 2123)]:
        raise ValueError("published official task IDs differ")
    rows, initial_states, native_scenes = [], [], []
    for condition in plan["conditions"]:
        name = condition["name"]
        run = decode(read(root / name, "run.json"))
        initial = decode(read(root / name, "initial-state.json"))
        native = decode(read(root / name, "native-scene.json"))
        initial_states.append({key: initial[key] for key in ("qpos", "qvel", "time_s")})
        native_scenes.append(native)
        if (
            run.get("schema") != "robot-reel.libero-plus-run.v1"
            or run.get("source") != source or run.get("condition") != condition
            or run.get("status") not in ("success", "step_limit")
            or run.get("error") is not None or type(run.get("task_success")) is not bool
            or type(run.get("steps")) is not int or not 1 <= run["steps"] <= plan["max_steps"]
            or len(run.get("frames", [])) != run["steps"]
            or run["task_success"] != (run["status"] == "success")
            or (run["status"] == "step_limit" and run["steps"] != plan["max_steps"])
        ):
            raise ValueError(f"inconsistent run outcome: {name}")
        for index, frame in enumerate(run["frames"]):
            policy = frame["policy"]
            if (
                frame.get("step") != index or policy.get("step") != index
                or policy.get("inference") != (index % 10 == 0)
                or type(frame.get("success")) is not bool
                or frame["success"] != (run["task_success"] and index == run["steps"] - 1)
                or not math.isclose(frame["time_s"], initial["time_s"] + index / 20, abs_tol=1e-8)
                or not math.isclose(frame["next_time_s"], frame["time_s"] + 0.05, abs_tol=1e-8)
            ):
                raise ValueError(f"inconsistent source clock or terminal state: {name}/{index}")
            for key in ("action", "proposed_action"):
                values = policy.get(key)
                if not isinstance(values, list) or len(values) != 7 or not all(
                    type(value) in (int, float) and math.isfinite(value) for value in values
                ):
                    raise ValueError("expected seven finite control values")
            if policy["action"] != [min(1, max(-1, value)) for value in policy["proposed_action"]]:
                raise ValueError("applied control differs from the documented clipping")
        if media:
            import imageio_ffmpeg
            count, seconds = imageio_ffmpeg.count_frames_and_secs(str(root / name / "rollout.mp4"))
            if count != run["steps"] + 1 or not math.isclose(seconds, count / 20, abs_tol=0.055):
                raise ValueError(f"video frame count or source FPS differs: {name}")
        rows.append(run)
    if any(initial != initial_states[0] for initial in initial_states[1:]):
        raise ValueError("paired native initial physical states differ")
    if (
        native_scenes[0]["cam_pos"] == native_scenes[1]["cam_pos"]
        and native_scenes[0]["cam_quat"] == native_scenes[1]["cam_quat"]
    ):
        raise ValueError("official camera perturbation is absent")
    if native_scenes[0]["light_diffuse"] == native_scenes[2]["light_diffuse"]:
        raise ValueError("official light perturbation is absent")
    for run in rows[1:]:
        common = min(rows[0]["steps"], run["steps"])
        for index in range(0, common, 10):
            if rows[0]["frames"][index]["policy"]["noise_sha256"] != run["frames"][index]["policy"]["noise_sha256"]:
                raise ValueError("paired inference noise differs")
    # The prose, no-JavaScript table and comparison controls describe this public
    # case study. Do not silently publish a different outcome under those labels.
    if [(run["task_success"], run["steps"]) for run in rows] != [(True, 77), (False, 220), (True, 87)]:
        raise ValueError("recording differs from this published case-study template")
    return {
        "schema": "robot-reel.libero-plus-site.v1", "plan": plan, "source": source,
        "checks": {
            "identical_initial_physics": True, "native_camera_change": True,
            "native_light_change": True, "matched_inference_noise": True,
        },
        "runs": [{
            **{key: run[key] for key in ("condition", "status", "task_success", "steps", "elapsed_seconds")},
            "actions": [frame["policy"]["action"] for frame in run["frames"]],
        } for run in rows],
    }


METHODS = """# Official LIBERO-Plus subset: same task, changed scene

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
"""


def verify(root, *, media=False):
    root = Path(root)
    manifest = decode(read(root, "manifest.json"))
    expected = {
        *COMMON_FILES, "index.html", "libero_plus.js", "lab.json", "METHODS.md",
        *(f"{condition}/{name}" for condition in CONDITIONS for name in RUN_FILES),
    }
    if manifest.get("schema") != "robot-reel.libero-plus-site.v1" or set(manifest.get("files", {})) != expected:
        raise ValueError("LIBERO-Plus site inventory differs")
    for name in expected:
        content = read(root, name)
        if manifest["files"][name] != {"sha256": digest(content), "bytes": len(content)}:
            raise ValueError(f"LIBERO-Plus site file changed: {name}")
    measured = inspect(root, media=media)
    if measured != decode(read(root, "lab.json")):
        raise ValueError("derived presentation differs from recorded evidence")
    return {"valid": True, "runs": len(measured["runs"]), "checks": measured["checks"]}


def build(recording, output):
    lab = inspect(recording, media=True)
    output = Path(output)
    if output.exists():
        raise ValueError("choose a new publication directory")
    with tempfile.TemporaryDirectory(prefix="robot-reel-plus-") as temporary:
        stage = Path(temporary)
        for name in COMMON_FILES:
            (stage / name).write_bytes(read(recording, name))
        for condition in CONDITIONS:
            (stage / condition).mkdir()
            for name in RUN_FILES:
                (stage / condition / name).write_bytes(read(Path(recording) / condition, name))
        for target, name in (("index.html", "libero_plus.html"), ("libero_plus.js", "libero_plus.js")):
            (stage / target).write_bytes(Path(__file__).with_name(name).read_bytes())
        (stage / "lab.json").write_text(json.dumps(lab, indent=2) + "\n")
        (stage / "METHODS.md").write_text(METHODS)
        (stage / "manifest.json").write_text(json.dumps({
            "schema": "robot-reel.libero-plus-site.v1",
            "files": {
                path.relative_to(stage).as_posix(): {"sha256": digest(path.read_bytes()), "bytes": path.stat().st_size}
                for path in sorted(stage.rglob("*")) if path.is_file()
            },
        }, indent=2) + "\n")
        verify(stage)
        shutil.copytree(stage, output)
    return verify(output)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    plan = sub.add_parser("plan", help="select the reviewed official subset before running a policy")
    plan.add_argument("--repository", type=Path, required=True)
    plan.add_argument("--output", type=Path, required=True)
    site = sub.add_parser("build", help="publish an existing native recording")
    site.add_argument("--recording", type=Path, required=True)
    site.add_argument("--output", type=Path, required=True)
    check = sub.add_parser("verify", help="check source consistency without a GPU")
    check.add_argument("--output", type=Path, required=True)
    check.add_argument("--media", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.command == "plan":
            if args.output.exists():
                raise ValueError("choose a new plan path")
            result = make_plan(args.repository)
            args.output.write_text(json.dumps(result, indent=2) + "\n")
        elif args.command == "build":
            result = build(args.recording, args.output)
        else:
            result = verify(args.output, media=args.media)
    except (ValueError, OSError, KeyError) as error:
        parser.exit(2, f"LIBERO-Plus: {error}\n")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
