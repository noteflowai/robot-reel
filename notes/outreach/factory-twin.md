# Drafts: Factory Twin Lab announcement

Not posted. Drafts for the repository owner; each channel's own rules still need
checking in [promotion-channels.md](../promotion-channels.md) before submission.
Disclose that it is your project on every channel. Every number below is in
[docs/claims.md](../../docs/claims.md) or the lab's `seeds.json`; keep the
"simulation, not calibrated" sentence in every version.

Assets:

- Film (24 s, 1600×900, H.264): https://noteflowai.github.io/robot-reel/factory-twin/film.mp4
- Cover (1280×960, Chinese text): `factory-twin-cover.png` in this folder
- Stills: `docs/factory-twin/render-{aerial,hall,cnc,energy}.jpg`
- Lab: https://noteflowai.github.io/robot-reel/factory-twin/
- Space: https://huggingface.co/spaces/glayguo/robot-reel
- Dataset: https://huggingface.co/datasets/glayguo/robot-reel-factory-twin
- Blender + OpenUSD: https://github.com/noteflowai/robot-reel/releases/download/v0.18.1/factory-twin-blender.zip

## Bilibili（上传 film.mp4，封面用 factory-twin-cover.png）

标题候选：

- 工厂数字孪生：同一班次，闭环 vs 只给建议｜Blender 5.2 程序化园区
- 数字孪生真的“闭环”了吗？12 组配对仿真，主轴故障 11 次 → 0 次

简介：

> 一个仿真工厂和园区（6 工位产线、3 台 AMR、车间温控、光伏车棚和充电桩）每 5 秒向数字孪生发送
> 带噪声、会丢包、有 5 秒延迟的遥测。孪生体只看遥测：同步产线状态，用扩展卡尔曼滤波估计看不见的
> 主轴磨损，在自己的模型上推演 14 种维护方案，预测 15 分钟计费需量，再把指令下发回工厂。
>
> 每个班次都跑两遍：闭环（指令执行）和影子模式（同一个孪生体只给建议）。两边的扰动和噪声完全相同。
> 12 组配对里，主轴故障影子 11 次、闭环 0 次；超出需量上限的计费时段 8 个 → 0 个；合格品 10 组增加、2 组减少。
>
> 园区在 Blender 5.2 中程序化建模，没有下载任何模型或贴图；视频由记录数据驱动，镜头运动是运镜设计。
> 这是示意仿真，参数未按真实工厂标定。所有数字都可以用 `pip install robot-reel` 后
> `robot-reel factory-twin --verify --all-seeds` 逐位复现。
>
> 在线体验：https://noteflowai.github.io/robot-reel/factory-twin/
> 源码：https://github.com/noteflowai/robot-reel （我维护的开源项目，Apache-2.0）

标签：数字孪生、智能制造、Blender、预测性维护、工业仿真、OpenUSD

## 知乎 / 掘金 文章开头

标题：让数字孪生真正“闭环”：一个可逐位复现的工厂与园区仿真

> 很多“数字孪生”演示只是把传感器数据画成三维大屏。闭环意味着孪生体要做出决定并改变工厂。
> 怎么知道这个决定有没有用？我把同一个班次跑两遍：一次执行孪生体的指令，一次只记录它的建议，
> 其余一切（故障参数、云层、传感器噪声、丢包）完全相同。差别就只来自“闭环”本身。
>
> 结果（12 组配对，均为仿真）：主轴故障影子 11 次、闭环 0 次；超限计费时段 8 → 0；
> 合格品 10 组增加、2 组减少——减少的两组是故障本来就发生得很晚、提前保养反而损失产量。

正文结构：遥测与延迟 → EKF 估计 → 14 方案推演与代价函数 → 需量控制与舒适度约束 →
影子对照 → Blender 建模与逐帧校验 → 局限。配图顺序：aerial、cnc（磨损仪表）、energy、hall。

## Blender Artists（Finished Projects 或 Animations）

Title: Procedural factory campus driven by a recorded digital-twin simulation (Blender 5.2, free .blend)

> I maintain Robot Reel, an open-source project, and built this campus entirely
> procedurally in Blender 5.2 LTS: no downloaded meshes, textures or HDRIs. The
> animation is not keyframed by hand. A simulated production line and campus
> energy system drive 313 animated channels over 2,161 frames with constant
> interpolation: station beacons, spindles, weld robot joints, crates in every
> buffer slot, AMRs, a wear gauge and the sun dimming under a recorded cloud.
> A checker compares all 676,393 values per project with the source data and
> reads the OpenUSD export back at every time code.
>
> The flythrough is Cycles/OptiX, 40 spp with adaptive sampling, about 3.6 s per
> 1080p frame on an L40S (577 frames in 35 minutes). The camera path is a Catmull–Rom spline through nine
> key poses. Both .blend projects (closed loop and shadow twin) and their USD
> exports are free (Apache-2.0).

Attach: film, `render-hall.jpg`, `render-cnc.jpg`.

## LinkedIn / X (English)

> Same shift. Same failure. Close the loop.
>
> I ran a simulated factory and campus twice per shift, with identical
> disturbances and sensor noise: once with its digital twin's commands applied,
> once with the same twin only advising. Over 12 pairs: 11 → 0 spindle failures,
> 8 → 0 billing intervals over the demand limit; output up in 10 pairs, down in 2.
>
> The twin sees only noisy, lossy, 5 s-late telemetry, estimates hidden wear with
> an EKF and tests 14 maintenance plans on its own model. The campus is
> procedural Blender 5.2; every frame is checked against the data.
> It is an illustrative simulation, not a calibrated plant, and every number
> re-executes: `pip install robot-reel` → `robot-reel factory-twin --verify --all-seeds`.
>
> https://noteflowai.github.io/robot-reel/factory-twin/ (my open-source project)

## Reddit angle

r/DigitalTwin or r/PLC: lead with the shadow-mode comparison as a method
("how do you show a twin's decisions helped, not just that it has a 3D view?")
and the two seeds where closing the loop cost output. r/blender: lead with the
procedural build and data-driven animation. Ask for criticism of the cost
weights rather than claiming savings.
