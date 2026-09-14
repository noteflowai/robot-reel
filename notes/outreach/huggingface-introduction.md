**Solver Lab: one launch, mind the timestep.** Robot Reel 0.10.0 adds six actual L40S/CUDA flights from Genesis 1.4.1 and Newton 1.6.0. Use 30, 120 or 480 integration steps per second, compare the recordings with the analytic solution, and inspect every position, velocity and energy diagnostic.

[Open Solver Lab](https://glayguo-robot-reel.static.hf.space/solver-lab/) · [All five labs](https://huggingface.co/spaces/glayguo/robot-reel) · [Release 0.10.0](https://github.com/noteflowai/robot-reel/releases/tag/v0.10.0) · [Methods](https://github.com/noteflowai/robot-reel/blob/v0.10.0/docs/solver-lab.md)

The measured maximum position error drops from about **32.70 cm to 2.05 cm** as the timestep shrinks. Both engines produce matching values in this no-contact, no-drag flight. It is an integration diagnostic, not a simulator ranking or a real-robot result.

All 366 recorded states are downloadable as JSON/CSV. Genesis native trajectories and the editable OpenUSD were read back sample by sample. Take the complete lab offline and use `robot-reel solver-lab --output solver-lab --verify` to check its sources and recompute its metrics without a GPU. The browser runs no simulation.

The existing Microduck, SmolVLA, cloth and Butterfly labs retain their recordings. Explore learned joint targets, paired policy failures, deforming cloth and pendulum trajectories in the same Space.

Maintainer post, developed with AI assistance. Original procedural code and Solver Lab data are Apache-2.0; third-party media retain their original terms. File consistency is separate from producer authentication.
