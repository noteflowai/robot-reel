# Factory Twin Lab: methods and limits

This folder is a complete, offline copy of a closed-loop digital-twin
experiment. A simulated factory and campus (the **plant**) streams telemetry to
a **digital twin**. The twin keeps its own state from that telemetry alone,
estimates what it cannot measure, predicts the consequences of candidate
actions and sends commands back. Every run is paired: in **closed** mode the
commands reach the plant; in **shadow** mode the same twin runs, logs the same
kinds of decisions and sends nothing.

Everything is simulated. The plant, its parameters and the twin's cost weights
were chosen for this demonstration and are **not calibrated to a real site**.
The pair shows what closing this particular loop changes inside this model.

## The plant (ground truth, 1 s steps, 10:00–13:00)

| Subsystem | Model |
| --- | --- |
| Line | Kitting → CNC 1 ‖ CNC 2 → robotic weld cell → assembly → inspection. Finite buffers (10, 10, 6, 6, 24 parts); blocking and starving. Nominal cycles 38, 80, 80, 42, 41, 34 s. |
| CNC 2 spindle | Hidden wear `w` grows per busy second at a seed-dependent rate. Cycle time × (1 + 0.5 w); defect probability 0.006 + 0.9 max(0, w − 0.5)². At a seed-dependent threshold (0.96–1.04) the spindle fails: the part is scrapped and repair takes 45 min. Planned service takes 15 min. Derating to 80 % feed cuts wear accrual to 45 %. |
| Other events | Weld tip dressing (90 s every 40 welds); assembly and inspection lunch break 12:00–12:20. |
| Logistics | Three AMRs carry batches of 8 finished parts from the hall to the warehouse along a fixed route. |
| Hall climate | One thermal node: machine heat, solar gain, envelope conductance to outdoor air and a proportional chiller with a setpoint. |
| Energy | Machine, base, chiller (COP falls with outdoor temperature), AMR and EV loads; a 520 kWp solar carport with one cloud passage per seed; eight 22 kW EV chargers scheduled 11:30–12:45. Import is billed as the mean of each 15-minute interval against a 520 kW limit. |

Randomness comes from a counter-based generator keyed by seed, stream and
index, so both modes of a pair see identical disturbances and sensor noise.
Only integer and IEEE-754 arithmetic influences the simulation; the Python
standard library re-executes each run bit for bit.

## Telemetry (what the twin receives)

Every 5 s the plant emits five packet groups — PLC (station states, cycle
progress, buffer counts, counters), CNC (vibration, spindle temperature),
energy meter (load, PV, chiller, EV, interval energy so far), hall climate and
AMR poses. Values carry sensor noise and rounding, and each group is lost with
2–3 % probability. Packets arrive one sample (5 s) late. The twin never reads
plant state directly: `--verify` replays the twin from the recorded telemetry
and requires identical estimates and decisions.

## The twin

1. **Sync.** The twin mirrors station states, buffers and AMR poses from the
   last packet of each group, and keeps the age of each group.
2. **Estimate.** An extended Kalman filter over CNC 2 `[wear, wear rate]`
   uses the quadratic vibration model `v = 2.4 + 5.5 w² + noise` while busy.
   The twin starts from nominal parameters (initial wear 0.45, nominal rate,
   threshold 1.0) that differ from every seed's hidden values.
3. **Predict.** When the conservative (2σ) remaining life drops below
   150 busy minutes, every 5 minutes it forward-simulates its own line model for
   90 minutes under 14 candidate plans: service now, in 10, 20, 30, 45 or
   60 minutes, or not at all, each with and without derating. Each plan's
   value is expected good parts minus the spindle life thrown away by early
   service (40 parts per unit of wear) and minus 25 parts if the plan fails.
   Every minute it forecasts the current and next billing interval.
4. **Decide.** It requests service when "now" is the best plan, switches
   derating only when the gain exceeds 1.5 parts, and moves through four demand
   levels (hall setpoint +1/+2 °C, EV chargers at 50 %) with hysteresis and a
   comfort guard below 27 °C.
5. **Act.** In closed mode a command reaches the plant 5 s after it is sent.

## Results in this folder

`seeds.json` holds all 12 pairs; `trace-closed.json` and `trace-shadow.json`
hold every sample of the featured seed: plant truth, raw telemetry packets,
twin snapshots, the decision log with evidence and prediction, and forecast
checks against what the plant then produced. `lab.json` is the browser payload
derived from them.

Over the 12 pairs the closed loop had no spindle failures (shadow: 11) and no
billing interval over the limit (shadow: 8). Good parts rose in 10 pairs and
fell in 2; those two seeds' failures happen late or not at all, so earlier
service costs output inside the 3-hour window. Read the exact values in
`seeds.json`.

## The 3D model

`scripts/build_factory_twin_blender.py` builds the campus procedurally in
Blender 5.2 LTS: assembly hall with steel frame, crane, racking and cutaway
roof; the six stations (CNC enclosures, a fenced weld cell with two six-axis
robots, assembly benches with cobots, an inspection portal); buffers, pallets,
AMRs, warehouse with racks and trucks, office tower with the twin operations
center, energy center, substation, chillers, cooling and water towers, solar
carport, chargers, roads, cars and trees. No external meshes, textures or HDRIs
are used. The recorded samples drive constant-interpolated keyframes (frame
`k + 1` = sample `k`, 30 fps); Blender performs no physics.

`blender-check.json` records `scripts/check_factory_twin_blender.py` for both
modes: every animated channel at every frame compared with `lab.json`,
independent checks of AMR positions, visible crates, beacon colors and the
wear gauge, constant hold between frames, and an OpenUSD export whose animated
prim transforms were read back at every time code with `pxr`. `robot-reel
factory-twin --verify` checks that receipt's input hash but does not rerun
Blender. The `.blend` and `.usdc` files are release assets.

## Verify

```bash
robot-reel factory-twin --output factory-twin --verify              # featured pair
robot-reel factory-twin --output factory-twin --verify --all-seeds  # all 12 pairs
```

Both commands need only Python 3.12 and the standard library.
