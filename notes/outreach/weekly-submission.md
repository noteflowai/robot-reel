维护者自荐：**robot-reel**。Robot Reel 将机器人策略与物理仿真录制做成交互网页。可对照 SmolVLA 的成功与失败、旋转 GPU 布料模型、探索 Microduck 关节和双摆轨迹，下载源数据与离线包。新版把播放控制放到三维视图旁，补齐键盘操作、视频重试和文件导出反馈；收到帧记录后可用安装包独立复核。适合具身智能教学、实验复盘与技术演示。

在线体验：https://huggingface.co/spaces/glayguo/robot-reel

- **Microduck 动作实验室**：两组原始步行记录，14 个关节、8,400 个实测角度样本，支持目标叠加、逐帧分享、JSON/CSV 和完整离线 ZIP。0.9.1 改善手机布局，支持四向键盘视角控制；视频失败可重试，并保留所选帧和关节。
- **从演示到交付**：`robot-reel microduck-review` 可独立核对离线包和帧 JSON，不需要源码目录、GPU 或模型服务。发布过程同步整个查看器并核对清单，原始录制保留原样。
- **GPU 布料与 Blender**：三组 Newton 布料录制只改变弯曲系数，可旋转叠加、导出测量图片，并通过 OpenUSD 进入 Blender。
- **保留失败证据**：SmolVLA 的 30 次单任务闭环仿真全部保留；十二个双摆世界还可组成三维时间轨迹。

```sh
python3 -S -m robot_reel.cli cloth --output docs/cloth --verify
```

从源码检出目录，用 Python 3.12+ 只读校验附带的布料记录，无需 GPU：

项目：https://github.com/noteflowai/robot-reel
版本：https://github.com/noteflowai/robot-reel/releases/tag/v0.9.1

![在浏览器里逐帧检查机器人与物理仿真实验](https://huggingface.co/spaces/glayguo/robot-reel/resolve/main/thumbnail.png)

项目由本账号维护，与 AI 结对开发，仍处于早期阶段。代码采用 Apache-2.0；第三方模型与素材遵守上游许可。Microduck 使用 PD 近似仿真，模型衍生结构和录像保留非商业／相同方式共享条款。策略实验为单任务受控诊断，布料未启用碰撞和自接触；这些录制不提供真实机器人能力证明。
