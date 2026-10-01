# Robot Reel roadmap

Updated: 2026-09-29 · Owner: NoteFlowAI maintainer · Review: weekly, with a monthly product decision.

This is the current proposed product direction. “Now / Next / Later” expresses priority, not promised release dates. The earlier [research roadmap](docs/roadmap.zh-CN.md) remains useful background.

## User and outcome

Help a robotics practitioner answer: **what failed in my recorded experiment, where did it fail, and what evidence supports my next change?**

The primary journey is an owned episode → synchronized replay → identified failure → portable evidence shared with a collaborator. A simulation demonstration is a learning aid; it is not proof that the tool works on a user's recordings.

## Current baseline

Reviewed `f69ffee` / v0.17.1. The project already offers LeRobot episode inspection, camera/joint replay, evidence hashes, policy comparison and specialized physics/stress labs. The next work should make those capabilities easier to use and verify before adding more labs.

External first-use time, repeat use and debugging success have not been established by this review. Recent issue history does not provide an external demand backlog.

## External evidence and positioning — reviewed 2026-09-29

[Rerun](https://rerun.io/) already offers multimodal logging, visualization and data querying. [Foxglove](https://docs.foxglove.dev/docs/data) already supports recording management, events, metadata and robotics inspection. Their product descriptions establish capabilities, not independent comparisons. A general viewer, offline mode or a failure timeline alone is insufficient differentiation.

Robot Reel already supports [LeRobot v3/v2](docs/lerobot.md), native Rerun export and MCAP/Foxglove inspection; do not rebuild these integrations. Test the narrower hypothesis that a small, portable, provenance-preserving diagnosis is easier to produce and share. [LeRobot's v3 specification](https://huggingface.co/docs/lerobot/lerobot-dataset-v3) makes episode metadata and video offsets essential. [Upstream timestamp report #4524](https://github.com/huggingface/lerobot/issues/4524) is a reproduction lead, not a confirmed defect in Robot Reel or proof of demand.

For RR-01/RR-02, compare the same permitted episode and debugging question against an existing Rerun/LeRobot workflow. Record setup effort, correct diagnosis, missing evidence and collaborator reopening time. Within 30 days, seek three independent attempts. If the baseline solves the task as well, prefer an upstream contribution or a smaller integration over another viewer feature. User recruitment and improvement targets remain unfulfilled validation work.

## Now — make one real workflow dependable

| ID | Outcome | Acceptance evidence |
| --- | --- | --- |
| RR-01 | A new user can inspect their own episode | Publish a reproducible path from an independently sourced, permitted dataset to replay. Cover missing frames, timestamps, cameras and unsupported schemas with actionable errors. Observe three first-use attempts; target first useful replay within 15 minutes and record failures, including installation time. |
| RR-02 | A teammate can reproduce the diagnosis | Export a compact evidence bundle with input hashes, frame/time selection, configuration and limitations. Another clean environment must reopen it and locate the same failure; a tampered input must be identified. Reuse existing export/provenance code. |
| RR-03 | Existing labs make appropriately limited claims | Inventory each lab's task, baseline, sample size, seed and measured result. Separate real recordings, synthetic fixtures and illustrative scenes. Link each public conclusion to its saved evidence and preserve failed runs. |

RR-03 progress (2026-10-01): [docs/claims.md](docs/claims.md) links 23 README headline numbers across 10 labs to their evidence files and evidence kind, checks that the Chinese README states the same numbers, and lists each lab's task, sample, seeds, runtime and comparison read from its evidence. It also covers headline numbers on the website landing page, the Space card and page, and the results dataset card. `scripts/claims_inventory.py` runs in the standard test suite. Still open: static prose in individual lab page templates (their data panels render from payloads that each lab's verifier compares with its source files).

Prioritize blocking defects in this journey ahead of a new visualization or statistical variation.

## Next — after the first-use evidence

| ID | Outcome | Entry and exit gates |
| --- | --- | --- |
| RR-04 | Compare two runs without ambiguous alignment | Start only after RR-01 identifies actual alignment needs. Support one documented recording format end to end; show unmatched frames and uncertainty. Verify the same comparison on a held-out episode. |
| RR-05 | Reuse evaluation decisions across tools | Agree a versioned evidence exchange with EvalArc. Robot Reel owns capture, synchronization and replay; EvalArc owns generic checks and regression decisions. Round-trip one evidence bundle without two competing scoring engines. |

## Later — conditional research

Multi-engine simulation, Gaussian-splat twins and additional soft-body labs remain experiments. Promote one only when a reproducible user case cannot be served by the current workflow, data is available, and an affordable acceptance experiment exists.

## Measures and decisions

- Record first-use completion/time and the reason for abandonment; do not treat downloads or stars as successful use.
- Seek three independent trial users, then check whether at least two return with another episode within four weeks. These are validation targets, not existing results.
- Track reproduced diagnoses, invalid-data failures, support effort and regression rate.
- If repeat use does not emerge, simplify onboarding and interview trial users before expanding the lab catalog.
- Collect diagnostics only with consent; no recording uploads or telemetry are required by default.

## Boundaries and delivery

No robot actuation, training platform, news feed or general Agent scheduler. Preserve offline inspection and established commands.

Every development task must reference a milestone ID, observed problem, acceptance evidence and a follow-up date. A no-change, defect fix or onboarding improvement is a valid outcome. A daily new-feature quota is not a product goal. Keep one active product milestone; pass existing checks and verify the exact released commit before claiming delivery.
