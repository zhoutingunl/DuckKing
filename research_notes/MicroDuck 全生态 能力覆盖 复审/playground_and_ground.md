# Playground 全仓库能力与地面覆盖复审

> 静态来源审计保留当时 `9cac621` 基线。当前41项实现与未移植范围见 [施工核销](../../docs/SCENE_DISCOVERY_ROLLOUT.md)。原始第三方抓取缓存未入库，保留在本地 `.duckking/`。

本轮独立复查日期为 **2026-11-13（Asia/Shanghai，检索开始 UTC 2026-11-12 16:02）**。`git ls-remote` 实查 main 仍为 `052a2494dd6372289221c7a4f24a245b443dd75f`。本次使用这个提交的完整 Git 树（1,023 个文件），49 份 experiments / hardware / docs / integrations 原始 Markdown，以及 canonical src/scripts、内嵌 desk-climb 源码快照，另外现场查询八个 HF 模型库元数据和关键配置。没有把先前调研结论作为证据，也没有重新执行训练或物理轨迹。静态展开主 `tasks/__init__.py` 得到 **46 个声明任务 ID（其中 17 个 Backlash 变体）**；这是代码声明审计，不是已经运行成功的 46 项技能。对应列表保留在本地 `.duckking/ecosystem-research-cache/playground-evidence/task-ids.json`。— [任务注册源码](https://github.com/Vottivott/microduck-playground/blob/052a2494dd6372289221c7a4f24a245b443dd75f/src/mjlab_microduck/tasks/__init__.py)；[固定提交树](https://github.com/Vottivott/microduck-playground/tree/052a2494dd6372289221c7a4f24a245b443dd75f)

DuckKing 对照基线为 feature branch 提交 `9cac621484f87131b754b8e7a3303fa869af8e9c`，不是声明已在 main 或公网发布。— [功能目录](https://github.com/zhoutingunl/DuckKing/blob/9cac621484f87131b754b8e7a3303fa869af8e9c/src/duckking/feature_catalog.py)

## 首页十项实验及深层源码还有哪些应纳入的能力

### Takeaway

首页十项都应进入完整产品施工范围。当前 DuckKing 只有五项已有可运行适配，且秋千完整验收仍不通过；另五项并非没价值或没模型，是真实遗漏/尚未施工。深入仓库后，又发现了此前总表未完整列入的轮滑细分、复杂地形、恢复和旧攀爬研究任务；其中只有源码的内容必须与可直接下载 ONNX 的能力分开。— [首页完整实验表](https://github.com/Vottivott/microduck-playground/blob/052a2494dd6372289221c7a4f24a245b443dd75f/README.md)；[当前功能目录](https://github.com/zhoutingunl/DuckKing/blob/9cac621484f87131b754b8e7a3303fa869af8e9c/src/duckking/feature_catalog.py)；[秋千评分实现](https://github.com/zhoutingunl/DuckKing/blob/9cac621484f87131b754b8e7a3303fa869af8e9c/src/duckking/feature_swing.py)

### Cited Findings

下表的“已有”仅表示代码已有适配；所有上游成功率属于作者测试。这里没有以下载清单替代 DuckKing 实际复现验收。

| 首页实验 | 当前 DuckKing 状态 | 已有真实资产、接入条件与应保留的子项 | 证据 |
|---|---|---|---|
| Self-pumped swing | 有 CPU 接入，仍需修复完整绳长验收 | 已发布单一 ONNX；原场景为座椅、两根弹性绳和泵摆策略，不能把“动起来”当成悬挂几何通过 | [实验](https://github.com/Vottivott/microduck-playground/blob/052a2494dd6372289221c7a4f24a245b443dd75f/experiments/swing/README.md)；[适配和验收](https://github.com/zhoutingunl/DuckKing/blob/9cac621484f87131b754b8e7a3303fa869af8e9c/src/duckking/feature_swing.py) |
| Blind basketball balance | 最近补入，代码支持原地平衡/小步滚动 | LSTM 递归记忆，actor 没有球状态；平衡和前进应保留为同一场景的两种操作 | [实验](https://github.com/Vottivott/microduck-playground/blob/052a2494dd6372289221c7a4f24a245b443dd75f/experiments/basketball/README.md)；[接入](https://github.com/zhoutingunl/DuckKing/blob/9cac621484f87131b754b8e7a3303fa869af8e9c/src/duckking/feature_playground.py) |
| Fast running | 最近补入，有界五秒快跑 | 当前发布 iteration 12195；root、11748 lineage、8749 legacy 是策略版本，不是三种新技能 | [实验](https://github.com/Vottivott/microduck-playground/blob/052a2494dd6372289221c7a4f24a245b443dd75f/experiments/running/README.md)；[HF 文件树](https://huggingface.co/HannesVonEssen/microduck-running/tree/9f45af1f4b04252f3aa1f4c056fa7fa0d4b35e4c)；[接入](https://github.com/zhoutingunl/DuckKing/blob/9cac621484f87131b754b8e7a3303fa869af8e9c/src/duckking/feature_playground.py) |
| Stilt walking | **尚未接入；完整遗漏** | 已有八个高度专用 ONNX：10 / 15 / 20 / 25 / 50 cm / 1 / 1.4 / 2 m；每个须配对应质量、惯量、接触几何、blend 0.5 的模型，不能只把普通鸭腿拉长 | [八高度实验表](https://github.com/Vottivott/microduck-playground/blob/052a2494dd6372289221c7a4f24a245b443dd75f/experiments/stilts/README.md)；[形态生成器](https://github.com/Vottivott/microduck-playground/blob/052a2494dd6372289221c7a4f24a245b443dd75f/src/mjlab_microduck/robot/stilt_constants.py)；[HF](https://huggingface.co/HannesVonEssen/microduck-stilts/tree/371b7e0a8843d215afa768439b9e6ceab6248979) |
| Climbing | **尚未接入；完整遗漏** | 爬梯 → 落上桌 → 恢复站起；27 踏板，当前桌面 1.4×0.8 m、高 0.66 m；两 actor 与手工监督切换均需复刻，不能播轨迹代替运行 | [实验](https://github.com/Vottivott/microduck-playground/blob/052a2494dd6372289221c7a4f24a245b443dd75f/experiments/desk-climb/README.md)；[CPU 动作契约](https://github.com/Vottivott/microduck-playground/blob/052a2494dd6372289221c7a4f24a245b443dd75f/experiments/desk-climb/RUNTIME.md) |
| Chimney climbing | **尚未接入；完整遗漏** | 进入 / 支撑攀爬 / 退出三个已发布 ONNX，加官方站起；12.5 cm 缝隙、3 m 展示台是作者选中录像配置；子阶段不应虚增为四个互不相关“新技能” | [完整契约](https://github.com/Vottivott/microduck-playground/blob/052a2494dd6372289221c7a4f24a245b443dd75f/docs/chimney-climb.md)；[HF](https://huggingface.co/HannesVonEssen/microduck-chimney-climb/tree/1dea21224039f74fb2557456b9bcdec870d96fd7) |
| Raised-platform long jump | 最近补入 | 固定间隙 0.30 m / 落差 0.25 m 的发布模型；不等于任意跳台、平地长跳或后空翻 | [实验](https://github.com/Vottivott/microduck-playground/blob/052a2494dd6372289221c7a4f24a245b443dd75f/experiments/parkour/long-jump/README.md)；[接入](https://github.com/zhoutingunl/DuckKing/blob/9cac621484f87131b754b8e7a3303fa869af8e9c/src/duckking/feature_playground.py) |
| Raised-platform backflip | **尚未接入；完整遗漏** | 已发布 ONNX；0.8 m 跳台落差是“台顶到垫顶”，不是原地后空翻；必须带数值软接触垫 | [细节](https://github.com/Vottivott/microduck-playground/blob/052a2494dd6372289221c7a4f24a245b443dd75f/experiments/parkour/backflip/README.md)；[HF](https://huggingface.co/HannesVonEssen/microduck-backflip/tree/0aff1c74c8ad3953f331193a5a671257ef5aab37) |
| Self-charging dock v1 | **尚未接入；完整遗漏** | 原版为站姿倒退回桩，复用未修改的官方 velstand；AprilTag 真值加噪声和 USB 停止是仿真脚本，不是 onboard 视觉/真实充电功能 | [原版完整说明](https://github.com/Vottivott/microduck-playground/blob/052a2494dd6372289221c7a4f24a245b443dd75f/hardware/microdock/README.md)；[现有仅 v2 适配](https://github.com/zhoutingunl/DuckKing/blob/9cac621484f87131b754b8e7a3303fa869af8e9c/src/duckking/feature_dock.py) |
| MicroDock v2 | 已有坐姿入坞/离坞 | 还应细分核对是否完成“入坞 → 舵机断电休眠 → 静置充电代理 → 重新上电 → 离坞 → 站立”；现代码只提供有限时长的虚拟电量，不应称真实充电 | [v2 说明](https://github.com/Vottivott/microduck-playground/blob/052a2494dd6372289221c7a4f24a245b443dd75f/hardware/microdock-v2/README.md)；[现有适配](https://github.com/zhoutingunl/DuckKing/blob/9cac621484f87131b754b8e7a3303fa869af8e9c/src/duckking/feature_dock.py) |

**几个容易误读、必须写在施工单上的契约：**

- 高跷不是一个默认配置覆盖全部高度。八个目录分别有各自策略与 continuation；作者特别说明极高模拟高跷不等于能在实体原机上安装。建议一个场景内选择八高度，10 cm 先验收，不能把八高度当八项全新原理。— [高度和形态](https://github.com/Vottivott/microduck-playground/blob/052a2494dd6372289221c7a4f24a245b443dd75f/experiments/stilts/README.md)；[硬件与匹配几何](https://github.com/Vottivott/microduck-playground/blob/052a2494dd6372289221c7a4f24a245b443dd75f/hardware/stilts/README.md)
- 桌上攀爬：50 Hz / 61D / 14D，全 13 命令槽归零；爬梯 raw action 不滤波。get-up 增益相对爬梯为 0.8，头/颈滤波 alpha=0.5、腿=0.7；34:48 观测回填上一 raw action，而非滤波后执行值；切换时滤波初态来自上一爬梯执行值、BAM 延迟不清空。触发条件为脚直接接触桌面且 root 进入边沿至少 4 cm；这是监督器读仿真真值。— [动作与切换契约](https://github.com/Vottivott/microduck-playground/blob/052a2494dd6372289221c7a4f24a245b443dd75f/experiments/desk-climb/RUNTIME.md)
- 攀爬 README 写 warm get-up control，但附带 assessment 报告其 standing10s 为 106/256，对照 official 105/256，未保留明显收益并建议继续 official+56500 climber。因此不能只凭 selected video 宣称“可靠上桌”；集成时应该保存 official/warm 对照与实际接触、边缘/滑移/恢复结果。— [README](https://github.com/Vottivott/microduck-playground/blob/052a2494dd6372289221c7a4f24a245b443dd75f/experiments/desk-climb/README.md)；[assessment](https://github.com/Vottivott/microduck-playground/blob/052a2494dd6372289221c7a4f24a245b443dd75f/experiments/desk-climb/evidence/ASSESSMENT.md)
- 烟囱 enter 使用站姿 offset；climb/exit 用 BRACE offset。进入需要相对走廊定位，退出需要平台相对目标位置；作者视频的退出向负 y 方向通过观测、目标和历史镜像实现。其原 seed29 选中录像最终站稳，但这次 publication port 的 fresh seed29 到达出口后未完成恢复；原视频不是保证可重新执行的成功率证据。— [分阶段契约与 fresh failure](https://github.com/Vottivott/microduck-playground/blob/052a2494dd6372289221c7a4f24a245b443dd75f/docs/chimney-climb.md)
- 后空翻垫厚 0.44342 m，软碰撞 solref=(0.03,1)，solimp=(0.9,0.95,0.01,0.5,2)，不是损伤/舵机结构应力模型。作者 fresh rollout 在翻转落地和站起后，7.62 s 漂出垫而摔倒，所以“翻转、落地、短时恢复”和“稳定站住不滑出”应分别评分。— [后空翻](https://github.com/Vottivott/microduck-playground/blob/052a2494dd6372289221c7a4f24a245b443dd75f/experiments/parkour/backflip/README.md)；[fresh verification](https://github.com/Vottivott/microduck-playground/blob/052a2494dd6372289221c7a4f24a245b443dd75f/experiments/parkour/VERIFICATION.md)

**首页之外的完整补查结果：**

| 项目/变体 | 代码/权重证据 | DuckKing 缺口与建议归类 |
|---|---|---|
| RollerSlope 下坡轮滑 | 有独立任务及平地-坡道-出口地形，源码提供 2–20° 坡度训练课程；本仓未把某个下载链接锁定为此任务成品策略 | 现有“轮滑小鸭”有 roller / crouch，未展示独立坡道；**应纳入候选，先核验成品权重**。— [任务](https://github.com/Vottivott/microduck-playground/blob/052a2494dd6372289221c7a4f24a245b443dd75f/src/mjlab_microduck/tasks/microduck_roller_slope_env_cfg.py)；[现有策略列表](https://github.com/zhoutingunl/DuckKing/blob/9cac621484f87131b754b8e7a3303fa869af8e9c/src/duckking/simulation.py) |
| RollerStandUp 轮上起立 | 有专用训练任务和政策摘要；轮子为被动关节，索引不同于脚模型；需要最终自由滚动摩擦条件的策略 | 现项目未载入专用 roller_standup；应作为“摔倒后轮上起立”候选，**不能由 sit→stand 冒充**。— [摘要](https://github.com/Vottivott/microduck-playground/blob/052a2494dd6372289221c7a4f24a245b443dd75f/docs/roller_standup_policy_summary.md)；[现有加载](https://github.com/zhoutingunl/DuckKing/blob/9cac621484f87131b754b8e7a3303fa869af8e9c/src/duckking/simulation.py) |
| Spin 轮上快速旋转 | 有独立 task/reward/phase envelope 设计，属左右轮差速滚动 | 已有 turn_left/right 不代表 spin；缺成品权重锁定与真实角速度/滚动评分，列候选。— [设计](https://github.com/Vottivott/microduck-playground/blob/052a2494dd6372289221c7a4f24a245b443dd75f/docs/superpowers/specs/2026-08-04-spin-env-design.md)；[实现](https://github.com/Vottivott/microduck-playground/blob/052a2494dd6372289221c7a4f24a245b443dd75f/src/mjlab_microduck/tasks/microduck_spin_env_cfg.py) |
| Swizzle 对称八字轮滑 | 有专用任务；与 alternating stride 是不同训练行为 | 当前只有通用 roller.onnx，未按谱系显示 stride/swizzle 对比；在未确认现有 roller 权重谱系前，**只说没有独立对比，不能断言完全不会 swizzle**。— [设计](https://github.com/Vottivott/microduck-playground/blob/052a2494dd6372289221c7a4f24a245b443dd75f/docs/superpowers/specs/2026-07-23-swizzle-env-design.md)；[加载列表](https://github.com/zhoutingunl/DuckKing/blob/9cac621484f87131b754b8e7a3303fa869af8e9c/src/duckking/simulation.py) |
| StandUp 自起 / VelStand 跌倒恢复 | 有独立 StandUp 及 Rough 任务；VelStand 本身含跌倒恢复 | 当前 velstand 步态已有，但缺专门“躺倒→自己起来”可控演示和恢复率统计；避免把同一底层能力重复当新策略。— [注册表](https://github.com/Vottivott/microduck-playground/blob/052a2494dd6372289221c7a4f24a245b443dd75f/src/mjlab_microduck/tasks/__init__.py)；[当前模拟器](https://github.com/zhoutingunl/DuckKing/blob/9cac621484f87131b754b8e7a3303fa869af8e9c/src/duckking/simulation.py) |
| Rough 地形行走/坐起/啄取/恢复 | 具有 Flat/Rough 训练分支及具体 terrain generator | 当前 25 mm 单门槛不能代表复杂地形系列；应新增地形实验模式，但需模型和前端高度场渲染。— [地形配置](https://github.com/Vottivott/microduck-playground/blob/052a2494dd6372289221c7a4f24a245b443dd75f/src/mjlab_microduck/tasks/microduck_velocity_env_cfg.py)；[当前目录](https://github.com/zhoutingunl/DuckKing/blob/9cac621484f87131b754b8e7a3303fa869af8e9c/src/duckking/feature_catalog.py) |
| Backlash 齿隙 | 静态表 17 个 Backlash 对应变体，±1° 串联被动齿隙和 encoder-through-backlash | 当前 hop/footsteps 用齿隙模型，但没有“松动舵机 vs 理想舵机”的用户可见对照；适合科普对照模式，**不是17个新技能**。— [变体表](https://github.com/Vottivott/microduck-playground/blob/052a2494dd6372289221c7a4f24a245b443dd75f/src/mjlab_microduck/tasks/__init__.py)；[现有策略适配](https://github.com/zhoutingunl/DuckKing/blob/9cac621484f87131b754b8e7a3303fa869af8e9c/src/duckking/feature_policies.py) |
| RunningFlight | 给跑步增加受控腾空起始奖励的 ablation | 有任务不等于另有已发布成品；归入快跑训练对照，而非必须新建独立场景。— [两配方说明](https://github.com/Vottivott/microduck-playground/blob/052a2494dd6372289221c7a4f24a245b443dd75f/src/mjlab_microduck/tasks/microduck_running_env_cfg.py) |
| LongJump 共享平地基础 | 平地长跳是 PlatformJump 和 Flip 共用的训练基础 | 发布承诺目前仅两项跑酷成品；不要用共享 LongJump 训练源码推断另有第三份公开可运行政策。— [发布范围](https://github.com/Vottivott/microduck-playground/blob/052a2494dd6372289221c7a4f24a245b443dd75f/experiments/parkour/README.md)；[任务](https://github.com/Vottivott/microduck-playground/blob/052a2494dd6372289221c7a4f24a245b443dd75f/src/mjlab_microduck/tasks/microduck_long_jump_env_cfg.py) |
| LongStairsBlind 连续小楼梯/长梯 | 在内嵌 desk-climb/source 存档有注册和 pilot：64 踏板、每级23.1 mm、62° | 值得列科研候选，未找到独立成品发布；更接近长斜梯，不是已学会走家居大楼梯。— [源码](https://github.com/Vottivott/microduck-playground/blob/052a2494dd6372289221c7a4f24a245b443dd75f/experiments/desk-climb/source/src/mjlab_microduck/tasks/microduck_long_stair_env_cfg.py)；[pilot](https://github.com/Vottivott/microduck-playground/blob/052a2494dd6372289221c7a4f24a245b443dd75f/experiments/desk-climb/source/scripts/long_stairs_pilot.py) |
| FloorDeskBlind 地面到桌面 | 内嵌源码有地面起步、30 tread / 0.74 m桌面的旧训练 recipe | 与主页27 tread/0.66 m当前发布不是同场景；归入爬梯场景历史/研究变体，不保证现成权重适配。— [源码](https://github.com/Vottivott/microduck-playground/blob/052a2494dd6372289221c7a4f24a245b443dd75f/experiments/desk-climb/source/src/mjlab_microduck/tasks/microduck_floor_desk_env_cfg.py)；[pilot](https://github.com/Vottivott/microduck-playground/blob/052a2494dd6372289221c7a4f24a245b443dd75f/experiments/desk-climb/source/scripts/floor_desk_pilot.py) |
| DeskRecoveryBlind 上桌后恢复 | 内嵌专用训练任务和 get-up 资产 | 是攀爬完整链的必要子阶段，不再作为一个全新独立高层技能计数。— [任务](https://github.com/Vottivott/microduck-playground/blob/052a2494dd6372289221c7a4f24a245b443dd75f/experiments/desk-climb/source/src/mjlab_microduck/tasks/microduck_desk_recovery_env_cfg.py)；[发布两模型](https://github.com/Vottivott/microduck-playground/blob/052a2494dd6372289221c7a4f24a245b443dd75f/experiments/desk-climb/README.md) |
| 降落柱/连续柱跳跃 | README 明确 descending-pillar source/policy publication deferred | 仅列“知道存在、未公开”，**不进入承诺可交付施工单**。— [明确未发布](https://github.com/Vottivott/microduck-playground/blob/052a2494dd6372289221c7a4f24a245b443dd75f/experiments/parkour/README.md) |
| XL330 单关节台架 | 一自由度跟踪、BAM 参数验证任务与脚本 | 是工具/电机科普，不是鸭子新动作；可放高级教学，非一站式场景主线。— [任务](https://github.com/Vottivott/microduck-playground/blob/052a2494dd6372289221c7a4f24a245b443dd75f/src/mjlab_microduck/tasks/testbench_env_cfg.py)；[验证脚本](https://github.com/Vottivott/microduck-playground/blob/052a2494dd6372289221c7a4f24a245b443dd75f/scripts/validate_bam_testbench.py) |
| 多种 CAD、STL、Blender 渲染和录制轨迹 | 硬件目录有梯子、高跷、座椅、v1/v2坞及 source；部分视频选中轨迹可重播 | 是场景资产/制造展示，不自动等于学习到新技能；建议“机器人结构”侧栏，且精确区分回放和真实执行。— [目录](https://github.com/Vottivott/microduck-playground/blob/052a2494dd6372289221c7a4f24a245b443dd75f/README.md)；[梯子](https://github.com/Vottivott/microduck-playground/blob/052a2494dd6372289221c7a4f24a245b443dd75f/hardware/ladder/README.md) |

**现场核对的八个 HF 发布库**（所有库元数据标注 Apache-2.0；权重/配置来自作者，硬件许可仍分别处理）：

| 库 | 2026-11-13 查询到的 revision | 关键 ONNX 路径 |
|---|---|---|
| [HannesVonEssen/microduck-swing](https://huggingface.co/HannesVonEssen/microduck-swing/tree/e7a603fa89a74b589608c5a026a7720339cb22e0) | `e7a603fa89a74b589608c5a026a7720339cb22e0` | `policy.onnx` |
| [HannesVonEssen/microduck-basketball](https://huggingface.co/HannesVonEssen/microduck-basketball/tree/6e61a733aeff338bdd352148819bc99cf9a51491) | `6e61a733aeff338bdd352148819bc99cf9a51491` | `policy.onnx` |
| [HannesVonEssen/microduck-running](https://huggingface.co/HannesVonEssen/microduck-running/tree/9f45af1f4b04252f3aa1f4c056fa7fa0d4b35e4c) | `9f45af1f4b04252f3aa1f4c056fa7fa0d4b35e4c` | `legacy/iteration-8749/policy.onnx`、`lineage/iteration-11748/policy.onnx`、`policy.onnx` |
| [HannesVonEssen/microduck-stilts](https://huggingface.co/HannesVonEssen/microduck-stilts/tree/371b7e0a8843d215afa768439b9e6ceab6248979) | `371b7e0a8843d215afa768439b9e6ceab6248979` | `100cm/policy.onnx`、`10cm/policy.onnx`、`140cm/policy.onnx`、`15cm/policy.onnx`、`200cm/policy.onnx`、`20cm/policy.onnx`、`25cm/policy.onnx`、`50cm/policy.onnx`、`policy.onnx` |
| [HannesVonEssen/microduck-climb](https://huggingface.co/HannesVonEssen/microduck-climb/tree/15723878fa5cc31e326ce522ab16e25d5142632e) | `15723878fa5cc31e326ce522ab16e25d5142632e` | `models/climber.onnx`、`models/getup.onnx`、`policy.onnx` |
| [HannesVonEssen/microduck-chimney-climb](https://huggingface.co/HannesVonEssen/microduck-chimney-climb/tree/1dea21224039f74fb2557456b9bcdec870d96fd7) | `1dea21224039f74fb2557456b9bcdec870d96fd7` | `enter/policy.onnx`、`exit/policy.onnx`、`policy.onnx` |
| [HannesVonEssen/microduck-long-jump](https://huggingface.co/HannesVonEssen/microduck-long-jump/tree/fdcdc787e72b8784bb842159ee70607859cd17ed) | `fdcdc787e72b8784bb842159ee70607859cd17ed` | `policy.onnx` |
| [HannesVonEssen/microduck-backflip](https://huggingface.co/HannesVonEssen/microduck-backflip/tree/0aff1c74c8ad3953f331193a5a671257ef5aab37) | `0aff1c74c8ad3953f331193a5a671257ef5aab37` | `policy.onnx` |

### Inferences

- 本仓首页至少五项完整场景仍未在 DuckKing 接入，加上四类轮滑/恢复细分和 Rough/Backlash 对照，并不应只围绕用户点名的三个例子继续补丁。应对每个来源保留“来源条目→高层能力→已实现/待施工/研究/不可交付”一一映射，避免再次看过却漏掉。
- 首批可交付顺序建议：**v1/v2 充电姿态对照 → 10 cm 高跷（同一场景逐步扩展八高度）→ 爬梯上桌完整链 → 软垫跳台后空翻（分阶段评分）→ 烟囱攀爬**。烟囱作者 fresh reproduction 自己记录恢复失败，当前不宜作为无人在场、保证成功的一键秀。以上是基于源码/契约复杂度的工程判断，不是本次实测工期。
- 坡道轮滑、轮上起立、Spin、Swizzle 对比、推倒自起、复杂地形应保留在下一批清单，不能因暂缺锁定权重而从总表删除；先确认可用成品，再决定下载适配还是训练。Backlash/RunningFlight 属教学模式。

### Gaps

- 本轮没有独立运行这些未接入行为，没有新测成功率、CPU耗时、真机安全性或法语云端调用。模型文件存在和 CPU ONNX reference 存在，只说明适配有基础，不能证明真实物理轨迹在现部署必然复现。
- 本仓没有为 RollerSlope / RollerStandUp / Spin / Rough / LongStairsBlind 单独锁定成品模型下载链接；这不等于整个 HF/GitHub 生态都没有，需由官方/社区调研交叉查权重。
- 只以源码静态展开得出46个主任务，不声称完整导入 GPU 训练环境后 `list-envs` 运行成功；内嵌 source 是独立历史快照，不能混进这个46计数。

## 当前地面有哪些现成选择以及为什么网页只见默认平面

### Takeaway

“地面外观”和“物理地形/接触”应作为两种设置。Playground 现成外观主要为平面棋盘格及场景物体颜色；现成物理内容则包括低台阶、随机高低网格、缓坡、长坡、跳台/软垫、梯子/窄壁。DuckKing 前端当前统一画 Three.js 浅色平面和网格，并不直接使用 MuJoCo XML 的 texture，且尚不能显示 MuJoCo heightfield，直接接新地形有物理和显示错位风险。— [native scene_walk](https://github.com/Vottivott/microduck-playground/blob/052a2494dd6372289221c7a4f24a245b443dd75f/src/mjlab_microduck/robot/microduck/scene_walk.xml)；[rough 地形](https://github.com/Vottivott/microduck-playground/blob/052a2494dd6372289221c7a4f24a245b443dd75f/src/mjlab_microduck/tasks/microduck_velocity_env_cfg.py)；[渲染实现](https://github.com/zhoutingunl/DuckKing/blob/9cac621484f87131b754b8e7a3303fa869af8e9c/frontend/src/physics-view.js)；[几何协议](https://github.com/zhoutingunl/DuckKing/blob/9cac621484f87131b754b8e7a3303fa869af8e9c/src/duckking/model_assets.py)

### Cited Findings

| 类型 | 仓库已有内容 | 范围 / 接入意义 | 来源 |
|---|---|---|---|
| native 平面棋盘格 | scene.xml / scene_walk.xml / scene_rollers.xml 中 builtin checker 2D groundplane，纹理重复、反射参数和 gradient skybox | 这是现成视觉样式；不是木纹、草地或冰面模型。恢复到前端需程序生成棋盘纹理或传递原 XML 材质数据 | [scene_walk](https://github.com/Vottivott/microduck-playground/blob/052a2494dd6372289221c7a4f24a245b443dd75f/src/mjlab_microduck/robot/microduck/scene_walk.xml) |
| Rough 平地 | BoxFlatTerrainCfg，占 rough 课程25% | 无新台阶几何，作为对照 | [rough config](https://github.com/Vottivott/microduck-playground/blob/052a2494dd6372289221c7a4f24a245b443dd75f/src/mjlab_microduck/tasks/microduck_velocity_env_cfg.py) |
| 小金字塔台阶 | 步高0–15 mm、步宽0.15 m、顶平台2 m，占25% | 会实际改变脚部碰撞，不是换地板图片；不能推广成上家居大楼梯 | [rough config](https://github.com/Vottivott/microduck-playground/blob/052a2494dd6372289221c7a4f24a245b443dd75f/src/mjlab_microduck/tasks/microduck_velocity_env_cfg.py) |
| 随机高低块网格 | grid_width=.45 m，高差0–10 mm、平台1.5 m，占30% | 少量块即可产生凹凸；不宜照搬多环境训练的10×20个大地图到网页单场景 | [rough config](https://github.com/Vottivott/microduck-playground/blob/052a2494dd6372289221c7a4f24a245b443dd75f/src/mjlab_microduck/tasks/microduck_velocity_env_cfg.py) |
| 缓坡 / 高度场 | 坡度 rise/run=.03–.10，约1.7–5.7°；1 mm竖向量化、平台2 m，占20% | MuJoCo hfield；需要高度场或三角网格下发，不然网页看不见坡 | [rough config](https://github.com/Vottivott/microduck-playground/blob/052a2494dd6372289221c7a4f24a245b443dd75f/src/mjlab_microduck/tasks/microduck_velocity_env_cfg.py) |
| 轮滑长下坡 | 平台2 m → 长3–8 m的2–20°下坡 → 出口平台4 m；tile15×4 m | 需要相机跟随/更大视野，物理轮子与坡面衔接不可偷换为水平滑动动画 | [生成器](https://github.com/Vottivott/microduck-playground/blob/052a2494dd6372289221c7a4f24a245b443dd75f/src/mjlab_microduck/tasks/slope_terrain.py)；[任务](https://github.com/Vottivott/microduck-playground/blob/052a2494dd6372289221c7a4f24a245b443dd75f/src/mjlab_microduck/tasks/microduck_roller_slope_env_cfg.py) |
| 跳台间隙 | A/B 两个平台和坑底；发布longjump间隙.30 m、落差.25 m | 应按真实平台/坑底形状显示；不能让固定装饰平面挡住物理坑 | [平台构造](https://github.com/Vottivott/microduck-playground/blob/052a2494dd6372289221c7a4f24a245b443dd75f/src/mjlab_microduck/robot/platform_stage.py)；[发布参数](https://github.com/Vottivott/microduck-playground/blob/052a2494dd6372289221c7a4f24a245b443dd75f/experiments/parkour/long-jump/README.md) |
| 软垫 | 发布 backflip 的有数值软接触箱体 | 改成纯木板/硬地会改变落地物理，不属于“只换皮肤” | [flip stage](https://github.com/Vottivott/microduck-playground/blob/052a2494dd6372289221c7a4f24a245b443dd75f/src/mjlab_microduck/robot/flip_stage.py)；[实验](https://github.com/Vottivott/microduck-playground/blob/052a2494dd6372289221c7a4f24a245b443dd75f/experiments/parkour/backflip/README.md) |
| 梯子 / 桌面 / 窄壁 | 对应高摩擦支撑、台沿、手工几何 | 场景各自有具体接触和观察器要求，不宜套一个全局摩擦滑杆当“真实木地板” | [爬梯](https://github.com/Vottivott/microduck-playground/blob/052a2494dd6372289221c7a4f24a245b443dd75f/experiments/desk-climb/README.md)；[烟囱](https://github.com/Vottivott/microduck-playground/blob/052a2494dd6372289221c7a4f24a245b443dd75f/docs/chimney-climb.md) |

当前显示默认地面的具体原因：

1. `physics-view.js` 自行建立20×20 m浅色 Plane，roughness=1，再加8 m/80格的 GridHelper；不是把 MuJoCo 原生 viewer 当网页嵌入。— [前端固定地面](https://github.com/zhoutingunl/DuckKing/blob/9cac621484f87131b754b8e7a3303fa869af8e9c/frontend/src/physics-view.js#L30)
2. `model_assets.geometry()` 传网格 vertices/faces、几何尺寸、rgba和部件信息，没有导出纹理像素、UV或 MuJoCo material 原参数；前端再通过自有 appearance 重建材质。换 XML groundplane texture 本身不会传到浏览器。— [几何导出](https://github.com/zhoutingunl/DuckKing/blob/9cac621484f87131b754b8e7a3303fa869af8e9c/src/duckking/model_assets.py#L85)；[材质重建](https://github.com/zhoutingunl/DuckKing/blob/9cac621484f87131b754b8e7a3303fa869af8e9c/frontend/src/physics-view.js#L138)
3. 渲染分支覆盖 mesh(7) 和 primitive 2–6，没有 hfield(1) 路径，几何协议也不带 hfield grid。粗糙地形中 `HfPyramidSlopedTerrainCfg` 需要额外三角化/高度场数据支持，否则物理里有坡而前端仍画平地。— [类型处理](https://github.com/zhoutingunl/DuckKing/blob/9cac621484f87131b754b8e7a3303fa869af8e9c/frontend/src/physics-view.js#L145)；[hfield来源](https://github.com/Vottivott/microduck-playground/blob/052a2494dd6372289221c7a4f24a245b443dd75f/src/mjlab_microduck/tasks/microduck_velocity_env_cfg.py)
4. 固定完整 Git 树中未找到预置“木地板/水泥/草坪/PBR地板材质库”；PNG/JPG 多为实验/硬件渲染和视频poster。不能宣称这些主题已经来自此仓库。— [完整固定提交](https://github.com/Vottivott/microduck-playground/tree/052a2494dd6372289221c7a4f24a245b443dd75f)

### Inferences

- 最先可做三种轻量外观：**当前浅色网格、上游风格棋盘格、纯色无网格**。它们能用程序材质生成，选择只改变视觉，不改摩擦和碰撞，无需下载大图。木纹、混凝土、橡胶运动场也可后续做，但应明确为 DuckKing 新增材质而非上游已提供；不建议第一批用高分辨率贴图/HDR增加手机加载成本。
- 在“地面外观”之外，另做“实验地形”：平地/15 mm低台阶/10 mm高低格/缓坡/轮滑坡道。改变地形应明确重置当前物理试验，并按该策略支持的配置显示可选范围，不能让所有策略随意落在未经验证的地形上后仍承诺成功。
- 将物理 surface geometry 和渲染器共用来源、补齐 hfield mesh/可见性后再接复杂地形，比只更换底色更能改善真实性；保持外观、摩擦、接触刚度的实际关系透明。

### Gaps

- 本轮仅做源码核查，未量测新增纹理/地形在手机的加载、显存或帧率；“轻量优先”是实现建议。
- 这里的软垫为 MuJoCo 数值接触模型，不能给出真实材料弹性/冲击或硬件耐受参数；摩擦参数也没有经过实体木地板/草地标定。

## 哪些结论可立即进入完整施工单以及审计边界

### Takeaway

以来源行逐项核销的方式推进，优先接已有公开策略/场景且有可验证物理闭环的项目；保留研究项而不伪装完成。完整清单应同时包含“尚未接入的首页五项”和“首页外新查出的候选及地形”，而不是只把用户点名的三个补入后结束。— [完整首页](https://github.com/Vottivott/microduck-playground/blob/052a2494dd6372289221c7a4f24a245b443dd75f/README.md)；[任务层](https://github.com/Vottivott/microduck-playground/blob/052a2494dd6372289221c7a4f24a245b443dd75f/src/mjlab_microduck/tasks/__init__.py)；[当前能力表](https://github.com/zhoutingunl/DuckKing/blob/9cac621484f87131b754b8e7a3303fa869af8e9c/src/duckking/feature_catalog.py)

### Cited Findings

- 上游软件为 Apache-2.0，硬件为单独的 CC BY-NC-SA 4.0；每个模型元数据应继续单独核验许可，不能因为 ONNX 为 Apache 而把网格模型也笼统标 Apache。— [软件许可](https://github.com/Vottivott/microduck-playground/blob/052a2494dd6372289221c7a4f24a245b443dd75f/LICENSE)；[硬件许可](https://github.com/Vottivott/microduck-playground/blob/052a2494dd6372289221c7a4f24a245b443dd75f/LICENSE-HARDWARE)
- 当前 DuckKing 18 个功能入口包括其他来源的 hop、flamingo、FootstepNet、circus；它们不能拿来填充 Playground 十项覆盖率分母。对 Playground 而言五项有运行适配、其中 swing 完整验收仍欠缺。三鸭跳绳来自另一仓库，并且自己也未通过完整接触评分。— [目录source字段](https://github.com/zhoutingunl/DuckKing/blob/9cac621484f87131b754b8e7a3303fa869af8e9c/src/duckking/feature_catalog.py)；[跳绳验收](https://github.com/zhoutingunl/DuckKing/blob/9cac621484f87131b754b8e7a3303fa869af8e9c/src/duckking/feature_circus.py)；[秋千验收](https://github.com/zhoutingunl/DuckKing/blob/9cac621484f87131b754b8e7a3303fa869af8e9c/src/duckking/feature_swing.py)
- 此仓没有 apartment 或 vslam 场景 XML；它们属于其他官方源，不能在“Playground已有场景”一列混入。— [固定提交树](https://github.com/Vottivott/microduck-playground/tree/052a2494dd6372289221c7a4f24a245b443dd75f)

### Inferences

- 建议项目总表一行一能力族，附“状态、原始来源、策略路径与锁定版本、几何资产、观测/动作契约、需额外硬件、CPU可执行性、已验证证据、语音交互方案、下一步”。变体挂在同族，不按源码环境数量制造覆盖率。
- 语音入口应能切换高度/模式、启动有时限试验、暂停、询问本轮实测结果；云端工具回答只能引用真实 verified/pending 状态，不能把作者3,072次篮球统计当成本次结果。
- 有些还未拿到独立策略的任务适合新PPO教学：坡道轮滑、自起、连续小台阶；需先建立基线和可见物理地形，再训练并比较，不能先写“支持”再补模型。

### Gaps

- 审计集中在此repo当前主提交、公开链接的八HF库及DuckKing代码；其他组织/fork/公开issue里的额外技能由其他研究者负责。本笔记没有声称穷尽整个互联网。
- 没有把作者编辑的选中录像、saved trajectory replay、训练脚本存在或模型卡指标，当成DuckKing本机/部署环境的复现成功。
