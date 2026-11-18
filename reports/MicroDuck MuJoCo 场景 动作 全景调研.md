# MicroDuck MuJoCo 场景与动作全景调研

截至 2026 年 11 月 10 日，MicroDuck 的公开 MuJoCo 生态已经超出走路、踢球和轮滑，**坐姿 Self-charging／回桩也有可信的社区源码与已发布策略**。最值得接入的是 MicroDock v2：它把官方行走、坐站与新训练的坐姿后蹭、脱离策略连成机械对接流程。但标签定位来自仿真真值加噪声，USB 连接是几何判据，电池、休眠和唤醒仍是模拟或脚本，不能称为实体自主充电闭环。([MicroDock v2 发布说明](https://github.com/Vottivott/microduck-playground/blob/052a2494dd6372289221c7a4f24a245b443dd75f/hardware/microdock-v2/README.md))

官方当前有 **10 个部署 ONNX、13 个 RL 任务家族、33 个注册任务 ID**，另有情绪、音乐、RGB／ToF 和多机仿真；任务注册不等于已发布训练完成的策略。DuckKing 当前八个固定下载的官方运动策略都已接入，而且已有嘴部搬运、四个物理鸭体的合唱与发布会、转盘和自由配重跷跷板 PPO，应优先补统一入口、参数和证据反馈，再增加真正不同的场景。([官方任务注册](https://github.com/pollen-robotics/microduck_rl/blob/bae39f5900b318f7e87fc485c30a31213cfa14eb/src/mjlab_microduck/tasks/__init__.py)、[官方策略集合](https://huggingface.co/pollen-robotics/microduck-policies/tree/283771bcb3690a0a94a288c108365d9b630d21e4)、[DuckKing 当前加载表](https://github.com/zhoutingunl/DuckKing/blob/5d9b92cb8c096814fae311d6700ac829792df687/src/duckking/simulation.py#L128))

建议首波采用“**已有能力参数实验室＋官方情绪短剧＋四鸭互动导演**”作为稳定主线，以“**回窝歇会儿：MicroDock 仿真对接**”作为重点新增；25 mm 门槛和三色物体搜索进入紧随其后的候选池。所有新技能先经过独立重放、契约适配、取消与失败验收，再开放实时语音入口。

**同日增补修订：**对照[补充调研报告](https://aiops.qbox.net/files/691082629293bdf4/microduck-mujoco-survey-2026-11-10.md)，本版补入 happy-hop、flamingo-cycle、footsteps、官方 Arena 及多鸭接触任务，细化 MicroDock 条件；保留原有 **22 项路线与首批六项范围**，新增项另列补充短名单。最值得马上做合同验证的是 happy-hop 与 flamingo-cycle；footsteps 则应作为独立落足规划系统评估，不能按普通步态替换。下面记录采纳与纠错，具体原始来源见相应章节。

| 对照结论 | 本版处理 |
|---|---|
| 采纳有工件的增量 | 新增单鸭动作、Circus 跳绳、Piano 键盘接触、严格视觉足球、Arena 与 TorchRL；逐项保留许可、模型与失败边界 |
| 细化已有结果 | MicroDock 加 v1 对照及 v2 的 6 N／8 N 条件、分轴误差；apartment／vslam 已在本地旧 pin，vslam 为六地标柱 |
| 保留原报告的正确口径 | 10 个部署 ONNX、13 家族／33 ID／15 Backlash；官方已有 alpha_stand；v9 是 velstand 回退，本站仍固定 v8 |
| 纠正增补中的归类和数量 | Arena 是六事件、同世界最多八鸭；TorchRL 当前为九技能实验 prior，非 Pollen 随包技能；Grabette 的 red-cube-blue-box 不列 MicroDuck VLA |
| 不采纳缺证据的推广 | 不把 61→14 当即插即用，不把 moonwalk／electric-slide 当完成动作，不采用“43 条全验证”“HF 长尾无增量”或真实充电已闭环等说法 |

本报告的“已实现／已发布”表示查到对应源码、配置或工件，**不表示本次运行成功**。本轮读取公开代码、文档、模型清单和 DuckKing 固定版本，未新跑仿真、推理、训练、云端会话或硬件测试。文中的社区成绩均为**作者报告、未在本轮复现**；DuckKing 的训练成绩是**仓库保存的历史固定评估记录**。投入与排序是工程估计，不是实测工期、训练成本或用户偏好调查。

| 决策 | 建议 | 理由 |
|---|---|---|
| 最快可交付 | 整理已有场景、速度／姿态参数、四鸭导演与结果回执 | 控制和物理底座已在，主要是产品接线与边界验证 |
| 最有辨识度的新增 | MicroDock v2 坐姿入坞／离坞 | 策略、机械场景、训练资料与评估记录齐备，行为一眼可懂 |
| 第一批感知增量 | 先展示 RGB／ToF，再做三色物体搜索 | 能明确区分真值控制、传感器输入与模型识别 |
| 第二批身体技能 | 25 mm 门槛、秋千、篮球平衡 | 有具体工件，但碰撞、执行器或循环网络适配增加验收工作 |
| 暂不承诺 | 真实自动充电、任意楼梯、平地无辅助后空翻、通用地面抓取 | 当前公开证据不能支撑这些广义能力 |

## 1. 先固定版本和证据，避免把任务、视频与可交付技能混在一起

调研截点为 **2026-11-10，Asia/Shanghai**。下列固定提交构成主要事实锚点；网页后续更新不应反过来改变本报告的时间口径。社区项目各自版本列在后文矩阵。DuckKing 的源码 HEAD 也不自动等于公网部署或视频拍摄版本。([DuckKing 素材版本说明](https://github.com/zhoutingunl/DuckKing/blob/5d9b92cb8c096814fae311d6700ac829792df687/README.md#L9))

| 范围 | 本轮版本 | 读取深度 |
|---|---|---|
| DuckKing | [`5d9b92c`](https://github.com/zhoutingunl/DuckKing/tree/5d9b92cb8c096814fae311d6700ac829792df687) | 动作、物理后端、语音、节目、工坊、训练工件与测试源码 |
| 官方 runtime | [`microduck@da34a22`](https://github.com/pollen-robotics/microduck/commit/da34a2212ae12eddfd73d0dfbf924f291aaf1dc9)，2026-11-06 | robotd、duck-control、kinematics、媒体、情绪、模拟协议等 |
| 官方 RL | [`microduck_rl@bae39f5`](https://github.com/pollen-robotics/microduck_rl/commit/bae39f5900b318f7e87fc485c30a31213cfa14eb)，develop，2026-10-27 | 任务注册、环境、模型、训练／导出／推理、body server、许可证 |
| 官方部署策略 | [HF `283771b`／v9](https://huggingface.co/pollen-robotics/microduck-policies/commit/283771bcb3690a0a94a288c108365d9b630d21e4) | 文件树、manifest、版本 diff；未重新下载全部权重并校验哈希 |
| 官方情绪／检测器 | [emotions `431c73d`](https://github.com/pollen-robotics/microduck_emotions/commit/431c73df8a9d3cb6b6067d09ced6c169fdfa59fd)；[duck_detector `cc1b52e`](https://github.com/pollen-robotics/duck_detector/commit/cc1b52eb3ace9643c8948320e63f46a85cf6fb65) | 情绪清单、关键帧／声音、检测训练与导出入口 |
| 官方浏览器／检测模型 | [simulator `efedf47` 页面](https://huggingface.co/spaces/pollen-robotics/microduck-simulator/tree/main)；[detector `da26178`／v2 页面](https://huggingface.co/pollen-robotics/microduck-duck-detector/tree/main) | README 和工件树级核查；链接为浮动页面，记录访问日与页面短 SHA |
| 当前 DuckKing 依赖 | runtime `942e58e`、RL `b02fdea`、policy `665ae4e`／v8 | 是应用固定依赖，和本轮官方最新版本不同；见[安装 pin](https://github.com/zhoutingunl/DuckKing/blob/5d9b92cb8c096814fae311d6700ac829792df687/scripts/setup_simulator.sh#L23)与[下载及哈希表](https://github.com/zhoutingunl/DuckKing/blob/5d9b92cb8c096814fae311d6700ac829792df687/scripts/fetch_scene_assets.py#L9) |

本文采用四类证据：**A：实现与公开部署工件可定位**；**B：源码／训练任务存在，部署权重或完整链路未确认**；**C：作者说明、视频或发现线索，缺少本轮充分核验**；**N：本次检索范围未找到**。A 只说明有可审计的复现起点，不能替代 DuckKing 本地验收。硬件、原生 MuJoCo、浏览器 MuJoCo WASM、GPU 训练框架和纯运动学代理分别标识；MJX／Brax／Isaac 的任务或成绩，也只有在同一 MicroDuck 身体、相同控制契约下完成原生 MuJoCo 复现后，才可成为本站相应能力的证据。

## 2. 官方已发布 10 个运动策略，情绪、感知和音乐拓宽了展示范围

### 2.1 十个 ONNX 中，DuckKing 已用了八个

runtime 的 **七个槽位**是 `walk／stand／sitstand／ground_pick／kick_left／kick_right／roulade` 控制角色；**十个 ONNX**是此处固定 HF manifest 的部署文件数，另含旧双策略和足轮文件。两者统计单位不同，不能用七槽位否定十文件，也不能把后文独立 Arena 模型库直接累加为同一随包集合。([runtime 槽位说明](https://github.com/pollen-robotics/microduck/blob/da34a2212ae12eddfd73d0dfbf924f291aaf1dc9/docs/robot/cheatsheet.md#the-slots-and-four-things-worth-knowing)、[部署 manifest](https://huggingface.co/pollen-robotics/microduck-policies/blob/283771bcb3690a0a94a288c108365d9b630d21e4/manifest.json))

官方发布集合遵循 **61 维观测、14 维关节输出、50 Hz** 的主要部署契约；嘴部由额外控制处理。维度相同不意味着命令语义相同：行走使用速度，坐站借用命令槽作为二值标志，啄地和蹲滑使用相位。下面十个文件均属 A 级工件证据，具体场景组合仍待运行验收。([策略 manifest](https://huggingface.co/pollen-robotics/microduck-policies/blob/283771bcb3690a0a94a288c108365d9b630d21e4/manifest.json)、[runtime 策略契约](https://github.com/pollen-robotics/microduck/blob/da34a2212ae12eddfd73d0dfbf924f291aaf1dc9/docs/policy-manifest.md))

| 已发布文件 | 实际行为与边界 | DuckKing `5d9b92c` |
|---|---|---|
| [`velstand.onnx`](https://huggingface.co/pollen-robotics/microduck-policies/blob/283771bcb3690a0a94a288c108365d9b630d21e4/velstand.onnx) | 当前默认行走、零速度站立及一定范围恢复；不能保证任意地面与姿态恢复 | 已接 v8，尚未切当前 v9 |
| [`alpha_walking.onnx`](https://huggingface.co/pollen-robotics/microduck-policies/blob/283771bcb3690a0a94a288c108365d9b630d21e4/alpha_walking.onnx) | 旧行走策略／教师，可做历史对照 | 未进入当前加载表 |
| [`alpha_stand.onnx`](https://huggingface.co/pollen-robotics/microduck-policies/blob/283771bcb3690a0a94a288c108365d9b630d21e4/alpha_stand.onnx) | 独立站立／起身与身体命令，属于旧双策略组合 | 未进入当前下载八项 |
| [`alpha_sitstand.onnx`](https://huggingface.co/pollen-robotics/microduck-policies/blob/283771bcb3690a0a94a288c108365d9b630d21e4/alpha_sitstand.onnx) | 0＝站、1＝坐，头仍可控；不是任意坐高控制，也不是充电策略 | 已接，含稳定状态验收 |
| [`alpha_ground_pick.onnx`](https://huggingface.co/pollen-robotics/microduck-policies/blob/283771bcb3690a0a94a288c108365d9b630d21e4/alpha_ground_pick.onnx) | 相位驱动嘴尖触地再回站立；没有“找到并抓住任意物体”的含义 | 已接，明确不算物体抓起 |
| [`ball_kick_left.onnx`](https://huggingface.co/pollen-robotics/microduck-policies/blob/283771bcb3690a0a94a288c108365d9b630d21e4/ball_kick_left.onnx) | 左脚单次踢球，actor 不看球 | 已接，先摆球再验接触／位移 |
| [`ball_kick_right.onnx`](https://huggingface.co/pollen-robotics/microduck-policies/blob/283771bcb3690a0a94a288c108365d9b630d21e4/ball_kick_right.onnx) | 右脚单次踢球；不是自主找球或连续盘带 | 已接 |
| [`roulade.onnx`](https://huggingface.co/pollen-robotics/microduck-policies/blob/283771bcb3690a0a94a288c108365d9b630d21e4/roulade.onnx) | 前滚翻；需要身体／头部落地碰撞模型 | 已接 |
| [`roller.onnx`](https://huggingface.co/pollen-robotics/microduck-policies/blob/283771bcb3690a0a94a288c108365d9b630d21e4/roller.onnx) | 两脚四个被动轮的速度控制，专用模型与 action scale | 已接；不是独立滑板 |
| [`roller_crouch.onnx`](https://huggingface.co/pollen-robotics/microduck-policies/blob/283771bcb3690a0a94a288c108365d9b630d21e4/roller_crouch.onnx) | 相位驱动的轮滑下蹲滑行 | 已接 |

DuckKing 状态依据[资产清单](https://github.com/zhoutingunl/DuckKing/blob/5d9b92cb8c096814fae311d6700ac829792df687/scripts/fetch_scene_assets.py#L11)、[加载映射](https://github.com/zhoutingunl/DuckKing/blob/5d9b92cb8c096814fae311d6700ac829792df687/src/duckking/simulation.py#L128)与[高级技能判分](https://github.com/zhoutingunl/DuckKing/blob/5d9b92cb8c096814fae311d6700ac829792df687/src/duckking/official_skills.py#L91)。不能把这八项再次列成“尚待接入的新官方技能”。

**v9 的意义是一次回退，不是自动升级承诺。** 当前 HF 提交把 velstand 回到 v7，官方作者说明 v8 在机器人上表现更差；DuckKing 当前固定的仍是 v8。应保持场景、执行器、随机种子、命令轨迹和评价条件一致，对 v8 与 v9 做受控 A/B 回归，再决定是否切换。真机上的作者判断不能直接证明 DuckKing 的 XML 伺服、多鸭场景或任务 PPO 在 v9 上更好。RL 文档仍有“v8 current”的滞后文字，Yocto 树也仍见 v8 recipe，因此不能把不同仓库的 pin 合并成一个统一“官方版本”。([HF 精确变更](https://huggingface.co/pollen-robotics/microduck-policies/commit/283771bcb3690a0a94a288c108365d9b630d21e4)、[RL 说明](https://github.com/pollen-robotics/microduck_rl/blob/bae39f5900b318f7e87fc485c30a31213cfa14eb/docs/velstand_policy.md)、[Yocto 固定树](https://github.com/pollen-robotics/microduck_yocto/tree/63b47a8a25428d3c6fc55c23b0016931176d5236))

### 2.2 十三个任务家族展开为 33 个 ID，但四类没有核实独立发布策略

下表用 `{Flat,Rough}` 表示两个 ID，`[-Backlash]` 表示有／无该段两个 ID；这是注册名称的紧凑展开写法，不是新的任务别名。合计 **18 个基础 ID＋15 个 Backlash ID＝33**。Backlash 用于模拟齿隙，不能把它当额外娱乐动作。([完整注册实现](https://github.com/pollen-robotics/microduck_rl/blob/bae39f5900b318f7e87fc485c30a31213cfa14eb/src/mjlab_microduck/tasks/__init__.py))

| 任务家族 | 注册 ID 模式 | 数量 | 发布与用途 |
|---|---|---:|---|
| Velocity | `Mjlab-Velocity-{Flat,Rough}[-Backlash]-MicroDuck` | 4 | 传统速度跟踪；有 alpha_walking 部署资产 |
| VelStand | `Mjlab-VelStand-{Flat,Rough}[-Backlash]-MicroDuck` | 4 | 行走／恢复／身体命令；有 velstand |
| StandUp | `Mjlab-StandUp-{Flat,Rough}[-Backlash]-MicroDuck` | 4 | 从地面姿态起身；有 alpha_stand |
| SitStand | `Mjlab-SitStand-{Flat,Rough}[-Backlash]-MicroDuck` | 4 | 命令坐站；有 alpha_sitstand |
| GroundPick | `Mjlab-GroundPick-{Flat,Rough}[-Backlash]-MicroDuck` | 4 | 嘴尖触地；有 alpha_ground_pick |
| BallKick | `Mjlab-BallKick-Flat[-Backlash]-MicroDuck` | 2 | 定点踢球；有左右脚导出策略 |
| Velocity-Rollers | `Mjlab-Velocity-Flat[-Backlash]-MicroDuck-Rollers` | 2 | 被动足轮速度跟踪；有 roller |
| Swizzle | `Mjlab-Velocity-Swizzle[-Backlash]-MicroDuck` | 2 | 对称蹬轮；未在十个发布文件中确认独立模型 |
| RollerCrouch | `Mjlab-RollerCrouch-Flat[-Backlash]-MicroDuck` | 2 | 蹲滑；有 roller_crouch |
| RollerSlope | `Mjlab-RollerSlope-Flat[-Backlash]-MicroDuck` | 2 | 平台→斜坡→缓冲区的被动下滑；独立权重未确认 |
| RollerStandUp | `Mjlab-RollerStandUp-Flat-MicroDuck` | 1 | 穿轮滑起身；独立权重未确认 |
| Spin | `Mjlab-Spin-Flat-MicroDuck` | 1 | 轮上相位驱动旋转；独立权重未确认 |
| Roulade | `Mjlab-Roulade-Flat-MicroDuck` | 1 | 前滚翻；有 roulade |

Swizzle、Slope、RollerStandUp、Spin 属于优先核查 checkpoint 的 B 级候选，不能仅因任务可 `train/play` 就加入“现成可玩”菜单。RollerStandUp 文档还记录过早期训练依赖不现实摩擦的问题。当前注册表和十个部署文件未找到官方 jump；更新架构文档中的 `model-jump` 是设计例子，不能作为跳跃已发布的证据。([轮滑起身设计与问题](https://github.com/pollen-robotics/microduck_rl/blob/bae39f5900b318f7e87fc485c30a31213cfa14eb/docs/roller_standup_policy_summary.md)、[Spin 配置](https://github.com/pollen-robotics/microduck_rl/blob/bae39f5900b318f7e87fc485c30a31213cfa14eb/src/mjlab_microduck/tasks/microduck_spin_env_cfg.py)、[更新系统设计例子](https://github.com/pollen-robotics/microduck/blob/da34a2212ae12eddfd73d0dfbf924f291aaf1dc9/docs/design/updater-design.md))

“官方发布集合未含 jump”不排除社区跳跃策略。happy-hop 等新增发布物见 §4.2；它们需要各自的入口姿态、延迟与收尾合同，不归入上述官方十文件计数。

### 2.3 场景已经包括公寓与视觉房间，碰撞模型必须随技能选用

| 模型／场景 | 已有内容 | 集成时的关键区别 |
|---|---|---|
| `robot_walk.xml` 及 Backlash 版 | 精简身体碰撞的行走模型 | 不能用来证明翻滚、趴地或嘴部接触；见[模型](https://github.com/pollen-robotics/microduck_rl/blob/bae39f5900b318f7e87fc485c30a31213cfa14eb/src/mjlab_microduck/robot/microduck/robot_walk.xml) |
| `robot_groundcontact.xml` 及 Backlash 版 | 支持落地姿态的身体碰撞 | 是地面接触技能的重要底座；见[模型](https://github.com/pollen-robotics/microduck_rl/blob/bae39f5900b318f7e87fc485c30a31213cfa14eb/src/mjlab_microduck/robot/microduck/robot_groundcontact.xml) |
| `robot_groundcontact_rollers.xml` 及 Backlash 版 | 增加四个被动轮，策略仍输出 14 个伺服目标 | 轮关节、摩擦和姿态接口必须保留；见[模型](https://github.com/pollen-robotics/microduck_rl/blob/bae39f5900b318f7e87fc485c30a31213cfa14eb/src/mjlab_microduck/robot/microduck/robot_groundcontact_rollers.xml) |
| `robot_allcollisions.xml` 及 Backlash 版 | 全部部件碰撞 | 实际 registry 的 VelStand Backlash 用全碰撞映射；不能只信 README 的旧描述；见[模型](https://github.com/pollen-robotics/microduck_rl/blob/bae39f5900b318f7e87fc485c30a31213cfa14eb/src/mjlab_microduck/robot/microduck/robot_allcollisions.xml) |
| `scene.xml`、`scene_backlash.xml`、`scene_walk*`、`scene_allcollisions.xml`、`scene_rollers.xml` | 对应模型＋平地，多数含 INIT／STAND／SIT／FOLD 关键帧 | 关键帧是初态资产，不等于训练策略；见[场景目录](https://github.com/pollen-robotics/microduck_rl/tree/bae39f5900b318f7e87fc485c30a31213cfa14eb/src/mjlab_microduck/robot/microduck) |
| `scene_ball.xml`＋`ball.xml` | 有物理球的 groundcontact 场景 | 不自带四姿态关键帧；见[球场景](https://github.com/pollen-robotics/microduck_rl/blob/bae39f5900b318f7e87fc485c30a31213cfa14eb/src/mjlab_microduck/robot/microduck/scene_ball.xml) |
| `scene_apartment.xml`＋`apartment.xml` | 房间、门、家具、地标与充电桩外形，可提供 RGB／ToF | 桩关闭碰撞，没有自主回充控制器；见[公寓 XML](https://github.com/pollen-robotics/microduck_rl/blob/bae39f5900b318f7e87fc485c30a31213cfa14eb/src/mjlab_microduck/robot/microduck/apartment.xml) |
| `scene_vslam.xml`＋`vslam_room.xml` | 供视觉定位研究的纹理与物体 | 有房间不等于 SLAM／导航闭环已完成；见[视觉场景](https://github.com/pollen-robotics/microduck_rl/blob/bae39f5900b318f7e87fc485c30a31213cfa14eb/src/mjlab_microduck/robot/microduck/scene_vslam.xml) |
| `xl330_test_bench/scene.xml` | 执行器模型标定台 | 工程工具，不计娱乐技能；见[试验台](https://github.com/pollen-robotics/microduck_rl/blob/bae39f5900b318f7e87fc485c30a31213cfa14eb/src/mjlab_microduck/robot/xl330_test_bench/scene.xml) |

增补只读检查确认，**apartment／vslam 两个 scene 及其几何文件已存在于 DuckKing 本地旧 pin `b02fdea`**，均引用 `robot_allcollisions.xml`，但应用构建器尚无对应入口。vslam 是约 11 m 房间、**六个彩色地标柱**，不是五柱；地板边长与墙内净宽也不是同一尺度。公寓中的家具、楼梯与桩只提供环境资产；加载文件不能证明自主漫游、避障、SLAM 或爬楼梯，本轮也未编译或渲染它们。([旧 pin 公寓 scene](https://github.com/pollen-robotics/microduck_rl/blob/b02fdea4902c2b93b7d34a83a6f05da4ececb7d3/src/mjlab_microduck/robot/microduck/scene_apartment.xml)、[旧 pin vslam 几何](https://github.com/pollen-robotics/microduck_rl/blob/b02fdea4902c2b93b7d34a83a6f05da4ececb7d3/src/mjlab_microduck/robot/microduck/vslam_room.xml)、[本站场景构建器](https://github.com/zhoutingunl/DuckKing/blob/5d9b92cb8c096814fae311d6700ac829792df687/src/duckking/simulation.py#L157))

官方训练入口为 `train <TASK>`、`play <TASK>` 和 `list-envs`，另有最近运行选择、ONNX 导出与发布工具。**CPU 原生 MuJoCo＋ONNX replay** 已有 `infer_policy.py`；**真实 robotd 接模拟身体** 已有 `duck-body`／`body_server.py`，通过协议 1 的逐行 JSON TCP 接口工作。训练使用 mjlab／MuJoCo Warp 的 CUDA 路径；不能把训练需要 GPU 推断成每次网页体验也需要 GPU。ONNX 不含继续训练所需的 critic、optimizer 等完整状态；官方 training bundle 机制存在，但本次未确认所有动作都有公开可读的完整训练包。([入口定义](https://github.com/pollen-robotics/microduck_rl/blob/bae39f5900b318f7e87fc485c30a31213cfa14eb/pyproject.toml)、[CPU 推理脚本](https://github.com/pollen-robotics/microduck_rl/blob/bae39f5900b318f7e87fc485c30a31213cfa14eb/scripts/infer_policy.py)、[body server](https://github.com/pollen-robotics/microduck_rl/blob/bae39f5900b318f7e87fc485c30a31213cfa14eb/src/mjlab_microduck/sim/body_server.py)、[训练包说明](https://github.com/pollen-robotics/microduck_rl/blob/bae39f5900b318f7e87fc485c30a31213cfa14eb/docs/training_checkpoints.md))

### 2.4 情绪、声音和感知适合做增量，但不应换名夸大

| 能力 | 公开实现 | 应保留的边界 |
|---|---|---|
| 头／身体／嘴、定向注视 | kinematics、gaze 与 robotd 控制 | 目标点命令不等于已识别人脸；各策略对 head／body 槽位的支持不同；见[运动学](https://github.com/pollen-robotics/microduck/tree/da34a2212ae12eddfd73d0dfbf924f291aaf1dc9/kinematics) |
| 自然待机、无声哈欠 | 随机四处看、漂移、侧头、呼吸式身体运动 | 程序生成行为，没有视觉注意力；roller 默认禁用 idle 头动；见[idle 实现](https://github.com/pollen-robotics/microduck/blob/da34a2212ae12eddfd73d0dfbf924f291aaf1dc9/robotd/src/idle_head.rs) |
| 情绪表演 | 独立仓库 **14 项**：sad、devastated、curious、mmh、yes、yes_fast、no、defiant、angry、mock、excited、impatient、laugh、play_dead | 关键帧＋声音，不是新 RL；当前 runtime 随包 **13 项，不含 play_dead**。后者说明需要垫子，旧 patch 不能直接套最新 runtime；见[情绪清单](https://github.com/pollen-robotics/microduck_emotions/blob/431c73df8a9d3cb6b6067d09ced6c169fdfa59fd/emotions.json)与[随包目录](https://github.com/pollen-robotics/microduck/tree/da34a2212ae12eddfd73d0dfbf924f291aaf1dc9/robotd/emotions) |
| Quack、开关机声、抚摸反应 | 本地合成声音；麦克风分类可触发 coo，默认关闭 | 本地音效不是 Linx 回答；真实抚摸识别需要音频输入和分类链；见[声音与抚摸说明](https://github.com/pollen-robotics/microduck/blob/da34a2212ae12eddfd73d0dfbf924f291aaf1dc9/docs/robot/cheatsheet.md) |
| ToF theremin | `robotctl theremin`：8×8 ToF 最近有效距离映射连续音高，嘴随音符变化 | **不是已实现的手指追踪空气键盘**，墙面也会触发；仿真可用射线／几何输入，但网页端尚需接线；见[theremin 源码](https://github.com/pollen-robotics/microduck/blob/da34a2212ae12eddfd73d0dfbf924f291aaf1dc9/robotd/src/theremin.rs) |
| 多鸭合唱 | BLE beacon 同步四声部、`duck-ether` 延迟／丢包模拟、固定乐谱 | 官方文档作者报告多容器合唱测试，本轮未复跑。`outer-wilds` 标为测试资产，不应纳入发布曲库；见[chorale](https://github.com/pollen-robotics/microduck/blob/da34a2212ae12eddfd73d0dfbf924f291aaf1dc9/robotd/src/chorale.rs)与[模拟设计](https://github.com/pollen-robotics/microduck/blob/da34a2212ae12eddfd73d0dfbf924f291aaf1dc9/docs/design/simulation.md) |
| 头部 RGB、ToF | body server 相机渲染、64 射线 ToF、mediad／tofd 模拟入口 | 相机帧／距离可作真实软件输入；NPU、ISP、GPIO 等硬件驱动不在模拟范围；见[模拟使用与边界](https://github.com/pollen-robotics/microduck/blob/da34a2212ae12eddfd73d0dfbf924f291aaf1dc9/docs/robot/simulation.md) |
| 识别同伴鸭 | YOLO11n，公开 PT／ONNX／RKNN | 一个 duck 类，不是通用物体或桩检测；CPU 可走 ONNX，仍须适配前后处理；模型库 v2 与 runtime minimum duck-v1 要明确选择；见[训练仓库](https://github.com/pollen-robotics/duck_detector/blob/cc1b52eb3ace9643c8948320e63f46a85cf6fb65/README.md)与[模型文件](https://huggingface.co/pollen-robotics/microduck-duck-detector/tree/main) |
| 视频处理示例 | H264／JPEG 输入、Canny／帧差／光流与几何叠加 | 是 CPU OpenCV 示例，不是多模态理解；媒体流与控制 RPC 分开；见[vision demo](https://github.com/pollen-robotics/microduck/blob/da34a2212ae12eddfd73d0dfbf924f291aaf1dc9/spaces/vision-demo/README.md) |
| 抱起暂停／放回恢复研究 | pickup 数据、训练、评估、demo 与 robotd 脚本 | `pickup_battery` 的 battery 指测试组，不是“拾取电池”；CPU demo 的 detector 默认是本地训练路径，未随十个动作直接交付；见[pickup demo](https://github.com/pollen-robotics/microduck_rl/blob/bae39f5900b318f7e87fc485c30a31213cfa14eb/scripts/pickup_demo.py) |
| 脸部 LED／照明 | beta 板 LED 与 flashlight 控制 | 硬件输出；网页表情需明确额外映射；见[LED 实现](https://github.com/pollen-robotics/microduck/blob/da34a2212ae12eddfd73d0dfbf924f291aaf1dc9/robotd/src/leds.rs) |
| 官方浏览器 sandbox | MuJoCo WASM＋onnxruntime-web、腿／轮双模型、动作与彩色皮肤、P2P ghost | 物理在各自 tab，ghost 是姿态广播，不是共享碰撞世界；也不是 robotd／Linx 连接；见[Space README](https://huggingface.co/spaces/pollen-robotics/microduck-simulator/blob/main/README.md) |

### 2.5 官方 Arena 增加的是六类赛事与同世界演出格式

Pollen 官方 `microduck-challenges@5cee942` 与前述浏览器 sandbox、StephenForte 的同名社区工作坊分别统计。固定 README 列出 **sprint、roller-sprint、hill-climb、got-a-talent、tug-of-war、sock-heist 六事件**。其中 got-a-talent 是最多 20 秒的 timeline 表演与投票，可在同一物理世界安排最多八鸭，各自固定策略、编排、voice 与 song；这比跨 tab 的 ghost 广播多了共享物理条件。对 DuckKing 最直接的增量是借鉴节目合同和多鸭声部格式，先复用已有四鸭；八鸭容量与六事件在线可玩状态均未在本轮实测。([官方挑战规则](https://github.com/pollen-robotics/microduck-challenges/blob/5cee942d8b434aafd395070facb659034aac3b5e/README.md)、[Arena Space 固定说明](https://huggingface.co/spaces/pollen-robotics/microduck-arena/blob/9305b754862c56b2b2ce512c063c34600efbf932/README.md))

官方还独立发布了 `got-a-talent-reference@0454fe8` 的 ONNX／PT／timeline，仍是 sitstand 与头部命令编排，不是新学会的一整套才艺；`sock-heist-6m-reference@ee81c13` 则发布 ONNX、checkpoint 与 schema-2 manifest，61→14、50 Hz。后者在巨鸭看向跑道时由外层规则清零命令，策略不看相机，也不负责用嘴拿袜；作者报告选定 checkpoint 在 Space x86 的五个种子全部完成，应称有界“红绿灯”规则任务。两份 reference 属独立模型库，不改写十文件计数；本轮未确认它们及 challenge 仓库的独立许可证，接入分发前须补清。([才艺参考](https://huggingface.co/pollen-robotics/microduck-got-a-talent-reference/blob/0454fe8a848526338ba6edf72b8358fbf51d6b21/README.md)、[偷袜参考及选择条件](https://huggingface.co/pollen-robotics/microduck-sock-heist-6m-reference/blob/ee81c1368572753528c01ee493c938c6aaac3ed0/README.md)、[命令合同](https://huggingface.co/pollen-robotics/microduck-sock-heist-6m-reference/blob/ee81c1368572753528c01ee493c938c6aaac3ed0/manifest.json))

## 3. 坐姿回桩已有社区工件，真正的自动充电仍有分层边界

### 3.1 官方坐姿与公寓桩，只构成回充的前置资产

官方 `alpha_sitstand` 能坐下；公寓也有 dock 外形和 `dock_site`。然而 dock 的四个几何体均关闭碰撞，body server 的电压和温度是常数，没有 SOC 动态或充电接触模型。官方 runtime 的低电处理、启动时通过电压变化推测曾充过电，也不能替代实时 power-good／充电电流确认。本次未找到官方完整 dock 任务、部署策略和返航→对接→充电→恢复链。([公寓桩源码](https://github.com/pollen-robotics/microduck_rl/blob/bae39f5900b318f7e87fc485c30a31213cfa14eb/src/mjlab_microduck/robot/microduck/apartment.xml)、[模拟传感器](https://github.com/pollen-robotics/microduck_rl/blob/bae39f5900b318f7e87fc485c30a31213cfa14eb/src/mjlab_microduck/sim/body_server.py)、[vetbook 充电推测](https://github.com/pollen-robotics/microduck/blob/da34a2212ae12eddfd73d0dfbf924f291aaf1dc9/robotd/src/vetbook.rs))

硬件讨论中，官方参与者曾说最终量产单元会有 onboard charging；后续关于电流、外部充电冲突、断电后供电自启的追问，在本轮读取页面中没有完整可引用答案。因此“机载充电电路”“有可视桩”“会自己回桩”应分开叙述。非 Pollen 域名的 dock 商品／Isaac 文案不作为官方证据。([官方问题 #174](https://github.com/pollen-robotics/microduck/issues/174)、[充电问题 #470](https://github.com/pollen-robotics/microduck/issues/470)、[Pollen 产品页](https://pollen-robotics.com/microduck/))

### 3.2 MicroDock v2 最适合做本站首个“回窝”物理节目

**v1 提供了不新增低层训练的对照：**同一固定仓库的 MicroDock v1 使用未修改官方 velstand，按标签接近、转 180°、以 `vx=-0.4` 倒退，满足几何连接后停止。作者在 BAM、4 N 磁力、真值标签加噪声条件下记录 **30/30 入坞、无电源按钮接触**；正式批次用了 `--stop_gap 0`，不能以脚本默认 14 替代。它适合对比站姿与坐姿机械入坞，不代表已具备 v2 的离坞／休眠流程，更不是实机充电。([v1 条件与复现入口](https://github.com/Vottivott/microduck-playground/blob/052a2494dd6372289221c7a4f24a245b443dd75f/hardware/microdock/README.md)、[30 次作者记录](https://github.com/Vottivott/microduck-playground/blob/052a2494dd6372289221c7a4f24a245b443dd75f/hardware/microdock/results/backin30.json))

**Vottivott/microduck-playground 的 MicroDock v2 是独立社区扩展，固定版本 `052a249`，2026-11-05 合入。** 它发布了 `scoot_dock.onnx`、`scoot_undock.onnx`、训练 patch／环境、CAD 生成器、STL／3mf、装配图、评估 JSON 和重放脚本。低层策略训练的是坐姿速度跟踪；入坞与离坞依赖外层控制器和机械场景，不能把策略文件名解读为端到端视觉回充。其 61→14、50 Hz 接口与官方形式相近，但模型采用对应版本的 BAM XL330，仍需独立契约适配。([v2 说明](https://github.com/Vottivott/microduck-playground/blob/052a2494dd6372289221c7a4f24a245b443dd75f/hardware/microdock-v2/README.md)、[策略目录](https://github.com/Vottivott/microduck-playground/tree/052a2494dd6372289221c7a4f24a245b443dd75f/hardware/microdock-v2/policy)、[训练契约](https://github.com/Vottivott/microduck-playground/blob/052a2494dd6372289221c7a4f24a245b443dd75f/hardware/microdock-v2/training/README.md))

| 阶段 | MicroDock v2 已有内容 | 仍须标明的模拟边界 |
|---|---|---|
| 找桩、接近、转身 | 官方 velstand＋标签位置控制 | 标签是仿真真值加高斯噪声，不是渲染图像 AprilTag 检测或全屋 SLAM |
| 坐下、后蹭入坞 | 官方 sitstand＋社区 scoot_dock，导向壁、滑动罩和磁力 | 是真实 MuJoCo 接触过程配合简化磁力；打印容差、真实摩擦／磁力未验 |
| “USB connected” | 接口几何误差进入设定窗口 | 轴向误差 −4 至 2 mm，横／竖误差各小于 2.5 mm；不是电源仪表读数 |
| 休眠／等待 | 仿真连接后零指令、可关闭伺服 | 没有硬件充电电流、热管理或真实低功耗证据 |
| 离坞、站起、走开 | 脚本唤醒＋scoot_undock＋官方动作 | 满电条件与唤醒是外围模拟；延迟与磁力显著影响能否脱离 |

表中边界可核查于[入坞脚本](https://github.com/Vottivott/microduck-playground/blob/052a2494dd6372289221c7a4f24a245b443dd75f/hardware/microdock-v2/sim/docking_seated.py)、[离坞脚本](https://github.com/Vottivott/microduck-playground/blob/052a2494dd6372289221c7a4f24a245b443dd75f/hardware/microdock-v2/sim/undocking_seated.py)及[接触／磁力模型](https://github.com/Vottivott/microduck-playground/blob/052a2494dd6372289221c7a4f24a245b443dd75f/hardware/microdock/source/dock.py)。磁力通过 `mj_applyFT` 对接头与罩施加相反力；它是公开声明的环境模型，不应隐藏成“策略自己产生的吸附”。

**作者记录、未在本轮复现的 v2 结果如下。**不同磁力下分开记录入坞、脱离、站起和走开，不能用“8 N 出不来”代替其实际失败分布。

| 磁力条件 | 入坞 | 脱离 | 站起／走开 | 脱离时间 |
|---|---:|---:|---|---|
| 4 N | 30/30 | 30/30 | 均 30/30 | 中位 1.06 s，最大 1.34 s |
| 6 N | 10/10 | 10/10 | 均 10/10 | 中位 1.49 s，最大 5.26 s |
| 8 N | 10/10 | 2/10 | 各 1/10 | 不作为稳定工作条件 |

表中数值来自作者[4 N 批次](https://github.com/Vottivott/microduck-playground/blob/052a2494dd6372289221c7a4f24a245b443dd75f/hardware/microdock-v2/results/undock30.json)与[6／8 N 批次](https://github.com/Vottivott/microduck-playground/blob/052a2494dd6372289221c7a4f24a245b443dd75f/hardware/microdock-v2/results/undock_magnet.json)。4／6 N 共 40 次中两次起身擦罩，最大 5.6 N；8 N 批次最大起身罩接触力为 92.6 N。对作者 `seated30.json` 静态取最大绝对值，轴向／横向／竖向误差分别为 **0.11／0.64／0.46 mm**；这是坐姿机械对接记录中的分轴误差，不能写成三维 0.1 mm、相机定位或实机精度。坞座固定和滑轨罩条件必须保留，不能外推真实 USB-C 插拔；坐姿本身也不证明零发热、无磨损或不会倒。([坐姿记录](https://github.com/Vottivott/microduck-playground/blob/052a2494dd6372289221c7a4f24a245b443dd75f/hardware/microdock-v2/results/seated30.json)、[完整限制](https://github.com/Vottivott/microduck-playground/blob/052a2494dd6372289221c7a4f24a245b443dd75f/hardware/microdock-v2/README.md))

**延迟是合同的一部分。**作者 README 报告移除匹配训练的延迟后离坞仅 1/10，本轮未找到独立延迟消融 JSON，不能把该数写成本次重算结果。源码为 scoot 注入 15–30 ms 动作延迟，并让关节速度／IMU 观测滞后一控制步 20 ms；真实硬件延迟未测。DuckKing 当前驱动把目标直接写入 XML position actuators，读取当前观测，尚不等同于上述 BAM＋延迟管线。正式目录发布两个 scoot ONNX 及一个实验 ONNX，没有 `.pt` 完整训练 checkpoint，因此“训练配方齐备”不等于“完整续训状态齐备”。([延迟源码](https://github.com/Vottivott/microduck-playground/blob/052a2494dd6372289221c7a4f24a245b443dd75f/hardware/microdock-v2/sim/latency.py)、[训练说明](https://github.com/Vottivott/microduck-playground/blob/052a2494dd6372289221c7a4f24a245b443dd75f/hardware/microdock-v2/training/README.md)、[本站驱动](https://github.com/zhoutingunl/DuckKing/blob/5d9b92cb8c096814fae311d6700ac829792df687/src/duckking/simulation.py#L77))

### 3.3 duckmind 更适合借鉴状态机，不应与 MicroDock 合并为同一能力

`joseyarashio/duckmind@719e139`（2026-11-09）把性格、记忆、年龄、电池与回家流程放在一套脑／身体／世界系统中。它发布找标签、J 形转向、倒车、坐下、读取 `pg`、有限重试与求助的控制代码，提供真实图像标签接口；它不是另一套新发布的低层“自充电 ONNX”。与 MicroDock 不同，其 dock 接触采用 sensor-only 代理，相关几何关闭碰撞，电池按软件规则增加。规范明确电气部分是设计假设，没有真机充电验收。([duckmind README](https://github.com/joseyarashio/duckmind/blob/719e139b03bb2dd934b07561d0eb4a90def91863/README.md)、[身体执行器](https://github.com/joseyarashio/duckmind/blob/719e139b03bb2dd934b07561d0eb4a90def91863/src/duckmind/duckbody/dockexec.py)、[接触代理](https://github.com/joseyarashio/duckmind/blob/719e139b03bb2dd934b07561d0eb4a90def91863/src/duckmind/world/dock.py)、[电气假设与虚拟电量](https://github.com/joseyarashio/duckmind/blob/719e139b03bb2dd934b07561d0eb4a90def91863/docs/dock-hardware.md))

| 比较项 | MicroDock v2 | duckmind |
|---|---|---|
| 最强增量 | 坐姿移动策略＋机械入坞／脱离 | 低电返航、状态管理、标签流程、重试求助 |
| 定位输入 | 真值标签位置加噪声 | 有图像标签接口与里程计流程；仍需本地端到端验证 |
| 接通证据 | 简化机械接触＋接口几何窗口 | `pg` 传感器代理 |
| 电池／休眠 | 外围脚本／模拟 | 软件电量与脑状态机 |
| 本站建议 | 先提取独立物理场景和策略适配器 | 借鉴交互和失败处理，避免整栈替换 |

**产品命名建议：“回窝歇会儿——社区仿真对接实验”。** 页面并排展示“定位：真值加噪声”“连接：仿真几何判据”“电量：虚拟状态”。若暂时只做已有 A* 走到休息区再坐下，就称“到点休息”；只有接入并验收 MicroDock 机械过程后，才增加“入坞／离坞”标签。未来要称实体自主充电，还需单独验证定位、触点电气、电池／热管理、断电恢复与持续循环，当前报告不为这些硬件能力背书。

## 4. 社区提供了导航、门槛和新接触技能，成熟度差异决定交付顺序

以下矩阵中的“有 ONNX／checkpoint”指本轮读到发布文件或作者工件页，**未执行、未复刻成绩，也未下载全部大权重或 LFS 文件**。增补核查下载了指定单鸭动作的 14 个 ONNX 文件并静态解析接口，包含两份相同 FootstepNet；这不等于运行 checker、数值推理或闭环验证。CPU 适配性根据现有推理入口和依赖作判断，未给出本机帧率或并发保证。许可为仓库声明和资产边界摘要，不作法律结论；外取 Pollen 网格不因包装仓库采用 Apache 或 MIT 就改变其来源条款。

### 4.1 导航和感知已有复现起点，必须说明它们看到了什么

| 项目与固定版本 | 工件与场景 | 关键限制 | 运行／CPU判断／许可 |
|---|---|---|---|
| [quacknav `9a56a6c`](https://github.com/andreagenovese/quacknav/blob/9a56a6ceea3ca1212dadf4b42c65d16c9ce60e43/README.md) | ToF 建图定位、悬崖防护、命名地点、探索／go_to、JSON-RPC；pilot ONNX／JSON；MuJoCo twin 与运动学 paper twin | 全为仿真证据，paper twin 成绩不能当 MuJoCo 成绩；pilot 与步态／daemon 版本须匹配 | Rust＋官方 robotd／RL twin；CPU 路线有依据，实际容量待测；代码 Apache-2.0，外取模型独立 |
| [LightNav-0 `3015508`](https://github.com/lightorigins/LightNav-0/blob/3015508b70fb6e30bbd66701e94c9b916dcb8df8/mujoco_demo/README.md) | 真正的可选 MicroDuck adapter；ProcTHOR 多房间 MJCF，RGB→VLN waypoint→MPC→官方步态；公开 safetensors／action tokenizer | MPC 反馈使用真值位姿／速度，固定初态与目标；无通用地图、全局规划和碰撞响应；其它身体论文成绩不能算 MicroDuck 结果 | MuJoCo／CasADi／ONNX 客户端可 CPU，约 9.7 GB 的 VLN 权重另需 GPU 服务；代码／权重 Apache-2.0，场景与网格另核；见[模型文件](https://huggingface.co/LightOriginsHQ/LightNav-0/tree/main) |
| [Bravo-Robots 室内找物 `5f087e4`](https://github.com/Bravo-Robots/microduck-indoor-object-search-rl/blob/5f087e452b970c6405a3d61f7badb0ac450f2d1a/README.md) | v0.2.1；房间／家具、生成器、45→6 supervisor ONNX／PT、61→14 motor、RGB 检测、深度护栏与评估 | 仅红球／蓝箱／黄柱，理想里程计；SE(2) 代理训练、MuJoCo 全身评估；supervisor 不能直接放进 walk 槽 | Linux x86-64／Python 3.12，CPU 演示有入口；代码／自建道具 Apache-2.0，机器人与混合 blend 为 CC BY-NC-SA；见[模型契约](https://github.com/Bravo-Robots/microduck-indoor-object-search-rl/blob/5f087e452b970c6405a3d61f7badb0ac450f2d1a/outputs/release/MODEL_CARD.md) |
| [microduck-qwen `2f7872d`](https://github.com/atlasmarkz/microduck-qwen/blob/2f7872d2460aa42df7985796e84419b27302120f/README.md) | 中文→Qwen3-VL-4B＋LoRA 技能 JSON，深度建图、前沿探索、A*、返回起点；有源码和实验记录 | LoRA **不分发，需先训练**；位姿／安全使用仿真真值；本轮未确认根 LICENSE | 作者使用 Windows／CUDA；不宜当现成 CPU 插件；复用许可与权重缺口先解决 |
| [jonathanhawkins/microduck-lab `8dad921`](https://github.com/jonathanhawkins/microduck-lab/blob/8dad9218062f7b0ad29ae6d564305411f5a117c2/README.md) | CPU MuJoCo＋SB3、训练／评估／浏览器；follow-v1～v5、find_ball、左右 kick ONNX；房间／玩具、1v1～3v3 足球 | 摄像头检测是感知代理，噪声可调；嘴部搬运辅助约束须另查；后空翻有 spotter 起跳辅助 | Apple Silicon CPU 路线有依据；代码 Apache-2.0、各身体资产独立；多机器人仓库中其它身体技能不计入 MicroDuck |
| [duckophila `6da8c1c`](https://github.com/first-it-consulting/duckophila/blob/6da8c1c87f40b2922a04448242037256fd106e94/README.md) | 果蝇连接组闭环、受惊／视动反射／目标跟随／抚摸偏好，MuJoCo 场景与官方 daemon 桥接 | 感觉编码、增益、惊跳形状和学习规则含手写部分；跟人不稳定；FlyWire 数据需另取；依赖说明涉及官方 PR513 | Mac／Linux＋uv＋外部数据；代码 Apache-2.0、数据另有条款；接入成本高，适合研究展区 |

其中，Bravo 作者报告 **49/60**、包含 **9 次跌倒**；microduck-qwen 作者报告 **69/80** 的单一世界实验。**这些均未在本轮复现，任务、输入与终止条件也不相同，不能据百分比横排“谁更聪明”。** 前者目标类别窄、工件较齐，适合作为本站第一项相机找物；LightNav 的自然语言表现力更强，但服务链长，宜后置。([Bravo 发布说明](https://github.com/Bravo-Robots/microduck-indoor-object-search-rl/blob/5f087e452b970c6405a3d61f7badb0ac450f2d1a/README.md)、[Qwen 实验记录入口](https://github.com/atlasmarkz/microduck-qwen/blob/2f7872d2460aa42df7985796e84419b27302120f/README.md))

### 4.2 新身体技能中，门槛最容易解释，秋千与篮球最有观赏性

Playground 下列子项目共同固定在 `052a249`，其软件／策略多采用 Apache-2.0，机器人网格及打印件应分别读取上游条款。表中“高／中投入”为相对工程估计，取决于是否已有原生 CPU replay、模型差异和终止／恢复是否完整。

| 项目／固定证据 | 模型、checkpoint、播放代码 | 能力边界 | CPU／投入判断 |
|---|---|---|---|
| [25 mm 门槛 `ec76957`](https://github.com/bihaokun/microduck-step-up-policy/blob/ec769571438c2558a2d847a164a91022971fceb0/README.md) | 门槛 MJCF、walk／recovery 两个 ONNX、训练源码快照、`infer_policy.py`、记录／视频 | 双脚上台后需人或外部感知置零切换恢复；头可撑地刹车；恢复 actor 原 PPO checkpoint 未保留 | CPU MuJoCo 可用入口明确；中。代码 Apache-2.0、网格另计 |
| [自驱秋千](https://github.com/Vottivott/microduck-playground/blob/052a2494dd6372289221c7a4f24a245b443dd75f/experiments/swing/README.md) | 秋千环境、`alpha050.pt`、导出／评估／续训脚本与 HF ONNX | 是秋千，不是 DuckKing 已有跷跷板；坐垫材料与硬件载荷未验 | mjlab／BAM；训练 CUDA，CPU 部署契约需复核；中高 |
| [篮球平衡](https://github.com/Vottivott/microduck-playground/blob/052a2494dd6372289221c7a4f24a245b443dd75f/experiments/basketball/README.md) | 自由滚动篮球、b11 ONNX／PT／config／source 包；本体观测＋LSTM | 不会自行登球或跌落自救；actor 不看球真值；需维护／重置循环隐状态 | 非无状态 walk 替换；CPU ONNX 适配可研究，性能未测；高；见[发布工件](https://huggingface.co/HannesVonEssen/microduck-basketball/tree/main) |
| [高跷](https://github.com/Vottivott/microduck-playground/blob/052a2494dd6372289221c7a4f24a245b443dd75f/experiments/stilts/README.md) | 多高度独立策略、模型生成器、视频和续训 checkpoint；HF 分高度工件 | 每高度匹配策略／质量／拓扑，不能任意拉长腿；极高版本只是仿真 | 原生重放与模型适配须确认；中高；[工件目录](https://huggingface.co/HannesVonEssen/microduck-stilts/tree/main) |
| [爬梯到桌面](https://github.com/Vottivott/microduck-playground/blob/052a2494dd6372289221c7a4f24a245b443dd75f/experiments/desk-climb/README.md)／[夹缝攀爬](https://github.com/Vottivott/microduck-playground/blob/052a2494dd6372289221c7a4f24a245b443dd75f/experiments/chimney-climb/README.md) | 定制梯／支架生成器、策略配对、源码快照和 HF 权重链接；夹缝有进入／爬升／退出 | 爬桌切换用脚桌接触与 root 真值；夹缝是选定成功序列，非稳健全链成功率 | 多阶段与恢复复杂；高，先保留实验入口 |
| [高台跳远／后空翻](https://github.com/Vottivott/microduck-playground/blob/052a2494dd6372289221c7a4f24a245b443dd75f/experiments/parkour/README.md) | 两个独立 ONNX／PT、场景、软接触垫、replay 和 parity 记录 | 不是平地原地后空翻；无视觉；垫未标定、不模拟损坏；选定后空翻站起后又跌出垫；descending-pillar 未发布 | 作者推荐 CUDA 的 mjlab 路线，不能保证 CPU 即插即用；高 |
| [快跑](https://github.com/Vottivott/microduck-playground/blob/052a2494dd6372289221c7a4f24a245b443dd75f/experiments/running/README.md) | 选定策略、HF ONNX／完整 PPO、评估与续训配方 | 作者标为 simulation-only hardware candidate；不是实体跑速证据 | 原身体的步态变体；中，但需起停／跑道／跌倒验收 |
| [积木击打 `0f977ea`](https://github.com/speccy88/microduck-jenga-sim/blob/0f977eaf989fff819bdcb75d303c6805505ebe69/README.md) | 两块自由积木、CEM 头部轨迹、冻结 VelStand、`checkpoint_100.json`、重放／接触检查 | 固定近距离与方位；不是搭塔，另一三块 PPO 实验尚无成立策略；第三方平衡权重要另恢复 | 作者 Linux／WSL2＋CUDA；CPU 重放需核验；中高。代码 Apache-2.0、模型／录像 CC BY-NC-SA |
| [witcheer 地形系列 `0073595`](https://github.com/notwitcheer/microduck-lab/blob/0073595d1282a0d5cee649a9c961a8ff1305f93d/README.md) | 工具／地形 patch／评估，HF flat／rough／slope／step／stairs／slip／gale／recover 模型 | stairs 强扰动结果没有优于基线；训练导出含未提交 overlay，单一上游 SHA 不足以还原 | 中；适合策略对照。Apache-2.0，overlay 与模型一并固定；见[stairs 模型卡](https://huggingface.co/witcheer/microduck-walk-stairs) |
| [单足站立 collision-flamingo-ii](https://huggingface.co/Teethyfish/microduck-collision-flamingo-ii) | ONNX、全壳碰撞 overlay 与推理契约 | 作者 safe infer 路径与训练 play／Viser 表现不一致，差异未解；本次未下载整个树 | 中，但先解决执行差异；代码／策略 Apache-2.0，网格独立 |
| [辅助后空翻 `8bde27e`](https://github.com/Lulzx/microduck-backflip/blob/8bde27eb141c8f14db05fc4370e536521203a98d/README.md#backflip-training-and-evaluation) | mjlab 任务、checkpoint／ONNX、评估、辅助吊带场景与视频 | 作者明确是有辅助翻转；大量 task 名不代表各自已收敛 | mjlab／CUDA；高。Apache-2.0＋网格 CC 条款；不列决赛首波 |

**作者报告、未在本轮复现的局部结果**包括：门槛网格试验 13/14 稳定；秋千严格全程门槛 71/100；两块积木严格成功 25/30；witcheer stairs 的指定强扰动试验 3/15 存活、基线 5/15。它们应连同初态、接触、辅助、策略切换和终止标准阅读，不能转为本站成功率，也不能从一个成功镜头推断连续任务可靠。([门槛记录](https://github.com/bihaokun/microduck-step-up-policy/blob/ec769571438c2558a2d847a164a91022971fceb0/README.md)、[秋千记录](https://github.com/Vottivott/microduck-playground/blob/052a2494dd6372289221c7a4f24a245b443dd75f/experiments/swing/README.md)、[积木记录](https://github.com/speccy88/microduck-jenga-sim/blob/0f977eaf989fff819bdcb75d303c6805505ebe69/README.md)、[stairs 模型卡](https://huggingface.co/witcheer/microduck-walk-stairs))

**新增单鸭候选中，happy-hop、flamingo-cycle 与 footsteps 的增量最清楚。**下表独立于前面的身体技能目录；成绩仍全为作者报告。前三项模型卡声明 Apache-2.0，但其可接入性需要整份控制合同，而非只有 61→14 的形状。

| 新增候选／固定来源 | 可复用能力与制品 | 接入门槛与成熟度 |
|---|---|---|
| [happy-hop `c0447da`](https://huggingface.co/joanfox/microduck-happy-hop/blob/c0447da668255436eea070e862ad8eb89bad2ba1/README.md) | 单次跳跃 ONNX／manifest；作者报告 Pollen 于 2026-09-01 实机演示成功 | 优先合同验证；站稳入口、50 Hz、20 ms 动作延迟、零命令、无动作低通，Backlash／BAM XL330 须匹配。3 秒由外层结束，本站未复现 |
| [flamingo-cycle `a69e4f6`](https://huggingface.co/RemiFabre/microduck-flamingo-cycle/blob/a69e4f6103a70e355983eb5d4e919da76778a40f/README.md) | 可命令左／右单足抬起、保持、放下；ONNX／控制脚本，CPU MuJoCo 路线 | 与 collision-flamingo-ii 不同；twist 改作 flag／side，需专用角色。仅仿真；作者 24 次压力试验有 2 次跌倒，后向推扰是弱项 |
| [footsteps `19c38fa`](https://huggingface.co/apirrone/microduck-footsteps/blob/19c38fae6afabddf9c0821009028d0a37963f05f/README.md) | 落足追踪 ONNX＋FootstepNet；作者称追踪器测过机器人、仿真误差约 5–7 mm | 独立系统集成；twist 是支撑足坐标中的落足目标，需 footsteps runtime 分支、支撑足里程计、左右镜像及坐标裁剪；硬件说法未独立核验 |
| [groove `b94e53d`](https://huggingface.co/kramp/microduck-groove/blob/b94e53dfad4c277c48447d44c6b8c014820fcc89/README.md) | 10 秒舞蹈 ONNX／manifest／视频；作者 CPU 记录约 126 BPM 膝部起伏 | 到时 daemon 中途切 stand，不是网络主动收稳；训练 fork 未公开、未实机、未找到明确模型许可，先留研究候选 |
| [playdead `7b49a6a`](https://huggingface.co/drfonz-indigo/microduck-playdead/blob/7b49a6a70e781096c6a39fc3ce5cea25307e8565/README.md)／[polite-bow `9a9d21a`](https://huggingface.co/fffiloni/microduck-polite-bow-b1d864/blob/9a9d21a85cf7b5cbd1854c03ad58bd949502a5ea/compiled_motion.json) | 前者 5 秒坐下仰躺，另接 velstand 恢复；后者有 ONNX、checkpoint、生成源码与 CPU 指标 | 均未找到明确模型许可。装死嘴部另编排，非单网络完成起身；轻鞠躬依赖头俯仰 15°／身体下降 4 mm 的外部命令，body pitch 目标为零，不证明明显躯干鞠躬 |
| [beak-throw `410ed22`](https://github.com/llama/microduck-beak-throw/blob/410ed2249d62cd7aa4c642cd2c4e9b56f9a0cbfd/README.md) | 24 mm 球抛掷 ONNX／checkpoint、训练 overlay、runtime 补丁，Apache-2.0 | 嘴垫／唇边／挡块与定时开嘴、stand 接管均需适配。作者 50/50 仿真通过依赖强制限幅，原始网络输出门全部失败；无实机验证，高投入实验 |
| [max-height-jump `7e5dc60`](https://github.com/ThomasBurgess2000/microduck-max-height-jump/blob/7e5dc6028900f13d145e6710847378b007a675e9/README.md)／[chenp9527 jump `ace589e`](https://github.com/chenp9527/microduck-jump/blob/ace589eadd1be6aed4e39a27d8bd8e275b2b9cfe/README.md) | 均有 ONNX／checkpoint／任务源码，Apache-2.0；前者单种子 CPU 高度 31.67 mm，后者 128 次随机仿真中 50.8% 达 3–6 cm、未跌倒 | 前者单策略未持续站稳，需双策略混合收尾；后者落地峰值 128.3 N 超过作者 40 N 目标，且命令须全零。都不是稳定跳跃或实机承诺 |
| [318_lab `512d4be`](https://github.com/Liyucheng1997/318_lab-microduck-simulator/blob/512d4bec6fc3ba321d29c93312be72856ad21268/app/src/game/game.js#L660) | 原待核线索现已确认 jump.onnx、训练任务及浏览器 ONNX→关节目标→MuJoCo 步进链 | 触发清动作历史，2 秒后直立交回 walk，3 秒超时，失败可 reset；未建立 BAM／Backlash 一致性，未本地运行，根许可未确认 |

happy-hop 的实机说法还存在**同版本元数据不一致**：README 报告实机演示，manifest 却仍标 `sim-only-hardware-candidate`，且未完整写入新增的一步动作延迟。因此可称“作者报告实机演示”，不能给它统一的“本站实机验证／自动安装完成”标签。flamingo-cycle 的测试脚本暂占 walk、禁用 stand 与其他技能并修改 fall 门限，永久接入应新增专用角色。FootstepNet 自身是 8→3 规划器，不能与 61→14 追踪策略混为一个网络；同维度策略中速度、落足目标、flag／side 与跳跃触发也不能共用命令解释。([happy-hop manifest](https://huggingface.co/joanfox/microduck-happy-hop/blob/c0447da668255436eea070e862ad8eb89bad2ba1/manifest.json)、[flamingo 控制器](https://huggingface.co/RemiFabre/microduck-flamingo-cycle/blob/a69e4f6103a70e355983eb5d4e919da76778a40f/control.py)、[FootstepNet 合同](https://huggingface.co/apirrone/microduck-footstepnet/blob/1132e672d261cb8520c296acaa06fac955424b14/README.md))

**多鸭新接触任务和视觉足球应独立验收。**新增价值是绳、琴键和 RGB 控制链，不是增加鸭子数量；下表均未在本站运行。

| 项目／固定来源 | 实际新增与作者结果 | DuckKing 接入判断 |
|---|---|---|
| [Circus `1034ed0`](https://github.com/ros-claw/microduck/blob/1034ed000c352476cf213ebe1544eb8c7db8b0e7/docs/COOPERATIVE_ROPE_SKIPPING.md) | 三鸭同一 MuJoCo 跳绳；跳鸭 61 维、摇绳鸭 73 维，各有 PPO ONNX、50 Hz、CPU 推理入口；作者 442/516 clean cycles、5/8 runs 通过 | 高投入接触实验。嘴柄与绳端 equality 约束、相位真值协调；排除绳–摇绳鸭及绳自碰撞，不是端到端多智能体 RL。后续四鸭审计有 23–37 mm 穿入、移动接力未过；训练 patch 存在，完整 PT／日志未齐 |
| [Piano `1692d44`](https://github.com/KhushiJ2911/microduck-piano-learning/blob/1692d4432c9a3833288b2aa763380d9cdeffdd62/README.md) | 两个自由根鸭踩 16 个被动弹簧键；VelStand 微调 ONNX／审计工件；作者 64 世界仅 1 个严格通过，选中世界完成 6 键按下释放 | 研究储备。方向由 evaluator 预排，不会按谱自主选键；控制与保存状态的渲染回放分开。ONNX 用 CPU 不证明 mjlab／Warp 全链可在本机 CPU 复现，完整训练包未见 |
| [Vision Soccer `23cdfbc`](https://github.com/toyhank/microduck-vision-soccer/blob/23cdfbce04083ff1883a2d6ceb7bb3b6b49e15c0/README.md) | 从待核线索提升为感知接线候选；strict 用头部 RGB＋仿真 IMU／编码器，视觉校准／状态机调用既有 walk／stand／kick；非新足球 RL | 中高投入，先核严格模式。早期 strict 7/10 踢球接触、0/10 进球；当前新增校准及盲区里程计，当前成功率未核。98/100 属真值基线，不能作为视觉成绩 |

Circus 的碰撞简化可查[物理审计](https://github.com/ros-claw/microduck/blob/1034ed000c352476cf213ebe1544eb8c7db8b0e7/docs/PHYSICAL_FIDELITY_AUDIT.md)。Soccer 的 `demo` 路径在踢球触发时直接重定位球，需与 `strict` 分开；`--headless` 仍需 RGB 渲染，双相机 CPU 吞吐未测，onboard 接线也不证明整场实机足球。三项目声明代码 Apache-2.0，机器人资产各自独立。建议次序为严格视觉链、跳绳独立实验、键盘研究储备。([足球入口与模式](https://github.com/toyhank/microduck-vision-soccer/blob/23cdfbce04083ff1883a2d6ceb7bb3b6b49e15c0/sim_duck_soccer.py)、[早期严格结果](https://github.com/toyhank/microduck-vision-soccer/blob/23cdfbce04083ff1883a2d6ceb7bb3b6b49e15c0/VALIDATION.md))

### 4.3 训练基础设施、相邻机器人和未核实线索不计作成熟 MicroDuck 技能

`dreamerarun/isaaclab_microduck@deb10a3` 提供 IsaacLab／PhysX 的 37 个环境注册、BAM、转换和 train／play／export，但作者预览只是两次 PPO 更新的 smoke 模型；它是训练基础设施，不是 37 个成熟动作，也不是 DuckKing 原生 MuJoCo 可直接播放的包。`lgtkgtv/microduck_sim@b7a50ac` 的 rough／stairs／push recovery、WASM 和视觉导航仍标为 Planned，教育模型还是 60／15 契约；不能把摘要中的规划事项列作交付能力，其 README 的 MIT 声明也不能代替本轮未确认的根 LICENSE。([IsaacLab 仓库](https://github.com/dreamerarun/isaaclab_microduck/blob/deb10a39e59504a8093a30bf8376b853020fa0ee/README.md)、[教育模拟器路线图](https://github.com/lgtkgtv/microduck_sim/blob/b7a50acee420029af3d0dbc01b01fd2fb982f0de/README.md))

`quackd@4ba2d0d` 的 MicroDuck adapter 和 `knowlin@f8b0920` 的多机器人入口可供编排架构参考；StephenForte/microduck-challenges 是社区训练评测工作坊，另见 §2.5 的 Pollen 官方同名仓库；duck-dreams 是梦境文本／漫画，microduck-aiprobe 是参数评测框架。它们不自动增加新的身体技能。**Open Duck Mini／v2、Reachy Mini、G1、MARS、MOSS、Asimov 以及四足 SkateNav 都属于相邻机器人**，即使出现在同仓库、采用相似训练栈，也不计入本报告的 MicroDuck 支持清单。([quackd adapter](https://github.com/rokbenko/quackd/blob/4ba2d0dc6cf9c591a7c7897bc9d80301d5a187b3/adapters/microduck/README.md)、[knowlin 来源表](https://github.com/knowlin-ai/knowlin/blob/f8b092081f26e3e8ce864caade505751f1868966/README.md)、[社区 challenges](https://github.com/StephenForte/microduck-challenges/blob/6155860d63491ff30fa8be73d165b2deac12dd47/README.md)、[dreams](https://github.com/StephenForte/duck-dreams/blob/58da60270b617699d2c914d894d25ce7deb84b9d/README.md)、[aiprobe](https://github.com/rahilmehta-dev/microduck-aiprobe/blob/076ba37a9715fe18db24154a391695dade505f73/README.md))

**TorchRL 应列为框架项目的九技能实验 prior。**`torchrl/microduck-skills@d676623` 当前包含站、前后左右、前跳、左右转、原地跳，发布 GRU128 recurrent PPO 的 `prior/checkpoint.ckpt`；不是 Pollen 官方“七技能”随包 ONNX。作者报告 Apple-silicon CPU MuJoCo 训练、每技能 32×500 步全存活，但仅一个训练种子／平地 reset、仅仿真。PyTorch 的 `MicroDuckSkills.from_pretrained` 默认仍指历史六技能 revision，接入需同时 pin 对应源码、任务顺序、GRU 状态与 action scale。football 为实验 selector、tag 为未解决 pilot，权重独立授权未确认；适合 CPU 研究线，不应直接进入节目菜单。([当前卡与工件](https://huggingface.co/torchrl/microduck-skills/blob/d6766234b24bf9cff6a6a8c55011a4584a8995d5/README.md)、[prior 条件](https://huggingface.co/torchrl/microduck-skills/blob/d6766234b24bf9cff6a6a8c55011a4584a8995d5/prior/README.md)、[PyTorch API](https://docs.pytorch.org/rl/main/reference/generated/torchrl.modules.tensordict_module.zoo.MicroDuckSkills.html))

| 新增平台／固定来源 | 可借鉴内容与边界 |
|---|---|
| [microdux `c486b89`](https://github.com/noahfarr/microdux/blob/c486b8967f8e35eed7dcec85ac3343a269cd4bc2/README.md) | JAX／MJX／Playground 的 14 行任务含 flat／rough 拆分，不与官方 13 家族相加；仅 flat velocity 作者称达上游水平，其他训练有缺口。A100 benchmark 非 CPU 成绩，未见完整已训策略集，根许可未确认 |
| [duckbench `a75d4dc`](https://github.com/craigm26/duckbench/blob/a75d4dc9b8a08c8072c15af0ab50dfb516ab144c/sim/PLANT.md) | CPU MuJoCo WASM＋onnxruntime-node、HTTP／MCP，可借鉴评测接口；作者明确 sim／site 两条 plant 的长轨迹不能互换，世界还有历史 step bank 条件。代码 Apache-2.0，不为接 MCP 更换本站物理引擎 |
| [microduck-twin `351e81d`](https://github.com/digows/microduck-twin/blob/351e81dded599c466a14380b374b10b23b989f2b/twin-body/twin_body/power.py) | 包装官方 CPU body／daemon，补声音传播、SOC／热与 HUD；电池／热模型明确未以实测拟合。可作回桩外围虚拟状态参考，不能证明真实续航或电气充电；代码 Apache-2.0、网格独立 |
| [Wicroduck `b0035c1`](https://github.com/ngxson/wicroduck/blob/b0035c15c532bbb69b22a7edc1bb79b7b7430cd0/docs/training-plan.md) | 浏览器 MuJoCo 200 Hz／ONNX 50 Hz；已有 CPU PPO／checkpoint、motion editor 与检查，不能再写“训练纯目标”。导入权重微调、从零训练／ONNX export 里程碑尚未完成；运动学预览与物理运行须分标，根许可未确认 |

这些平台改善开发与教学条件，不自动增加已学会的身体技能。另须排除同组织误归类：Pollen `red-cube-blue-box` π0.5 配置所指数据明确为 **Grabette**，图像＋2 维状态→11 维动作；相关 diffusion 也是类似契约，均非 MicroDuck 61→14 部署包，未见鸭体转换验证，不能列为可接入的 MicroDuck VLA。数据集许可也不自动覆盖权重。([π0.5 配置](https://huggingface.co/pollen-robotics/red-cube-blue-box_pi05_best/blob/eb2127a8d110d987c45c18e25d58404561ceaf55/train_config.json)、[Grabette 数据元信息](https://huggingface.co/datasets/simheo/red-cube-blue-box_graspproj_v2/blob/854830ce317c20a7f438029894bbfc77e6afd5f2/meta/info.json)、[diffusion 契约](https://huggingface.co/pollen-robotics/red-cube-blue-box-30fps_diffusion/blob/b12622b97ec7234b0460f93d2039ecdc536a44b9/config.json))

**动作名也不能代替语义验收。**moonwalk 的导出权重虽存在，指标明确 `motion_quality_passed=false`、`semantic_quality_unverified=true`，只能支持后退步态预演，不能称已学会月步。electric-slide 最新说明已撤回完成舞蹈的结论，CPU BAM 诊断跌倒，未完成 25 鸭终演或实机部署；早期脚本编舞视频不改变该状态。QingMuLYL 社区 standup 另有 6 秒 ONNX，但入口为 sitting、训练来自 dirty checkout，不能据此宣称任意推倒恢复；官方 alpha_stand 早已发布。([moonwalk 指标](https://huggingface.co/fffiloni/microduck-moonwalk-backward-55e6af/blob/951073cb7791a898e3e5ecb242c5bcccf40aa72f/preview_metrics.json)、[electric-slide 当前说明](https://huggingface.co/Histochemichael/microduck-electric-slide-policy/blob/67eb1f1eaf5e3a91f027fe45b8b9bb4efaa6be04/README.md)、[社区 standup manifest](https://huggingface.co/QingMuLYL/microduck-standup/blob/7f8d01e9aae4ab005b8685677f16df1710d81bd8/manifest.json))

为保留搜索线索而不夸大推荐，以下只列待核查方向。它们目前不应进入“点击即玩”的正式能力目录。发现入口为固定的[awesome-microduck 索引](https://github.com/joeynyc/awesome-microduck/blob/b99984a56182525598c4187cc0138c89bc1c7c79/readme.md)，索引描述不作为本地复现证据。

| 线索组 | 未解决的关键问题 |
|---|---|
| [microduck-courier](https://github.com/selinayfilizp/microduck-courier) | 待核嘴部辅助约束／完整搬运终止；318_lab 跳跃已移至 §4.2 的有工件候选 |
| [sidekick-dance](https://github.com/pezzonovante7/microduck-sidekick-dance)、[MotrixLab](https://github.com/jjshdbndg/MotrixLab-MicroDuck)、[action-pack](https://github.com/wat-bill/microduck-action-pack) | 前者 task only；MotrixLab 兼容性未核；节奏动作包属于编排，需与现有舞蹈去重 |
| [PPO navigation](https://github.com/zakiyamaaaaa/microduck-ppo-navigation)、[roller racer](https://huggingface.co/spaces/Nirav-Madhani/microduck-racer) | checkpoint、避障／比赛重置尚未核实；Vision Soccer 已移至 §4.2，严格视觉与真值成绩分开 |
| [rough-walk-e](https://huggingface.co/RemiFabre/microduck-rough-walk-e)、[rough-walk-g](https://huggingface.co/RemiFabre/microduck-rough-walk-g)、[stairs challenge](https://huggingface.co/datasets/craigm26/microduck-stairs-challenge) | 地形策略卡／下降限制需复核；challenge 是数据集，不是可运行 harness，作者目标尚未达到 |
| [Sourccey dome](https://huggingface.co/cetiennec/microduck-on-sourccey-dome)、[flywire-microduck](https://huggingface.co/spaces/AlexWortega/flywire-microduck)、[micro-garden](https://github.com/ChristianNHill/micro-garden) | 联合机器人场景或连接组／花园展示；页面、模型与刺激读出未充分核查 |
| [microduck-mjbatch](https://github.com/tailong-wu/microduck-mjbatch)、[Microduck-Workshop](https://github.com/NV-DLI/Microduck-Workshop) | CPU 训练、Newton／Isaac 课程是基础设施线索，尚不能当新增 MuJoCo 技能包 |

### 4.4 本次广覆盖调查有明确上限

同日增补对指定线索做了定点核查，没有变成全网穷尽审计。固定社区 `policies.json` 可数得 **43 条 entries**，但其中有 source-only／probe-provider，且 TorchRL、Wicroduck 的目录描述已滞后；条目数不是全部工件、许可和运行结果的验证数。补充报告的“HF 1,137 项／38 页／长尾无增量”缺少可复查的分页与分类记录，本版不采用该排他结论。([固定目录数据](https://github.com/joeynyc/awesome-microduck/blob/b99984a56182525598c4187cc0138c89bc1c7c79/policies.json)、[目录自述](https://github.com/joeynyc/awesome-microduck/blob/b99984a56182525598c4187cc0138c89bc1c7c79/readme.md)、[补充报告](https://aiops.qbox.net/files/691082629293bdf4/microduck-mujoco-survey-2026-11-10.md))

检索覆盖 `microduck`、`microduck in:name fork:true`、`microdock`、`microduck_rl in:name fork:true` 等 GitHub 查询、公开社区目录及作者 HF 工件页。GitHub 查询各取第一页，后续遇到 API 限流；HF API／raw 连接也多次重置，改用公开工件页读取。没有逐库比较所有 fork，没有遍历全部分支／PR／release，也未覆盖私人模型、Discord、所有社交视频和已删除工件。镜像、未核实 fork 与官方 ONNX 再包装不重复算能力；Bravo 与 david2526IA 的镜像关系按一个项目计。([可复查搜索入口](https://api.github.com/search/repositories?q=microduck&per_page=100&sort=updated)、[社区索引](https://github.com/joeynyc/awesome-microduck/blob/b99984a56182525598c4187cc0138c89bc1c7c79/readme.md)、[Bravo 来源说明](https://github.com/Bravo-Robots/microduck-indoor-object-search-rl/blob/5f087e452b970c6405a3d61f7badb0ac450f2d1a/README.md))

因此，准确结论是：本轮找到可信的仿真机械回桩，却没有找到经过核实的真实自主电气充电闭环；找到若干门槛／地形策略，却没有通用任意楼梯的证据；找到秋千和篮球平衡，却没有核实到可直接替换 DuckKing 当前自由配重跷跷板的社区完整包。这是检索与验证范围的陈述，不是能力“不可能存在”的断言。

## 5. 当前 DuckKing 的主要缺口，是统一接入与新增观测，不是基础动作数量

### 5.1 当前源码已经覆盖 11 个物理场景族、13 幕和 10 项互动工坊

常规场景为 `ball、duo、carry、skills、rollers、stage、choir、table、seated`，另有独立 backend／API 的 `balance` 与 `seesaw`，可整理为 **11 个物理场景族**。13 幕是演出目录，10 项工坊是交互任务，均不等于同数量的新 RL 策略。下表只以 `5d9b92c` 为准，旧产品报告中“尚缺点名轮唱／递送暂停”等判断不能继续沿用。([场景生成](https://github.com/zhoutingunl/DuckKing/blob/5d9b92cb8c096814fae311d6700ac829792df687/src/duckking/simulation.py#L157)、[13 幕目录](https://github.com/zhoutingunl/DuckKing/blob/5d9b92cb8c096814fae311d6700ac829792df687/frontend/src/demo-catalog.js)、[10 项工坊](https://github.com/zhoutingunl/DuckKing/blob/5d9b92cb8c096814fae311d6700ac829792df687/frontend/src/studio-catalog.js))

| 能力群 | 当前已有 | 真正剩余缺口／新增工作类型 |
|---|---|---|
| 基础步态、头部、身体 | 前后左右／转向、有界头动、固定朝向、部分 body z／roll／pitch | 速度字段已在后端，但 MCP／本地语法未充分暴露；先验证离散档与实际位移。是参数接线；见[Action](https://github.com/zhoutingunl/DuckKing/blob/5d9b92cb8c096814fae311d6700ac829792df687/src/duckking/motion.py#L54)与[MCP](https://github.com/zhoutingunl/DuckKing/blob/5d9b92cb8c096814fae311d6700ac829792df687/src/duckking/mcp.py#L35) |
| 坐下／坐稳／站起 | 官方 sitstand，身体高度、膝角、接触、upright、持续稳定共同验收；坐着能头动 | 连续坐高并无策略契约；不能靠 slider 或改验收高度实现。需新条件控制／训练才是另一能力；见[posture](https://github.com/zhoutingunl/DuckKing/blob/5d9b92cb8c096814fae311d6700ac829792df687/src/duckking/posture.py#L8) |
| 滚翻／啄地／足轮／蹲滑 | 四类官方技能与物理判分均已接 | 尚无通用地面抓物、独立滑板、蹬地上板；这些改变接触任务，不是换名称；见[技能验收](https://github.com/zhoutingunl/DuckKing/blob/5d9b92cb8c096814fae311d6700ac829792df687/src/duckking/official_skills.py#L91) |
| 待机与舞蹈 | 本地自然待机、哈欠、闪身步、哆嗦毛 | 官方 13 情绪全套及其声音／时序未接；已有舞蹈是编排，不是新训练；见[idle](https://github.com/zhoutingunl/DuckKing/blob/5d9b92cb8c096814fae311d6700ac829792df687/src/duckking/idle.py)与[choreography](https://github.com/zhoutingunl/DuckKing/blob/5d9b92cb8c096814fae311d6700ac829792df687/src/duckking/choreography.py) |
| 踢球教练 | 左右脚策略、显式摆球、脚球接触／位移；工坊已有 observe→prepare→kick | 自主找球、盘带、守门／球队需要新感知与连续任务；见[球动作](https://github.com/zhoutingunl/DuckKing/blob/5d9b92cb8c096814fae311d6700ac829792df687/src/duckking/simulation.py#L694) |
| 嘴部递送 | 从架上夹轻棒、持续上下嘴接触、离架、固定接物台放稳；暂停续送已在工坊 | 近似改编嘴铰链未实机标定；任意物体／地面拾取／自由目的地仍需新控制与接触验收；见[夹取状态机](https://github.com/zhoutingunl/DuckKing/blob/5d9b92cb8c096814fae311d6700ac829792df687/src/duckking/grasp.py#L132)与[来源边界](https://github.com/zhoutingunl/DuckKing/blob/5d9b92cb8c096814fae311d6700ac829792df687/THIRD_PARTY.md#L14) |
| 双鸭发现／碰面 | 同世界碰撞；真值 FOV＋距离＋射线遮挡发现同伴 | 不是相机检测或 BLE；接官方 detector 才增加真实图像链；见[discover](https://github.com/zhoutingunl/DuckKing/blob/5d9b92cb8c096814fae311d6700ac829792df687/src/duckking/simulation.py#L572) |
| 双声部、四声部、桌上四鸭 | 第 10 幕 choir 为 **四个真实物理实例**；第 11／12 幕也有四个根节点；音频为本地合成或指定音源 | 不是“两鸭＋视觉替身”，也不是官方 BLE／云端歌声；官方声音 RPC、ToF 乐器是独立增量；见[实例生成](https://github.com/zhoutingunl/DuckKing/blob/5d9b92cb8c096814fae311d6700ac829792df687/src/duckking/simulation.py#L202)与[音轨](https://github.com/zhoutingunl/DuckKing/blob/5d9b92cb8c096814fae311d6700ac829792df687/frontend/src/chorale-demo.js) |
| 坐姿轮唱／点名 | 指定成员站稳独唱再坐回；工坊已有 C→A 和临时改队列 | 新增是更丰富的实时导演规则，不是首次支持点名；见[seated choir](https://github.com/zhoutingunl/DuckKing/blob/5d9b92cb8c096814fae311d6700ac829792df687/src/duckking/seated_choir.py) |
| 四鸭发布会 | 随机散落、集结排队、碰撞坐站反应、选中鸭翻滚／坐下／齐舞，语音目标快照 | 队形老师、接龙、交通规则可复用状态机；场景编排与规则导航不改称 PPO；见[stage](https://github.com/zhoutingunl/DuckKing/blob/5d9b92cb8c096814fae311d6700ac829792df687/src/duckking/stage.py) |
| A* 到点／避让 | stage 内有界网格 A*、重规划、真值位置闭环、避其他鸭与排队验收 | 尚非通用物体地图、相机避障或全屋导航；抽取接口＋道具地图是控制工程；见[A*](https://github.com/zhoutingunl/DuckKing/blob/5d9b92cb8c096814fae311d6700ac829792df687/src/duckking/stage.py#L89) |
| 互动工坊 | 导演、递送续送、评委指挥、声音身份、暗号、足球教练、鸭王说、追问、专注、换班人格 | 受限计划最多六步／二十秒；主要是状态与工具编排，扩展通常不需新运动策略；见[任务契约](https://github.com/zhoutingunl/DuckKing/blob/5d9b92cb8c096814fae311d6700ac829792df687/src/duckking/studio.py#L22) |
| 转盘与跷跷板 PPO | 均已有专用后端、策略与历史评估 | 优先增强解释／可靠性／回放，不重复立项；当前训练形式见下文 |
| 自充电、视觉找物、官方乐器 | 当前场景／工具没有完整接线 | MicroDock、RGB／ToF／detector、theremin 分别是新机械任务、新感知、新音乐接口；不能一并算简单 UI 工作 |

第 7 幕“一屏双魂”是两个独立物理房间；双鸭／四鸭同场才是共享物理世界。桌上跌落剧情也不能承诺任意跌落自救。坐姿四鸭、四鸭发布会以及现有工坊已把语音改口、目标选择与编排推进到较完整阶段，后续应展示新的用户决策和新终态证据，而非再次播放同一动作。([完整剧目](https://github.com/zhoutingunl/DuckKing/blob/5d9b92cb8c096814fae311d6700ac829792df687/frontend/src/demo-catalog.js)、[桌上控制](https://github.com/zhoutingunl/DuckKing/blob/5d9b92cb8c096814fae311d6700ac829792df687/src/duckking/table_choir.py))

### 5.2 已有 PPO 应按当前任务契约解释，旧设计设想不能覆盖现状

当前转盘不是从零训练走路，也不是已部署关节残差 PPO。它用 **25→64→64→3 网络、10 Hz 学三个非负反馈强度**，再由显式中心／朝向反馈生成有界速度；底层冻结官方 velstand 以 50 Hz 控制，物理以 200 Hz 步进。三个目标为随盘站稳、保持朝向、偏心回中。**历史固定评估记录、非本轮测试：**13 秒、100 个未见环境种子，PPO 分别 100/100、89/100、59/100，同条件官方基线 100/100、0/100、0/100。第一关没有证明必须使用 PPO，后两关的稳定性仍是改进方向，不能只放最成功镜头。([当前动作映射](https://github.com/zhoutingunl/DuckKing/blob/5d9b92cb8c096814fae311d6700ac829792df687/src/duckking/balance.py#L321)、[L1 记录](https://github.com/zhoutingunl/DuckKing/blob/5d9b92cb8c096814fae311d6700ac829792df687/training/results/level1-cpu-v4/test.json)、[L2 记录](https://github.com/zhoutingunl/DuckKing/blob/5d9b92cb8c096814fae311d6700ac829792df687/training/results/level2-cpu-v4/test.json)、[L3 记录](https://github.com/zhoutingunl/DuckKing/blob/5d9b92cb8c096814fae311d6700ac829792df687/training/results/level3-cpu-v4/test.json))

当前跷跷板是 `seesaw-v4-passive-docking`：板与配重均无电机，17 维观测、站定／前进／后退三个离散动作，鸭子走位压板，让自由配重移动并反向制动到中央目标区；底层仍是官方步态加横向／朝向反馈。**历史固定评估记录、非本轮测试：**100 回合 98 成功，零步速、回中、仅配平三规则基线均 0/100。actor 从旧 v3 迁移，`early` 是当前阶段学习前的迁移模型，不能标成随机零步网络；旧 88/100、99/100 属于不同契约。真人对战里的语音延迟属于体验的一部分，不能包装成去除交互延迟的算法公平评测。([当前环境](https://github.com/zhoutingunl/DuckKing/blob/5d9b92cb8c096814fae311d6700ac829792df687/src/duckking/seesaw.py)、[历史 report](https://github.com/zhoutingunl/DuckKing/blob/5d9b92cb8c096814fae311d6700ac829792df687/training/seesaw_results/report.json)、[工件来源与限制](https://github.com/zhoutingunl/DuckKing/blob/5d9b92cb8c096814fae311d6700ac829792df687/training/seesaw_results/README.md)、[真人对战说明](https://github.com/zhoutingunl/DuckKing/blob/5d9b92cb8c096814fae311d6700ac829792df687/docs/SEESAW_COACH.md))

### 5.3 一站式入口必须保留四种真实来源

**原创动画预览**只是运动学／画面表现；**DuckKing MuJoCo**是本项目直接加载官方模型与策略的 CPU 物理控制；**官方 robotd 连接**使用官方 daemon 与其状态／控制协议；**Linx 实时云语音**是独立的理解、音频和工具调用链。当前 robotd 适配主要覆盖 move／head／pose／stop／subscribe，sit、roll 与场景动作仍被限制在 MuJoCo；不能因为官网有技能就推断本项目硬件接口已接通，也不能为 robotd 伪造不存在的世界坐标。([预览后端](https://github.com/zhoutingunl/DuckKing/blob/5d9b92cb8c096814fae311d6700ac829792df687/src/duckking/motion.py#L251)、[物理后端](https://github.com/zhoutingunl/DuckKing/blob/5d9b92cb8c096814fae311d6700ac829792df687/src/duckking/simulation.py#L1)、[robotd 适配](https://github.com/zhoutingunl/DuckKing/blob/5d9b92cb8c096814fae311d6700ac829792df687/src/duckking/robotd.py#L26)、[动作分流](https://github.com/zhoutingunl/DuckKing/blob/5d9b92cb8c096814fae311d6700ac829792df687/src/duckking/motion.py#L382))

local-first 路由、预录剧本、本地音乐和本地确认音都应保留实际来源标签。云会话断开或真实后端失败时，维持明确失败／断开状态；不静默切预览，也不把本地动作结果说成云端响应。这个边界已在当前实现和测试中有基础，新社区场景应继承。([混合路由](https://github.com/zhoutingunl/DuckKing/blob/5d9b92cb8c096814fae311d6700ac829792df687/src/duckking/hybrid_voice.py#L98)、[语音 generation 隔离](https://github.com/zhoutingunl/DuckKing/blob/5d9b92cb8c096814fae311d6700ac829792df687/src/duckking/voice.py#L520)、[云失败行为测试](https://github.com/zhoutingunl/DuckKing/blob/5d9b92cb8c096814fae311d6700ac829792df687/frontend/tests/demos.spec.js#L67))

## 6. 先交付六条清楚的体验，再扩展需要新观测和动力学的节目

### 6.1 原有 22 项路线保持排序，新增候选先过合同验收

排序先看资产完整性、相对现有代码的增量、CPU 路线与取消／恢复，再看新鲜感、趣味和观众能否看懂结果。**部署工件缺失、许可来源不明、执行契约不匹配，或无法可靠终止任一项，都足以否决进入正式现场入口。** 这不会否决研究价值，可以先留来源卡、历史回放或实验页。以下所有新概念均为建议；“低／中／高投入”是相对估计，不代表工时承诺。

| 顺序／波次 | 概念与示例口令 | 观众看见什么 | 复用资产／新增工作 |
|---|---|---|---|
| 1／首波 | 参数实验室：“慢慢走两秒，再快一档。” | 同一鸭在有限档位内行动，命令速度与实测位移并列 | 当前 Action；新增参数暴露、包络与结果说明，低—中；不重训 |
| 2／首波 | 情绪小剧场：“先好奇，再不服，最后笑一下。” | 姿态、头部、嘴与短音构成可打断表演 | 官方 13 项随包情绪；关键帧／音轨适配与仲裁，中；编排 |
| 3／首波 | 四鸭临场导演：“A 和 C 接龙，B 坐着等，换个顺序。” | 选中成员执行、旁观成员保持，改口后旧队列消失 | 现有 stage／坐姿轮唱／工坊；扩展规则与统一入口，中；编排 |
| 4／首波重点 | 回窝歇会儿：“回窝坐好；先别睡，再出来。” | 接近、转身、坐下后蹭、仿真接通、脱离 | MicroDock v2；场景合成、BAM／延迟、策略切换、取消，中高；现成 RL＋控制组合 |
| 5／首波候补 | 门槛挑战：“慢点跨过去，站稳再告诉我。” | 双脚上 25 mm 门槛，恢复站稳；失败可见 | step-up 两个 ONNX 与 MJCF；接触切换、终态与停止，中；现成 RL |
| 6／首波后段 | 三色寻宝：“找到蓝箱子，停在前面。” | 第一视角／检测框、搜索轨迹、到达或找不到 | Bravo supervisor＋motor＋场景；相机／深度与任务适配，中高；现成模型链 |
| 7／第二波 | 传感器探险：“说说你前面有多远。” | RGB 与 8×8 ToF／射线覆盖随障碍变化 | 官方 body server；数据流、可视化、观测来源，中；无需新 RL |
| 8／第二波 | 距离乐器：“打开距离琴，我来改变音高。” | 虚拟物体接近 ToF，音高与嘴形变化 | 官方 theremin；射线交互、音频生命周期，中；不是手指空气钢琴 |
| 9／第二波 | 命名房间：“记住这里叫客厅，回门口等我。” | 地图、地点、路径与到点停稳 | quacknav 或先抽取 stage 真值导航；两种输入路线分开，高；不先要求新运动 RL |
| 10／第二波 | 平衡挑战课堂：“这次别跟着盘转；为什么没回中？” | 同条件基线／策略及轨迹、滑移、失败原因 | 当前 balance／seesaw；解释与回放，中；可靠性改进另立训练任务 |
| 11／第二波 | 秋千教练：“荡起来，先试低档。” | 动作与摆幅逐步形成，显示全程支撑 | Playground swing；模型／BAM 适配和停止方案，中高；未验停止前不承诺“停中央” |
| 12／第二波实验 | 球上杂技：“稳住，再向前挪一点。” | 鸭在自由滚动球上平衡，球与脚接触可见 | basketball LSTM；循环状态、reset、边界与跌落处理，高 |
| 13／后续 | 跟随与球队：“跟着 C，保持距离；两队开球。” | 动态跟随、避碰、球权与进球判据 | microduck-lab 策略或现有多鸭规则基线；感知代理标记、团队调度，高 |
| 14／后续 | 受控积木：“只碰上面那块，底下别动。” | 上块移动、下块保持，接触与位移可复查 | jenga CEM 轨迹＋冻结步态；固定初态／资产恢复，中高；不是新 PPO／搭塔 |
| 15／后续 | 看懂房间：“走到白桌旁边。” | 第一视角、语言 waypoint、接近目标 | LightNav VLN＋MPC；GPU 服务、模型／场景与失败链，高 |
| 16／实验 | 高跷巡游／计时快跑：“慢慢转一圈／跑到线前停。” | 形态或步态变化，起停／跌倒结果可见 | Playground 分高度模型／running；独立场景、控制包络，中高 |
| 17／实验 | 单足／轮滑花式：“单脚站稳／做一圈轮上旋转。” | 新支撑或轮上姿态 | collision-flamingo-ii 差异先查清；官方 Spin／Swizzle／Slope／RollerStandUp 先补权重，未齐前不能交付 |
| 18／实验 | 爬梯、夹缝、高台特技：“爬上去，再打招呼。” | 多阶段身体接触与明确失败终态 | Playground 发布包；阶段切换、辅助披露和恢复，高；不承诺平地无辅助空翻 |
| 19／研究 | 连续带球／守门：“把球送进蓝门，别踢太远。” | 连续触球或拦截全过程 | 当前单次 kick 作基线；新连续控制、感知与训练评价，高；不自动摆球掩盖失败 |
| 20／研究 | 推箱入库／真实地面拾物：“送进左边格子。” | 物体在接触下移动、离地或落稳 | 当前步态／架上夹棒作基线；新物体任务与控制／训练，高 |
| 21／研究 | 自由滑板／自主蹬板：“滑一段，停在标记前。” | 独立板、轮、脚真实接触 | 现有足轮不能替代；先平衡，再推进、转向、制动分开验证，很高 |
| 22／独立硬件线 | 真实回充／相机手指琴／实体迁移 | 真实电源遥测、真实手部感知或实机动作 | 需要额外硬件与实测闭环；不列本次仿真交付承诺 |

前六项构成首波清单，其中 **1—3 是可交付性最高的产品增量，4 是新鲜感与生活化叙事最强的新增，5 是最清楚的新身体技能，6 是第一项可辨认的视觉任务**。若时间收紧，先交付 1—4 的完整成功／改口／失败链；5—6 各自在隔离重放通过后再进入站点，而不是同时铺开所有实验。依据分别来自[当前动作与工坊](https://github.com/zhoutingunl/DuckKing/blob/5d9b92cb8c096814fae311d6700ac829792df687/src/duckking/studio.py)、[官方情绪](https://github.com/pollen-robotics/microduck/tree/da34a2212ae12eddfd73d0dfbf924f291aaf1dc9/robotd/emotions)、[MicroDock](https://github.com/Vottivott/microduck-playground/blob/052a2494dd6372289221c7a4f24a245b443dd75f/hardware/microdock-v2/README.md)、[门槛](https://github.com/bihaokun/microduck-step-up-policy/blob/ec769571438c2558a2d847a164a91022971fceb0/README.md)和[三色找物](https://github.com/Bravo-Robots/microduck-indoor-object-search-rl/blob/5f087e452b970c6405a3d61f7badb0ac450f2d1a/outputs/release/MODEL_CARD.md)。

增补候选不改动上面 22 项编号，也不把首波六项扩成新的承诺范围。下表是下一轮隔离验证的补充短名单，优先级属工程判断，来源和失败条件见 §2.5、§4.2—4.3。

| 补充候选 | 可展示的语音体验 | 进入站点前必须补齐 |
|---|---|---|
| happy-hop／flamingo-cycle：优先验证 | “跳一下，站稳再告诉我”／“抬左脚，放下后换右脚” | 前者延迟／滤波／落地恢复；后者专用角色／有限保持／落足与取消，不能沿用无限持续命令 |
| footsteps：系统能力 | “踩到标记上，走三步停下” | planner＋追踪器＋支撑足坐标／里程计全链；验实际落足误差，不把目标值当结果 |
| Arena timeline：优先借鉴格式 | 在已有四鸭导演中增加有时限的节目与声部安排 | 先验四鸭调度／取消和音源标记；八鸭容量与新赛事分别评测，参考权重授权另核 |
| strict Soccer／Circus／Twin：独立实验 | “找到球再踢”／“配合跳绳”／“回窝显示虚拟电量” | 分别验 RGB 输入、绳接触与协调、虚拟电量边界；不共用一个“已验证”标记 |
| Piano／TorchRL／其他单鸭实验：研究储备 | 键盘接触、技能切换及动作失败对照 | 先补成功率、许可、运行合同与恢复；groove 等许可未清模型不进入分发包 |

### 6.2 首波验收必须让动作结果决定台词

下列为拟议验收要求，阈值需在固定模型上标定并写入场景契约；它们不是本轮已通过的测试。

| 首波体验 | 主要工程工作 | 成功／失败的物理或状态证据 | 取消与恢复 |
|---|---|---|---|
| 参数实验室 | 将已验证速度／身体档位暴露给 UI、MCP 与本地语法；记录命令与实测 | 实际位移、速度、支撑和站稳；输入值不冒充达成值，跌倒／超时失败 | 替换旧动作，速度归零并等待稳定；坐姿移动需先站起，不能突然切策略 |
| 情绪小剧场 | 映射头／身体／嘴关键帧与音轨，动作所有权和前置姿态 | 指定关键帧序列确实执行、音轨对应、支持接触仍成立；播放完成不等于识别人类情绪 | 清旧关键帧与音轨；回到当前姿态可接受的稳定状态；夹物时嘴部表达让位于抓取 |
| 四鸭导演 | 复用目标快照、多选与队列，新增接龙／规则 | 正确成员行动、旁观者保持，队形／坐站／发声由本轮状态确认 | 全部选中成员与音轨同一 generation 撤销；旧队列不复活；独立房间互不影响 |
| MicroDock | 模型／磁力／BAM／延迟一致；walk→sit→scoot→undock 状态机；显式虚拟电量 | 阶段位置／朝向、身体接触、接口几何误差、连接标志、最终离坞站稳；未接通不得报已充电 | 未接通时有界减速并保持可支持姿态；已接通时取消任务不等于强拉离坞，离坞单独发令；无已验恢复则明确暂停实验并记中断，不算成功 |
| 门槛 | 模型、双脚上台检测、walk／recovery 切换 | 脚与台面接触、根位置、最终稳定及越界；允许的头撑地按作者条件披露 | 取消后停止推进；台边无法安全站稳则终止并保留状态，不瞬移过关；显式 reset 后再试 |
| 三色寻宝 | RGB／深度管线、supervisor／motor 调度、目标绑定、终态工具 | 图像检测证据、目标类别、距离与停稳；未见目标／跌倒／超时有独立失败理由 | 清 waypoint 与 supervisor 状态、速度归零；新任务重新绑定目标，旧观测过期后拒绝继续 |

现有 MotionController 的 request_id 幂等、任务取消、`finally stop`、有限输出检查和各场景实测判据可复用，但“源码里已有测试”不等于新控制器自动通过。首波至少覆盖成功、改口、取消、超时、断云、状态过期、策略异常以及重置后再运行；涉及新协议时补分帧／粘包／乱序与断连测试。([动作生命周期](https://github.com/zhoutingunl/DuckKing/blob/5d9b92cb8c096814fae311d6700ac829792df687/src/duckking/motion.py#L337)、[运动边界测试](https://github.com/zhoutingunl/DuckKing/blob/5d9b92cb8c096814fae311d6700ac829792df687/tests/test_motion_edges.py)、[协议测试](https://github.com/zhoutingunl/DuckKing/blob/5d9b92cb8c096814fae311d6700ac829792df687/tests/test_robotd.py)、[四鸭取消测试](https://github.com/zhoutingunl/DuckKing/blob/5d9b92cb8c096814fae311d6700ac829792df687/tests/test_stage.py))

**什么时候才需要新 RL？** 参数暴露、情绪、音乐、队列、地图到点和已有策略切换先用确定控制／状态机；导入已发布 ONNX 先解决契约与复现，不默认重训。连续控球、任意坐高、自由板平衡与推进、真实地面抓取等改变目标或接触任务，才进入新控制器／训练比较。即使需要 RL，也应保留强规则基线，并在相同观测、速度约束、初态和终止标准下比较；若基线已经满足任务，不为了展示“训练”增加不必要模型。

## 7. 一站式架构复用现有渲染器，用能力契约连接语音、策略和证据

### 7.1 统一入口，保持后端与资源边界

DuckKing 已有共享 `physicsView`、`createPhysicsModelLoader` 与 `renderScheduler`，场景、演出、转盘和跷跷板共用物理视图；模型按 revision 缓存并检查 DKM1 来源／物理标识，隐藏视图不持续渲染。**继续扩展这套显示层，不导入已知有问题的旧 DuckKing_PPO 渲染器。** 新增社区场景输出同一模型／状态契约，训练和控制的差异留在后端适配器中。([共享物理视图](https://github.com/zhoutingunl/DuckKing/blob/5d9b92cb8c096814fae311d6700ac829792df687/frontend/src/physics-view.js)、[模型缓存与校验](https://github.com/zhoutingunl/DuckKing/blob/5d9b92cb8c096814fae311d6700ac829792df687/frontend/src/model-loader.js#L8)、[渲染调度](https://github.com/zhoutingunl/DuckKing/blob/5d9b92cb8c096814fae311d6700ac829792df687/frontend/src/render-scheduler.js))

| 层 | 建议落地内容 | 验收要点 |
|---|---|---|
| 能力目录 | 单一 `capability_id` 记录场景、身体、目标、允许参数、前置姿态、时限、成功／失败、取消语义、脚本／规则／训练分类 | 由目录生成菜单、工具说明、语音提示和来源卡；防止 Action／MCP／grammar／节目各说一套 |
| 来源／证据 | 记录作者、commit、policy hash、模型版本、许可证、观测来源、音源、实测日期与证据等级 | 常驻只显示用户需要的“动画／MuJoCo／robotd”“本地／Linx”；技术细节放展开区，凭据与设备身份不进入响应或日志 |
| 语音意图／场景工具 | 先绑定当前房间、场景与实体，再接受有界目标；复合指令先完整校验；工具结果返回本轮终态 | 切场景不能遗留旧目标；不允许语言模型直接写力矩、任意代码或无限循环；云回复只能引用新鲜工具结果 |
| 模型／checkpoint 适配 | 独立声明关节顺序、HOME、单位／坐标、观测、动作语义、归一化、频率、BAM／PD、延迟／滤波、碰撞／摩擦与循环状态 | 61→14 只做第一道检查；完整 checkpoint 与推理 ONNX 分开；LSTM／历史缓冲在重置和任务边界显式处理 |
| 任务与房间隔离 | 每房间独立世界、控制器状态、generation、request_id 与超时；多鸭目标快照不可被下一轮悄然改写 | 取消旧任务后不再写控制；清除任务注入的外力／音轨；环境磁力等真实场景模型不因取消而消失 |
| 资源／性能 | 首页按需加载场景、mesh、ONNX、音频和相机；服务端设房间／相机配额；模型不可变资源可共享，状态不共享 | 未进入场景不启动相机或 GPU 服务；报告完整控制循环耗时、实时率与超期，不把单次 ONNX 耗时当系统实时性 |
| 结果／回放 | 同一时间线记录语音意图、接受／开始／取消／完成、物理观测、失败原因与版本；支持分享可复核回放 | 清楚区分实时和历史录像；回放不伪造云端会话；重播保留 seed／初态／控制输入与观测来源 |

当前目录分散在 Action、MCP、local_commands、demo-catalog、studio-catalog 和统计枚举中；源码已支持 choir，但统计 scene 白名单仍未列 choir，是统一目录的具体收益。迁移应先兼容现有工具名称和会话，不一次性重写所有后端。([统计白名单](https://github.com/zhoutingunl/DuckKing/blob/5d9b92cb8c096814fae311d6700ac829792df687/src/duckking/app.py#L307)、[工具目录](https://github.com/zhoutingunl/DuckKing/blob/5d9b92cb8c096814fae311d6700ac829792df687/src/duckking/mcp.py)、[本地语法](https://github.com/zhoutingunl/DuckKing/blob/5d9b92cb8c096814fae311d6700ac829792df687/src/duckking/local_commands.py))

### 7.2 分期施工以可复核的退出条件推进

| 阶段 | 交付物 | 进入下一阶段的条件 | 相对投入估计 |
|---|---|---|---|
| A：整理基线 | 11 场景能力地图、来源卡、真实后端／语音 route、历史与现场结果分离；参数实验室、四鸭入口 | 现有场景入口一致；取消、房间隔离、失败与协议检查通过；记录当前 v8 基线 | 低—中 |
| B：接入首波资产 | 官方情绪；MicroDock 独立 replay 和站点适配；门槛／三色找物各自隔离试验 | 固定 commit／hash／许可、模型契约可复核；至少具备成功和失败轨迹，停止／重置不残留控制 | 中—高，MicroDock 为重点 |
| C：形成可现场讲述的闭环 | 真人语音发起、临时改口、失败解释、再次尝试；首波完整节目与回放 | 真实 Linx 路由可见；工具执行与语音陈述一致；测量含网络与调度的端到端延迟；失败不降级冒充 | 中 |
| D：补感知与新接触 | RGB／ToF、theremin、命名地点、秋千；篮球／球队实验入口 | 各自 CPU／资源预算与观测来源明确；停止方案可验；新模型没有破坏原场景 | 中—高 |
| E：训练与硬件分支 | 连续物体控制、自由板等新任务；实体电气／感知／动作迁移另立计划 | 相同条件强基线、训练／验证／封存测试分离；硬件结果由硬件测量证明 | 高，不预报训练费用或成功率 |

版本升级安排在 A／B 间独立进行：保留 v8，导入 v9 候选，做同 seed／同模型的走停、坐站衔接、踢球、滚翻、多鸭及转盘／跷跷板回归，再决定 pin。不能为了接 MicroDock 同时悄然更换所有旧场景的执行器。新控制器若要求 BAM，先在独立场景保持其训练物理；如果转换到 DuckKing 当前运行物理，则重新评价输出和长轨迹，不能只比较一帧动作。

实施时沿用仓库 feature branch／PR 流程，不直接把应用更改推到 main，也不移动 v0。文档、能力卡、演示视频与发布 SHA 应同步；只发布实际跑过的证据，不补造作者、运行记录、云会话或训练成绩。本报告本身未修改应用、依赖 pin、测试或远程部署。

### 7.3 许可证按具体资产与版本管理

| 资产范围 | 已核实声明 | 接入动作 |
|---|---|---|
| 最新官方 RL | 代码／XML／JSON／配置等 Apache-2.0；指定模型目录 `.stl` 为 **CC BY-NC-SA 4.0** | 导入新版时逐文件保留来源和许可；见[模型许可边界](https://github.com/pollen-robotics/microduck_rl/blob/bae39f5900b318f7e87fc485c30a31213cfa14eb/LICENSE-MODELS.md)与[代码许可](https://github.com/pollen-robotics/microduck_rl/blob/bae39f5900b318f7e87fc485c30a31213cfa14eb/LICENSE) |
| 当前 DuckKing 旧 pin | 采用较早 RL／policy 版本，已有第三方来源表 | 分别核查旧 revision 当时文件与条款；不声称新版说明追溯改变旧 pin，也不以旧 pin 回避新资源条款；见[当前第三方说明](https://github.com/zhoutingunl/DuckKing/blob/5d9b92cb8c096814fae311d6700ac829792df687/THIRD_PARTY.md) |
| 官方策略／情绪／浏览器 | motion 模型卡、emotions 为 Apache-2.0；浏览器 README 的 app 代码声明不自动覆盖全部 mesh／音乐 | 按模型、关键帧、wav、转制 mesh 分别登记；见[策略模型卡](https://huggingface.co/pollen-robotics/microduck-policies/blob/283771bcb3690a0a94a288c108365d9b630d21e4/README.md)、[情绪许可](https://github.com/pollen-robotics/microduck_emotions/blob/431c73df8a9d3cb6b6067d09ced6c169fdfa59fd/LICENSE) |
| MicroDock／duckmind | MicroDock 软件／策略／训练 Apache-2.0，打印件 CC BY-NC-SA 4.0；duckmind 代码 Apache-2.0、官方身体资产另受其条款 | 保留 CAD／STL 与软件清单；见[MicroDock 硬件许可](https://github.com/Vottivott/microduck-playground/blob/052a2494dd6372289221c7a4f24a245b443dd75f/LICENSE-HARDWARE)、[duckmind 许可说明](https://github.com/joseyarashio/duckmind/blob/719e139b03bb2dd934b07561d0eb4a90def91863/README.md#licence) |
| 检测器／场景／音乐依赖 | 仓库外壳许可不能代表 Ultralytics、预训练权重、ProcTHOR、连接组数据或所有曲目 | 分开核对依赖和数据；排除明确 test-only 音乐；许可未清晰的候选先保留研究链接 |

这些是来源管理要求，不是法律结论。对外网页、视频和下载包都应能追到具体资产版本；特别是机器人网格、派生场景与曲目，不能只展示项目根目录的一张 LICENSE。

增补项也执行同一门槛：happy-hop、flamingo-cycle、footsteps 模型卡有 Apache-2.0；groove、playdead、polite-bow、moonwalk、社区 standup、TorchRL 权重及 Arena reference 未在所查固定树中找到明确独立授权。318_lab、Wicroduck、microdux 的根许可也未确认，electric-slide 标为 `other`。这是本轮授权证据缺口，不是断言作者禁止使用；各固定来源见 §2.5、§4.2—4.3，未补清前保留研究链接，不随本站重新分发。

## 8. 让每个体验都能回答“它为什么成功或失败”

DuckKing 最有价值的下一步，是让用户说出的目标、机器人实际采用的观测、动作过程和最终证据出现在同一条体验链里。回桩可以展示定位噪声、机械对准和离坞条件；找物可以展示相机看到的内容；平衡可以展示相同初态下规则与策略的差异。这样，已有脚本、官方策略与新社区模型都能各自提供清楚的体验价值。

首波完成后，一站式入口的扩展单位应是一份带版本、边界、终止和回放的“能力包”。这能让新模型更快接入，也让失败保留教学与调试价值：用户知道本轮发生了什么，后续开发者知道下一步究竟该补参数、控制、感知，还是训练。
