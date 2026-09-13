Robot Reel is now on Hugging Face: three interactive experiments with the
recordings that produced the pictures.

![Robot Reel: recorded SmolVLA, cloth and Newton experiments](https://huggingface.co/spaces/glayguo/robot-reel/resolve/main/thumbnail.png)

- **SmolVLA Stress Lab:** 30 real closed-loop trials on one LIBERO task, across
  ten paired initial states and three scene conditions. Every trial is retained,
  including failures. Compare both camera views, applied controls and measured
  trajectories.
- **GPU Cloth Lab:** three independent Newton cloth runs with different bending
  coefficients. Orbit the recorded meshes, export a measured figure, reopen a
  checked sample JSON, or import the original OpenUSD geometry into Blender.
- **Butterfly Lab:** twelve isolated Newton worlds released 0.05° apart,
  arranged into a three-dimensional time sculpture.

All three run directly in this Space from saved data. No live inference,
simulation or model-service account is needed to explore.

The policy recording uses `HuggingFaceVLA/smolvla_libero`, LeRobot and LIBERO;
the code and all source revisions are credited in the lab. This is a controlled
diagnostic, not an official benchmark or a real-robot result.

Try it: https://huggingface.co/spaces/glayguo/robot-reel

Source and all 13 demos: https://github.com/noteflowai/robot-reel

**Which recorded policy or simulator output would you like to inspect next?
What telemetry is missing when you try to explain a failure?**

**Model and data sources:** https://huggingface.co/collections/glayguo/robot-reel-physical-ai-replay-lab-6aa67e950ba650285033a4d0

Start with the Space, then inspect the actual SmolVLA policy and LIBERO asset snapshots. The collection notes record the source revisions and experiment scope.


**New: see what a net success rate hides.** The Stress Lab now groups every paired seed into both-successful, success-lost, success-gained and neither-completed outcomes. The camera condition's net gain of two contains three gains and one loss. Select any group to inspect its source recordings; exporting still retains both conditions and all seeds.

[Open paired outcomes](https://glayguo-robot-reel.static.hf.space/stress/index.html#outcomes). Robot Reel **0.8.0** now includes this workflow in the installed CLI and complete offline ZIP, with a matching, checksummed paired-outcome JSON. Cloth Lab also gains portable sample import and 1080p figures in the release. Both ZIPs are exported by the installed wheel and tested without network access at desktop and mobile sizes. [Download and verify](https://github.com/noteflowai/robot-reel/releases/tag/v0.8.0). These are descriptive results from one task, not a significance test or general robustness claim.

Maintainer disclosure: Robot Reel is our independent project. This update was written with AI assistance.
