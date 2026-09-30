"""Map the recorded factory twin run onto named 3D animation channels.

This module has no Blender dependency. The Blender builder turns these channels
into constant-interpolated keyframes; the Blender check re-evaluates the saved
project at every frame and compares it with the same channels and with the
original samples; unit tests check the channels against the trace directly.

Frame ``k + 1`` shows sample ``k`` (5 s of plant time per frame, 30 fps).
"""
from __future__ import annotations

import math

FPS = 30
TURNS_PER_CYCLE = 12
STATE_COLORS = (
    (0.95, 0.72, 0.18),  # idle / starved: amber
    (0.10, 0.90, 0.36),  # busy: green
    (1.00, 0.45, 0.05),  # blocked: orange
    (1.00, 0.04, 0.04),  # failed: red
    (0.10, 0.42, 1.00),  # maintenance: blue
    (0.55, 0.58, 0.64),  # break: grey
    (0.62, 0.32, 1.00),  # tip dress: violet
)
AMR_COLORS = (
    (0.30, 0.75, 1.00), (0.10, 0.90, 0.36), (0.95, 0.72, 0.18), (0.95, 0.72, 0.18), (0.30, 0.75, 1.00),
)
TWIN_CYAN = (0.0, 0.85, 1.0)
EV_COLORS = {"off": (0.12, 0.14, 0.16), "full": (0.10, 0.90, 0.36), "capped": (1.00, 0.55, 0.05)}
GAUGE_HEIGHT_M = 6.0  # full-scale wear = 1.0
IMPORT_SCALE_M_PER_KW = 0.02  # 1 MW column = 20 m
SUN_STRENGTH = 4.2
BUSY, FAILED, MAINT = 1, 3, 4
WELD_ROBOT_YAW = (-math.pi / 2, math.pi / 2)  # robot A faces south, robot B north, toward the positioner


def slot_position(buffer, index):
    """Crate slot centre: columns run east, rows step away from the line centreline."""
    columns, pitch = buffer["columns"], buffer["pitch"]
    x0, y0 = buffer["origin"]
    direction = -1 if y0 < 0 else 1
    return [x0 + pitch * (index % columns), y0 + direction * pitch * (index // columns)]


def weld_joints(progress, arm):
    """Six stylized joint angles (radians) for weld robot ``arm`` at cycle progress 0..1."""
    phase = 2 * math.pi * progress + (math.pi if arm else 0.0)
    sign = -1 if arm else 1
    return [
        sign * (0.55 * math.sin(phase)),
        -0.35 + 0.22 * math.sin(2 * phase),
        0.55 + 0.25 * math.cos(2 * phase),
        0.8 * math.sin(3 * phase),
        -0.6 + 0.3 * math.cos(phase),
        4 * phase,
    ]


def _const(value, n):
    return [value] * n


def channels(lab, mode="closed"):
    """Return {(owner, data_path, index): [value per frame]} and object metadata."""
    run = lab["runs"][mode]
    plant, twin = run["plant"], run["twin"]
    lay = lab["layout"]
    n = len(plant["good"])
    station_ids = [s["id"] for s in lab["config"]["stations"]]
    buffer_ids = list(lab["config"]["buffers"])
    out = {}

    def put(owner, path, index, values):
        if len(values) != n:
            raise ValueError(f"Channel length mismatch: {owner} {path}")
        out[(owner, path, index)] = [float(v) for v in values]

    # Station beacons (plant truth) and twin rings (the twin's mirrored state).
    for j, sid in enumerate(station_ids):
        for c in range(3):
            put(f"Station {sid} / beacon", "color", c, [STATE_COLORS[row[j]][c] for row in plant["state"]])
            put(f"Twin {sid} / ring", "color", c, [
                (TWIN_CYAN if row is None else STATE_COLORS[row[j]])[c] for row in twin["state"]])
    # CNC spindles and chamber lights.
    for j, sid in ((1, "cnc1"), (2, "cnc2")):
        put(f"Station {sid} / spindle", "rotation_euler", 2, [
            2 * math.pi * TURNS_PER_CYCLE * row[j] for row in plant["progress"]])
        for c in range(3):
            put(f"Station {sid} / chamber light", "color", c, [
                (0.55, 0.85, 1.0)[c] if row[j] == BUSY else (0.03, 0.03, 0.035)[c] for row in plant["state"]])
    # Weld robots.
    weld = station_ids.index("weld")
    for arm in (0, 1):
        for joint in range(6):
            axis = 2 if joint in (0, 5) else 1
            offset = WELD_ROBOT_YAW[arm] if joint == 0 else 0.0
            put(f"Weld robot {'AB'[arm]} / J{joint + 1}", "rotation_euler", axis, [
                offset + (weld_joints(row[weld], arm)[joint] if state[weld] == BUSY else weld_joints(0.0, arm)[joint])
                for row, state in zip(plant["progress"], plant["state"])])
    put("Station weld / arc", "scale", 0, [1.0 if s[weld] == BUSY and 0.1 < p[weld] < 0.9 else 0.0
                                          for s, p in zip(plant["state"], plant["progress"])])
    for i in (1, 2):
        put("Station weld / arc", "scale", i, out[("Station weld / arc", "scale", 0)])
    # Buffers: one crate per slot, shown by scale.
    for b, name in enumerate(buffer_ids):
        capacity = lab["config"]["buffers"][name]
        for i in range(capacity):
            values = [1.0 if row[b] > i else 0.0 for row in plant["buffers"]]
            for axis in range(3):
                put(f"Buffer {name} / slot {i + 1:02d}", "scale", axis, values)
    # AMRs: plant pose, payload, status; twin ghost from the twin's last received packet.
    homes = lay["amr"]["homes"]
    for i in range(len(homes)):
        put(f"AMR {i + 1}", "location", 0, [row[i][0] for row in plant["amr"]])
        put(f"AMR {i + 1}", "location", 1, [row[i][1] for row in plant["amr"]])
        put(f"AMR {i + 1}", "rotation_euler", 2, [row[i][2] for row in plant["amr"]])
        payload = [1.0 if row[i][4] > 0 else 0.0 for row in plant["amr"]]
        for axis in range(3):
            put(f"AMR {i + 1} / payload", "scale", axis, payload)
        for c in range(3):
            put(f"AMR {i + 1} / status", "color", c, [AMR_COLORS[row[i][3]][c] for row in plant["amr"]])
        put(f"Twin ghost AMR {i + 1}", "location", 0, [homes[i][0] if row is None else row[i][0] for row in twin["amr"]])
        put(f"Twin ghost AMR {i + 1}", "location", 1, [homes[i][1] if row is None else row[i][1] for row in twin["amr"]])
    # Twin overlay: CNC 2 wear, truth vs estimate with a two-sigma band.
    put("Twin overlay / wear truth", "scale", 2, [max(1e-3, w) for w in plant["wear"]])
    put("Twin overlay / wear estimate", "scale", 2, [max(1e-3, w) for w in twin["wear"]])
    put("Twin overlay / wear band", "scale", 2, [max(1e-3, 4 * sd) for sd in twin["wear_sd"]])
    put("Twin overlay / wear band", "location", 2, [
        (GAUGE_BASE_Z + GAUGE_HEIGHT_M * (w - 2 * sd)) for w, sd in zip(twin["wear"], twin["wear_sd"])])
    request = [1.0 if pm else 0.0 for pm in twin["pm"]]
    for axis in range(3):
        put("Twin overlay / service request", "scale", axis, request)
    # Campus energy: grid import column, colored by the running billing-interval mean.
    limit = lab["config"]["demand_limit_kw"]
    put("Twin overlay / grid import", "scale", 2, [max(1e-3, kw * IMPORT_SCALE_M_PER_KW) for kw in plant["net_kw"]])
    for c in range(3):
        put("Twin overlay / grid import", "color", c, [
            ((1.0, 0.1, 0.05) if kw > limit else TWIN_CYAN)[c] for kw in plant["interval_kw"]])
    for i in range(len(lay["parking"]["chargers"])):
        for c in range(3):
            put(f"EV charger {i + 1} / ring", "color", c, [
                EV_COLORS["off" if ev <= 0 else ("full" if cap >= 1 else "capped")][c]
                for ev, cap in zip(plant["ev_kw"], plant["ev_cap"])])
    for i in range(4):
        for c in range(3):
            put(f"Rooftop unit {i + 1} / status", "color", c, [
                ((0.2, 0.65, 1.0) if sp <= 24.0 else (1.0, 0.55, 0.05))[c] for sp in plant["setpoint_c"]])
    # Cloud passage dims the sun; the twin only sees the PV meter.
    put("light:Sun", "energy", 0, [SUN_STRENGTH * (1 - 0.8 * c) for c in plant["cloud"]])
    # Custom properties for DCC users.
    put("Digital twin", '["sim_time_s"]', 0, [5.0 * k for k in range(n)])
    put("Digital twin", '["good_units"]', 0, plant["good"])
    put("Digital twin", '["wear_truth"]', 0, plant["wear"])
    put("Digital twin", '["wear_estimate"]', 0, twin["wear"])
    put("Digital twin", '["grid_import_kw"]', 0, plant["net_kw"])
    return out


GAUGE_BASE_Z = 5.0
GAUGE_POSITION = (-44.0, -11.5)


def static_positions(lab):
    """Object locations that do not animate but are checked against the layout."""
    lay = lab["layout"]
    result = {}
    for name, buffer in lay["buffers"].items():
        for i in range(lab["config"]["buffers"][name]):
            result[f"Buffer {name} / slot {i + 1:02d}"] = slot_position(buffer, i)
    for station in lay["stations"]:
        result[f"Station {station['id']}"] = station["position"]
    return result
