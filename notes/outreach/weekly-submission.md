维护者自荐：**robot-reel**。Robot Reel 将机器人策略与物理仿真录制做成交互实验室。新版在 L40S 上录制 Genesis 与 Newton 的六次抛体运动，对照解析解检查步长误差，保留全部 366 个状态和原生回放，并导出可编辑 OpenUSD。另有 SmolVLA 失败复盘、GPU 布料和 Microduck 关节探索，适合具身智能教学、实验复盘与客户技术演示。

- **Solver Lab**：Genesis 1.4.1 与 Newton 1.6.0 各录制三种步长，支持轨迹、误差曲线、逐帧操作和完整 JSON/CSV；最大位置误差随步长缩小从约 32.70 厘米降到 2.05 厘米。
- **原生记录可复核**：逐帧读回 Genesis 轨迹和全部 OpenUSD 样本；安装包可独立核验并导出完整离线实验。
- **五个在线实验室**：保留 30 次 SmolVLA 单任务运行、42,471 个布料顶点样本、十二组双摆和两段 Microduck 步行，支持按场景查看记录。

在线体验：https://huggingface.co/spaces/glayguo/robot-reel

项目：https://github.com/noteflowai/robot-reel

版本：https://github.com/noteflowai/robot-reel/releases/tag/v0.10.0

从源码检出目录，以 Python 3.12+ 只读核对完整实验：

```sh
python3 -S -m robot_reel.cli solver-lab --output docs/solver-lab --verify
```

![Solver Lab：真实 CUDA 轨迹、步长控制与误差曲线](https://github.com/noteflowai/robot-reel/raw/v0.10.0/docs/solver-lab/poster.png)

项目由本账号维护，与 AI 结对开发，仍处于早期阶段。代码及原创抛体场景采用 Apache-2.0；第三方素材遵守上游许可。Solver Lab 是无接触、无阻力的积分误差实验，两引擎在此场景中数值相同，不构成仿真器排名或真实机器人准确率证明。Microduck 衍生结构与录像保留非商业／相同方式共享条款。
