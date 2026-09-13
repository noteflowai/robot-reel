# Robot Reel 发布定位

## 当前推广入口

Hugging Face Space 原生提供 SmolVLA 压力实验、GPU 布料和 Newton 蝴蝶效应
三个交互场景，并通过模型、数据集元信息关联实际使用的上游资产。入口：
https://huggingface.co/spaces/glayguo/robot-reel

以 Space Community 的首发介绍承接反馈，GitHub 首页与中英文 README 提供
互链；后续按真实问题分享具体实验。发布记录见
[huggingface-launch.md](huggingface-launch.md)，其他平台文案仍是草稿。
观察访客实际体验、复现反馈和有效贡献，不将上线或平台关联写成流量增长保证。

## 初始定位记录

核心承诺：一条命令，把机器人仿真做成视频，同时带上可复核的动作记录。

当前差异：Strands Robots 已经提供自然语言机器人接口；直接把它再包装成
“自然语言控制机器人”缺少区别。Robot Reel 把输出明确收窄为影片、原始帧、
轨迹和核验，适合教学、研究演示和 Agent 工具展示。

首版发布应包含：

1. 31 秒横版视频、竖版视频、封面及原始记录下载。
2. 不需要模型账号的复现路径，以及可选实时模型路径。
3. 中英文 README，明确 G1 是姿态展示、SO-100 是位置控制仿真。
4. 固定依赖、可运行检查和模型资产署名。

下一版优先考虑真实策略 rollout 的录制与任务成功条件，比如同一场景下的
抓取成功/失败对比。不要先扩张到几十个未经验证的机器人型号。

发布文案草稿：

> Robot demos should be easy to share—and easy to inspect.
> Robot Reel turns a MuJoCo run into a short film with joint telemetry and a
> motion trace. Try the no-credentials demo, or let a Strands agent direct the arm.
> The G1 segment is explicitly a kinematic showcase. No hidden claim of autonomy.

项目热度没有保证。首轮观察可复现反馈、有效 issue 和外部贡献；
不购买 Star，不把安装包的机型条目数当作已验证支持范围。
