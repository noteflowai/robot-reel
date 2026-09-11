# Robot Reel

**看机器人，也看清每一步。**

把物理 AI 仿真制作成可分享的视频，同时保留能逐帧检查的动作记录。
现在可以运行 **Microduck 官方步行策略**、对比两种汽车制动策略，或让
Strands Agent 控制机械臂。

[**Microduck 交互演示**](https://noteflowai.github.io/robot-reel/) ·
[**汽车制动对比**](https://noteflowai.github.io/robot-reel/braking/) ·
[**Agent 机械臂**](https://noteflowai.github.io/robot-reel/studio/) ·
[English](README.md)

![Microduck 官方策略仿真](docs/microduck/media/preview.gif)

[视频与证据包下载](https://github.com/noteflowai/robot-reel/releases/tag/v0.2.0)

## 已实现的三种场景

| 场景 | 实际运行内容 | 可查看的数据 |
| --- | --- | --- |
| Microduck | Pollen Robotics 官方 ONNX 步行策略，50 Hz，CPU MuJoCo | 14 个关节、每次策略输出、机身位移、策略校验值 |
| 汽车制动 | 相同初始条件下，两种脚本控制器驱动一维刚体车辆模型 | 速度、障碍间距、制动力、接触记录 |
| Studio | SO-100 位置执行器，可选实时 Agent；G1 为姿态编排 | 四次动作、目标与实测值、home 误差 |

网页不需要安装或登录：支持动作跳转、逐帧前进后退、切换关节、查看曲线、
分享具体时刻。还能调整机械臂的镜头计划，下载 JSON 后在本地生成自己的视频。
网页上的计划编辑器不会改变正在回放的视频，也不是在线实时仿真。

## 运行 Microduck

需要 Python 3.12+ 和 OpenGL。当前实测环境是 Linux、NVIDIA L40S、EGL。

```bash
git clone https://github.com/noteflowai/robot-reel.git
cd robot-reel
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e '.[microduck]'
robot-reel --pack microduck --output artifacts/duck
python -m robot_reel.verify artifacts/duck
```

直接用浏览器打开 `artifacts/duck/index.html`。第一次运行会下载固定版本的
官方模型资产和策略；不需要训练，也不需要模型服务账号。推理使用 CPU。
设置 `ROBOT_REEL_CACHE` 可以修改缓存位置。

当前适配使用上游提供的 XML PD 执行器回退方式，**不是官方部署使用的 BAM
电机模型**，因此录制的仿真结果不能等同于真机表现。

Microduck 上游将 3D 模型标为 **Creative Commons BY-SA-NC**，README 未标明
版本；Microduck 视频保留相关资产署名和非商业/相同方式共享条款。
Robot Reel 录制代码使用 Apache-2.0，不重新授权上游资产。详见
[第三方说明](THIRD_PARTY.md)。

## 汽车与机械臂

其他场景只需要 `pip install -e .`：

```bash
robot-reel --pack braking --output artifacts/braking
robot-reel --output artifacts/studio
robot-reel --shots examples/close-up.json --output artifacts/my-film
```

汽车场景是可重复的一维制动对照，不是 CARLA/AlpaSim 集成，也没有运行
Alpamayo 驾驶模型。它用于展示如何把控制差异、接触结果和视频联系起来；
不代表道路安全认证。汽车热点与后续真实接入边界见
[汽车物理 AI 说明](docs/automotive.md)。

G1 是固定根节点的运动学姿态展示，没有行走或学习得到的平衡策略。

## 输出与复核

每次输出包括横版 1280×720、竖版 720×1280 的 30 fps 视频、交互回放 HTML、
原始仿真画面、JSON 轨迹、封面和 SHA-256 清单。Microduck 成片 15 秒，
汽车对比 17 秒，Studio 31 秒。配乐为原创程序合成。

```bash
robot-reel --render-only --output artifacts/duck
python -m robot_reel.viewer artifacts/duck
```

校验器检查必需文件哈希、帧序、有限数值、动作与录制帧的一致性、策略输出与
画面的对应，以及制动接触汇总。哈希不是数字签名，不证明独立真实性、通用
策略能力或物理安全。

## 可选模型导演

配置 AWS SDK 凭据，并选择可用的 Bedrock 模型或推理配置后运行：

```bash
robot-reel --agent --model YOUR_BEDROCK_MODEL_OR_INFERENCE_PROFILE \
  --region us-west-2 --output artifacts/agent-film
```

这会产生模型调用费用。Agent 先检查关节，再完成限定的四次动作；提示词和
最终回复会保存，视频省略模型思考等待。它不是开放式自主任务规划。

欢迎贡献真实策略对比、公共后端适配和 AlpaSim/CARLA 录制导入。
详见 [CONTRIBUTING.md](CONTRIBUTING.md)。
