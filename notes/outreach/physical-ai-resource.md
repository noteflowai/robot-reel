### Resource name

Robot Reel

### URL

https://github.com/noteflowai/robot-reel

### Proposed category

Evaluation Methodology

### One-line description

Recorded robot-policy inspection tools with paired trial replay, source traces,
MCAP telemetry and portable browser experiments.

### Why is this high-signal?

Maintainer self-submission. The relevant part for this category is the
[Stress Lab](https://noteflowai.github.io/robot-reel/stress/):
30 closed-loop SmolVLA simulations on one LIBERO Spatial task, with ten paired
initial states across reference lighting, reduced light and a shifted camera.
All outcomes are retained. Readers can select a trial, compare both cameras,
inspect action/state telemetry and locate the largest measured end-effector
difference.

This complements the listed LeRobot evaluation scripts with an inspectable,
portable record of a small experiment. The
[protocol and limitations](https://github.com/noteflowai/robot-reel/blob/858886243c100f866be773d2c32eb13c2e2da917/docs/stress.md)
and source recordings are included. It is a single-task diagnostic with a
160-action cap, not an official LIBERO score, evidence of sim-to-real validity
or a replacement for multi-task statistical evaluation.

The repository also includes recorded Newton/OpenUSD experiments, but this
suggestion is for one primary category only and does not propose a new
simulator, model or benchmark.

### Maintenance / credibility evidence

- Public repository created September 11, 2026; actively updated September 13.
  This is an early project with one GitHub star at submission, below the
  preferred 100-star level. No established adoption or production use is claimed.
- Apache-2.0 code, reproduction guides, source manifests and an interactive
  [Hugging Face Space](https://huggingface.co/spaces/glayguo/robot-reel).
  Third-party models and assets retain their upstream terms.
- The current source passed the repository's six validation jobs:
  [Check run](https://github.com/noteflowai/robot-reel/actions/runs/34753574145).
  These are project checks, not independent certification.
- Included cloth and rigid-body recordings were also checked locally with the
  documented standard-library verifiers before this submission.

### Start-here proposal (optional)

- [ ] This is a Start-here proposal (replaces the existing Start-here entry for the chosen category).

### Confirmations

- [x] I have read CONTRIBUTING.md.
- [x] I have personally used or can genuinely recommend this resource.
- [x] This resource is not already listed.
