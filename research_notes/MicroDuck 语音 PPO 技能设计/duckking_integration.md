# DuckKing 现有能力与语音 PPO 技能集成研究

研究时间：2026-11-01，Asia/Shanghai。本笔记基于本地只读源码检查；DuckKing HEAD 为 `2e821bd60163a6611c4bcf0839aebafc2e734a94`，分支 `fix/appearance-test-budget`；固定上游模型 checkout 为 `b02fdea4902c2b93b7d34a83a6f05da4ececb7d3`。没有启动训练、运行物理验收、修改应用代码、推送或部署。下述指标与奖励均为设计提案，不是测得的性能。未追踪的用户文档、reports 与既有 research_notes 保持原样。远端冻结时间已过，后续实现仍需满足仓库的显式解冻指令及 feature branch / PR 要求。[仓库约束](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/AGENTS.md:1) [固定资产版本](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/scripts/fetch_scene_assets.py:9)

## 1. 已经有什么：控制链、物理自由度与不能包装为新学习的能力

### Takeaway

DuckKing 已经是“官方预训练策略 + 真实 MuJoCo 接触 + 自研高层调度与网页渲染”的系统；已有四鸭 A* 导航、翻滚、坐站、轮滑、踢球与固定位置的嘴部搬运。新增 PPO 最合适先承担**条件化任务决策**，必须清楚标为“在既有官方步态上学习的新任务控制器”，而不是重新声称学会走路、首次自主到点或首次轮滑。[驱动](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/src/duckking/simulation.py:54) [四鸭寻路](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/src/duckking/stage.py:89) [既有技能](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/src/duckking/official_skills.py:110)

### Cited Findings

**实际运行链。**

- `MuJoCoBackend` 独立于 `robotd`，加载八个固定 ONNX，使用 CPUExecutionProvider，单个 ONNX session 的 intra/inter thread 均为 1。walk 实际映射 `velstand.onnx`，其余为左右踢球、sitstand、roulade、ground_pick、roller、roller_crouch。文件哈希固定在下载脚本，策略仓库版本为 `665ae4eb20bfe13bca1ef4ea6d4bb6b4a096e448`；manifest 列出更多文件，不等于应用全部加载。[加载代码](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/src/duckking/simulation.py:120) [文件摘要](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/scripts/fetch_scene_assets.py:9)
- 每次 `Driver.step()` 拼 61D float32：角速度 3、投影重力 3、14 个关节位置减 HOME、14 个关节速度、上一动作 14、命令 13。命令块是 twist 3 + neck/head pose 4 + body pose 6。ONNX 产生 14D，检查形状和 finite 后写 `data.ctrl = HOME + action * scale`；普通比例为 1、roulade 为 0.9、roller base 为 0.8，previous_action 保留网络原单位。**输出是关节位置目标，不是根节点位移，也不是网络直接输出力矩。**[实际推理](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/src/duckking/simulation.py:77) [上游布局](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/external/microduck_rl/AGENTS.md:54)
- 应用控制每 20 ms 一次、每次调用四个 5 ms MuJoCo 步：50 Hz 策略、200 Hz 物理。当前 plain XML chosen_actuator 是 position servo：kp=0.55、kv=0、joint damping=0.053、frictionloss=0.0048、armature=0.0018、forcerange ±0.96、ctrlrange ±10；因此应准确称“位置目标经 XML 位置伺服与被动阻尼生成作用力”。不能描述成任意关节扭矩控制，也不能把宽 ctrlrange 当关节机械可达角。[步进](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/src/duckking/simulation.py:274) [伺服定义](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/external/microduck_rl/src/mjlab_microduck/robot/microduck/robot_allcollisions.xml:41)
- 重大动力学边界：固定上游训练代码现用 BAM M6 电压/负载摩擦模型与 actuator delay；DuckKing 当前 CPU 场景直接使用上述 XML 位置执行器，未接 BAM。共同使用 MicroDuck 网格、HOME 或 61D 并不保证动力学一致。上游还要求导出时烘焙 normalizer，不可手工转换权重；默认策略无 action EMA，任意加滤波会改变迁移条件。[上游 BAM](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/external/microduck_rl/src/mjlab_microduck/robot/microduck_constants.py:149) [规范](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/external/microduck_rl/AGENTS.md:69)
- 应用 actor 没有 RGB、深度或图像编码器；gravity 是直接从仿真旋转矩阵取值，关节/IMU 也是仿真量。高层四鸭导航直接读根位置/朝向，`find_companion` 是仿真几何距离、±60°视场与射线遮挡判定，ball observe 明确返回 `sensor=mujoco_state_query`。可以称“仿真状态感知/几何可见性”，不能说摄像头视觉理解。上游 walking actor 明确移除 base_lin_vel 与 height_scan，critic 可用额外真值；这不等于应用高层目标控制也没有特权状态。[actor 输入](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/src/duckking/simulation.py:89) [球与同伴](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/src/duckking/simulation.py:525) [critic 区别](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/external/microduck_rl/src/mjlab_microduck/tasks/microduck_velocity_env_cfg.py:531)
- `robotd` 是另一条路径：Unix socket 上 newline-delimited JSON-RPC，发送 `robot.move` 速度意图，订阅 20 Hz 官方状态，1 秒过期即拒绝动作；snapshot 不捏造世界坐标，`physics=None`，官方 viewer 拥有物理画面。新 PPO 首期应明确接 `mujoco` 场景，不默认宣称已能控制官方 daemon 或真机。[robotd 协议](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/src/duckking/robotd.py:26) [状态边界](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/src/duckking/robotd.py:170)

**身体/模型自由度。**

| 部位/模式 | 实际定义及边界 | 源码证据 |
|---|---|---|
| 两腿 | 每腿 hip_yaw、hip_roll、hip_pitch、knee、ankle，各 5 个 hinge | [关节次序](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/src/duckking/simulation.py:31) |
| 颈/头 | neck_pitch、head_pitch、head_yaw、head_roll，4 个主动 hinge；不是四维空间姿态 quaternion 命令 | [关节次序](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/src/duckking/simulation.py:31) [head command](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/external/microduck_rl/src/mjlab_microduck/tasks/microduck_velocity_env_cfg.py:656) |
| 躯干 | root freejoint，世界 xyz + 旋转共 6 个自由度；没有给身体独立的 6 个平移/旋转电机，body_pose 6 是策略条件 | [root](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/external/microduck_rl/src/mjlab_microduck/robot/microduck/robot_allcollisions.xml:95) [body 条件写入](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/src/duckking/simulation.py:469) |
| 普通官方模型 | 静态 XML 检查得到 14 scalar joint + 1 freejoint + 14 actuators，即 20 个广义速度自由度，21 qpos（四元数 4 分量）；该计数为结构推导，没有在本次编译模型验收 | [XML](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/external/microduck_rl/src/mjlab_microduck/robot/microduck/robot_allcollisions.xml:95) |
| 嘴部 | 官方嘴原为融合结构。DuckKing 实验改编增加 mouth hinge 与第 15 个 position actuator，30°开/-5°合，±0.025 force；不是官方策略 14D 中的动作。skills、carry、stage 构建器可加入它 | [实验声明](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/src/duckking/grasp_model.py:1) [mouth 定义](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/src/duckking/grasp_model.py:140) [场景选择](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/src/duckking/skills_model.py:10) |
| 轮滑 | 每脚前后两轮，共四个被动 wheel hinge：LF、LR、RF、RR；仍只有 14 主动关节。结构为 18 scalar + free root，即 24 广义速度自由度。实际滚轮摩擦在构建后设 .003。没有 wheel motor、车把或滑板甲板 | [轮轴](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/external/microduck_rl/src/mjlab_microduck/robot/microduck/robot_groundcontact_rollers.xml:175) [右轮](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/external/microduck_rl/src/mjlab_microduck/robot/microduck/robot_groundcontact_rollers.xml:351) [被动摩擦](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/src/duckking/skills_model.py:26) |
| 搬运物品 | 4g 小棒是独立 free body，通过上下 pad 接触与重力运动，读取真实接触法向力、滑移、离架高度与落台支撑；不是 weld/attach 把物体粘到嘴上 | [物品模型](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/src/duckking/grasp_model.py:62) [验收](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/src/duckking/grasp.py:54) |
| 四鸭 | stage 通过给四个 allcollisions 模型加 a_/b_/c_/d_ 前缀，放到**同一** MjModel/MjData，实际互相碰撞；每只独立 Driver。四种颜色是浏览器外观，不是四种控制器或四个训练等级 | [四鸭模型](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/src/duckking/stage.py:55) [四 Driver](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/src/duckking/simulation.py:197) [颜色](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/frontend/src/duck-appearance.js:7) |

**已实现，不应计入新学习成果。**

- 行走、后退/横移、转向、头部跟踪、站稳/跌倒恢复底座来自既有官方策略；sit/stand、roulade、ground_pick、rollers 和 crouch 已接入。ground_pick 的结果特意写 `object_grasped=False`，实际是低头到地面动作，并非完成了抓取。[驱动策略表](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/src/duckking/simulation.py:131) [测量与结果](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/src/duckking/official_skills.py:99)
- 四鸭 `path_to` 已实现 10cm 网格 A* 避让其他鸭身体位置；`navigate` 约每 .65 仿真秒重规划，steer 根据实际 xy/yaw 写速度与转向，以到点与朝向阈值确认，超时、越界、失稳失败。已经有随机散落、集结、排队、碰撞后编排坐站恢复、选中多鸭翻滚、同拍舞蹈与实际外力 poke。所以“语音说去某点，然后鸭子走过去”本身不能证明 PPO 超越现状。[A*](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/src/duckking/stage.py:89) [反馈寻路](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/src/duckking/stage.py:229) [有界 poke](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/src/duckking/stage.py:570)
- 固定物品夹起/搬运/放下、停但不松嘴与继续送已是工坊能力；头部/嘴部轨迹由手写 ramp 与阶段机控制，底层仍是官方 gait；新增 PPO 不能把其成功录像当训练所得。[搬运阶段机](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/src/duckking/grasp.py:132) [工坊 delivery](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/src/duckking/studio.py:272)
- “世界杯小教练”现有 observe/prepare/kick：observe 只读真值，prepare 明确摆球，kick 使用已准备的脚前球；暗号配方、临场导演与“鸭王说”是已有动作编排/规则游戏，代码明确禁止将它们称为训练新策略。新分类需避免与现有“教练”混淆。[现有工具边界](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/src/duckking/studio.py:120) [工坊目录](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/frontend/src/studio-catalog.js:1)

### Inferences

- 建议新能力命名为“PPO 学习的导航/任务策略 + 官方步态”。若未来确实重新训练 14D 关节策略，再单独标明“新身体控制策略”。四种配色可帮助辨认比较对象，不能以配色本身暗示学习程度。[分层证据](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/src/duckking/simulation.py:77) [外观独立](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/frontend/src/duck-appearance.js:57)
- 当前最稳妥的训练仿真范围是复用 DuckKing 现有 plain XML CPU dynamics 与 frozen ONNX；若改成上游 BAM，应同时改训练、rehearsal 和实际运行，另做迁移评估。只替换网格或只保证 61D 不够。[运行](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/src/duckking/simulation.py:152) [训练模型](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/external/microduck_rl/src/mjlab_microduck/robot/microduck_constants.py:156)

### Gaps

- 本次仅源码与 XML 结构审计，不宣称这些功能在当前公网服务逐一验证成功；测试文件存在不等于本次运行通过。既有 tests 覆盖取消、无移动不能报成功、实际碰撞、房间隔离等，可在实现期复用验收方法。[测试入口](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/tests/test_official_skills.py:50) [房间测试](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/tests/test_rooms.py:98)
- 未发现现应用的可倾平台、独立滑板、滑板车或学习型推箱 task；这是本次检索范围内的代码结论，不是物理上不可行的证明。资源/吞吐/GPU 型号未核验，不估算保证训练时长。当前机器人无手臂，不能以人体“扶住车把”想象直接移植滑板车动作。[完整动作枚举](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/src/duckking/motion.py:51) [身体关节](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/src/duckking/simulation.py:31)

## 2. 集成设计：语音目标、策略、仿真和渲染如何共用契约

### Takeaway

保留现有语音、房间、任务取消与 Three.js 物理渲染。新增严格目标 schema、策略工件注册、task observation/action adapter 与评估层；语言只表达目标/约束，不直接写关节或生成 root 位移。训练作业独立于生产 YZH737，网页明确区分离线训练记录、当前 checkpoint 推理和真实语音来源。[现有架构](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/docs/ARCHITECTURE.md:91) [现任务边界](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/src/duckking/studio.py:210)

### Cited Findings

- 本地优先语音先识别完整录音并解析整个句子，命中后顺序提交实际动作；unknown/ASR failure 在动作开始前才将原录音交云端。generation 检查阻断旧轮次，执行失败不会云端重做已执行动作。scene-voice 在服务端绑定本房间 scene controller，未加载场景就明确拒绝。[本地路由](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/src/duckking/hybrid_voice.py:96) [房间语音](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/src/duckking/app.py:558)
- `Action` 为 extra=forbid、finite-only，速度/时长有界；同 request_id 不同参数被拒绝，重复同请求不重做；新动作先取消旧任务，连“首调度前取消”的边界也处理；finally 总尝试 backend.stop，无法确认停止会改成失败。物理动作在非 MuJoCo 后端直接报错。[schema](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/src/duckking/motion.py:51) [仲裁与取消](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/src/duckking/motion.py:328) [结果收尾](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/src/duckking/motion.py:435)
- 每个物理房间现在实际构造自己的 `MuJoCoBackend`，新 scene/reset 分配独立 `MjData`；有物理房间上限和 room lock。当前 `discover()` 临时修改 `model.geom_group`，因此未来缓存/共享 MjModel 不能不审计这些可变字段。ONNX 工件可做只读复用，但 last_action、RNN hidden state、任务目标、随机种子、指令和 rollouts 必须每 room/duck 独立。[场景创建](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/src/duckking/app.py:297) [data 重建](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/src/duckking/simulation.py:183) [模型临时变动](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/src/duckking/simulation.py:574)
- 物理状态输出每个 geom 的世界 position 和 3×3 rotation、revision、sim_time、real_time_factor、实际 policy/fallen/contact/error；前端只在 revision 匹配时应用，world group 绕 x 轴 -π/2，故 `(x,y,z)_MuJoCo → (x,z,-y)_Three`。目前没有给新训练器另做骨架或坐标变换的必要。[状态契约](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/src/duckking/simulation.py:802) [坐标适配](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/frontend/src/physics-view.js:24) [矩阵应用](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/frontend/src/physics-view.js:70)
- 当前 renderer 的 primitive 路径明确区分 box，其他 primitive 走 sphere；平台/障碍可先使用 box，独立滑板/轮子如采用新 cylinder primitive 必须扩充真实几何支持，不能把碰撞形状与看见的形状分离。[primitive 渲染](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/frontend/src/physics-view.js:49)

### Inferences

以下全部为**建议架构**，不是现成模块或已测试实现；基于上面的现有接缝。

```text
真实麦克风 → local ASR / Linx（来源独立显示）
            → strict SkillGoal + 服务器已知目标 ID
            → 房间 TaskRunner（仲裁、界限、停止、结果）
            → 已核验 checkpoint + 版本化 task observation
            → [首期：10 Hz 高层 PPO 速度/转向]
            → [50 Hz 官方 frozen 61D→14D locomotion]
            → [200 Hz 同一 MuJoCo 模型/接触]
            → 现有 geometry + revision + geom transforms
            → 原有 physics-view / 四色模型

离线训练作业 → 固定工件 + holdout evaluation → 人可审查的候选策略
```

1. **建立单一仿真/契约库，而不是复制新的 simulator 与 renderer。**建议 `skill_contracts`（joint order、HOME、frame transform、dt/decimation、scene spec、obs schema、limits）、`skill_world`（相同模型构建/step/reset/state）、`policy_registry`（不可变工件验证）、`skill_runner`（room-local rollout/task 状态）、`skill_eval`（同场景同种子评估）。训练目录只依赖这些纯模块，不 import 启动 FastAPI、音频服务或云凭据。[现有重复常量位置](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/src/duckking/simulation.py:31) [现有模型 builder](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/src/duckking/skills_model.py:10)
2. **Goal 不混入 61D locomotion command。**建议 schema：`skill_id / checkpoint_id / target_duck / goal_id-or-bounded-xy / goal_heading / speed_limit / stop_distance / max_sim_seconds / layout_seed / request_id / scene_revision / scene_instance`。词语“蓝鸭”“我前面”“左边”要用本轮锁定的稳定 ID 与明确坐标定义解析；不能将浏览器颜色/镜头左右当世界坐标，也不能让 LLM 任意文件路径加载模型。用离散 preset 或有界数字，未知/冲突则回传待澄清且保持停止。[已有屏幕顺序与实例锁](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/src/duckking/stage.py:29) [颜色是本地偏好](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/frontend/src/duck-appearance.js:19)
3. **首期保留分层控制。**PPO 的独立 obs 包含 body-frame 相对目标、目标距离/朝向、速度估计、障碍相对位置/射线以及上一高层动作；标为 simulator-state 输入。先用两维 forward/yaw 控制降低动作空间，后续有必要再增加 vy。其输出写 Driver.command[:3]，不能 overwrite 14D servo action。既有 61D 网络输入、normalizer 和官方权重不变；new PPO artifact 的 shape/normalization 与 frozen gait 分开记录。[底层命令入口](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/src/duckking/simulation.py:459)
4. **严格工件 manifest。**建议至少包含 model/scene hash、来源 commit、训练代码 commit、dirty flag、task ID、checkpoint step、seed、训练/评估 split、obs/action 字段顺序及单位、normalizer hash、HOME hash、关节名序列、dt/decimation、坐标系、actuator 模式、action scale/clipping/filtering、frozen base ONNX hash、runtime deps、允许场景与 bounds、评估报告摘要。checkpoint 载入先 shape/finite smoke，再同 CPU runtime golden rollout；不兼容就 `policy_incompatible`，不换成另一个能跑的网络。[现有摘要固定方式](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/scripts/fetch_scene_assets.py:11) [normalizer 要求](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/external/microduck_rl/AGENTS.md:74)
5. **取消/停止是端到端契约。**旧任务 generation 失效 → 停止高层策略写命令 → 零速度目标并切回指定站立/已验证停止控制 → 清除 xfrc/mouth 临时写入 → 清空上一高层动作与 recurrent state → 完成 cancelled 状态。stop 不把 robot 传送回起点；reset 才重建状态与 episode ID。底层保持姿态/惯性收敛需要时间，必须分别显示“停止指令生效”与“实测速度进入停止阈值”。若已跌倒，不假称瞬时站稳。对平台/板子还需取消平台扰动控制并明确世界继续/暂停策略。[现有停止](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/src/duckking/simulation.py:474) [现有清力](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/src/duckking/stage.py:596)
6. **限制与错误可观察。**建议同时约束作用空间、总轨迹长度、仿真时长、wall deadline、速度与加速度/动作变化、接触冲量、连续失稳/越界；使用实际状态验收。新 checkpoint 动作按训练相同规则 bound，加入过滤必须 train/deploy 同步。错误区分 `policy_invalid_output / model_mismatch / goal_unreachable / task_timeout / out_of_bounds / fallen / contact_failure / simulation_error / cancelled`。不能因为 reward 上升、计时结束或到达脚本最后一步就成功。[现有实际动作验收](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/src/duckking/official_skills.py:99) [现有数值失败](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/src/duckking/simulation.py:282)
7. **保持通信与计算边界。**语音工具返回 accepted/task_id 后，真实 task 状态推进 completed/failed/cancelled；TTS 不能早于证据宣布成功。CPU 推理放生产有界 runtime；训练 job 用独立 worker/容器/机器，性能测量后才决定 GPU/环境数。页面“教我慢一点”只改变已训练 conditioning 范围内的目标，不在 production 隐式开 PPO.learn。若用户要求训练，就创建明确离线 job，并展示排队/训练/评估记录，绝不几秒后偷偷切换预置脚本称“刚学会”。[既有 accepted 与 task 状态](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/src/duckking/studio.py:210) [生产边界](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/docs/ARCHITECTURE.md:93)
8. **产品显示。**最少保持四条独立信息：语音来源（Linx live / local ASR / rehearsal）、动作来源（official gait / learned task PPO / authored choreography）、环境（MuJoCo simulation / preview / robotd）、checkpoint provenance。用户无需看到完整 obs vector；可点开技术详情看 manifest、seed、失败和指标。不能以新页面接通 Linx 为证据说学习本身发生于 Linx。[现有 source 字段](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/src/duckking/official_skills.py:83) [stage 来源标签](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/src/duckking/stage.py:602)

### Gaps

- 现有 `Action` 不是泛化 PPO goal schema，不能只往前端加按钮就接受任意坐标或 checkpoint；需新增受控接口与后端 validator。现有 Studio 真人语音主要走 Linx，新分类若要本地优先必须补 local parser/tool route，而不是以 UI 标签假装已有支持。[Action](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/src/duckking/motion.py:51) [工具选择](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/src/duckking/studio.py:115)
- 有限算力下四个 checkpoint 同屏并发是否可实时未知。公平比较应先采用独立世界、同 seed、顺序运行或小窗回放；不要将四鸭塞同一共享物理世界当 checkpoint 比较，因为相互碰撞会改变控制变量。[四鸭共享接触](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/src/duckking/simulation.py:303)

## 3. 新分类与三阶段实现：怎样证明学到了新技能

### Takeaway

建议分类名“语音教练 / PPO 技能学习”，首推“会绕路、会追随的新任务策略”作为可验证增量。先完成真实训练/工件/公平对照，再扩展接触操纵与低层平衡；独立滑板与滑板车放研究阶段，不以现成脚底滚轮冒充。所有 demonstration 都用离线获得的未训练/早期/成熟 checkpoint，现场展示推理与改目标，不演“瞬间训练”。[已有导航基线](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/src/duckking/stage.py:247) [已有滚轮](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/src/duckking/skills_model.py:10)

### Cited Findings

- 最强可复用基线已经不是 open-loop waypoint 动画，而是 MuJoCo 真值反馈、定期 A*、其他鸭避让与姿态/边界 guard；新导航必须拿它做比较。[基线实现](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/src/duckking/stage.py:89) [guard](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/src/duckking/stage.py:210)
- 可复用扰动原语已有短促外力 poke，但现有 1N/.08s 只是当前演示参数，不是新任务适用的验证后范围；平台角度、板轮摩擦、接触阈值必须单独标定。[已有 poke 参数](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/src/duckking/stage.py:570)
- roller_crouch 与 skating 已有 ONNX 和轮轴转角/位移/站稳的验证；球场现有左右 kick；这让轮滑绕桩、到点停车、持续推物有可复用底座，但不证明新目标任务已被学会。[现有技能指标](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/src/duckking/official_skills.py:99) [球状态](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/src/duckking/simulation.py:541)

### Inferences

**候选排序（这是技术建设顺序，依据当前代码支持；不等于新颖性排名或训练成功概率测量）。**

| 排序 | 候选 | 真实新增能力/语音变化 | 所需新增 | 判断 |
|---|---|---|---|---|
| 1 | 避障到目标 + 到点减速停车 | “绕过蓝鸭到紫标记，慢一点，停远一点”；在陌生位置/狭窄通道/移动障碍中学反馈决策 | 目标/障碍 obs、PPO task actor、地图随机化、基线接口 | 最适合第一集成；单纯到点演示不够，必须公开 A* 对照。[既有 A*](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/src/duckking/stage.py:89) |
| 2 | 跟随伙伴 / 领航游戏 | “跟着 A，保持 40cm，A 停你也停”；目标突然转弯、速度变化和挡路 | 相对位置/速度 goal、leader轨迹、间距奖励与碰撞边界 | 现有双/四鸭世界适合；学习的是跟随间距与反应，不是现有口令规则游戏。[双/四鸭](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/src/duckking/simulation.py:197) |
| 3 | 轮滑绕桩/定点停车 | “走左侧绕桩，在圈内停下”；摩擦/初速度未见组合 | 滚轮任务 obs、障碍布局和刹停评价 | 现有 roller 网络可作底座，优先验证其转弯/制动条件范围；“会轮滑”本身不是新增。[roller scene](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/src/duckking/simulation.py:205) |
| 4 | 将球/轻块推入指定区域，绕开挡板 | “把球推入左门，别撞红柱”；目标位置、物品质量/摩擦变化 | 非踢飞的持续接触任务、物体相对状态、接触奖励、重置 | 可复用球/接触记录，仍需验证 morphology 可控接触；不调用脚前自动摆球来隐藏找球失败。[摆球边界](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/src/duckking/simulation.py:504) |
| 5 | 倾斜平台稳站 / 抗扰保持头部方向 | “慢慢倾斜、保持面朝我、恢复平衡”；平台幅度/频率变化 | 新平台刚体、低层 14D 新策略或可解释 residual、训练动力学一致性 | 新低层技能更有说服力，但研发成本高；官方 stand 已有平衡能力，必须在新平台扰动上胜出。[已有站立底座](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/src/duckking/simulation.py:132) |
| 6 | 独立被动滑板：上板→稳站→滑行→停车 | “站到板上，滑到圈里”；板位置/角度/初速度变化 | 新 articulated board、轮-地与足-板接触、分阶段 curriculum、低层控制 | 高风险研究项。脚底四轮不等于脚站独立板；先做静止板上平衡，再谈上板/推进。[现脚轮结构](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/external/microduck_rl/src/mjlab_microduck/robot/microduck/robot_groundcontact_rollers.xml:175) |
| 7 | 滑板车 | 若无手/夹持车把，先定义无需手的车体形式与推进方式 | 超出当前模型的接触和结构设计 | 不建议首轮承诺；先做独立板可行性。不能套用人的扶把骑行。[14 关节构型](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/src/duckking/simulation.py:31) |

从用户可见的新颖性看，持续接触的目标推送、动态平台平衡、独立被动板是更显著的新能力；从工程建设看，应先完成高层导航、共享契约和基线比较。不可将“工程最早做”误写为“最值得炫耀的全新技能”。独立板属于探索项，脚轮 skating 或带手臂扶把的滑板车成果不能替代 MicroDuck 板上控制证据。[现有脚轮构型](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/external/microduck_rl/src/mjlab_microduck/robot/microduck/robot_groundcontact_rollers.xml:175)

**60–120 秒演示方案（待训练与评估通过后才可录制，以下时间是编排提案）。**

- **95 秒“教练带鸭绕路”**：0–12s 显示同 seed、目标与 checkpoint（“未训练高层策略，官方走路能力保留”）；12–27s 未训练 rollout，保留碰撞/超时；27–42s 早期 checkpoint，真实展示绕行但犹豫/停车偏差；42–65s 成熟 checkpoint 同题；65–83s 真人说“目标换到蓝圈，速度减半”，在训练允许范围的未见目标上执行；83–95s 突然障碍/一次可重复扰动，展示成功或真实失败。侧栏始终保留 A* 同 seed 的成功率/路径/耗时，不只比较随机策略。允许失误，不能因失败剪掉本轮统计。[基线依据](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/src/duckking/stage.py:247)
- **90 秒“跟我走，别撞我”**：三个 checkpoint 各 15s 同一领航轨迹（45s）；15s 语音改变跟随间距/速度；20s 未见停走、急转和遮挡布局；10s 明确“停”和速度收敛。leader 是明确标示的 scripted test trajectory 或操作者控制，follower 才是 learned actor；不把领航脚本也叫学会。[多 Driver 基础](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/src/duckking/simulation.py:204)
- **110 秒“滚轮绕桩停车”**：20s 讲清既有官方 roller baseline；早期/成熟各 25s 同一绕桩；20s 语音换终点/限速；20s held-out 摩擦或小扰动。屏幕展示轮轴转角、实际轨迹和停稳时间，不只模型倾斜动画。[当前 wheel evidence](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/src/duckking/official_skills.py:66)
- **后期 100 秒“摇晃站台上的鸭子”**：未训练新低层/官方 stand/早期/成熟各 15s同一倾斜；20s 真人选择预训练范围内更大幅度；20s holdout 扰动与 stop。此方案只有平台模型与独立 checkpoint 通过评估才进入分类，不能复用 stage poke 或头部倾斜称为平台技能。[既有 body pose 仅条件](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/src/duckking/simulation.py:469)

**三阶段范围与交付门槛。**

1. **阶段一：可信集成与可复现实验。**抽取共享 world/contract；注册一个高层 PPO navigation actor；沿用现有 3D/颜色/语音；提供未训练/早期/成熟三个真实 checkpoint 与同 seed baseline；把停止/替换/房间隔离/失败/模型不兼容做成测试；完整 manifest 与报告。这一阶段的声明仅是“新任务控制器已接通并实测”，不宣称优于 A*。训练 worker 先小规模 smoke 与吞吐 profiling，再决定资源；不在 YZH737 web service 内训练。[可复用生命周期](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/src/duckking/motion.py:328)
2. **阶段二：证明任务策略的新增价值。**选一项（动态避障/跟随优先，其次轮滑绕桩/物体推送），把目标、初始朝向、布局、速度/摩擦和扰动拆成训练/验证/隐藏测试。至少三训练 seeds，独立评估，不因看见 test 失败反复调同一测试集合；与 A*+原 waypoint controller、固定官方网络、去掉 task conditioning 的消融比较。若优势只在某些分布，报告适用范围；若未胜出，保留研究结果而非更名“成功”。[需胜过的现基线](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/src/duckking/stage.py:229)
3. **阶段三：新接触/新身体技能。**统一动力学后才做平台平衡 14D（可 warm-start 或 residual，但明确训练层）；评估 foot/platform 接触和稳定性，再研究独立被动滑板、上板 curriculum；模型变更、renderer primitives、工件兼容版本均独立审核。真机/robotd 接入另列工程与实测，不从 MuJoCo 成绩直接外推。[执行器差异](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/external/microduck_rl/src/mjlab_microduck/robot/microduck_constants.py:149)

**训练与奖励提案。**

- 高层导航：身体坐标系目标向量/相对 yaw、状态估计、障碍距离、上次 task action；奖励为到目标势函数差、成功稳定驻留、碰撞/跌倒/越界罚、适量时间与动作变化罚。避免仅“离目标近”但不到达、长期停住刷 alive reward，或靠碰撞挤到目标得高分。限制动作与动力学一致；不把 root force 写入 locomotion action。[实际任务/运动接缝](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/src/duckking/simulation.py:459)
- 跟随：目标间距误差、速度匹配、视角/路径约束、碰撞与超速；leader 在 episode 内随机停走/转弯，训练和测试轨迹隔离。推物：物体到目标进度、成功区域驻留与低速度、必要接触证据、摔倒/越界与过冲惩罚；不要仅奖励 robot 接近物体。平台：身体 upright、质心/支撑范围、足板接触、头向目标及合理力/平滑项，按真实可达范围设 curriculum。[可复用接触量测方法](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/src/duckking/grasp.py:54)
- 未训练 checkpoint 若为高层随机策略，底层 official gait 仍然已训练，必须明确；若从既有 PPO warm start，起点叫“迁移前 checkpoint”，不能叫“零学习”。不要用不同动作限幅、不同模型或更有利 spawn 给成熟 checkpoint 制造比较优势。[固定底层网络](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/src/duckking/simulation.py:127)

**建议验收矩阵与阈值（全是提案，需预先冻结；不是已达标）。**

| 类别 | 记录的原始证据 | 建议门槛/比较方法 |
|---|---|---|
| 到点成功 | goal error、yaw error、实际 xy 速度、接触/跌倒、耗时 | 示例：0.10m 内且速度<0.05m/s 连续0.5s，指定姿态需<15°；限时完成且无越界。先确认尺寸/任务合理后冻结 |
| 泛化 | held-out目标/朝向/障碍布局/速度/摩擦/扰动 seed | 建议 ≥100 个固定隐藏 episodes/训练 seed、≥3 seeds；逐类成功率、95% CI，不能只展示总平均 |
| 比基线 | 相同模型/hash/seed/初态/限制，A*、fixed controller、early/trained | 比较成功率/碰撞率，同时展示 path length、time、final error；可提议目标为隐藏困难集合成功率提高≥10个百分点，但 CI 与样本量决定是否支持结论 |
| 平滑与受力 | 真实动作变化、力矩/接触冲量、地面支撑、最高速度 | 展示量纲和分布，不能 reward 总分替代；界限先通过 baseline 统计/可达性设定 |
| 停止/取消 | command last-write time、任务generation、实测速度、后续写入 | stop 后下一 task 控制周期不再写非零任务命令；物理停止时间另统计。连播/改口/切场景/断线/首调度前取消均不复活旧命令 |
| 隔离/兼容 | room A/B 状态、hidden states、model revision/hash、旧消息 | A 取消/重置不改 B；旧 revision 拒绝；obs/action/hash/normalizer不匹配明确失败 |
| 故障 | 缺模型、NaN、数值失稳、超时、未知 goal、不可达、接触丢失 | 可见 failed/reason，保留真实轨迹；绝不切 scripted/preview 伪装成功 |
| 运行性能 | CPU、每 step P50/P95/P99、sim RTF、房间数、WS 延迟 | 先测生产容量；若超预算降并发/拒绝新任务并明确报告，不悄悄跳物理步或变成动画 |

这些指标是对现有“实际位移、站稳、接触、有限时长与显式失败”验收方式的扩展。[现验证模式](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/src/duckking/official_skills.py:99) [既有失败与停止测试](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/tests/test_official_skills.py:107) [已有场景隔离测试](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/tests/test_rooms.py:98)

**2026-11-01 用户最新方向：以真人—Linx—鸭子对话为主角，而不是给 PPO 做一个“开始”按钮。以下为优先级更高的体验设计。**

用户说明竞赛题目是“智能硬件：复刻一台 Micro Duck，并在其内装上灵矽通过语音交互”。因此竞赛展示模式应保留真实 Linx STT/工具调用/TTS 连接，默认不能把本地规则模拟说成 Linx；本地安全停止可以作为单独、明确标记的保障路径。既有 local-first 保留为其他体验模式即可，不替代竞赛主线。[现语音时序与来源区分](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/docs/ARCHITECTURE.md:119)

所有新场景遵循同一个六段对话循环：**真人口述 → Linx 根据实际场景确认或澄清 → bounded goal/constraint 工具 → learned policy 执行 → 途中改口或停止 → Linx 根据真实结果回答**。Linx 负责语言理解与交流，PPO 负责已经训练过的动作决策；异步语音/网络不进入 10/50/200Hz 回路。指令只有映射到 policy 已训练的目标、限速、距离、layout/扰动范围时才可执行，词汇可多样，物理能力不会因换句话就凭空出现。超出范围返回“这项策略尚未学过/当前做不到”，而不是现场把它拆成脚本冒充学习。[工具边界依据](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/src/duckking/studio.py:120) [实际循环](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/src/duckking/simulation.py:274)

建议首个 voice-first 场景为 **100 秒“教练，跟紧一点”**（训练成功后）：

| 时间 | 真人与鸭的对话（示例，不预录冒充真人） | 系统真实动作/证据 |
|---|---|---|
| 0–12s | 人：“跟着蓝鸭走，别贴太近。”鸭：“保持四十厘米，可以；我会跟着蓝鸭。”若当前“蓝鸭”映射不唯一，先问“是鸭 D 吗？” | 获取本轮可见对象及稳定 ID；目标确认来自真实场景；提交 follower goal(distance=.40) |
| 12–30s | 人可继续观察或对话，领航鸭开始移动 | follower 策略追踪；marker、跟随距离、实际轨迹来自同一物理世界。leader 明示为测试领航，不声称其路线也是新学的 |
| 30–43s | 人：“慢一点，再离远一点。”鸭：“速度调低，间距改为六十厘米。” | 原任务版本失效/更新，policy conditioning 改到训练覆盖的速度与间距，不改 reward、不训练新权重 |
| 43–58s | 人：“你刚开始学时也会吗？”鸭：“那时常常跟丢，我给你看训练初期的记录。” | 主任务先停止；切真实 checkpoint replay，清楚标记“离线训练初期回放，非当前动作”；记录对应同一测试 seed |
| 58–78s | 人：“现在换个没走过的路线。”鸭：“好，换一条测试路线，仍然保持六十厘米。” | 回到 live MuJoCo，明确 reset/episode；选择预先保留的未见 layout/leader trajectory，不保证一定成功 |
| 78–90s | 人：“停，别再跟了。”鸭：“已经停止跟随。” | task actor 立即停止输出；等实际速度和任务结果达到对应状态才说“站稳了”。如云端失联，可按本地停止并显示来源 |
| 90–100s | 鸭基于结果：“这次没有碰到蓝鸭，保持距离的平均误差是……；刚才转弯时距离偏大。”或如实说明失败 | 回复只读本轮测量与失败码；不编造训练过程，不讲未记录的数据 |

同样结构可用于 **“把球轻轻推到那边，别踢飞”**（更高新颖性，技术第二阶段）：Linx 先确认“那边”对应的目标标记与球 ID；actor 学习接触/方向控制；“换到左边、慢些、停”只映射已训练目标/速度；若当前只是固定 kick skill，必须回答“当前只能踢球，持续推送策略尚未就绪”，不能通过自动摆球/脚本推进假装会推物。[当前踢球与摆球区别](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/src/duckking/simulation.py:504) [现 coach 限制](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/src/duckking/studio.py:132)

**新 demo 页面分镜与真实状态标签（建议）。**

1. 页面入口在现有剧场/工坊增加“语音教练 / PPO 技能学习”。主体仍为原 `physics-view`：四色鸭、同一模型 revision、MuJoCo 几何与状态。目标圈、路径、距离线作为此 world group 下的 overlay，使用世界 `(x,y,z)`，禁止另一套 PPO renderer 或浏览器自行推算鸭位置。[现 renderer 契约](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/frontend/src/physics-view.js:70)
2. 最突出操作是“按住与鸭说话”，旁边保留显式停止、重置；话题卡只是可说的句子（“跟着蓝鸭”“再远一点”“给我看训练初期”），而非只有开始/播放按钮。大字展示真人转写、鸭的实际回复；小条显示已接受目标/当前执行/待澄清/失败。目标示意可点选辅助指代，但仍由真人说话发起主体验。[可复用语音入口](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/src/duckking/app.py:568)
3. 三组独立 badge：**语音：灵矽实连 / 本地识别 / 脚本排练**；**控制：自训练任务 PPO + 官方步态 / 官方技能 / 本地编排**；**执行：实时 MuJoCo / 已录 rollout 回放 / 离线训练任务（排队、训练中、评估中、已结束）**。回放绝不能继续显示“实时控制”；观看训练曲线不等于训练仍在跑；选择训练初期工件不应模拟慢慢变强的在线训练动画。[现有来源模型](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/src/duckking/official_skills.py:83)
4. 常驻一行可理解结果：本轮目标、是否接触、是否到达/停稳、耗时；“证据”展开才显示 checkpoint ID/训练步数/工件摘要、seed、baseline/holdout成绩与原始量测。未训练、初期、成熟可以通过语音切换，并保持相同 spawn/seed；跨切换必须先取消旧任务。[现有取消规范](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/src/duckking/motion.py:357)
5. 竞赛展示优先一只 learned follower 与一只明确领航鸭，减少四 checkpoint 同屏的解释负担；需要展示四鸭能力时使用已有 stage。checkpoint 公平比较使用隔离世界顺序演示/录制，并明确来源，不让四鸭相互碰撞干扰对照。[共享世界事实](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/src/duckking/simulation.py:303)

### Gaps

- 尚无新 task 的基线分布、训练曲线、rollout 视频或隐藏测试结果，因此不能判断哪项一定能学会、达到多少成功率或几小时训练完成。平台/板子尤其需要形体与接触可行性验证后才选 reward。
- 当前 branch 的测试文件提供证据标准，但本研究没有运行 suite；若后续落地，应按改动运行 relevant tests，明确分别报告“源码存在”“本机此次通过”“生产已测”，不能跨层替代。[仓库验证要求](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/AGENTS.md:7)
- 本笔记不审核 DuckKing_PPO UI，也不复用该 UI；外部训练工程的有效性由并行研究单独处理。本设计的策略工件只有在共享契约、CPUMuJoCo rollout、停止/房间测试与隐藏评估通过后才可接入现 DuckKing。
