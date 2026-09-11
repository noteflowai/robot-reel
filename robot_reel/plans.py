"""Portable shot plans. Loading a plan never imports a simulator."""
import json
import math


def validate_plan(plan):
    if not isinstance(plan, dict) or set(plan) != {"version", "shots"} or type(plan["version"]) is not int or plan["version"] != 1:
        raise ValueError("Plan must contain version: 1 and shots")
    shots = plan["shots"]
    if not isinstance(shots, list) or len(shots) != 4:
        raise ValueError("A plan must have exactly four shots")
    for index, shot in enumerate(shots):
        if not isinstance(shot, dict):
            raise ValueError("Each shot must be an object")
        label = shot.get("label")
        if not isinstance(label, str) or not label.strip() or len(label) > 64:
            raise ValueError("Each label must contain 1–64 characters")
        if index == 3:
            if set(shot) != {"label", "home"} or shot["home"] is not True:
                raise ValueError("The fourth shot must use home: true")
        else:
            if set(shot) != {"label", "targets"} or not isinstance(shot["targets"], dict) or not shot["targets"]:
                raise ValueError("The first three shots require nonempty targets")
            for name, value in shot["targets"].items():
                if not isinstance(name, str) or not name:
                    raise ValueError("Joint names must be nonempty strings")
                if type(value) not in (int, float) or not math.isfinite(value):
                    raise ValueError("Joint targets must be finite numbers in radians")
    return plan


def load_plan(path):
    return validate_plan(json.loads(path.read_text()))


DEFAULT_PLAN = {
    "version": 1,
    "shots": [
        {"label": "Find your angle.", "targets": {"Rotation": -0.8}},
        {"label": "Explore the other side.", "targets": {"Rotation": 0.8}},
        {"label": "A new perspective.", "targets": {"Wrist_Roll": 0.6, "Jaw": 0.5}},
        {"label": "Back to home.", "home": True},
    ],
}
