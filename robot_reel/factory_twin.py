"""Closed-loop factory and campus digital twin: simulate, verify and export.

A deterministic plant model (six-station production line, AMR logistics, hall
thermal behavior and campus energy) emits noisy, lossy, delayed telemetry. The
digital twin receives only that telemetry. It mirrors the line, estimates hidden
CNC spindle wear with an extended Kalman filter, forecasts the billed demand,
plans maintenance by forward-simulating its own model of the line, and sends
commands back to the plant after an actuation delay.

Every run is paired: in ``shadow`` mode the twin observes and advises but no
command reaches the plant; in ``closed`` mode the same twin's commands are
actuated. Both modes share every disturbance through a counter-based random
generator, so the only difference between a pair is the loop closure.

The plant is a simulation. Its parameters were chosen to include one spindle
degradation, one cloud passage over the solar canopy, a scheduled EV charging
block and a lunch break inside a three-hour window. It is not a model of a
specific real factory and none of its numbers are measured.

Only the Python standard library is used, and only integer and IEEE-754
arithmetic operations (no transcendental functions) influence the simulation,
so a verifier re-executes every run bit-for-bit.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
from pathlib import Path
import tempfile
import zipfile

SCHEMA = "robot-reel-factory-twin-1"
SAMPLE_S = 5
DURATION_S = 3 * 3600
START_CLOCK_S = 10 * 3600
SAMPLES = DURATION_S // SAMPLE_S + 1
FEATURED_SEED = 10
SEEDS = tuple(range(1, 13))
MODES = ("shadow", "closed")

# Production line ---------------------------------------------------------------
IDLE, BUSY, BLOCKED, FAILED, MAINT, BREAK, DRESS = range(7)
STATE_NAMES = ("idle", "busy", "blocked", "failed", "maintenance", "break", "tip-dress")
STATIONS = (
    # id, label, nominal cycle s, input buffer, output buffer, busy kW, idle kW
    ("kitting", "Kitting", 38.0, None, "kit", 6.0, 2.0),
    ("cnc1", "CNC 1", 80.0, "kit", "machined", 38.0, 9.0),
    ("cnc2", "CNC 2", 80.0, "kit", "machined", 38.0, 9.0),
    ("weld", "Robotic weld cell", 42.0, "machined", "welded", 55.0, 8.0),
    ("assembly", "Assembly", 41.0, "welded", "assembled", 12.0, 4.0),
    ("inspect", "Inspection", 34.0, "assembled", "outbound", 5.0, 3.0),
)
SPEC = {row[0]: row for row in STATIONS}
STATION_IDS = tuple(row[0] for row in STATIONS)
ORDER = ("inspect", "assembly", "weld", "cnc1", "cnc2", "kitting")  # downstream first
BUFFERS = {"kit": 10, "machined": 10, "welded": 6, "assembled": 6, "outbound": 24}
BUFFER_IDS = tuple(BUFFERS)
BREAK_WINDOW = (12 * 3600, 12 * 3600 + 20 * 60)  # assembly and inspection lunch break
BREAK_STATIONS = ("assembly", "inspect")
DRESS_EVERY, DRESS_S = 40, 90.0  # weld tip dressing
WEAR_SLOWDOWN = 0.5  # CNC cycle multiplier 1 + 0.5 w
DERATE_SPEED, DERATE_WEAR = 0.8, 0.45
RESET_WEAR = 0.05
PM_S, REPAIR_S = 900.0, 2700.0
BASE_DEFECT, WEAR_DEFECT = 0.006, 0.9  # p = 0.006 + 0.9 max(0, w - 0.5)^2
CNC1_WEAR = 0.18

# Logistics ---------------------------------------------------------------------
AMR_COUNT, BATCH, LOAD_S = 3, 8, 30.0
AMR_PARKED, AMR_OUT, AMR_LOADING, AMR_UNLOADING, AMR_RETURN = range(5)
AMR_STATES = ("parked", "to-warehouse", "loading", "unloading", "returning")

# Energy ------------------------------------------------------------------------
PV_KWP = 520.0
SOLAR_NOON_S, SOLAR_HALF_WIDTH_S = 12 * 3600 + 45 * 60, 6.5 * 3600
EV_WINDOW = (11 * 3600 + 30 * 60, 12 * 3600 + 45 * 60)
EV_KW = 8 * 22.0
DEMAND_LIMIT_KW = 520.0
BILLING_S = 900
DEFAULT_SETPOINT = 24.0
COMFORT_MAX_C = 27.0
KP_COOL = 150.0  # kW thermal per K
Q_COOL_MAX = 900.0
AUX_HALL_KW, COMPRESSOR_KW = 45.0, 30.0
OFFICE_KW, OFFICE_SUN_KW, WAREHOUSE_KW, IT_KW = 110.0, 20.0, 40.0, 35.0
AMR_KW = 1.5

# Twin ---------------------------------------------------------------------------
NOMINAL_WEAR_RATE = 1 / (5.0 * 3600)  # per busy second
THRESHOLD_SD = 0.04
VIB_BASE, VIB_LOAD, VIB_WEAR, VIB_SD = 1.8, 0.6, 5.5, 0.35
PLAN_EVERY_S, PLAN_DT, PLAN_HORIZON_S = 300, 15.0, 90 * 60
PLAN_OFFSETS = (None, 0, 600, 1200, 1800, 2700, 3600)
PLAN_TRIGGER_RUL_MIN = 150.0
PLAN_TIE_UNITS = 0.25
LIFE_COST_UNITS = 40.0  # a spindle rebuild valued as 40 good parts; discarded life is charged
FAILURE_COST_UNITS = 25.0  # collateral damage beyond the simulated repair downtime
DERATE_SWITCH_UNITS = 1.5  # hysteresis: a feed change must be worth this much
ENERGY_EVERY_S = 60
ESCALATE_MARGIN_KW, RELEASE_MARGIN_KW, RELEASE_CHECKS = 15.0, 70.0, 5
LEVELS = (
    {"setpoint_c": 24.0, "ev_cap": 1.0, "label": "normal operation"},
    {"setpoint_c": 25.0, "ev_cap": 1.0, "label": "hall setpoint +1 °C"},
    {"setpoint_c": 25.0, "ev_cap": 0.5, "label": "setpoint +1 °C, EV chargers at 50%"},
    {"setpoint_c": 26.0, "ev_cap": 0.5, "label": "setpoint +2 °C, EV chargers at 50%"},
)

# Counter-based random numbers: common disturbances in both loop modes -------------
MASK = (1 << 64) - 1
STREAMS = {name: i + 1 for i, name in enumerate((
    "params", "vib1", "vib2", "temp1", "temp2", "hall", "outdoor", "load", "pv", "chiller",
    "ev", "drop", "inspect", "flicker"))}
SQRT2 = 1.4142135623730951


def _mix(z):
    z = (z + 0x9E3779B97F4A7C15) & MASK
    z = ((z ^ (z >> 30)) * 0xBF58476D1CE4E5B9) & MASK
    z = ((z ^ (z >> 27)) * 0x94D049BB133111EB) & MASK
    return z ^ (z >> 31)


_KEYS = {}


def uniform(seed, stream, index):
    key = _KEYS.get((seed, stream))
    if key is None:
        key = _KEYS[(seed, stream)] = _mix(_mix(seed) ^ STREAMS[stream])
    return (_mix(key ^ index) >> 11) * 2.0 ** -53


def normal(seed, stream, index):
    """Irwin–Hall approximation (six uniforms): unit variance, integer-exact."""
    total = 0.0
    for j in range(6):
        total += uniform(seed, stream, index * 8 + j)
    return (total - 3.0) * SQRT2


def plant_parameters(seed):
    u = [uniform(seed, "params", i) for i in range(10)]
    return {
        "seed": seed,
        "cnc2_initial_wear": 0.50 + 0.08 * u[0],
        "cnc2_wear_rate_per_busy_s": NOMINAL_WEAR_RATE * (0.9 + 0.2 * u[1]),
        "cnc2_failure_threshold": 0.96 + 0.08 * u[2],
        "hall_ua_kw_k": 12.0 * (0.95 + 0.1 * u[3]),
        "hall_capacity_kj_k": 250000.0 * (0.95 + 0.1 * u[4]),
        "cloud_start_clock_s": 11 * 3600 + 10 * 60 + 1200.0 * u[5],
        "cloud_duration_s": 35 * 60 + 1200.0 * u[6],
        "cloud_depth": 0.6 + 0.2 * u[7],
        "amr_speed_m_s": 1.1 + 0.2 * u[8],
        "outdoor_start_c": 28.5 + u[9],
    }


def twin_parameters():
    return {"cnc2_initial_wear": 0.45, "cnc2_wear_rate_per_busy_s": NOMINAL_WEAR_RATE,
            "cnc2_failure_threshold": 1.0, "hall_ua_kw_k": 12.0, "hall_capacity_kj_k": 250000.0}


# Site layout shared by the browser viewer and the Blender build ------------------
def _trees():
    trees, index = [], 0
    for x in range(-122, 126, 9):
        for y in (-84, 84):
            index += 1
            if y == 84 and -60 < x < 16:
                continue  # office forecourt stays open
            trees.append([x + 3 * (uniform(99, "params", index) - .5), y + 2 * (uniform(98, "params", index) - .5),
                          0.8 + 0.5 * uniform(97, "params", index)])
    for y in range(-72, 80, 10):
        for x in (-124, 124):
            index += 1
            if x == 124 and -20 < y < 8:
                continue  # main gate
            trees.append([x + 2 * (uniform(99, "params", index) - .5), y + 3 * (uniform(98, "params", index) - .5),
                          0.8 + 0.5 * uniform(97, "params", index)])
    for i in range(10):
        index += 1
        trees.append([-60 + 9.5 * i + 2 * uniform(96, "params", index), 72 + 3 * uniform(95, "params", index),
                      0.7 + 0.4 * uniform(97, "params", index)])
    return [[round(x, 3), round(y, 3), round(s, 3)] for x, y, s in trees]


def layout():
    homes = [[26.0, -9.0], [26.0, -12.5], [26.0, -16.0]]
    corridor = [[22.0, -5.0], [34.0, -5.0], [40.0, -5.0], [40.0, 12.0], [52.0, 12.0], [58.0, 12.0]]
    return {
        "units": "metres; x east, y north, z up; origin at the hall's east–west axis",
        "site": {"x": [-130.0, 130.0], "y": [-90.0, 90.0]},
        "buildings": [
            {"id": "factory", "label": "Assembly hall", "kind": "hall", "center": [-20.0, 0.0], "size": [100.0, 44.0], "height": 12.0},
            {"id": "warehouse", "label": "Finished-goods warehouse", "kind": "warehouse", "center": [72.0, 12.0], "size": [40.0, 36.0], "height": 14.0},
            {"id": "office", "label": "Offices & twin operations center", "kind": "office", "center": [-22.0, 56.0], "size": [54.0, 16.0], "height": 16.0},
            {"id": "energy", "label": "Energy center & substation", "kind": "utility", "center": [-98.0, 40.0], "size": [22.0, 16.0], "height": 8.0},
            {"id": "gate", "label": "Gatehouse", "kind": "small", "center": [112.0, -25.0], "size": [8.0, 6.0], "height": 4.0},
        ],
        "stations": [
            {"id": "kitting", "position": [-60.0, 0.0], "size": [6.0, 4.0, 2.0]},
            {"id": "cnc1", "position": [-44.0, 7.0], "size": [6.0, 4.0, 3.0]},
            {"id": "cnc2", "position": [-44.0, -7.0], "size": [6.0, 4.0, 3.0]},
            {"id": "weld", "position": [-26.0, 0.0], "size": [9.0, 8.0, 3.5]},
            {"id": "assembly", "position": [-8.0, 0.0], "size": [8.0, 4.0, 1.2]},
            {"id": "inspect", "position": [8.0, 0.0], "size": [6.0, 4.0, 2.5]},
        ],
        "buffers": {
            "kit": {"origin": [-53.5, -1.3], "columns": 5, "pitch": 1.3},
            "machined": {"origin": [-37.5, -1.3], "columns": 5, "pitch": 1.3},
            "welded": {"origin": [-19.0, -1.3], "columns": 3, "pitch": 1.3},
            "assembled": {"origin": [-0.5, -1.3], "columns": 3, "pitch": 1.3},
            "outbound": {"origin": [14.0, -3.0], "columns": 6, "pitch": 1.3},
        },
        "amr": {"homes": homes, "corridor": corridor, "batch": BATCH},
        "roads": [
            {"center": [0.0, -34.0], "size": [250.0, 9.0]}, {"center": [0.0, 34.0], "size": [250.0, 9.0]},
            {"center": [-80.0, 0.0], "size": [9.0, 77.0]}, {"center": [37.0, 0.0], "size": [7.0, 77.0]},
            {"center": [104.0, -14.0], "size": [38.0, 10.0]}, {"center": [96.0, 12.0], "size": [8.0, 36.0]},
        ],
        "parking": {"center": [75.0, -58.0], "size": [64.0, 30.0], "canopy_rows": 3, "pv_kwp": PV_KWP,
                    "chargers": [[50.0 + 7.0 * i, -44.5] for i in range(8)]},
        "utilities": {
            "chillers": [[-98.0, -20.0], [-98.0, -8.0]], "cooling_towers": [[-110.0, -20.0], [-110.0, -8.0]],
            "transformer": [-112.0, 40.0], "water_tower": [-108.0, -62.0], "twin_servers": [-4.0, 56.0],
        },
        "trees": _trees(),
    }


def _route(home, corridor):
    points = [home, *corridor]
    lengths = [0.0]
    for a, b in zip(points, points[1:]):
        lengths.append(lengths[-1] + math.sqrt((b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2))
    return points, lengths


def route_pose(points, lengths, s, reverse=False):
    """Position and heading (radians, atan2 only for display) at distance s along a route."""
    s = max(0.0, min(lengths[-1], s))
    for i in range(1, len(points)):
        if s <= lengths[i] or i == len(points) - 1:
            a, b = points[i - 1], points[i]
            span = lengths[i] - lengths[i - 1]
            f = 0.0 if span == 0 else (s - lengths[i - 1]) / span
            dx, dy = b[0] - a[0], b[1] - a[1]
            if reverse:
                dx, dy = -dx, -dy
            return a[0] + f * (b[0] - a[0]), a[1] + f * (b[1] - a[1]), math.atan2(dy, dx)


# Line model used by both the plant (dt=1 s, random inspection) and the twin -------
class Line:
    def __init__(self, wear, wear_rate, threshold):
        self.buffers = {name: [] for name in BUFFER_IDS}
        self.stations = {sid: {"state": IDLE, "rem": 0.0, "part": None, "resume": IDLE} for sid in STATION_IDS}
        self.wear, self.wear_rate, self.threshold = wear, wear_rate, threshold
        self.derate = False
        self.pm_request = False
        self.weld_count = 0
        self.good = 0.0
        self.scrap = 0.0
        self.inspected = 0
        self.failures = 0
        self.maintenances = 0
        self.outbound_unlimited = False

    def clone(self):
        other = copy.copy(self)
        other.buffers = {k: list(v) for k, v in self.buffers.items()}
        other.stations = {k: dict(v) for k, v in self.stations.items()}
        return other

    def cycle(self, sid):
        base = SPEC[sid][2]
        if sid == "cnc1":
            return base * (1 + WEAR_SLOWDOWN * CNC1_WEAR)
        if sid == "cnc2":
            return base * (1 + WEAR_SLOWDOWN * self.wear) / (DERATE_SPEED if self.derate else 1.0)
        return base

    def _push(self, sid, part, inspect):
        out = SPEC[sid][4]
        if sid == "inspect":
            defect = part if inspect is None else float(inspect(self.inspected, part))
            if not self.outbound_unlimited and len(self.buffers["outbound"]) >= BUFFERS["outbound"] and defect < 1:
                return False
            self.inspected += 1
            self.scrap += defect
            self.good += 1 - defect
            if defect < 1 and not self.outbound_unlimited:
                self.buffers["outbound"].append(0.0)
            return True
        if len(self.buffers[out]) >= BUFFERS[out]:
            return False
        self.buffers[out].append(part)
        return True

    def step(self, dt, clock, inspect=None):
        on_break = BREAK_WINDOW[0] <= clock < BREAK_WINDOW[1]
        for sid in ORDER:
            self._station(sid, dt, on_break, inspect)

    def _station(self, sid, dt, on_break, inspect):
        s = self.stations[sid]
        state = s["state"]
        if state in (FAILED, MAINT, DRESS):
            s["rem"] -= dt
            if s["rem"] > 0:
                return
            if state in (FAILED, MAINT):
                self.wear = RESET_WEAR
                self.derate = False
                if state == MAINT:
                    self.pm_request = False
            s["state"], s["rem"] = IDLE, 0.0
            return
        if sid in BREAK_STATIONS:
            if on_break:
                if state != BREAK:
                    s["resume"], s["state"] = state, BREAK
                return
            if state == BREAK:
                state = s["state"] = s["resume"]
        over = 0.0
        if state == BUSY:
            s["rem"] -= dt
            if sid == "cnc2":
                self.wear += self.wear_rate * dt * (DERATE_WEAR if self.derate else 1.0)
                if self.wear >= self.threshold:
                    s["state"], s["rem"], s["part"] = FAILED, REPAIR_S, None
                    self.failures += 1
                    self.scrap += 1
                    return
            if s["rem"] > 0:
                return
            over = -s["rem"]  # carry the overshoot so coarse steps keep the mean cycle time
            state = s["state"] = BLOCKED
            if sid == "weld":
                self.weld_count += 1
        if state == BLOCKED:
            if not self._push(sid, s["part"], inspect):
                return
            s["part"], s["state"] = None, IDLE
            if sid == "weld" and self.weld_count % DRESS_EVERY == 0:
                s["state"], s["rem"] = DRESS, DRESS_S
                return
        if sid == "cnc2" and self.pm_request:
            s["state"], s["rem"] = MAINT, PM_S
            self.maintenances += 1
            return
        source = SPEC[sid][3]
        if source is None:
            part = 0.0
        elif self.buffers[source]:
            part = self.buffers[source].pop(0)
        else:
            return
        if sid == "cnc2":
            excess = max(0.0, self.wear - 0.5)
            part = BASE_DEFECT + WEAR_DEFECT * excess * excess
        elif sid == "cnc1":
            part = BASE_DEFECT
        s["state"], s["rem"], s["part"] = BUSY, self.cycle(sid) - over, part

    def progress(self, sid):
        s = self.stations[sid]
        if s["state"] not in (BUSY, BREAK) or s["part"] is None:
            return 0.0
        return max(0.0, min(1.0, 1 - s["rem"] / self.cycle(sid)))


# Plant: line + AMRs + hall thermal + campus energy + telemetry -----------------------
def clear_sky(clock):
    x = (clock - SOLAR_NOON_S) / SOLAR_HALF_WIDTH_S
    return max(0.0, 1 - x * x)


def cloud_cover(p, clock):
    start, duration, depth = p["cloud_start_clock_s"], p["cloud_duration_s"], p["cloud_depth"]
    ramp = 300.0
    if clock <= start or clock >= start + duration:
        return 0.0
    edge = min(clock - start, start + duration - clock)
    return depth * min(1.0, edge / ramp)


def outdoor_c(p, clock):
    return p["outdoor_start_c"] + 4.0 * (clock - START_CLOCK_S) / DURATION_S


def cop(t_out):
    return 5.2 - 0.08 * (t_out - 25.0)


def station_kw(sid, state):
    if state in (BUSY,):
        return SPEC[sid][5]
    if state in (FAILED, MAINT):
        return 1.0
    return SPEC[sid][6]


class Plant:
    def __init__(self, seed):
        self.seed = seed
        self.p = plant_parameters(seed)
        p = self.p
        self.line = Line(p["cnc2_initial_wear"], p["cnc2_wear_rate_per_busy_s"], p["cnc2_failure_threshold"])
        self.t = 0
        self.hall_c = 24.2
        self.spindle_c = [36.0, 38.0]
        self.setpoint = DEFAULT_SETPOINT
        self.ev_cap = 1.0
        self.amr_routes = [_route(h, layout()["amr"]["corridor"]) for h in layout()["amr"]["homes"]]
        self.amrs = [{"mode": AMR_PARKED, "s": 0.0, "timer": 0.0, "load": 0} for _ in range(AMR_COUNT)]
        self.reserved = 0
        self.delivered = 0
        self.energy = {"import_kws": 0.0, "export_kws": 0.0, "pv_kws": 0.0, "ev_kws": 0.0, "chiller_kws": 0.0}
        self.interval_kws = 0.0
        self.interval_start = START_CLOCK_S
        self.demand_history = []
        self.max_hall_c = self.hall_c
        self.failed_s = 0
        self.maint_s = 0
        self.last = {}
        self.pending = []  # (apply_at_t, command)
        self._flicker = {}

    def clock(self):
        return START_CLOCK_S + self.t

    def _inspect(self, serial, p_defect):
        return 1.0 if uniform(self.seed, "inspect", serial) < p_defect else 0.0

    def apply(self, command):
        if "pm" in command:
            self.line.pm_request = bool(command["pm"])
        if "derate" in command:
            self.line.derate = bool(command["derate"])
        if "setpoint_c" in command:
            self.setpoint = command["setpoint_c"]
        if "ev_cap" in command:
            self.ev_cap = command["ev_cap"]

    def _amrs(self, dt):
        out = self.line.buffers["outbound"]
        speed = self.p["amr_speed_m_s"]
        for i, a in enumerate(self.amrs):
            points, lengths = self.amr_routes[i]
            pickup = lengths[1]
            if a["mode"] == AMR_PARKED:
                if len(out) - self.reserved >= BATCH:
                    self.reserved += BATCH
                    a["mode"] = AMR_OUT
            elif a["mode"] == AMR_OUT:
                before = a["s"]
                a["s"] = min(lengths[-1], a["s"] + speed * dt)
                if a["load"] == 0 and before < pickup <= a["s"]:
                    a["s"], a["mode"], a["timer"] = pickup, AMR_LOADING, LOAD_S
                elif a["s"] >= lengths[-1]:
                    a["mode"], a["timer"] = AMR_UNLOADING, LOAD_S
            elif a["mode"] == AMR_LOADING:
                a["timer"] -= dt
                if a["timer"] <= 0:
                    del out[:BATCH]
                    self.reserved -= BATCH
                    a["load"], a["mode"] = BATCH, AMR_OUT
            elif a["mode"] == AMR_UNLOADING:
                a["timer"] -= dt
                if a["timer"] <= 0:
                    self.delivered += a["load"]
                    a["load"], a["mode"] = 0, AMR_RETURN
            elif a["mode"] == AMR_RETURN:
                a["s"] = max(0.0, a["s"] - speed * dt)
                if a["s"] <= 0:
                    a["mode"] = AMR_PARKED

    def amr_pose(self, i):
        a = self.amrs[i]
        points, lengths = self.amr_routes[i]
        return route_pose(points, lengths, a["s"], reverse=a["mode"] == AMR_RETURN)

    def step(self):
        """Advance one second."""
        while self.pending and self.pending[0][0] <= self.t:
            self.apply(self.pending.pop(0)[1])
        clock = self.clock()
        line = self.line
        line.step(1.0, clock, self._inspect)
        self._amrs(1.0)
        states = {sid: line.stations[sid]["state"] for sid in STATION_IDS}
        self.failed_s += states["cnc2"] == FAILED
        self.maint_s += states["cnc2"] == MAINT
        for k, sid in enumerate(("cnc1", "cnc2")):
            busy = states[sid] == BUSY
            wear = CNC1_WEAR if k == 0 else line.wear
            target = 30.0 + (16.0 + 12.0 * wear if busy else 0.0)
            self.spindle_c[k] += (target - self.spindle_c[k]) / 240.0
        flows = self._flows(states, integrate=True)
        net = flows["net"]
        self.energy["import_kws"] += max(0.0, net)
        self.energy["export_kws"] += max(0.0, -net)
        self.energy["pv_kws"] += flows["pv"]
        self.energy["ev_kws"] += flows["ev"]
        self.energy["chiller_kws"] += flows["chiller"]
        self.interval_kws += max(0.0, net)
        self.t += 1
        if (START_CLOCK_S + self.t - self.interval_start) >= BILLING_S:
            self.demand_history.append(self.interval_kws / BILLING_S)
            self.interval_kws = 0.0
            self.interval_start += BILLING_S
        self.last = flows

    def sense(self):
        """Evaluate power flows at the current instant without advancing time."""
        states = {sid: self.line.stations[sid]["state"] for sid in STATION_IDS}
        self.last = self._flows(states, integrate=False)

    def _flows(self, states, integrate):
        p, clock = self.p, self.clock()
        sun = clear_sky(clock)
        cloud = cloud_cover(p, clock)
        flicker = self._flicker.get(clock // 30)
        if flicker is None:
            flicker = self._flicker[clock // 30] = 0.04 * normal(self.seed, "flicker", clock // 30)
        pv = PV_KWP * sun * (1 - cloud) * (1 + flicker)
        machines = 0.0
        for sid in STATION_IDS:
            machines += station_kw(sid, states[sid])
        t_out = outdoor_c(p, clock)
        q_int = 0.85 * machines + 20.0 + 95.0 * sun * (1 - 0.5 * cloud)
        ua, cap = p["hall_ua_kw_k"], p["hall_capacity_kj_k"]
        q_cool = KP_COOL * (self.hall_c - self.setpoint) + q_int + ua * (t_out - self.hall_c)
        q_cool = max(0.0, min(Q_COOL_MAX, q_cool))
        if integrate:
            self.hall_c += (q_int + ua * (t_out - self.hall_c) - q_cool) / cap
            self.max_hall_c = max(self.max_hall_c, self.hall_c)
        chiller = q_cool / cop(t_out)
        ev = EV_KW * self.ev_cap if EV_WINDOW[0] <= clock < EV_WINDOW[1] else 0.0
        moving = sum(a["mode"] != AMR_PARKED for a in self.amrs)
        base = AUX_HALL_KW + COMPRESSOR_KW + OFFICE_KW + OFFICE_SUN_KW * sun + WAREHOUSE_KW + IT_KW
        load = machines + base + chiller + ev + AMR_KW * moving
        return {"pv": pv, "load": load, "net": load - pv, "chiller": chiller, "ev": ev, "t_out": t_out,
                "machines": machines, "q_cool": q_cool, "sun": sun, "cloud": cloud}

    # Sensors: rounded, noisy, lossy -------------------------------------------------
    def telemetry(self, k):
        s, t, line, last = self.seed, self.t, self.line, self.last
        drop = {g: uniform(s, "drop", k * 8 + j) < rate for j, (g, rate) in enumerate(
            (("plc", 0.02), ("cnc", 0.03), ("energy", 0.02), ("hall", 0.02), ("amr", 0.02)))}
        packet = {"t": t, "ok": {g: not d for g, d in drop.items()}}
        if not drop["plc"]:
            packet["plc"] = {
                "state": [line.stations[sid]["state"] for sid in STATION_IDS],
                "progress": [round(line.progress(sid), 3) for sid in STATION_IDS],
                "buffers": [len(line.buffers[b]) for b in BUFFER_IDS],
                "inspected": line.inspected, "scrap": int(line.scrap), "weld_count": line.weld_count,
                "derate": line.derate, "pm_request": line.pm_request,
            }
        if not drop["cnc"]:
            vib, temp = [], []
            for j, sid in enumerate(("cnc1", "cnc2")):
                busy = line.stations[sid]["state"] == BUSY
                wear = CNC1_WEAR if j == 0 else line.wear
                v = (VIB_BASE + VIB_LOAD + VIB_WEAR * wear * wear + VIB_SD * normal(s, f"vib{j + 1}", k)) if busy \
                    else 0.4 + 0.1 * normal(s, f"vib{j + 1}", k)
                vib.append(round(max(0.0, v), 3))
                temp.append(round(self.spindle_c[j] + 0.3 * normal(s, f"temp{j + 1}", k), 2))
            packet["cnc"] = {"vibration_mm_s": vib, "spindle_c": temp}
        if not drop["energy"]:
            packet["energy"] = {
                "load_kw": round(last["load"] * (1 + 0.01 * normal(s, "load", k)), 1),
                "pv_kw": round(last["pv"] * (1 + 0.01 * normal(s, "pv", k)), 1),
                "chiller_kw": round(last["chiller"] * (1 + 0.01 * normal(s, "chiller", k)), 1),
                "ev_kw": round(last["ev"], 1),
                "interval_kwh": round(self.interval_kws / 3600, 3),
                "setpoint_c": self.setpoint, "ev_cap": self.ev_cap,
            }
        if not drop["hall"]:
            packet["hall"] = {"hall_c": round(self.hall_c + 0.1 * normal(s, "hall", k), 2),
                              "outdoor_c": round(last["t_out"] + 0.1 * normal(s, "outdoor", k), 2)}
        if not drop["amr"]:
            packet["amr"] = [[round(v, 2) for v in self.amr_pose(i)[:2]] + [a["mode"], a["load"]]
                             for i, a in enumerate(self.amrs)]
        return packet

    def truth(self):
        line, last = self.line, self.last
        poses = [self.amr_pose(i) for i in range(AMR_COUNT)]
        return {
            "state": [line.stations[sid]["state"] for sid in STATION_IDS],
            "progress": [round(line.progress(sid), 4) for sid in STATION_IDS],
            "buffers": [len(line.buffers[b]) for b in BUFFER_IDS],
            "good": int(round(line.good)), "scrap": int(round(line.scrap)), "delivered": self.delivered,
            "wear": round(line.wear, 5), "derate": int(line.derate), "pm_request": int(line.pm_request),
            "amr": [[round(x, 4), round(y, 4), round(yaw, 5), a["mode"], a["load"]] for (x, y, yaw), a in zip(poses, self.amrs)],
            "hall_c": round(self.hall_c, 4), "outdoor_c": round(last["t_out"], 4),
            "pv_kw": round(last["pv"], 3), "load_kw": round(last["load"], 3), "net_kw": round(last["net"], 3),
            "chiller_kw": round(last["chiller"], 3), "ev_kw": round(last["ev"], 3),
            "setpoint_c": self.setpoint, "ev_cap": self.ev_cap, "cloud": round(last["cloud"], 4),
            "interval_kw": round(self.interval_kws / max(1, (START_CLOCK_S + self.t - self.interval_start)), 3),
        }


# Digital twin: consumes telemetry packets only ----------------------------------------
class Twin:
    def __init__(self, mode):
        self.mode = mode
        self.params = twin_parameters()
        tp = self.params
        self.w = tp["cnc2_initial_wear"]
        self.r = tp["cnc2_wear_rate_per_busy_s"]
        self.P = [[0.2 ** 2, 0.0], [0.0, (0.3 * NOMINAL_WEAR_RATE) ** 2]]
        self.plc = None
        self.energy = None
        self.energy_t = 0
        self.hall = None
        self.amr = None
        self.cnc = None
        self.prev_cnc2_state = IDLE
        self.command = {"pm": False, "derate": False, "setpoint_c": DEFAULT_SETPOINT, "ev_cap": 1.0}
        self.level = 0
        self.release_count = 0
        self.decisions = []
        self.advice = {}
        self.last_plan = None
        self.forecast_kw = None
        self.forecast_next_kw = None
        self.stale = {"plc": 0, "cnc": 0, "energy": 0, "hall": 0, "amr": 0}

    # Sync --------------------------------------------------------------------
    def ingest(self, packet):
        for group in self.stale:
            if packet["ok"][group]:
                self.stale[group] = 0
                setattr(self, group, packet[group])
                if group == "energy":
                    self.energy_t = packet["t"]
            else:
                self.stale[group] += 1
        if packet["ok"]["plc"]:
            state = packet["plc"]["state"][2]
            if self.prev_cnc2_state in (MAINT, FAILED) and state not in (MAINT, FAILED):
                self.w, self.P = RESET_WEAR, [[0.02 ** 2, 0.0], [0.0, self.P[1][1]]]
                self._log(packet["t"], "sync", "CNC 2 back in service; wear estimate reset",
                          {"previous_state": STATE_NAMES[self.prev_cnc2_state]}, {})
            if state == FAILED and self.prev_cnc2_state != FAILED:
                self._log(packet["t"], "alarm", "CNC 2 spindle failure detected",
                          {"estimated_wear": round(self.w, 4)}, {})
            if state == MAINT and self.prev_cnc2_state != MAINT:
                self._log(packet["t"], "sync", "CNC 2 maintenance started", {}, {})
            if state in (MAINT, FAILED):
                self.command["pm"] = False
                self.command["derate"] = False
            self.prev_cnc2_state = state

    def _estimate(self):
        """EKF over [wear, wear rate] with a quadratic vibration measurement."""
        busy = self.prev_cnc2_state == BUSY
        derate = self.plc["derate"] if self.plc else False
        factor = DERATE_WEAR if derate else 1.0
        b = SAMPLE_S * factor if busy else 0.0
        P = self.P
        self.w += self.r * b
        # P = F P F' + Q, F = [[1, b], [0, 1]]
        p00 = P[0][0] + 2 * b * P[0][1] + b * b * P[1][1] + 1e-7 * b
        p01 = P[0][1] + b * P[1][1]
        p11 = P[1][1] + 1e-16 * b
        if busy and self.cnc is not None and self.stale["cnc"] == 0:
            z = self.cnc["vibration_mm_s"][1]
            h = VIB_BASE + VIB_LOAD + VIB_WEAR * self.w * self.w
            H = 2 * VIB_WEAR * self.w
            S = H * H * p00 + VIB_SD * VIB_SD
            k0, k1 = p00 * H / S, p01 * H / S
            innovation = z - h
            self.w += k0 * innovation
            self.r += k1 * innovation
            p00, p01, p11 = (1 - k0 * H) * p00, (1 - k0 * H) * p01, p11 - k1 * H * p01
        self.w = max(0.0, self.w)
        self.r = max(0.1 * NOMINAL_WEAR_RATE, self.r)
        self.P = [[max(p00, 1e-8), p01], [p01, max(p11, 1e-18)]]

    def wear_sd(self):
        return math.sqrt(self.P[0][0])

    def rul_minutes(self, sigmas=0.0):
        """Busy minutes until the conservative wear estimate reaches the nominal threshold."""
        derate = self.plc["derate"] if self.plc else False
        rate = self.r * (DERATE_WEAR if derate else 1.0)
        w = self.w + sigmas * self.wear_sd()
        return max(0.0, (self.params["cnc2_failure_threshold"] - w) / rate / 60)

    def failure_probability(self, minutes=60):
        """Display-only probability of crossing the threshold within the next busy minutes."""
        derate = self.plc["derate"] if self.plc else False
        b = minutes * 60 * (DERATE_WEAR if derate else 1.0)
        mean = self.w + self.r * b
        var = self.P[0][0] + 2 * b * self.P[0][1] + b * b * self.P[1][1] + THRESHOLD_SD ** 2
        return 0.5 * (1 + math.erf((mean - self.params["cnc2_failure_threshold"]) / math.sqrt(2 * var)))

    # Predict ------------------------------------------------------------------------
    def mirror(self):
        plc = self.plc
        line = Line(self.w, self.r, self.params["cnc2_failure_threshold"])
        line.outbound_unlimited = True
        line.derate = bool(plc["derate"])
        line.weld_count = plc["weld_count"]
        for name, count in zip(BUFFER_IDS, plc["buffers"]):
            line.buffers[name] = [BASE_DEFECT] * count if name != "outbound" else []
        for sid, state, progress in zip(STATION_IDS, plc["state"], plc["progress"]):
            s = line.stations[sid]
            s["state"] = state
            if state == BUSY:
                s["part"] = BASE_DEFECT
                s["rem"] = (1 - progress) * line.cycle(sid)
            elif state == BLOCKED:
                s["part"] = BASE_DEFECT
            elif state == FAILED:
                s["rem"] = REPAIR_S / 2
            elif state == MAINT:
                s["rem"] = PM_S / 2
            elif state == DRESS:
                s["rem"] = DRESS_S / 2
            elif state == BREAK:
                s["state"], s["resume"] = BREAK, BUSY if progress > 0 else IDLE
                s["part"] = BASE_DEFECT if progress > 0 else None
                s["rem"] = (1 - progress) * line.cycle(sid)
        return line

    def forecast_line(self, base, clock, offset, derate, wear):
        line = base.clone()
        line.wear, line.derate = wear, derate
        line.threshold = self.params["cnc2_failure_threshold"]
        steps = int(PLAN_HORIZON_S / PLAN_DT)
        maintained = line.stations["cnc2"]["state"] == MAINT
        failed_at = service_wear = None
        for i in range(steps):
            elapsed = i * PLAN_DT
            if offset is not None and elapsed >= offset and not maintained and failed_at is None:
                line.pm_request = True
            before = line.wear
            line.step(PLAN_DT, clock + elapsed, None)
            if not maintained and line.stations["cnc2"]["state"] == MAINT:
                maintained, service_wear = True, before
            if failed_at is None and line.stations["cnc2"]["state"] == FAILED:
                failed_at = elapsed + PLAN_DT
        penalty = 0.0
        if service_wear is not None:
            penalty += LIFE_COST_UNITS * max(0.0, line.threshold - service_wear)
        if failed_at is not None:
            penalty += FAILURE_COST_UNITS
        return {"good": line.good - base.good, "penalty": penalty, "failed_at_s": failed_at,
                "service_wear": service_wear, "maintained": maintained}

    def plan(self, t, clock):
        base = self.mirror()
        # Two standard deviations of wear-estimate and failure-threshold uncertainty combined.
        conservative = min(1.2, self.w + 2 * math.sqrt(self.P[0][0] + THRESHOLD_SD ** 2))
        options = []
        for derate in (False, True):
            for offset in PLAN_OFFSETS:
                result = self.forecast_line(base, clock, offset, derate, conservative)
                options.append({"offset_s": offset, "derate": derate,
                                "value": result["good"] - result["penalty"], **result})
        # Prefer later maintenance and no derate when values tie.
        rank = {offset: i for i, offset in enumerate((None, 3600, 2700, 1800, 1200, 600, 0))}

        def key(o):
            return (round(o["value"] / PLAN_TIE_UNITS), -o["derate"], -rank[o["offset_s"]])
        best = max(options, key=key)
        current = self.command["derate"]
        if best["derate"] != current and best["offset_s"] != 0:
            same = max((o for o in options if o["derate"] == current), key=key)
            if best["value"] - same["value"] < DERATE_SWITCH_UNITS:
                best = same
        self.last_plan = {"t": t, "best": best, "options": options, "conservative_wear": conservative}
        return best

    def forecast_demand(self):
        """Forecast the billed 15-minute mean import from the latest meter reading."""
        e = self.energy
        clock = START_CLOCK_S + self.energy_t
        interval_start = clock - (clock - START_CLOCK_S) % BILLING_S
        elapsed = clock - interval_start
        remaining = BILLING_S - elapsed
        other = e["load_kw"] - e["chiller_kw"] - e["ev_kw"]
        # Chiller response to a setpoint change the twin itself requested (nominal model).
        # In shadow mode that request is never applied, so the shadow twin forecasts as
        # if its advice were followed; the plant and its telemetry are unaffected.
        cop_now = cop(self.hall["outdoor_c"]) if self.hall else cop(30.0)
        chiller = max(0.0, e["chiller_kw"] - KP_COOL * (self.command["setpoint_c"] - e["setpoint_c"]) / cop_now)

        def ev_average(start, duration):
            active = max(0, min(start + duration, EV_WINDOW[1]) - max(start, EV_WINDOW[0]))
            return EV_KW * self.command["ev_cap"] * active / duration

        net_now = other + chiller + ev_average(clock, max(1, remaining)) - e["pv_kw"]
        current = (e["interval_kwh"] * 3600 + max(0.0, net_now) * remaining) / BILLING_S
        net_next = other + chiller + ev_average(interval_start + BILLING_S, BILLING_S) - e["pv_kw"]
        return current, max(0.0, net_next)

    # Decide / act -----------------------------------------------------------------
    def _log(self, t, kind, action, evidence, prediction, actuated=None):
        entry = {"t": t, "clock": _clock(START_CLOCK_S + t), "kind": kind, "action": action,
                 "evidence": evidence, "prediction": prediction}
        if actuated is not None:
            entry["actuated"] = actuated
        self.decisions.append(entry)

    def decide(self, t):
        """Return commands for the plant (the caller drops them in shadow mode)."""
        clock = START_CLOCK_S + t
        commands = {}
        if self.plc is None:
            return commands
        self._estimate()
        cnc2 = self.plc["state"][2]
        in_service = cnc2 not in (MAINT, FAILED)
        if in_service and t % PLAN_EVERY_S == 0 and (
                self.rul_minutes(2) < PLAN_TRIGGER_RUL_MIN or self.command["derate"]):
            best = self.plan(t, clock)
            evidence = {"estimated_wear": round(self.w, 4), "wear_sd": round(self.wear_sd(), 4),
                        "conservative_wear": round(self.last_plan["conservative_wear"], 4),
                        "rul_busy_min_2sigma": round(self.rul_minutes(2), 1),
                        "vibration_mm_s": self.cnc["vibration_mm_s"][1] if self.cnc else None,
                        "buffers": dict(zip(BUFFER_IDS, self.plc["buffers"]))}
            prediction = {"horizon_min": PLAN_HORIZON_S // 60, "expected_good_units": round(best["good"], 2),
                          "candidates": len(self.last_plan["options"]),
                          "defer_expected_good_units": round(next(
                              o["good"] for o in self.last_plan["options"]
                              if o["offset_s"] is None and not o["derate"]), 2),
                          "defer_predicts_failure_min": next(
                              (round(o["failed_at_s"] / 60, 1) for o in self.last_plan["options"]
                               if o["offset_s"] is None and not o["derate"] and o["failed_at_s"] is not None), None)}
            if best["offset_s"] == 0 and not self.command["pm"]:
                self._command(t, commands, "maintenance", {"pm": True, "derate": False},
                              "Schedule CNC 2 spindle service now (15 min)", evidence, prediction)
            elif best["derate"] != self.command["derate"]:
                action = ("Derate CNC 2 to 80% feed until service" if best["derate"]
                          else "Restore CNC 2 to full feed")
                self._command(t, commands, "maintenance", {"derate": best["derate"]}, action, evidence,
                              {**prediction, "planned_service_in_min": None if best["offset_s"] is None
                               else best["offset_s"] // 60})
            else:
                key = ("plan", best["offset_s"], best["derate"])
                if self.advice.get("plan") != key:
                    self.advice["plan"] = key
                    if best["offset_s"] == 0:
                        action = "Service now is still the best plan (earlier advice not actuated)"
                    elif best["offset_s"] is None:
                        action = "Keep running; no service needed within 90 min"
                    else:
                        action = f"Keep running; best service start in {best['offset_s'] // 60} min"
                    self._log(t, "plan", action, evidence, prediction)
        if self.energy is not None and t % ENERGY_EVERY_S == 0:
            current, following = self.forecast_demand()
            self.forecast_kw, self.forecast_next_kw = current, following
            peak = max(current, following)
            hall = self.hall["hall_c"] if self.hall else None
            target = self.level
            if peak > DEMAND_LIMIT_KW - ESCALATE_MARGIN_KW and self.level < len(LEVELS) - 1:
                target = self.level + 1
                self.release_count = 0
            elif peak < DEMAND_LIMIT_KW - RELEASE_MARGIN_KW and self.level > 0:
                self.release_count += 1
                if self.release_count >= RELEASE_CHECKS:
                    target, self.release_count = self.level - 1, 0
            else:
                self.release_count = 0
            if hall is not None and hall > COMFORT_MAX_C - 0.3 and target == len(LEVELS) - 1:
                target = len(LEVELS) - 2  # comfort guard: never hold +2 °C near the hall limit
            if target != self.level:
                self.level = target
                level = LEVELS[target]
                self._command(t, commands, "demand", {"setpoint_c": level["setpoint_c"], "ev_cap": level["ev_cap"]},
                              f"Demand level {target}: {level['label']}",
                              {"pv_kw": self.energy["pv_kw"], "load_kw": self.energy["load_kw"],
                               "hall_c": hall, "interval_kwh_so_far": self.energy["interval_kwh"]},
                              {"billing_interval_kw": round(current, 1), "next_interval_kw": round(following, 1),
                               "limit_kw": DEMAND_LIMIT_KW})
        return commands

    def _command(self, t, commands, kind, values, action, evidence, prediction):
        self.command.update(values)
        commands.update(values)
        self._log(t, kind, action, evidence, prediction, actuated=self.mode == "closed")

    def snapshot(self):
        return {
            "wear": round(self.w, 5), "wear_sd": round(self.wear_sd(), 5),
            "rul_min": round(min(999.0, self.rul_minutes(0)), 2),
            "p_fail_60": round(self.failure_probability(60), 4),
            "forecast_kw": None if self.forecast_kw is None else round(self.forecast_kw, 2),
            "level": self.level, "pm": int(self.command["pm"]), "derate": int(self.command["derate"]),
            "hall_c": None if self.hall is None else self.hall["hall_c"],
            "buffers": None if self.plc is None else list(self.plc["buffers"]),
            "state": None if self.plc is None else list(self.plc["state"]),
            "amr": None if self.amr is None else [list(a) for a in self.amr],
            "stale": sum(self.stale.values()),
        }


def _clock(seconds):
    seconds = int(seconds)
    return f"{seconds // 3600:02d}:{seconds // 60 % 60:02d}:{seconds % 60:02d}"


# Run one paired arm ----------------------------------------------------------------------
def simulate(seed, mode, *, record=True):
    if mode not in MODES:
        raise ValueError(f"Unknown mode: {mode}")
    plant, twin = Plant(seed), Twin(mode)
    columns = {"plant": [], "telemetry": [], "twin": []}
    inbox = None
    for k in range(SAMPLES):
        if k:
            for _ in range(SAMPLE_S):
                plant.step()
        else:
            plant.sense()
        packet = plant.telemetry(k)
        if inbox is not None:  # one sample of network latency
            twin.ingest(inbox)
            commands = twin.decide(plant.t)
            if commands and mode == "closed":
                plant.pending.append((plant.t + SAMPLE_S, commands))
        inbox = packet
        if record:
            columns["plant"].append(plant.truth())
            columns["telemetry"].append(packet)
            columns["twin"].append(twin.snapshot())
    demand = plant.demand_history
    line = plant.line
    kpis = {
        "good_units": int(round(line.good)), "scrap_units": int(round(line.scrap)),
        "delivered_units": plant.delivered,
        "cnc2_failures": line.failures, "cnc2_maintenances": line.maintenances,
        "cnc2_unplanned_down_min": round(plant.failed_s / 60, 2),
        "cnc2_planned_service_min": round(plant.maint_s / 60, 2),
        "grid_import_kwh": round(plant.energy["import_kws"] / 3600, 2),
        "pv_kwh": round(plant.energy["pv_kws"] / 3600, 2),
        "ev_kwh": round(plant.energy["ev_kws"] / 3600, 2),
        "chiller_kwh": round(plant.energy["chiller_kws"] / 3600, 2),
        "peak_demand_kw": round(max(demand), 2),
        "intervals_over_limit": sum(d > DEMAND_LIMIT_KW for d in demand),
        "billing_intervals_kw": [round(d, 2) for d in demand],
        "max_hall_c": round(plant.max_hall_c, 3),
        "commands_actuated": sum(1 for d in twin.decisions if d.get("actuated")),
    }
    kpis["import_kwh_per_good_unit"] = round(kpis["grid_import_kwh"] / max(1, kpis["good_units"]), 3)
    result = {"seed": seed, "mode": mode, "kpis": kpis, "decisions": twin.decisions}
    if record:
        result["samples"] = columns
        # Compare wear only in steady service: skip the latency window after a reset.
        errors = [abs(columns["twin"][k]["wear"] - columns["plant"][k]["wear"]) for k in range(3, SAMPLES)
                  if all(columns["plant"][j]["state"][2] == BUSY for j in (k, k - 1, k - 2, k - 3))]
        hall = [abs(tw["hall_c"] - pl["hall_c"]) for tw, pl in zip(columns["twin"], columns["plant"])
                if tw["hall_c"] is not None]
        mirror = sum(tw["buffers"] != pl["buffers"] for tw, pl in zip(columns["twin"], columns["plant"]))
        result["fidelity"] = {
            "wear_mae_busy": round(sum(errors) / len(errors), 5),
            "wear_max_abs_error_busy": round(max(errors), 5),
            "hall_mae_c": round(sum(hall) / len(hall), 4),
            "buffer_mirror_mismatch_samples": mirror,
            "samples": SAMPLES,
            "telemetry_dropouts": sum(not ok for p in columns["telemetry"] for ok in p["ok"].values()),
        }
        result["prediction_checks"] = prediction_checks(result)
    return result


def prediction_checks(run):
    """Compare each maintenance forecast with what the plant actually produced."""
    plant = run["samples"]["plant"]
    by_t = {k * SAMPLE_S: row for k, row in enumerate(plant)}
    checks = []
    for d in run["decisions"]:
        if d["kind"] not in ("maintenance", "plan") or "expected_good_units" not in d["prediction"]:
            continue
        end = d["t"] + PLAN_HORIZON_S
        if end not in by_t:
            continue
        actual = by_t[end]["good"] - by_t[d["t"]]["good"]
        checks.append({"t": d["t"], "kind": d["kind"], "predicted_good_units": d["prediction"]["expected_good_units"],
                       "actual_good_units": actual, "actuated": d.get("actuated")})
    return checks


def replay_twin(run):
    """Re-run the twin from the recorded telemetry alone; no plant state is available."""
    twin = Twin(run["mode"])
    snapshots = [twin.snapshot()]
    telemetry = run["samples"]["telemetry"]
    for k in range(1, SAMPLES):
        twin.ingest(telemetry[k - 1])
        twin.decide(telemetry[k]["t"])
        snapshots.append(twin.snapshot())
    return snapshots, twin.decisions


# Lab payload, verification and export -------------------------------------------------------
RENDERS = ("render-aerial.jpg", "render-hall.jpg", "render-cnc.jpg", "render-energy.jpg")
FILES = ("lab.json", "index.html", "METHODS.md", "LICENSE", "trace-shadow.json", "trace-closed.json",
         "seeds.json", "blender-check.json", "poster.png", *RENDERS)
MAX_FILE = 24 * 1024 * 1024


def digest(data):
    return hashlib.sha256(data).hexdigest()


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON key")
        result[key] = value
    return result


def decode(data):
    def reject(value):
        raise ValueError(f"Non-finite JSON number: {value}")
    return json.loads(data, object_pairs_hook=_pairs, parse_constant=reject)


def dumps(value):
    return json.dumps(value, separators=(",", ":"), allow_nan=False)


def read(root, name):
    path = Path(root) / name
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError(f"Symlink in input path: {name}")
    if not path.is_file() or path.stat().st_size > MAX_FILE:
        raise ValueError(f"Missing, non-regular or oversized file: {name}")
    data = path.read_bytes()
    if len(data) > MAX_FILE:
        raise ValueError(f"Oversized file: {name}")
    return data


def config():
    return {
        "schema": SCHEMA, "sample_s": SAMPLE_S, "duration_s": DURATION_S, "start_clock": _clock(START_CLOCK_S),
        "samples": SAMPLES, "featured_seed": FEATURED_SEED, "seeds": list(SEEDS), "modes": list(MODES),
        "stations": [{"id": r[0], "label": r[1], "cycle_s": r[2], "input": r[3], "output": r[4],
                      "busy_kw": r[5], "idle_kw": r[6]} for r in STATIONS],
        "buffers": BUFFERS, "state_names": list(STATE_NAMES), "amr_states": list(AMR_STATES),
        "break_window": [_clock(v) for v in BREAK_WINDOW], "ev_window": [_clock(v) for v in EV_WINDOW],
        "demand_limit_kw": DEMAND_LIMIT_KW, "billing_s": BILLING_S, "comfort_max_c": COMFORT_MAX_C,
        "levels": LEVELS, "latency_s": {"telemetry": SAMPLE_S, "actuation": SAMPLE_S},
        "maintenance": {"planned_min": PM_S / 60, "unplanned_repair_min": REPAIR_S / 60,
                        "plan_every_s": PLAN_EVERY_S, "horizon_min": PLAN_HORIZON_S / 60,
                        "offsets_min": [None if o is None else o // 60 for o in PLAN_OFFSETS],
                        "trigger_rul_min": PLAN_TRIGGER_RUL_MIN},
        "twin_parameters": twin_parameters(),
    }


def summarize(seed_runs):
    rows = []
    for seed in SEEDS:
        a, b = seed_runs[(seed, "shadow")]["kpis"], seed_runs[(seed, "closed")]["kpis"]
        keep = ("good_units", "scrap_units", "cnc2_failures", "cnc2_unplanned_down_min", "cnc2_planned_service_min",
                "peak_demand_kw", "intervals_over_limit", "grid_import_kwh", "ev_kwh", "max_hall_c",
                "import_kwh_per_good_unit", "commands_actuated")
        rows.append({"seed": seed, "shadow": {k: a[k] for k in keep}, "closed": {k: b[k] for k in keep}})
    gains = [r["closed"]["good_units"] - r["shadow"]["good_units"] for r in rows]
    return {
        "seeds": rows,
        "summary": {
            "pairs": len(rows),
            "good_units_gain": {"min": min(gains), "max": max(gains), "mean": round(sum(gains) / len(gains), 2),
                                "pairs_improved": sum(g > 0 for g in gains), "pairs_worse": sum(g < 0 for g in gains)},
            "shadow_failures": sum(r["shadow"]["cnc2_failures"] for r in rows),
            "closed_failures": sum(r["closed"]["cnc2_failures"] for r in rows),
            "shadow_intervals_over_limit": sum(r["shadow"]["intervals_over_limit"] for r in rows),
            "closed_intervals_over_limit": sum(r["closed"]["intervals_over_limit"] for r in rows),
            "max_closed_hall_c": max(r["closed"]["max_hall_c"] for r in rows),
        },
    }


def build_record():
    runs = {mode: simulate(FEATURED_SEED, mode) for mode in MODES}
    seed_runs = {(seed, mode): (runs[mode] if seed == FEATURED_SEED else simulate(seed, mode, record=False))
                 for seed in SEEDS for mode in MODES}
    seeds = summarize(seed_runs)
    lab = make_lab(runs, seeds)
    return runs, seeds, lab


def compact(run):
    """Browser payload: plant truth, twin estimates and decisions (telemetry stays in the trace)."""
    s = run["samples"]
    plant_keys = ("state", "progress", "buffers", "good", "scrap", "delivered", "wear", "amr", "hall_c",
                  "pv_kw", "net_kw", "chiller_kw", "ev_kw", "setpoint_c", "ev_cap", "interval_kw", "cloud")
    twin_keys = ("wear", "wear_sd", "rul_min", "p_fail_60", "forecast_kw", "level", "pm", "derate", "hall_c",
                 "state", "amr", "buffers", "stale")
    return {
        "mode": run["mode"], "seed": run["seed"], "kpis": run["kpis"], "fidelity": run["fidelity"],
        "plant_parameters": plant_parameters(run["seed"]),
        "decisions": run["decisions"], "prediction_checks": run["prediction_checks"],
        "plant": {k: [row[k] for row in s["plant"]] for k in plant_keys},
        "twin": {k: [row[k] for row in s["twin"]] for k in twin_keys},
        "vibration": [None if "cnc" not in p else p["cnc"]["vibration_mm_s"][1] for p in s["telemetry"]],
    }


def normalize(value):
    """The JSON form of a value (tuples become lists), for exact comparison with decoded files."""
    return decode(dumps(value))


def make_lab(runs, seeds):
    return normalize({"schema": SCHEMA, "config": config(), "layout": layout(),
                      "runs": {mode: compact(runs[mode]) for mode in MODES}, "seeds": seeds})


def verify(root, *, check_archive=True, all_seeds=False, reexecute=True):
    root = Path(root)
    manifest = decode(read(root, "manifest.json"))
    if (not isinstance(manifest, dict) or manifest.get("schema") != SCHEMA
            or not isinstance(manifest.get("files"), dict) or set(manifest["files"]) != set(FILES)):
        raise ValueError("Unexpected experiment inventory")
    data = {name: read(root, name) for name in FILES}
    for name, content in data.items():
        if manifest["files"][name] != {"sha256": digest(content), "bytes": len(content)}:
            raise ValueError(f"File hash or size mismatch: {name}")
    runs = {}
    for mode in MODES:
        run = decode(data[f"trace-{mode}.json"])
        if run.get("seed") != FEATURED_SEED or run.get("mode") != mode:
            raise ValueError(f"Unexpected trace identity: {mode}")
        telemetry = run["samples"]["telemetry"]
        if len(telemetry) != SAMPLES or any(p["t"] != k * SAMPLE_S for k, p in enumerate(telemetry)):
            raise ValueError(f"Incomplete sample clock: {mode}")
        if reexecute:
            snapshots, decisions = replay_twin(run)
            if normalize(snapshots) != run["samples"]["twin"] or normalize(decisions) != run["decisions"]:
                raise ValueError(f"Twin state or decisions do not follow from telemetry alone: {mode}")
            if normalize(simulate(FEATURED_SEED, mode)) != run:
                raise ValueError(f"Re-executed plant and twin differ from the recorded trace: {mode}")
        runs[mode] = run
    seeds = decode(data["seeds.json"])
    if all_seeds:
        seed_runs = {(seed, mode): (runs[mode] if seed == FEATURED_SEED else simulate(seed, mode, record=False))
                     for seed in SEEDS for mode in MODES}
        if normalize(summarize(seed_runs)) != seeds:
            raise ValueError("Seed summary differs from re-executed runs")
    else:
        featured = next((r for r in seeds.get("seeds", []) if r.get("seed") == FEATURED_SEED), None)
        replay = summarize({(s, m): runs[m] for s in SEEDS for m in MODES})["seeds"][0]
        if featured is None or {k: featured[k] for k in MODES} != normalize({k: replay[k] for k in MODES}):
            raise ValueError("Featured seed summary differs from its trace")
    lab = make_lab(runs, seeds)
    if decode(data["lab.json"]) != lab:
        raise ValueError("Lab payload differs from the source traces")
    marker = '<script id="lab-data" type="application/json">'
    html = data["index.html"].decode("utf-8")
    if html.count(marker) != 1 or decode(html.split(marker)[1].split("</script>", 1)[0]) != lab:
        raise ValueError("Browser payload differs from the source traces")
    check = decode(data["blender-check.json"])
    if (not isinstance(check, dict) or check.get("schema") != SCHEMA
            or check.get("inputs", {}).get("lab.json") != digest(data["lab.json"])
            or check.get("frames_checked") != SAMPLES or check.get("verified") is not True
            or check.get("usd_frames_checked") != SAMPLES):
        raise ValueError("Blender readback receipt does not match lab.json")
    if data["poster.png"][:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("Poster is not a PNG")
    for name in RENDERS:
        if data[name][:3] != b"\xff\xd8\xff":
            raise ValueError(f"Render is not a JPEG: {name}")
    if set(check.get("modes", {})) != set(MODES) or any(
            check["modes"][m].get("verified") is not True or check["modes"][m].get("frames_checked") != SAMPLES
            for m in MODES):
        raise ValueError("Blender readback receipt must cover both loop modes")
    if check_archive and (root / "experiment.zip").exists():
        read(root, "experiment.zip")
        with zipfile.ZipFile(root / "experiment.zip") as archive:
            names = (*FILES, "manifest.json")
            if len(archive.infolist()) != len(names) or set(archive.namelist()) != set(names):
                raise ValueError("Unexpected offline archive inventory")
            for name in names:
                original = read(root, name)
                if archive.getinfo(name).file_size != len(original) or archive.read(name) != original:
                    raise ValueError(f"Offline archive differs: {name}")
    k = {m: runs[m]["kpis"] for m in MODES}
    return {
        "verified": True, "seed": FEATURED_SEED, "samples_per_run": SAMPLES,
        "plant_and_twin_reexecuted": reexecute, "twin_replayed_from_telemetry": reexecute,
        "all_seeds_reexecuted": all_seeds, "pairs": len(SEEDS),
        "good_units": {m: k[m]["good_units"] for m in MODES},
        "cnc2_failures": {m: k[m]["cnc2_failures"] for m in MODES},
        "peak_demand_kw": {m: k[m]["peak_demand_kw"] for m in MODES},
        "blender_frames_checked": check["frames_checked"],
    }


def seal(root):
    root = Path(root)
    files = {}
    for name in FILES:
        content = read(root, name)
        files[name] = {"sha256": digest(content), "bytes": len(content)}
    (root / "manifest.json").write_text(json.dumps({"schema": SCHEMA, "files": files}, indent=2) + "\n")
    verify(root, check_archive=False, reexecute=False)
    with zipfile.ZipFile(root / "experiment.zip", "w", zipfile.ZIP_DEFLATED) as archive:
        for name in (*FILES, "manifest.json"):
            info = zipfile.ZipInfo(name, (2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, read(root, name))


def render_page(lab):
    template = Path(__file__).with_name("factory_twin.html").read_text()
    payload = dumps(lab).replace("&", "\\u0026").replace("<", "\\u003c").replace(">", "\\u003e")
    return template.replace("__LAB_DATA__", payload)


def record(output):
    """Write the traces, seed table and lab payload (before the Blender receipt exists)."""
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    runs, seeds, lab = build_record()
    for mode in MODES:
        (output / f"trace-{mode}.json").write_text(dumps(runs[mode]) + "\n")
    (output / "seeds.json").write_text(json.dumps(seeds, indent=1) + "\n")
    (output / "lab.json").write_text(dumps(lab) + "\n")
    return {"recorded": True, "output": str(output), "kpis": {m: runs[m]["kpis"] for m in MODES},
            "seed_summary": seeds["summary"]}


def export(source, destination):
    source, destination = Path(source).absolute(), Path(destination).absolute()
    if any(p.is_symlink() for p in (source, *source.parents, destination, *destination.parents)):
        raise ValueError("Output path cannot contain symlinks")
    source, destination = source.resolve(), destination.resolve()
    if destination == source or destination.is_relative_to(source) or source.is_relative_to(destination):
        raise ValueError("Output overlaps source")
    if destination.exists() and (not destination.is_dir() or any(destination.iterdir())):
        raise ValueError("Choose an empty output directory")
    verify(source)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=destination.parent, prefix=".factory-twin-") as temporary:
        stage = Path(temporary) / "lab"
        stage.mkdir()
        for name in FILES:
            (stage / name).write_bytes(read(source, name))
        (stage / "index.html").write_text(render_page(decode(read(stage, "lab.json"))))
        seal(stage)
        if destination.exists():
            destination.rmdir()
        stage.rename(destination)
    # The source was re-executed above; the copy differs only by its regenerated page.
    return verify(destination, reexecute=False)


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="robot-reel factory-twin", description=__doc__.split("\n\n")[0],
        epilog="The simulation is illustrative; it is not calibrated to a real site.")
    parser.add_argument("--output", type=Path, required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--verify", action="store_true", help="Re-execute plant and twin and check every file")
    mode.add_argument("--export-from", type=Path, help="Copy a verified lab into an empty directory")
    mode.add_argument("--record", action="store_true", help="Simulate all seeds and write traces (no Blender receipt)")
    parser.add_argument("--all-seeds", action="store_true", help="With --verify, re-execute all 12 seed pairs")
    args = parser.parse_args(argv)
    if args.all_seeds and not args.verify:
        parser.error("--all-seeds requires --verify")
    try:
        if args.record:
            result = record(args.output)
        elif args.verify:
            result = verify(args.output, all_seeds=args.all_seeds)
        else:
            result = export(args.export_from, args.output)
        print(json.dumps(result, indent=2))
        return 0
    except (ValueError, OSError, KeyError, TypeError, zipfile.BadZipFile) as exc:
        print(json.dumps({"verified": False, "error": str(exc)}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
