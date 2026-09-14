### 项目地址

https://github.com/noteflowai/robot-reel

### 类别

人工智能

### 项目标题

在浏览器里逐帧检查机器人与物理仿真实验

### 项目描述

Robot Reel 将机器人策略和物理仿真的录制结果做成可交互网页。无需安装即可对照机器人动作、旋转布料模型、探索双摆轨迹，并下载源数据、校验清单和离线实验包。支持将已录制的运动通过 OpenUSD 带入 Blender，适合具身智能教学、实验复盘与技术演示。代码采用 Apache-2.0，第三方模型和素材遵循上游许可。

### 亮点

- 不只提供演示视频：30 次 SmolVLA 单任务闭环仿真的全部结果都可检查，
  包括失败，支持双相机对照和轨迹差异定位。
- 三组 GPU 布料录制可以叠加查看，导出当前样本的 1080p 图片与 JSON；
  USD 和 Blender 导入检查覆盖全部 42,471 个顶点样本。
- 十二个 CPU Newton 双摆世界组成可旋转的“时间雕塑”，浏览器回放可离线打开。
- 初学者可以先体验交互，再按文档核对源轨迹、复现仿真，或在 Blender 中修改
  灯光和机位。浏览器查看与录制新仿真的环境要求分别说明。

这是维护者自荐，项目仍处于早期阶段。策略实验限于一个 LIBERO 任务，
并非官方基准成绩；布料未启用碰撞和自接触，参数不是经过标定的真实材料；
这些都是仿真记录，没有真实机器人验证。

### 示例代码

从源码检出目录，使用 Python 3.12+ 校验附带的布料录制。
此操作只读，使用标准库，不需要 GPU 或启动仿真：

```bash
python3 -S -m robot_reel.cli cloth --output docs/cloth --verify
```

### 截图或演示视频

在线体验：https://huggingface.co/spaces/glayguo/robot-reel

![四个可以直接体验的物理 AI 实验](https://huggingface.co/spaces/glayguo/robot-reel/resolve/main/thumbnail.png)

布料实验：https://noteflowai.github.io/robot-reel/cloth/

复现及 Blender 导入说明：https://github.com/noteflowai/robot-reel/blob/858886243c100f866be773d2c32eb13c2e2da917/docs/cloth.md

交互功能更新：Stress Lab 新增完整配对结果分组。相机条件净增两次成功，实际包含三次改善和一次退步；可点击对应种子查看录像，导出完整报告，并用安装后的 CLI 独立核验。0.8.0 正式发行包已包含配对分析、布料样本导入与高清图导出，同时提供完整配对 JSON 和校验和；两个离线包均经过实际安装程序导出及桌面、手机断网检查。


新增 **Microduck 动作实验室**：选择 14 个关节中的任意一个，旋转三维结构、叠加策略目标、点击误差热图，与两组原始录像同步对照。保留 8,400 个实测关节样本，支持指定帧分享、JSON/CSV 导出和完整离线包。它参考 Microduck Anatomy 的交互思路做原创实现；模型衍生结构与录像保留上游非商业、相同方式共享条款。三维结构固定机身坐标，实验使用 PD 执行器近似仿真，不推断真实硬件能力。

体验：https://noteflowai.github.io/robot-reel/microduck-lab/
