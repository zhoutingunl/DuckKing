# MicroDuck 社区能力与遗漏审计

> 静态来源审计保留当时 `9cac621` 基线。当前41项实现与未移植范围见 [施工核销](../../docs/SCENE_DISCOVERY_ROLLOUT.md)。原始第三方抓取缓存未入库，保留在本地 `.duckking/`。

## 当前公开生态究竟检查了多少，哪些结论需要更新

### Takeaway
本次从源头重查，而非沿用旧报告。社区远不止 Playground 十项：新版 registry 的44行、README的游戏/研究/感知/训练项目，以及HF模型卡里都有此前没有进入DuckKing清单的能力。下面“已有”指当前代码能力，不代表新增权重已接入或通过物理验收。

### Cited Findings
- 以 `joeynyc/awesome-microduck@9cfa5abca6f143b8af0048aeb6004dc5e67f81e8` 核验，machine registry **44行**。`artifact_mode=source-only` 是注册表消费方式，**不是“没有权重”**；例如courier、headstand、beak-throw都有单独发布的权重。[Registry](https://github.com/joeynyc/awesome-microduck/blob/9cfa5abca6f143b8af0048aeb6004dc5e67f81e8/policies.json)
- README 中排除 Pollen/Playground/DuckKing 后，尝试跟随 **207个GitHub仓库**，取得 **206份primary README**；Harboria/harboria返回404。另对29个技能/重点新候选查完整Git树，npow/microduck-coop、猜测的Raghav GitHub路径返回404；不能把HF卡的源码链接视作已取得代码。[README](https://github.com/joeynyc/awesome-microduck/blob/9cfa5abca6f143b8af0048aeb6004dc5e67f81e8/readme.md)
- HF `search=microduck&full=true` 跟随分页到next消失，**1191条模型元数据、2页**；全部ID/SHA/files/tags存于 本地 `.duckking/ecosystem-research-cache/community_sources/hf-search-inventory.json`。深查模型卡65份（含registry、显著新动作及展开家族）；33个额外新颖名称卡均取得。元数据总扫描**不等于1191个模型均做了能力验证**。[HF API](https://huggingface.co/api/models?search=microduck&limit=1000&full=true)
- 社区README链接的23个非官方HF Spaces取得21套metadata+README，未逐一运行浏览器功能。[社区应用目录](https://github.com/joeynyc/awesome-microduck/blob/main/readme.md#apps-and-ports)
- TorchRL主卡现为**九技能prior + football selector + tag selector**，不是registry仍写的七技能GRU。主树产物为`checkpoint.ckpt`，没有ONNX。football为experimental，tag为unsolved pilot，需TorchRL接口适配。[真实当前卡](https://huggingface.co/torchrl/microduck-skills/blob/main/README.md)
- DuckKing当前功能目录18项包括movement/emotions/director/dock/hop/flamingo/senses/theremin/step/search/soccer/navigation/footsteps/swing/circus/running/basketball/long_jump。旧页面还有前滚翻、嘴夹物、轮滑/下蹲，PPO页有转盘和跷跷板；这些不能等同于下面的新学得策略。[当前代码](https://github.com/zhoutingunl/DuckKing/blob/9cac621484f87131b754b8e7a3303fa869af8e9c/src/duckking/feature_catalog.py)；[旧仿真控制器](https://github.com/zhoutingunl/DuckKing/blob/9cac621484f87131b754b8e7a3303fa869af8e9c/src/duckking/simulation.py)

### Inferences
- 旧清单以少量高层主题分组，缺少“来源每项→功能→实际权重→当前接入状态”的总账，容易把整仓库压缩成一个名字，也容易把“普通后退/小球踢”误当成已覆盖“月步/巨球踢”。应保留总账，产品页再去重展示。
- 跑通61/14形状不足以宣称可集成；需同时查电机模型、延迟、输出限位、jaw时序、碰撞模型和高层切换条件。

### Gaps
- 本研究未执行任何新权重、未下载大checkpoint/媒体、未做云端训练/实机试验。所有成功率均为作者声明及其公开记录，不能写成DuckKing成绩。
- 公共搜索无法保证囊括全互联网、私库/已删源/未标microduck的项目。未读其余约千份HF长尾卡，故**不能再声称长尾没有增量价值**。完整文件/失败计数见 `community_coverage_log.json`。

## 注册表全部44项与DuckKing的逐项差距

### Takeaway
44行每行保留；已接入与相似能力、待集成与研究未达标、硬件不兼容分开记。Playground发布由相邻专责研究者核验，下面Hannes条目不重复声称本分支已经下载和验证。

### Cited Findings

| # | 原始来源 | 文件/许可核对 | DuckKing实际差距与处理 |
|---|---|---|---|
| 1 | [Lulzx/microduck-backflip](https://github.com/Lulzx/microduck-backflip) | ONNX 1；Apache-2.0 | 缺：平地后空翻；与Playground高台后空翻不同；独立后空翻候选；需按本模型重新做着陆验收 |
| 2 | [selinayfilizp/microduck-courier](https://github.com/selinayfilizp/microduck-courier) | ONNX 4；Apache-2.0 | 部分：有脚本嘴夹取/搬运，无其学习版公寓送书；可用作学习版搬运与现有脚本对照 |
| 3 | [Liyucheng1997/318_lab-microduck-simulator](https://github.com/Liyucheng1997/318_lab-microduck-simulator) | ONNX 10；未见明确顶层许可元数据；不得推定 | 相近：已有happy-hop；未接其跳跃策略；对照候选，非首要新增能力 |
| 4 | [pezzonovante7/microduck-sidekick-dance](https://github.com/pezzonovante7/microduck-sidekick-dance) | ONNX 0（源码树无ONNX不代表外部HF无权重）；未见明确顶层许可元数据；不得推定 | 缺：lateral sidekick 舞步；只有任务代码，无已训练模型，不能直接交付 |
| 5 | [bihaokun/microduck-step-up-policy](https://github.com/bihaokun/microduck-step-up-policy) | ONNX 2；Apache-2.0 | 已接：25mm step-up pair；保留现有接入与实测，不重复实现 |
| 6 | [ThomasBurgess2000/microduck-max-height-jump](https://github.com/ThomasBurgess2000/microduck-max-height-jump) | ONNX 2；Apache-2.0 | 相近：有hop；无该策略和高度指标；作为跳跃对照，需落地冲击验收 |
| 7 | [alertform/microduck-walking](https://github.com/alertform/microduck-walking) | ONNX 0（源码树无ONNX不代表外部HF无权重）；Apache-2.0 | 相近：有步态；无其yaw消融评测；步态质量评测，不算新动作 |
| 8 | [ros-claw/microduck](https://github.com/ros-claw/microduck) | ONNX 8；Apache-2.0 | 已接但未通过完整物理验收：三鸭跳绳；继续完成真实接触验收 |
| 9 | [RemiFabre/microduck-flamingo-cycle](https://huggingface.co/RemiFabre/microduck-flamingo-cycle) | ONNX 1；apache-2.0 | 已接：flamingo-cycle；保留，非新增 |
| 10 | [fffiloni/microduck-polite-bow-b1d864](https://huggingface.co/fffiloni/microduck-polite-bow-b1d864) | ONNX 1；未见明确顶层许可元数据；不得推定 | 缺：学习版鞠躬；有policy.onnx；许可元数据未明确，待澄清 |
| 11 | [fffiloni/microduck-moonwalk-backward-55e6af](https://huggingface.co/fffiloni/microduck-moonwalk-backward-55e6af) | ONNX 1；未见明确顶层许可元数据；不得推定 | 缺：月步；普通后退不等价；有policy.onnx；许可元数据未明确，待澄清 |
| 12 | [torchrl/microduck-skills](https://huggingface.co/torchrl/microduck-skills) | ONNX 0；未见明确顶层许可元数据；不得推定 | 相近基础动作；缺九技能prior/football selector；现卡已九技能，ckpt而非ONNX；需要TorchRL适配 |
| 13 | [HannesVonEssen/microduck-basketball](https://huggingface.co/HannesVonEssen/microduck-basketball) | Playground专责报告核对（此处未重复查文件/许可）；见Playground专责报告 | 已接：blind basketball；Playground专责核验 |
| 14 | [HannesVonEssen/microduck-swing](https://huggingface.co/HannesVonEssen/microduck-swing) | Playground专责报告核对（此处未重复查文件/许可）；见Playground专责报告 | 已接但绳长验收未通过：swing；Playground专责核验 |
| 15 | [HannesVonEssen/microduck-stilts](https://huggingface.co/HannesVonEssen/microduck-stilts) | Playground专责报告核对（此处未重复查文件/许可）；见Playground专责报告 | 缺：八档高跷；Playground专责核验，按高度配套模型 |
| 16 | [HannesVonEssen/microduck-running](https://huggingface.co/HannesVonEssen/microduck-running) | Playground专责报告核对（此处未重复查文件/许可）；见Playground专责报告 | 已接：running；Playground专责核验 |
| 17 | [HannesVonEssen/microduck-climb](https://huggingface.co/HannesVonEssen/microduck-climb) | Playground专责报告核对（此处未重复查文件/许可）；见Playground专责报告 | 缺：爬梯与攀爬恢复；Playground专责核验，含chimney伴随链接 |
| 18 | [HannesVonEssen/microduck-backflip](https://huggingface.co/HannesVonEssen/microduck-backflip) | Playground专责报告核对（此处未重复查文件/许可）；见Playground专责报告 | 缺：raised backflip；long-jump已接；Playground专责核验 |
| 19 | [joanfox/microduck-happy-hop](https://huggingface.co/joanfox/microduck-happy-hop) | ONNX 1；apache-2.0 | 已接：happy-hop；保留 |
| 20 | [llama/microduck-beak-throw](https://github.com/llama/microduck-beak-throw) | ONNX 0（源码树无ONNX不代表外部HF无权重）；Apache-2.0 | 缺：嘴抛球；q2p发布权重；jaw独立时序和动作clamp必需 |
| 21 | [zhoumiaosen/microduck-rl](https://github.com/zhoumiaosen/microduck-rl) | ONNX 0（源码树无ONNX不代表外部HF无权重）；Apache-2.0 | 相近：已有快跑，缺heading-hold直跑；可作为“跑得快/跑得直”对照 |
| 22 | [RemiFabre/microduck-rough-walk-e](https://huggingface.co/RemiFabre/microduck-rough-walk-e) | ONNX 1；apache-2.0 | 缺：rough terrain policy及场地；适合低台阶/碎石/缓坡对照 |
| 23 | [Teethyfish/microduck-collision-flamingo-ii](https://huggingface.co/Teethyfish/microduck-collision-flamingo-ii) | ONNX 1；apache-2.0 | 相近：已有单脚站，缺完整外壳碰撞版本；实验对照，play和ONNXviewer结果不一致 |
| 24 | [chenp9527/microduck-jump](https://github.com/chenp9527/microduck-jump) | ONNX 1；Apache-2.0 | 相近：已有hop，缺3–6cm目标与冲击指标；128N落地峰值未达40N门槛，不列稳定交付 |
| 25 | [QingMuLYL/microduck-standup](https://huggingface.co/QingMuLYL/microduck-standup) | ONNX 1；未见明确顶层许可元数据；不得推定 | 部分：步态可含恢复，无独立6s起身演示；导出自dirty checkout，需固定来源和许可 |
| 26 | [kramp/microduck-groove](https://huggingface.co/kramp/microduck-groove) | ONNX 1；未见明确顶层许可元数据；不得推定 | 缺：学习版原地groove；126BPM而非目标100；缺许可元数据 |
| 27 | [drfonz-indigo/microduck-playdead](https://huggingface.co/drfonz-indigo/microduck-playdead) | ONNX 1；未见明确顶层许可元数据；不得推定 | 缺：装死后仰躺，再自起；5s episodic，需后续恢复及嘴部独立控制；缺许可元数据 |
| 28 | [cetiennec/microduck-on-sourccey-dome](https://huggingface.co/cetiennec/microduck-on-sourccey-dome) | ONNX 1；未见明确顶层许可元数据；不得推定 | 缺：站在运动Sourccey穹顶上；需穹顶/移动底盘和低通/standing gain契约 |
| 29 | [Kyry10/microduck-arena-lab](https://huggingface.co/Kyry10/microduck-arena-lab) | ONNX 5；apache-2.0 | 相近：有快跑，缺受控竞速/坡道跑；可作为赛道公平对比，非全新动作 |
| 30 | [zachgarner/microduck-headstand](https://github.com/zachgarner/microduck-headstand) | ONNX 0（源码树无ONNX不代表外部HF无权重）；未见明确顶层许可元数据；不得推定 | 缺：六策略串联倒立杂技；发布权重在HF；GitHub未见LICENSE，不可假定Apache |
| 31 | [toyhank/microduck-vision-soccer](https://github.com/toyhank/microduck-vision-soccer) | ONNX 4；NOASSERTION | 部分：有RGB找球踢球，无守门员比赛；增加射门/守门员状态机；98/100是GT基线 |
| 32 | [AungKaung1928/microduck-rl](https://github.com/AungKaung1928/microduck-rl) | ONNX 1；MIT | 相近：已有PPO平衡，无其模型/CPU训练比较；训练方法和失败分析对照，不算独立新动作 |
| 33 | [KhushiJ2911/microduck-piano-learning](https://github.com/KhushiJ2911/microduck-piano-learning) | ONNX 2；Apache-2.0 | 缺：双鸭踩物理钢琴键；有ONNX；1/64严格验收，实验而非任意乐曲演奏 |
| 34 | [langli11/microduck-tricks](https://huggingface.co/langli11/microduck-tricks) | ONNX 3；apache-2.0 | 缺：助跑前滚翻/绕锥轮滑/短单脚滑；三套ONNX；持续长单脚滑未达标 |
| 35 | [hikarioyama/microduck-onefoot-skate](https://github.com/hikarioyama/microduck-onefoot-skate) | ONNX 4；Apache-2.0 | 缺：持续单脚轮滑；1/64达2秒；研究快照，不列稳定技能 |
| 36 | [pngwn/microduck-detector](https://huggingface.co/pngwn/microduck-detector) | ONNX 0；未见明确顶层许可元数据；不得推定 | 部分：几何/颜色感知，未接YOLO鸭检测；感知模型，不是运动策略；先做像素发现同伴对照 |
| 37 | [Datawhale/Microduck-RL-4096x6000](https://huggingface.co/Datawhale/Microduck-RL-4096x6000) | ONNX 1；other | 相近：已有步态/踢球，无该复现checkpoint；训练复现对照；无独立新增技能 |
| 38 | [wat-bill/microduck-action-pack](https://github.com/wat-bill/microduck-action-pack) | ONNX 1；Apache-2.0 | 相近：已有编排头部舞蹈，无其任务包；可复用动作调度，不声称新的RL能力 |
| 39 | [apirrone/microduck-footsteps](https://huggingface.co/apirrone/microduck-footsteps) | ONNX 2；apache-2.0 | 已接：Footsteps + FootstepNet；保留 |
| 40 | [RemiFabre/microduck-static-grasp](https://huggingface.co/RemiFabre/microduck-static-grasp) | ONNX 1；apache-2.0 | 部分：有嘴搬运，无低位static-grasp；新发布pick网络+jaw时序+runtime补丁；非单换ONNX |
| 41 | [witcheer/microduck-walk-flat](https://huggingface.co/witcheer/microduck-walk-flat) | ONNX 1；apache-2.0 | 缺：terrain walk family；rough/slope/step/stairs/slip/gale/recover，不应只列flat一项 |
| 42 | [witcheer/microduck-standup](https://huggingface.co/witcheer/microduck-standup) | ONNX 1；apache-2.0 | 部分：有起身/前滚翻/踢球等效功能，缺该家族及巨球；300mm巨球踢球是明确新增；普通小球踢不覆盖 |
| 43 | [mindthink/microduck-policies-repro](https://huggingface.co/mindthink/microduck-policies-repro) | ONNX 4；apache-2.0 | 相近：已有官方步态，无该复现修正；低速死区/质量对比工具，不算新动作 |
| 44 | [thejerrycheng/microduck_replication_feetech](https://github.com/thejerrycheng/microduck_replication_feetech) | ONNX 25；MIT | 不适配当前XL330硬件模型：HD1910 replica；需Feetech BAM和模型，不能直接装在当前鸭上 |

权重文件名、SHA、manifest存在性和本地证据路径均在 `community_registry_inventory.json`，不是只给项目名字。HF许可列是模型卡/API证据，GitHub列是仓库顶层许可；未见许可必须澄清，不能从母项目Apache推定模型重分发许可。

### Inferences
- 可在已有场景中优先扩展：低位真接触叼取、嘴抛球、巨球踢球、射门守门员、绕锥轮滑、倒立/头旋/后滚翻、粗糙/湿滑/大风地面。与现有场景有复用空间，但都仍需独立验收。
- 学习版动作（groove/月步/鞠躬）和本地编排同类表演应同时标明来源，不能把任意脚本姿势叫PPO学会。

### Gaps
- fffiloni bow/moonwalk、groove、playdead、QingMu standup及Sourccey卡未见明确顶层许可元数据；zachgarner headstand Git树未找到LICENSE。再分发前需解决许可，研究清单不能因此把它们静默删掉。

## 注册表之外还应纳入哪些场景与地面体验

### Takeaway
确有更多遗漏。以下按功能域补全，并标出交付程度；不能把视频主题或未完成训练直接列为“可运行技能”。

### Cited Findings
| 候选 | 已取得的实际资产与控制边界 | DuckKing增量 / 建议 |
|---|---|---|
| 倒立→腿部换姿→后滚翻→站回 | 六策略PyTorch checkpoint，六个HF发布含ONNX；61/14/50Hz、BAM，阶段切换用仿真接触；作者87/96全程，零延迟0/32。GitHub无LICENSE，必须澄清 | 新的完整杂技场景，优先级高；按延迟与handoff契约做真实CPU试跑。[headstand](https://github.com/zachgarner/microduck-headstand) |
| 逆立/左右头旋/后滚翻连续技 | Git树9个ONNX；Apache-2.0；CPU MuJoCo+BAM，15–30ms延迟作者50/50，≤5ms头旋退化 | 另一杂技实现，可优先作为许可明确的基线，而非同时重复两套产品入口。[acrobatics](https://github.com/reble2421/microduck-acrobatics) |
| 看球追踪、视觉射门与视觉守门员 | 有4个ONNX，头摄RGB+IMU/encoder；98/100是GT导航baseline，不能冒称RGB控制成功率 | 当前“找球踢球”之后的明显扩展。[vision soccer](https://github.com/toyhank/microduck-vision-soccer) |
| 双鸭踩地面琴键 | 树含键盘策略ONNX，6mm弹簧键真实按压；作者1/64全部严格门槛，不是任意曲目演奏 | 可展示接触→音符；应保留实验标签，不能承诺“输入歌名会弹”。[piano](https://github.com/KhushiJ2911/microduck-piano-learning) |
| 3v3足球 | 树9个ONNX；MuJoCo WASM+ONNX-web，6鸭同场；MIT | 可复用成多人观赛/指挥战术，需检查每鸭CPU成本与真实接触。[3v3](https://github.com/00make/microduck-arena) |
| 五鸭迷宫追逐/吃豆 | 树4个ONNX和7个checkpoints，BAM，每鸭自由体；策略层BC+进化策略，腿部官方RL；Apache-2.0 | 新的多鸭对抗玩法，不能把所有上层规则说成RL。[Duck-Man](https://github.com/nyle-prosal/duckman-microduck) |
| 跳房子Rayuela | ROS2 Humble/Jazzy，MuJoCo+BAM，摄像机估计球落在哪格；踢球、走/滚到格再返回，已有可变踢速策略名 | 语音“踢到第几格”很适合，移植状态机可避开必须部署整套ROS。[Rayuela](https://github.com/Bravo-Robots/microduck_rl-rayuela) |
| 嘴夹取的训练前后对照 | browser MuJoCo，jaw策略独立学习，当前trained 12/12 vs untrained0/12；scripted同样12/12，非胜过脚本；源码包括小checkpoint但无顶层清晰统一license | 展示“会咬也要会放”，比已有理想夹持有增量；需证实接触/约束边界并澄清许可。[beak lab](https://github.com/qilinxiaoxiang/microduck-beak-lab) |
| 按名字取玩具→搬到托盘 | 树/README含YOLO ONNX/RKNN和robotd策略，Mac纯CPU路径；RK3588 INT8作者52/60；抓牢后用weld | 不是纯接触夹持，但视觉语义识别和长任务有增量；可先用MacCPU，标注抓持代理。[toy retrieval](https://github.com/Baro7ue/microduck-rk3588-toy-retrieval) |
| 室内找红球/蓝盒/黄柱 | 4个ONNX+checkpoint、家具场景和RGB detector；PPO高层+guard+gait，CPU能跑；作者full-body49/60，9跌倒，proxy237/256不可混用 | 与现有颜色找球不同：有家具遮挡与搜索策略；适合PPO感知关卡。[indoor search](https://github.com/Bravo-Robots/microduck-indoor-object-search-rl) |
| 相似球干扰中的目标追踪 | 基于tracking库的目标锁定/取被扔出的球；registry有源，仍需逐控制路径确认 | “只追我刚扔的那颗”是新场景，不等于颜色分割。[tracking](https://github.com/AlexBodner/microduck-tracking) |
| 躲家具/矮障碍/悬崖的自主探索 | depth sensor+真实daemon+MuJoCo公寓；可选回家/卡住恢复；Apache-2.0 | 现有已知地图A*不覆盖在线感知、未知探索、悬崖保护。[brain](https://github.com/samoxis/microduck-brain)；[quack-nav](https://github.com/andreagenovese/quacknav) |
| 全局建图、标记地点、跨房间回家 | quack-nav已发布ToF SLAM/重定位/costmap/places/explorer，Muon twin+paper twin分开量化 | 可作为“一站式感知导航”高阶区，不和当前仿真真值导航混称。[quack-nav](https://github.com/andreagenovese/quacknav) |
| Jenga头部敲块 | CEM参数头轨迹+冻结平衡策略，受控14cm摆位，2块作者25/30；三块PPO未解，无成功PPO权重 | 可做“头部接触改变环境”实验；不是会搭积木、不是学会三块Jenga。[Jenga](https://github.com/speccy88/microduck-jenga-sim) |
| 双鸭合作推物MAPPO | HF有partial Torch checkpoints；V97被暂停、未评估，源码链接本次404，无ONNX；Apache-2.0卡 | 有趣且RL增量大，但交付性未满足；列研究候选，先解决源码与未完成训练。[coop MAPPO](https://huggingface.co/npow/microduck-coop-mappo) |
| 跟着音乐生成舞蹈 | EDGE→retarget→RL跟踪，flat/rough/rollers任务，Apache代码；源码树有pt文件，但明确外部歌曲/EDGE/Jukebox权重及训练成品未完整随包 | 当前编排动作之外的新训练方向；需补成品策略与音乐权利，不宣称任意歌曲即刻可用。[dance](https://github.com/tomomimu12345/microduck-dance) |
| 多鸭领航/妈妈带鸭 | HF Space browser-only，模拟ToF/detection而非RGB，两只跟随，非任意N群体控制 | 易懂的互动场景，需标示感知代理。[Mommy flock](https://huggingface.co/spaces/oliveirabruno01/microduck-mommy-flock) |
| 餐厅四鸭轮滑赛/三鸭双圈赛 | 复用官方策略的waypoint/赛程层，浏览器MuJoCo；三鸭各自独立世界并非互撞 | 可扩比赛玩法，明确“共享场/独立赛道”区别。[Racer](https://huggingface.co/spaces/Nirav-Madhani/microduck-racer)；[Competition](https://huggingface.co/spaces/HandsomeWu666/Microduck-playground-competition) |
| 足球/迷宫游戏的技能selector | TorchRL九技能prior+game selector：football experimental，tag unsolved；没有ONNX | 候选研究路线，不能直接当3v3成熟替代。[TorchRL](https://huggingface.co/torchrl/microduck-skills) |
| TinyVLA看图听语言控制 | Space分vision/semantic/action三个ONNX，CPU后端+浏览器物理；使用256px头摄+61状态+自然语言 | 适合作为“本地VLA vs 灵矽工具”对照；需要检查任务泛化和模型负载。[TinyVLA](https://huggingface.co/spaces/AlexWortega/microduck-vla-simulator) |
| 果蝇脑控制/多鸭感官花园 | FlyWire固定spiking网络+训练readout再驱动现有步态，非果蝇脑学会走路；MicroGarden五脑体有饥饿/渴状态 | 有教育展示价值，需CPU/内存预算；不归为现成61/14动作。[FlyWire](https://huggingface.co/spaces/AlexWortega/flywire-microduck)；[MicroGarden](https://github.com/ChristianNHill/micro-garden) |
| 地毯柔顺/变摩擦训练 | MIT配置面板+训练adapter，明确没有trained policy、接触模型近似不模拟纤维 | 可展示地面改变对步态影响；必须先验收策略，不当现成技能。[Carpet Lab](https://github.com/yuecui0130-create/microduck-carpet-lab) |
| 湿滑/逆风/连续小台阶/缓坡/碎石 | witcheer每变体policy.onnx和Apache-2.0；Remi rough-e/g也有权重；环境参数和matched模型需同步 | 应纳入“地形实验”而非只换颜色，适合训练前后PK。[slip](https://huggingface.co/witcheer/microduck-walk-slip)；[gale](https://huggingface.co/witcheer/microduck-walk-gale)；[rough](https://huggingface.co/RemiFabre/microduck-rough-walk-g) |
| 六个程序生成世界 | Chocolate factory/hospital/low-gravity hab/circus/mine/frozen lake，Blender资产+MuJoCo+HF policies；基线与world-trained对比。部分收益在噪声内，低重力1.62m/s²非地球环境 | 环境体验缺口很大，适合导入世界资产；不把“能展示世界”当全部任务已学会。[Duck Worlds](https://github.com/suvadityamuk/microduck-ppo-blender-kimi) |
| 外力/坏电机/延迟/弱电池压力实验 | Creature Lab通用机器人试验框架、Apache-2.0；主宣传图为G1，不保证所有实验已在MicroDuck验证 | 借鉴公平对照与解释，不直接复用G1结果或号称全鸭验收。[Creature Lab](https://github.com/oney-erge/Creature-Lab) |

### Inferences
优先组合不是再堆一次三个名字：
1. **现有动作深化**：低位夹取与嘴抛球、装死+起身、巨球踢球、绕锥轮滑、倒立头旋连续技；都有明确新表现，许可和运行契约分别把关。
2. **主动感知任务**：视觉射门/守门员、目标跟踪、家具房间找物、取指定玩具、在线建图与悬崖保护；明确区分像素/ToF、真值和抓持代理。
3. **多鸭与接触玩具**：3v3、迷宫追逐、踩琴键、Jenga；研究低成功率照实显示；MAPPO先研究不承诺交付。
4. **环境体验层**：程序世界、低台阶/缓坡/碎石/湿滑/地毯近似/逆风，和纯视觉地面皮肤分开。木地板、草坪或水泥贴图可由前端制作，但不能从项目名称推定其真实摩擦或材料模型。

### Gaps
- HF保龄球、鸭棋、Matrix躲子弹、Amour Impossible等卡本次确实查到了，但很多发布只是基础perpetual gait+节目说明；没有独立游戏/碰撞/动作编排资产的，不应声称“加载这一个ONNX就会保龄球/下棋/躲子弹”。[bowling卡](https://huggingface.co/linkTheWorld/microduck-duck-bowling)；[chess卡](https://huggingface.co/craigm26/microduck-kith-duck-chess)；[amour卡](https://huggingface.co/apirrone/microduck-amour-impossible)
- microduckapp数十卡声明各种表演并有ONNX/manifest，但没有足够源码/许可/物理验收证据，未按卡名提升为可交付能力。[示例](https://huggingface.co/microduckapp/microduck-slalom)
- Raghav动态柠檬/勺/球拍/重载套件卡声明主动Steadicam/pantograph，不是原机身体能力；未取得对应可用源码仓库，不能因夸张量化卡片就直接集成。[卡](https://huggingface.co/Raghav-16/Microduck_Manipulation)
- Cartesian cartwheel卡有policy.onnx和训练revision，但没有已核对的完整sim2sim验收记录；侧手翻属于进一步复测候选。[卡](https://huggingface.co/JacoCronje/microduck-cartwheel)
- 省略已确认“只是训练框架/硬件移植/控制面板/重复 gait”不会丢掉总账；全部README条目保留在 `community_readme_inventory.json`，可按类别继续追溯，不用把每一个包装项目都做成产品入口。
