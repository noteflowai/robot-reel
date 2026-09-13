# Robot Reel / Hugging Face launch

Target Space: `glayguo/robot-reel`.
Launch copy for the Space Community. Published announcements are visible under
the Space’s Community tab; other channel posts remain drafts.

## Published entry points

- [Interactive Space](https://huggingface.co/spaces/glayguo/robot-reel)
- [Pinned Community introduction](https://huggingface.co/spaces/glayguo/robot-reel/discussions/1)
- [Model and data collection](https://huggingface.co/collections/glayguo/robot-reel-physical-ai-replay-lab-6aa67e950ba650285033a4d0): the Space, the actual SmolVLA
  checkpoint and the LIBERO asset repository, with the recorded revisions in
  each source note. Published publicly on 2026-09-13.

The collection groups an independent project with its credited upstream sources;
it does not imply an upstream endorsement or change any asset license.

## Space Community announcement

Title: **Three Physical AI experiments you can replay and inspect**

Robot Reel is now on Hugging Face: three interactive experiments with the
recordings that produced the pictures.

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

## Chinese short post

Robot Reel 已准备好把三个物理 AI 实验带到 Hugging Face：逐帧检查 30 次
SmolVLA 闭环运行，旋转对照 GPU 布料形变，或探索 12 个 Newton 世界如何展开成
三维时间雕塑。网页托管原始录制，打开即可体验；还能导出附实测指标的图片，
核验共享样本，并把 OpenUSD 场景带入 Blender。

欢迎反馈：你希望下一步接入哪一种策略或仿真日志？复盘失败时还缺哪些记录？

The remaining channel-specific drafts are in `launch-kit.md`. Publishing this
Space does not imply those drafts have been posted to other communities.
