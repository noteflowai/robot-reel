"""Export the Factory Twin Lab's tables for Hugging Face Datasets.

    python3 scripts/build_hf_factory_twin.py --output artifacts/hf-factory-twin

Every table is derived from the verified published lab (docs/factory-twin); the
exporter re-runs `robot_reel.factory_twin.verify` first, including plant and
twin re-execution. Configs:

  seeds      24 rows: one per (seed, loop mode) with shift KPIs
  pairs      12 rows: closed-loop minus shadow for each seed
  samples    4,322 rows: every 5 s sample of the featured seed, both modes
  decisions  every twin decision of the featured seed, with evidence/prediction
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from robot_reel import factory_twin as ft  # noqa: E402

SITE = ROOT / "docs/factory-twin"
KPIS = ("good_units", "scrap_units", "cnc2_failures", "cnc2_unplanned_down_min", "cnc2_planned_service_min",
        "peak_demand_kw", "intervals_over_limit", "grid_import_kwh", "ev_kwh", "max_hall_c",
        "import_kwh_per_good_unit", "commands_actuated")
SAMPLE_FIELDS = ("mode", "sample", "time_s", "clock", "good", "scrap", "delivered", "cnc2_state", "wear_truth",
                 "wear_twin", "wear_twin_sd", "rul_busy_min", "p_fail_60", "net_kw", "interval_kw",
                 "twin_forecast_kw", "pv_kw", "ev_kw", "chiller_kw", "hall_c", "setpoint_c", "ev_cap",
                 "demand_level", "cloud", "buffers")


def table(fields, rows):
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue()


def seed_rows(seeds):
    return [{"seed": r["seed"], "mode": mode, "featured": r["seed"] == ft.FEATURED_SEED, **r[mode]}
            for r in seeds["seeds"] for mode in ft.MODES]


def pair_rows(seeds):
    rows = []
    for r in seeds["seeds"]:
        row = {"seed": r["seed"]}
        for key in KPIS:
            row[f"shadow_{key}"], row[f"closed_{key}"] = r["shadow"][key], r["closed"][key]
        row["good_units_gain"] = r["closed"]["good_units"] - r["shadow"]["good_units"]
        rows.append(row)
    return rows


def sample_rows(lab):
    names = lab["config"]["state_names"]
    rows = []
    for mode in ft.MODES:
        p, t = lab["runs"][mode]["plant"], lab["runs"][mode]["twin"]
        for k in range(lab["config"]["samples"]):
            rows.append({
                "mode": mode, "sample": k, "time_s": k * ft.SAMPLE_S, "clock": ft._clock(ft.START_CLOCK_S + k * ft.SAMPLE_S),
                "good": p["good"][k], "scrap": p["scrap"][k], "delivered": p["delivered"][k],
                "cnc2_state": names[p["state"][k][2]], "wear_truth": p["wear"][k], "wear_twin": t["wear"][k],
                "wear_twin_sd": t["wear_sd"][k], "rul_busy_min": t["rul_min"][k], "p_fail_60": t["p_fail_60"][k],
                "net_kw": p["net_kw"][k], "interval_kw": p["interval_kw"][k],
                "twin_forecast_kw": "" if t["forecast_kw"][k] is None else t["forecast_kw"][k],
                "pv_kw": p["pv_kw"][k], "ev_kw": p["ev_kw"][k], "chiller_kw": p["chiller_kw"][k],
                "hall_c": p["hall_c"][k], "setpoint_c": p["setpoint_c"][k], "ev_cap": p["ev_cap"][k],
                "demand_level": t["level"][k], "cloud": p["cloud"][k], "buffers": json.dumps(p["buffers"][k]),
            })
    return rows


def decision_rows(lab):
    return [{"mode": mode, "t": d["t"], "clock": d["clock"], "kind": d["kind"], "action": d["action"],
             "actuated": "" if d.get("actuated") is None else d["actuated"],
             "evidence": json.dumps(d["evidence"], sort_keys=True), "prediction": json.dumps(d["prediction"], sort_keys=True)}
            for mode in ft.MODES for d in lab["runs"][mode]["decisions"]]


CARD = """---
pretty_name: Robot Reel Factory Twin — closed loop vs. shadow twin
license: apache-2.0
language:
  - en
size_categories:
  - 1K<n<10K
task_categories:
  - time-series-forecasting
tags:
  - digital-twin
  - manufacturing
  - predictive-maintenance
  - energy
  - simulation
  - blender
  - openusd
configs:
  - config_name: pairs
    default: true
    data_files:
      - split: test
        path: pairs.csv
  - config_name: seeds
    data_files:
      - split: test
        path: seeds.csv
  - config_name: samples
    data_files:
      - split: test
        path: samples.csv
  - config_name: decisions
    data_files:
      - split: test
        path: decisions.csv
---

# Robot Reel Factory Twin: close the loop

**12 paired simulated shifts of a factory and campus, each run twice: once with
the digital twin's commands applied (closed loop) and once with the identical
twin only advising (shadow).** Both modes of a pair share every disturbance and
sensor-noise sample.

| Over 12 pairs | Shadow twin | Closed loop |
| --- | ---: | ---: |
| CNC 2 spindle failures | __SF__ | __CF__ |
| Billing intervals over the 520 kW limit | __SO__ | __CO__ |
| Pairs with more good parts | | __IMP__ of 12 (__WORSE__ fewer) |

- [Interactive lab](https://noteflowai.github.io/robot-reel/factory-twin/) ·
  [Hugging Face Space](https://huggingface.co/spaces/glayguo/robot-reel) ·
  [Methods](https://github.com/noteflowai/robot-reel/blob/main/examples/factory-twin/METHODS.md) ·
  [Blender + OpenUSD projects](https://github.com/noteflowai/robot-reel/releases/latest/download/factory-twin-blender.zip)

## Configs

- `pairs` (default): one row per seed, closed-loop and shadow KPIs side by side.
- `seeds`: one row per seed and mode.
- `samples`: every 5-second sample of the featured seed (__FEATURED__) in both
  modes: plant truth (hidden spindle wear, buffers, power flows, hall
  temperature) beside the twin's estimates (wear ± σ, remaining life, demand
  forecast, demand level).
- `decisions`: every twin log entry for the featured seed with the evidence it
  had received and its model's prediction. `actuated` is `True` only in closed mode.

```python
from datasets import load_dataset
pairs = load_dataset("glayguo/robot-reel-factory-twin", "pairs", split="test")
samples = load_dataset("glayguo/robot-reel-factory-twin", "samples", split="test")
```

## Scope

This is a simulation. The plant model, its parameters and the twin's cost
weights were chosen for the demonstration and are **not calibrated to a real
factory**; nothing here is measured. It is evaluation output for inspecting a
digital-twin loop, not training data or a benchmark. Every number re-executes
bit for bit: `pip install robot-reel` then
`robot-reel factory-twin --output factory-twin --verify --all-seeds` on the
extracted offline lab.

`source-manifest.json` records the source commit and SHA-256 of every file;
tables derive from `lab.json` and `seeds.json` with those hashes. Source commit:
`__SOURCE_COMMIT__`.
"""


def build(output, allow_dirty=False):
    output = Path(output)
    if output.is_symlink() or output.exists():
        raise ValueError("Choose a new dataset output directory")
    source = subprocess.check_output(["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True).strip()
    dirty = bool(subprocess.check_output(["git", "-C", str(ROOT), "status", "--porcelain", "--", "docs", "robot_reel",
                                          "scripts"], text=True).strip())
    if dirty and not allow_dirty:
        raise ValueError("Commit source changes before publishing")
    ft.verify(SITE)
    lab, seeds = ft.decode((SITE / "lab.json").read_bytes()), ft.decode((SITE / "seeds.json").read_bytes())
    s = seeds["summary"]
    card = CARD
    for key, value in (("__SF__", s["shadow_failures"]), ("__CF__", s["closed_failures"]),
                       ("__SO__", s["shadow_intervals_over_limit"]), ("__CO__", s["closed_intervals_over_limit"]),
                       ("__IMP__", s["good_units_gain"]["pairs_improved"]),
                       ("__WORSE__", s["good_units_gain"]["pairs_worse"]),
                       ("__FEATURED__", ft.FEATURED_SEED), ("__SOURCE_COMMIT__", source)):
        card = card.replace(key, str(value))
    output.mkdir(parents=True)
    (output / "README.md").write_text(card)
    seed_fields = ("seed", "mode", "featured", *KPIS)
    (output / "seeds.csv").write_text(table(seed_fields, seed_rows(seeds)))
    pair_fields = ("seed", *(f"{m}_{k}" for k in KPIS for m in ("shadow", "closed")), "good_units_gain")
    (output / "pairs.csv").write_text(table(pair_fields, pair_rows(seeds)))
    (output / "samples.csv").write_text(table(SAMPLE_FIELDS, sample_rows(lab)))
    (output / "decisions.csv").write_text(table(
        ("mode", "t", "clock", "kind", "action", "actuated", "evidence", "prediction"), decision_rows(lab)))
    for name in ("seeds.json", "METHODS.md", "LICENSE", "poster.png"):
        shutil.copyfile(SITE / name, output / name)
    files = {path.name: {"bytes": path.stat().st_size, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
             for path in sorted(output.iterdir())}
    record = {"schema": "robot-reel-factory-twin-dataset-1", "source_commit": source, "source_dirty": dirty,
              "inputs": {name: hashlib.sha256((SITE / name).read_bytes()).hexdigest()
                         for name in ("lab.json", "seeds.json", "trace-closed.json", "trace-shadow.json")},
              "pairs": len(seeds["seeds"]), "samples": ft.SAMPLES * len(ft.MODES), "files": files}
    (output / "source-manifest.json").write_text(json.dumps(record, indent=2) + "\n")
    return record


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--allow-dirty", action="store_true")
    args = parser.parse_args()
    print(json.dumps(build(args.output, args.allow_dirty), indent=2))
