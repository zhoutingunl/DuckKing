# 多鸭、音乐、官方 HF 与平台增补核查

核查日：2026-11-10。仅核增补指定线索；通过作者 README、固定源码、HF 元数据／模型卡和小型配置文件核查。**本轮未运行仿真、训练、模型推理或硬件；下列性能均为作者报告，权重只确认文件存在，未下载全量校验。** 抓取证据位于 `.duckking/microduck-survey-review-20261110/social/`。主报告已读，对照以当前第 3、4.3、4.4、5.1 节为准。

## 1. 多鸭和音乐是否增加可接入的新任务？

### Takeaway

Circus 和 Piano 是有工件的新接触任务，但前者有真值协调与碰撞简化，后者还不会按谱选键。Vision Soccer 可从原报告“待核线索”提升为有代码／权重的视觉编排候选，不能把 oracle 的 98/100 当相机成绩。

### Cited Findings

| 判定／与原报告关系 | 固定原始证据 | 能力、工件、入口与限制 | 建议插入与优先级 |
|---|---|---|---|
| **新增** Circus；原报告未列该项目 | [ros-claw/microduck@1034ed0 方法](https://github.com/ros-claw/microduck/blob/1034ed000c352476cf213ebe1544eb8c7db8b0e7/docs/COOPERATIVE_ROPE_SKIPPING.md)、[训练工件说明](https://github.com/ros-claw/microduck/blob/1034ed000c352476cf213ebe1544eb8c7db8b0e7/training/README.md) | 三鸭同一 MuJoCo；`ropehop_contact.onnx`＋`turner_rope.onnx`，各自 PPO，跳鸭 61 维、摇绳鸭 73 维观测，50 Hz；以 `scripts/contact_skip.sh` 重放。作者验证 Linux／Python 3.13／MuJoCo 3.12，CPU 推理；训练源码以 patch 发布，缺原始 PT／完整日志。 | 第 4 节新增“物理跳绳”，**P2／高适配成本**：两个新契约、绳端约束及接触验收；不是现有四鸭舞蹈换皮。 |
| **纠正** Circus 的学习／物理边界 | [方法](https://github.com/ros-claw/microduck/blob/1034ed000c352476cf213ebe1544eb8c7db8b0e7/docs/COOPERATIVE_ROPE_SKIPPING.md)、[接触审计](https://github.com/ros-claw/microduck/blob/1034ed000c352476cf213ebe1544eb8c7db8b0e7/docs/PHYSICAL_FIDELITY_AUDIT.md)、[第三方说明](https://github.com/ros-claw/microduck/blob/1034ed000c352476cf213ebe1544eb8c7db8b0e7/THIRD_PARTY.md) | 绳端用 equality 约束连接嘴柄；没有 mocap 托绳／绳速截断，但排除绳–摇绳鸭和绳自碰撞；相位与起跳反馈来自仿真几何真值。作者三鸭接触评估 442/516 clean cycles、5/8 runs 通过；不能称端到端多智能体 RL。后续四鸭接触审计发现 23–37 mm 穿入，移动接力未通过。代码 Apache-2.0，模型网格独立 CC 条款；无硬件展示。 | 保留失败与碰撞排除；只列“仿真接触任务＋显式协调”，不沿用索引的泛化 agent learning 说法。 |
| **新增并降温** Piano；原报告多鸭合唱／音乐已有，但被动键盘接触未覆盖 | [KhushiJ2911/microduck-piano-learning@1692d44](https://github.com/KhushiJ2911/microduck-piano-learning/blob/1692d4432c9a3833288b2aa763380d9cdeffdd62/README.md)、[evaluator 源码](https://github.com/KhushiJ2911/microduck-piano-learning/blob/1692d4432c9a3833288b2aa763380d9cdeffdd62/scripts/render_velstand_keyboard_traverse.py) | 两个自由根鸭踩 16 个无电机弹簧键；VelStand actor 转移微调，`keyboard_step_model50.onnx`／父权重／审计 JSON／GIF。方向由 evaluator 预排，非按谱／自主选键。作者 64 个世界仅 1 个严格通过，选中世界 6 键完成按下释放；复位后在线控制不写根／关节状态，渲染阶段回放保存状态应与控制分开。 | 第 4 节列**研究候选 P3**；不能宣传“双鸭已学会弹琴”。源码 Apache-2.0、无真机声明；发布树只有 evaluator 和工件，未见完整训练包。 |
| **已有线索，提升但保留不确定性** Vision Soccer | [toyhank@23cdfbc README](https://github.com/toyhank/microduck-vision-soccer/blob/23cdfbce04083ff1883a2d6ceb7bb3b6b49e15c0/README.md)、[入口源码](https://github.com/toyhank/microduck-vision-soccer/blob/23cdfbce04083ff1883a2d6ceb7bb3b6b49e15c0/sim_duck_soccer.py)、[早期严格验证](https://github.com/toyhank/microduck-vision-soccer/blob/23cdfbce04083ff1883a2d6ceb7bb3b6b49e15c0/VALIDATION.md) | `python sim_duck_soccer.py --mode strict --goalkeeper`；渲染头部 RGB＋仿真 IMU／编码器观测驱动校准视觉控制，球与球门检测／状态机复用现成 ONNX walk／stand／kick，非新足球 RL。strict 与 oracle 守门员、demo 辅助路径分开。早期严格版 7/10 踢球接触、0/10 进球；当前 README 已增加校准／盲区里程计，旧数不能代表当前版。 | 原报告 4.3 的待核项提升到**P2 感知接线候选**；保留“当前严格视觉成功率未核实”。现有踢球教练已覆盖低层踢球，新增价值是寻球、对准、守门。 |

- Soccer 的 **98/100 goals、96/100 kick-contact goals、0 falls** 明确属于冻结的真值导航基线；两次进球仅为行走推球。源码 `strict` 分支渲染 RGB，`demo` 分支在踢球触发时会直接重定位球，应在接入时禁用／明确标示，不可共用“纯视觉”标签。早期作者环境是 Linux CPU＋软件 Mesa EGL，`--headless` 仍要渲染；当前双相机吞吐未在此测量。代码许可证正文为 Apache-2.0；onboard runner 只是 `mediad`／`robotd` 接线，整场真机足球未验证。— [入口](https://github.com/toyhank/microduck-vision-soccer/blob/23cdfbce04083ff1883a2d6ceb7bb3b6b49e15c0/sim_duck_soccer.py#L335)、[作者边界](https://github.com/toyhank/microduck-vision-soccer/blob/23cdfbce04083ff1883a2d6ceb7bb3b6b49e15c0/README.md)、[LICENSE](https://github.com/toyhank/microduck-vision-soccer/blob/23cdfbce04083ff1883a2d6ceb7bb3b6b49e15c0/LICENSE)
- Piano 的 ONNX session 指定 CPU；环境根据 `torch.cuda.is_available()` 选择设备，但发布复现依赖 mjlab／Warp，不能仅凭这个分支宣称本地 CPU 复现已经成立。— [evaluator L288、L307](https://github.com/KhushiJ2911/microduck-piano-learning/blob/1692d4432c9a3833288b2aa763380d9cdeffdd62/scripts/render_velstand_keyboard_traverse.py#L288)

### Inferences

建议报告用语：“新增物理道具任务以跳绳和地面键盘为代表，均需独立验收；多鸭数量本身不是新增能力。视觉足球的可借鉴部分是 RGB 感知到既有踢球策略的控制链。”优先级为 **Soccer 感知链 ＞ Circus 独立验证 ＞ Piano 研究储备**；都是工程判断，未本地复现。

### Gaps

未测三鸭 5 kHz 接触世界在本机的实时倍率；未验证 Piano CPU 环境路径；没有当前 Soccer 严格双视觉控制器的足量评估。三者的实体迁移均无本轮证据。

## 2. 官方 HF 生态与 TorchRL 的名称是否准确？

### Takeaway

补充官方 Arena 的新事件与多鸭演出格式很有价值；红方块／蓝盒子 VLA 被错误归入 MicroDuck，应删除。TorchRL 的“官方七技能”需改为“TorchRL 项目发布的九技能实验 prior”，和 Pollen 官方随包策略分开。

### Cited Findings

| 判定／去重关系 | 固定原始证据 | 可证实内容与报告建议 |
|---|---|---|
| **新增／纠正** Arena；原报告有 sandbox 和社区 StephenForte challenges，但未覆盖这个 Pollen 官方 challenge 仓库 | [pollen-robotics/microduck-challenges@5cee942](https://github.com/pollen-robotics/microduck-challenges/blob/5cee942d8b434aafd395070facb659034aac3b5e/README.md) | 当前作者列 **6 事件**：sprint、roller-sprint、hill-climb、got-a-talent、tug-of-war、sock-heist，增补的 4 事件过时。Got-a-talent 是最多 20 s 的 timeline 表演＋投票，可同一物理世界最多 8 鸭，各自 pin policy／编排／voice／song。已有坐站与合唱可去重，新增是赛事／编排格式。**P1 参考格式，P2 接事件**。 |
| **新增，但非视觉偷袜完整流程** sock-heist-6m reference | [HF@ee81c13](https://huggingface.co/pollen-robotics/microduck-sock-heist-6m-reference/blob/ee81c1368572753528c01ee493c938c6aaac3ed0/README.md)、[manifest](https://huggingface.co/pollen-robotics/microduck-sock-heist-6m-reference/blob/ee81c1368572753528c01ee493c938c6aaac3ed0/manifest.json)、[challenge 规则](https://github.com/pollen-robotics/microduck-challenges/blob/5cee942d8b434aafd395070facb659034aac3b5e/README.md) | 有 ONNX、checkpoint.pt、schema-2 manifest，61→14、50 Hz perpetual；作者选择 checkpoint 300 因 Space x86 上 5 seeds 全完成。巨鸭看向跑道时外部把命令清零，policy 只看命令，不是相机识别巨鸭／袜子，也不是嘴部拿袜。训练 NVIDIA／HF Jobs；官方 check／Arena score 可评估。**P2 有界红绿灯规则场景**。 |
| **已有动作的官方参考实现** got-a-talent reference | [HF@0454fe8](https://huggingface.co/pollen-robotics/microduck-got-a-talent-reference/blob/0454fe8a848526338ba6edf72b8358fbf51d6b21/README.md)、[文件树](https://huggingface.co/pollen-robotics/microduck-got-a-talent-reference/tree/0454fe8a848526338ba6edf72b8358fbf51d6b21) | sitstand slot、头部命令，61→14、50 Hz，ONNX／PT／timeline；不是新学会的“才艺集合”。优先借鉴 timeline／多鸭声部，不把它计为继 10 个部署 ONNX 之后同一集合的第 11 个：这是独立 Arena 模型库。 |
| **纠错／排除** red-cube-blue-box | [π0.5 train_config@eb2127a](https://huggingface.co/pollen-robotics/red-cube-blue-box_pi05_best/blob/eb2127a8d110d987c45c18e25d58404561ceaf55/train_config.json)、[训练数据 meta@854830c](https://huggingface.co/datasets/simheo/red-cube-blue-box_graspproj_v2/blob/854830ce317c20a7f438029894bbfc77e6afd5f2/meta/info.json)、[diffusion config@b12622b](https://huggingface.co/pollen-robotics/red-cube-blue-box-30fps_diffusion/blob/b12622b97ec7234b0460f93d2039ecdc536a44b9/config.json) | π0.5 配置指向 `simheo/red-cube-blue-box_graspproj_v2`，数据明确 `robot_type: grabette`，状态 strategy／closure 共 2 维，动作相对位姿＋抓取共 11 维；diffusion 同为图像＋2→11 契约。**不是 MicroDuck 的 61→14 部署包**。同属 Pollen 不等于同机器人；未发现鸭体转换／任务验证，不加入推荐。π0.5 与 diffusion 模型树无 README／LICENSE，config license=null；不可把数据集 Apache-2.0 自动转给权重。 |
| **纠错＋新增候选** TorchRL | [HF@d676623 当前卡](https://huggingface.co/torchrl/microduck-skills/blob/d6766234b24bf9cff6a6a8c55011a4584a8995d5/README.md)、[prior 卡](https://huggingface.co/torchrl/microduck-skills/blob/d6766234b24bf9cff6a6a8c55011a4584a8995d5/prior/README.md)、[对应 PyTorch 源提交](https://github.com/pytorch/rl/commit/c514a1361b5ff7fb8e86019a86d22c5e0bdd2697) | 当前九技能：站、前后左右、前跳、左右转、原地跳；GRU128 recurrent PPO，发布 `prior/checkpoint.ckpt`，不是 ONNX／robotctl 即装包。作者每技能 32×500 步、全存活；仅一个训练 seed／平地 reset。当前明确仅仿真，未验证硬件。应写“**TorchRL 项目发布**”，不能写成“Pollen 官方新增七技能”。**P2 CPU 研究候选**。 |

- TorchRL 官方文档确实有 `MicroDuckSkills.from_pretrained` 且默认仓库为 `torchrl/microduck-skills`，这比组织名更能证明项目关联；但文档默认仍指历史六技能 revision／`walker.ckpt`，当前卡为九技能 `prior/checkpoint.ckpt`。必须 pin 工件、对应源码、任务排序、GRU 状态和 action_scale，不能直接使用默认加载路径。作者训练记录是 Apple-silicon MacBook、原生 CPU MuJoCo、16 workers，**本轮没有重跑**。HF 工件树和卡未声明独立模型许可证，源项目许可不能自动推定权重许可。— [PyTorch 官方 API](https://docs.pytorch.org/rl/main/reference/generated/torchrl.modules.tensordict_module.zoo.MicroDuckSkills.html)、[固定训练记录](https://huggingface.co/torchrl/microduck-skills/blob/d6766234b24bf9cff6a6a8c55011a4584a8995d5/prior/training.json)、[固定工件树](https://huggingface.co/torchrl/microduck-skills/tree/d6766234b24bf9cff6a6a8c55011a4584a8995d5)
- TorchRL 的 football selector 为 experimental、tag 为 unsolved pilot，且都依赖九技能 prior；不能由视频推断可靠足球／追逐技能。— [football](https://huggingface.co/torchrl/microduck-skills/blob/d6766234b24bf9cff6a6a8c55011a4584a8995d5/games/football/README.md)、[tag](https://huggingface.co/torchrl/microduck-skills/blob/d6766234b24bf9cff6a6a8c55011a4584a8995d5/games/tag/README.md)
- Arena Space README 本身事件表只列三个竞速项目，晚于它的能力应以 challenge 源码／事件定义复核，不能只数 README 一张表。本轮确认官方 challenge 六事件与多鸭说明，未实测网站交互；官方发布仓库的模型卡给出加载命令也不构成真机试验记录。两份 reference HF 树和 challenge 根树本轮未找到独立许可证文件，不自动继承别库 Apache 标签。— [Space 固定 README](https://huggingface.co/spaces/pollen-robotics/microduck-arena/blob/9305b754862c56b2b2ce512c063c34600efbf932/README.md)、[challenge 固定树](https://github.com/pollen-robotics/microduck-challenges/tree/5cee942d8b434aafd395070facb659034aac3b5e)

### Inferences

建议第 3 节加入“官方 Arena 是任务／演出平台，独立 reference 模型不与出厂十文件合并计数”；第 4.3 节增加“同组织不同机器人排除例：Grabette 的 red-cube-blue-box”。TorchRL 放社区／框架实验项，既承认真正项目关联，也不混称 Pollen 的发布策略。

### Gaps

未验证 Arena 当前服务的六事件可点击运行；reference 的文件级许可／真机测试未确认；TorchRL 九技能模型的独立权重授权需补；diffusion 没有直接数据集元数据，能证实契约与 π0.5 类似，但不把 π0.5 的数据溯源强行套给所有同名前缀变体。

## 3. 平台是否应计成新技能，“43 全核实／HF 长尾无增量”是否成立？

### Takeaway

四个平台值得补一个基础设施表；不能合计成新的身体动作。增补的总量描述应降级：43 条目录能计数，但不证明逐项核实；本次已经发现目录过时，HF 长尾无增量没有证据支持。

### Cited Findings

| 判定／原报告去重 | 固定原始证据 | 实际状态、CPU／许可与插入建议 |
|---|---|---|
| **新增平台** microdux；原报告已覆盖“框架移植不等于成熟动作”的规则，未列该库 | [noahfarr@c486b89](https://github.com/noahfarr/microdux/blob/c486b8967f8e35eed7dcec85ac3343a269cd4bc2/README.md)、[pyproject](https://github.com/noahfarr/microdux/blob/c486b8967f8e35eed7dcec85ac3343a269cd4bc2/pyproject.toml) | JAX／MJX／Playground 14 行任务包含 flat 与 rough 拆分，不能与原官方 13 家族口径直接相加。仅 flat velocity 作者称训练达上游水平；其他未训／进行中，curriculum reset、逐任务超参有缺口。A100 benchmark 不是 CPU 成绩；有 `microdux.run`／registry／export 工具，本轮树未见可直接用的完整已训策略集。README Apache badge 链接 LICENSE，但根树无该文件、包元数据也无 license。**P3 基础设施**。 |
| **新增平台** duckbench；不把站点／手机 ghost 与物理 bench 混为一谈 | [craigm26@a75d4dc 根表](https://github.com/craigm26/duckbench/blob/a75d4dc9b8a08c8072c15af0ab50dfb516ab144c/README.md)、[bench setup](https://github.com/craigm26/duckbench/blob/a75d4dc9b8a08c8072c15af0ab50dfb516ab144c/sim/BENCH-SETUP.md)、[PLANT](https://github.com/craigm26/duckbench/blob/a75d4dc9b8a08c8072c15af0ab50dfb516ab144c/sim/PLANT.md)、[MCP 源码](https://github.com/craigm26/duckbench/blob/a75d4dc9b8a08c8072c15af0ab50dfb516ab144c/tools/duckbench-mcp.mjs) | `node sim/duckbench.mjs` 为 CPU MuJoCo WASM＋onnxruntime-node HTTP；MCP 是 stdio wrapper；权重在 sim/，根许可 Apache-2.0。作者明确 sim/ 与 site/ plant 存在旧新差异、两推理路径长期轨迹不可互换；live world 还有默认堆叠 step bank 的历史条件。只借鉴接口／验收，**P3，避免为接 MCP 换物理引擎**。不引用仓库遗留手机 app 文案当 bench 物理边界。 |
| **新增平台** microduck-twin；原报告只有官方恒压／恒温说明，本项正好补扩展 | [digows@351e81d](https://github.com/digows/microduck-twin/blob/351e81dded599c466a14380b374b10b23b989f2b/README.md)、[power.py](https://github.com/digows/microduck-twin/blob/351e81dded599c466a14380b374b10b23b989f2b/twin-body/twin_body/power.py)、[deps pin](https://github.com/digows/microduck-twin/blob/351e81dded599c466a14380b374b10b23b989f2b/deps.env) | 包装官方 CPU body／daemon，`./microduck-twin up`，补音频传播、模拟耳朵、SOC／热、HUD；不重训策略。power.py 明写电池／热模型是未拟合形状，未用电池／舵机实测数据；不能当真实续航、热极限或电气充电证据。Apache-2.0；网格独立 CC。README 尾部仍有“field／console 尚未到位”旧句，与状态表矛盾；本轮仅源码级确认。**P2 可作回桩外围模拟参考**。 |
| **新增平台／纠正索引过时** Wicroduck | [ngxson@b0035c1](https://github.com/ngxson/wicroduck/blob/b0035c15c532bbb69b22a7edc1bb79b7b7430cd0/README.md)、[训练计划](https://github.com/ngxson/wicroduck/blob/b0035c15c532bbb69b22a7edc1bb79b7b7430cd0/docs/training-plan.md)、[代码树](https://github.com/ngxson/wicroduck/tree/b0035c15c532bbb69b22a7edc1bb79b7b7430cd0/src/train) | 浏览器 WASM MuJoCo 200 Hz＋ONNX 50 Hz 复用 alpha_stand；`npm run dev`，没有独立新出厂技能。当前已含 CPU PPO／checkpoint、motion editor、训练代码／checks；M4 导入已发权重微调和 M5 从零训练／ONNX export 尚未完成。不能仍写“浏览器训练纯目标”，也不能写“新动作浏览器训好即可部署”。motion maker 可运动学预览或物理运行，必须分标；根树未见 LICENSE。**P3 教学工具**。 |
| **数目可核，验证结论未证** 43 条全核实 | [固定 policies.json@b99984a](https://github.com/joeynyc/awesome-microduck/blob/b99984a56182525598c4187cc0138c89bc1c7c79/policies.json)、[独立索引说明](https://github.com/joeynyc/awesome-microduck/blob/b99984a56182525598c4187cc0138c89bc1c7c79/readme.md) | 本轮直接计数 `entries`=43；字段 `generated_from=readme.md#policies-and-skills`、`artifact_mode` 有 source-only／probe-provider，并非运行认证。索引自述独立社区维护、无 Pollen/HF 背书；TorchRL 七技能与 Wicroduck 描述已滞后。因此只能写“目录 43 条，本轮对指定增量核查”，不能声称全 43 仿真验证。 |
| **未证实，删除排他判断** HF 1,137／38 页／长尾无增量 | [补充报告原文](https://aiops.qbox.net/files/691082629293bdf4/microduck-mujoco-survey-2026-11-10.md)、[当前 TorchRL 卡](https://huggingface.co/torchrl/microduck-skills/blob/d6766234b24bf9cff6a6a8c55011a4584a8995d5/README.md) | 1,137 未附时间戳查询响应／分页清单／去重分类；本轮不遍历全 HF，不确认该数量。即使数量正确，也不能推出所有长尾无演示价值；已有九技能与两个游戏工件足以说明需逐项看模型而非名字。本轮未试图证明这些一定来自“长尾”，只否定缺证据的穷尽判断。 |

### Inferences

报告第 4.3 节可加上述四行平台摘要，后接：“平台迁移、API/MCP 封装、动态电量模型和浏览器训练工作台提升开发条件，但不会自动增加已学会的 MicroDuck 技能。”原报告第 4.4 节保留检索上限，增加：“社区目录可作为发现入口，条目数不是工件／许可证／运行结果全量核验数。”

集成顺序建议：**P1 借鉴官方 timeline／troupe（复用已有四鸭） → P2 Soccer 感知链、Circus 独立实验、Twin 模拟外围（分别验收） → P3 Piano、MJX／浏览器／bench 生态参考**。授权或接入未核清的权重不进入分发包；不因本轮只读核查而修改执行后端。优先级属于 DuckKing 现有能力去重后的推断，并非作者结论。

### Gaps

没有针对这四平台运行测试；无法确认作者 CPU 实时速度可移植到本机。未做 HF 全量分页与语义分类，也未逐项验证目录 43 条；所以既不重复“全核实”，也不改写成“其他项目都不可用”。本轮仅检查指定主分支／HF head 和引用工件，未穷尽分支、release 或历史许可证。
