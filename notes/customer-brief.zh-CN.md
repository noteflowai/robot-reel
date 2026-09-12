# 面向关注 PAI 创新场景客户的介绍

Robot Reel 把物理 AI（Physical AI）的技术能力变成客户可以直接体验的创新场景：
在“策略压力实验室”对照光照和视角变化下的 30 次真实闭环运行，
由 NVIDIA L40S 执行策略推理，从成功或失败样本直接查看双相机、
动作、推理记录和轨迹差异；
在“蝴蝶效应实验室”旋转查看 12 组仿真轨迹如何展开成三维时间雕塑，
观看 SmolVLA 根据语言指令完成机械臂仿真任务，拖动对照原始物理画面与 Blender
电影场景，或让 MCP Agent 编排镜头、字幕和慢动作。项目还展示机器人
学习策略步行，以及 Newton 到 OpenUSD 的三维流程。每个演示都保留可检查的
动作或姿态记录，并提供相应的视频、证据和场景文件。压力实验还可下载完整离线包、
CSV 与 MCAP 遥测数据，让具身智能概念验证、策略复盘与三维内容制作
既看得到效果，也查得到依据。

项目：https://github.com/noteflowai/robot-reel

- 原始仿真 → 电影场景：https://noteflowai.github.io/robot-reel/remix/
- 策略压力实验室：https://noteflowai.github.io/robot-reel/stress/
- 蝴蝶效应实验室：https://noteflowai.github.io/robot-reel/chaos/
- VLA 双视角任务回放：https://noteflowai.github.io/robot-reel/vla/
- Agent 导演：https://noteflowai.github.io/robot-reel/director/
- Newton／OpenUSD：https://noteflowai.github.io/robot-reel/newton/
- Microduck：https://noteflowai.github.io/robot-reel/

对外交流口径：原有 VLA 示例是一次成功的仿真运行；新增压力实验是一个任务、
三种条件、十个配对种子、每次最多 160 步的受控实验。其统计结果只针对这组设置，
不代表官方 LIBERO 榜单成绩或实机能力。网页提供录制回放；自定义导演需连接
自己的 MCP Agent 并重新渲染。
本次实测参考光照、25% 灯光强度和相机平移三组分别成功 5/10、4/10、7/10，
共 3,525 个动作、360 次策略推理，零执行错误；这些小样本结果不能外推为普遍鲁棒性。
项目未声称已接入某一厂商名为 PAI 的托管平台。各类模型与媒体保留上游许可。
蝴蝶效应实验室展示固定设置下的仿真敏感性；雕塑深度表示时间，不是物理位移，
也不代表策略鲁棒性或实机测试结论。
