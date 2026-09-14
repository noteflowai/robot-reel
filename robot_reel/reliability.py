"""Say what a failure was, and whether running it again gives the same answer.

A success rate answers neither question. Fourteen of thirty recorded trials end at
the step limit, and that label alone does not distinguish a policy that froze
from one that was still moving when the budget ran out. This describes the
recording; selecting an effective intervention requires a controlled experiment.

Reproducibility is the other half. The paired design attributes an outcome flip
to a condition, which only holds if the same seed and condition give the same
answer twice. That is an empirical question about a particular machine and stack,
not something a plan can assert about itself, so it is measured rather than
claimed.

Nothing here re-runs a policy. Both measurements read recorded traces.
"""

from __future__ import annotations

import math

SCHEMA = "robot-reel-reliability-1"

# One millimetre of end-effector travel over the final tenth of recorded frames.
# This descriptive threshold does not distinguish slow progress from a stall,
# nor establish that a moving arm would succeed with a larger action budget.
STALL_METRES = 1e-3


def _positions(trace):
    """End-effector positions, in order."""
    return [frame["state"][:3] for frame in trace["frames"]]


def _travel(points):
    return sum(math.dist(points[i], points[i + 1]) for i in range(len(points) - 1))


def classify_run(trace, *, stall_metres=STALL_METRES):
    """Name what happened in one recorded trial, with the numbers behind it.

    A step-limit failure is split by whether the arm was still moving when the
    budget ran out. `terminated` is reported as the environment gave it: an
    early termination is a different event from exhausting the budget.
    """
    points = _positions(trace)
    if not math.isfinite(stall_metres) or stall_metres <= 0:
        raise ValueError("stall_metres must be finite and positive")
    if len(points) < 2:
        raise ValueError("A trial needs at least two recorded frames")
    outcome = trace["result"]["outcome"]
    tail = points[-max(2, len(points) // 10) :]
    tail_travel = _travel(tail)
    travel = _travel(points)
    displacement = math.dist(points[0], points[-1])
    if outcome == "success":
        kind = "success"
    elif outcome == "step_limit":
        kind = "step_limit_stalled" if tail_travel < stall_metres else "step_limit_in_motion"
    else:
        kind = outcome
    return {
        "kind": kind,
        "outcome": outcome,
        "frames": len(points),
        "tail_travel_m": tail_travel,
        "travel_m": travel,
        "displacement_m": displacement,
        # High when the arm covered a lot of ground to end up near where it
        # started, which is what repeated re-approaches look like. Descriptive
        # only: across the recorded collection failures wander more typically
        # (median 3.17 against 1.92) but the ranges overlap, so this does not
        # decide whether a run failed.
        "wander_ratio": travel / displacement if displacement > 0 else None,
    }


def taxonomy(traces):
    """Group a whole collection by what its failures actually were."""
    runs = {name: classify_run(trace) for name, trace in traces.items()}
    kinds = {}
    for name, run in sorted(runs.items()):
        kinds.setdefault(run["kind"], []).append(name)
    return {
        "trials": len(runs),
        "kinds": {kind: sorted(names) for kind, names in sorted(kinds.items())},
        "counts": {kind: len(names) for kind, names in sorted(kinds.items())},
        "stall_threshold_m": STALL_METRES,
        "runs": runs,
    }


def _input_frames(frames, action_steps):
    """Indices of the frames a policy call actually consumed.

    The recorder samples every simulator step but calls the policy once every
    `action_steps`, so most recorded frames never reach it. Only a difference on
    a consumed frame can change what the policy does next.
    """
    return {
        index
        for index, frame in enumerate(frames)
        if index % action_steps == 0 and frame.get("action") is not None
    }


def compare_run(reference, repeat, action_steps):
    """Compare one trial against its repeat, from outcome down to pixels.

    Reported as separate levels because they are separate claims. Agreeing
    outcomes are what the paired comparison rests on; identical physics is a
    stronger statement; identical renders on consumed frames is stronger again.
    """
    a, b = reference["frames"], repeat["frames"]
    action_steps = int(action_steps)
    if action_steps < 1:
        raise ValueError("action_steps must be positive")
    inputs_a, inputs_b = _input_frames(a, action_steps), _input_frames(b, action_steps)
    consumed = inputs_a | inputs_b
    shared = range(min(len(a), len(b)))
    render = {"input_frames": [0, 0], "recorded_frames": [0, 0]}
    for index in shared:
        key = "input_frames" if index in consumed else "recorded_frames"
        render[key][1] += 1
        hashes_a, hashes_b = a[index].get("raw_camera_sha256"), b[index].get("raw_camera_sha256")
        complete = all(
            isinstance(hashes, dict)
            and all(isinstance(hashes.get(camera), str) and hashes[camera]
                    for camera in ("main", "wrist"))
            for hashes in (hashes_a, hashes_b)
        )
        render[key][0] += complete and hashes_a == hashes_b
    return {
        "same_outcome": reference["result"]["outcome"] == repeat["result"]["outcome"],
        "same_action_count": reference["result"]["actions"] == repeat["result"]["actions"],
        "same_frame_count": len(a) == len(b),
        "identical_states": [frame["state"] for frame in a] == [frame["state"] for frame in b],
        "identical_actions": [frame.get("action") for frame in a] == [frame.get("action") for frame in b],
        "identical_input_renders": bool(consumed) and inputs_a == inputs_b
        and render["input_frames"][0] == len(consumed),
        "input_renders": {"identical": render["input_frames"][0], "compared": render["input_frames"][1]},
        "recorded_renders": {"identical": render["recorded_frames"][0], "compared": render["recorded_frames"][1]},
    }


def reproducibility(reference_traces, repeat_traces, action_steps):
    """Measure whether a repeat of the same plan gives the same answers.

    Both collections must cover exactly the same trials. A repeat that quietly
    omits a trial would otherwise raise every agreement rate it reports.
    """
    if set(reference_traces) != set(repeat_traces):
        raise ValueError("Reproducibility needs the same trials in both collections")
    if not reference_traces:
        raise ValueError("Reproducibility needs at least one trial")
    trials = {
        name: compare_run(reference_traces[name], repeat_traces[name], action_steps)
        for name in sorted(reference_traces)
    }
    total = len(trials)

    def agreed(key):
        return sum(bool(trial[key]) for trial in trials.values())

    renders = {
        level: {
            "identical": sum(trial[level]["identical"] for trial in trials.values()),
            "compared": sum(trial[level]["compared"] for trial in trials.values()),
        }
        for level in ("input_renders", "recorded_renders")
    }
    return {
        "schema": SCHEMA,
        "trials": total,
        "action_steps": int(action_steps),
        "levels": {
            "same_outcome": agreed("same_outcome"),
            "same_action_count": agreed("same_action_count"),
            "identical_states": agreed("identical_states"),
            "identical_actions": agreed("identical_actions"),
            "identical_input_renders": agreed("identical_input_renders"),
        },
        "frames": renders,
        "differing_trials": sorted(
            name
            for name, trial in trials.items()
            if not (
                trial["same_outcome"]
                and trial["same_action_count"]
                and trial["identical_states"]
                and trial["identical_actions"]
                and trial["identical_input_renders"]
            )
        ),
        "scope": (
            "One repeat of one plan on one machine. Agreement here does not "
            "establish determinism on other hardware, drivers or stack versions, "
            "and a render difference on a frame no policy call consumed cannot "
            "change an outcome but does not prove rendering is deterministic."
        ),
        "runs": trials,
    }
