# MicroDuck 全生态 能力覆盖 复审

> 工程进度：本报告的源码审计基线为 `9cac621`，保留当时18项的事实；后续41项实现、实验失败与未移植候选见 [场景核销](../docs/SCENE_DISCOVERY_ROLLOUT.md)，不能将来源审计当作新增策略的物理验收。


**重建 MicroDuck 一站式能力总账**

**全生态复审 · 2026-11-13（北京时间） · DuckKing 对照提交 `9cac621`**

**是的，其他仓库还有大量值得引入而此前没有完整纳入的场景；Playground 的遗漏只是一个可见例子。** 问题出在上轮先把内容压成少数主题，再选择几个代表，没有建立“每条来源→实际资产→产品能力→接入状态”的完整对应；“有相近动作”也被过早当成“已覆盖”。本次重新从官方任务与发布资产、Playground 整仓、awesome 注册表及链接项目、HF 模型分页查起。结果既补出高跷、攀爬、后空翻，也补出倒立连续技、轮滑绕锥、嘴抛球、巨球、双鸭拔河、偷袜子、视觉守门员、室内找物和多鸭游戏。另一方面，有些有趣名字只是节目包装，有些仅有训练代码、不同电机模型或未完成研究，不能一律写成可直接上线。下面保留这些区别，并给出完整总账和施工顺序。**这是资源与源码审计；本次没有运行新增权重、重新测成功率或完成实体机器人验证。**（[注册表](https://github.com/joeynyc/awesome-microduck/blob/9cfa5abca6f143b8af0048aeb6004dc5e67f81e8/policies.json)；[官方活动](https://github.com/pollen-robotics/microduck-challenges/blob/5cee942d8b434aafd395070facb659034aac3b5e/README.md)；[当前代码](https://github.com/zhoutingunl/DuckKing/blob/9cac621484f87131b754b8e7a3303fa869af8e9c/src/duckking/feature_catalog.py)）

## 1　先补闭环与真实新行为，清单不再止于十个名字

当前 feature 分支有 **18 张功能卡片**，旧页面还包含前滚翻、嘴部搬运、轮滑/下蹲、合唱与转盘/跷跷板 PPO。卡片数不能作为生态覆盖率：普通后退不等于月步，平地滑行不等于坡道轮滑，RGB 找球后踢一脚不等于视觉守门员，已有合唱也不等于踩下物理琴键。Playground 首页十项中，当前五项已有代码适配，秋千的完整绳长验收仍未通过；另外五项确实尚未施工。以下优先级是基于资产、观众辨识度、语音闭环和工程复杂度的判断，**不是已经完成的发布计划或工期承诺**。（[功能目录](https://github.com/zhoutingunl/DuckKing/blob/9cac621484f87131b754b8e7a3303fa869af8e9c/src/duckking/feature_catalog.py)；[原有物理控制](https://github.com/zhoutingunl/DuckKing/blob/9cac621484f87131b754b8e7a3303fa869af8e9c/src/duckking/simulation.py)；[PPO 页面](https://github.com/zhoutingunl/DuckKing/blob/9cac621484f87131b754b8e7a3303fa869af8e9c/frontend/balance.html)）

| 建议批次 | 能力族 | 资源与当前缺口 | 语音切入 | 必须看见的实际结果 |
|---|---|---|---|---|
| 基础先修 | 地形显示与可靠取消/重置 | 补高度场、地面与碰撞一致性；继续修秋千/跳绳验收 | “停下、重置、刚才失败在哪？” | 把源码存在和当前可交付区分开，避免新场景都立在错误画面上 |
| 第一批 | 独立自起与可控跌倒 | 官方 alpha_stand 已发布；缺显式演示和恢复验收 | “躺下再自己起来” | 身体姿态、脚部支撑、恢复耗时；区别 velstand 与独立恢复策略 |
| 第一批 | 高跷八高度 | 八档匹配 ONNX 与几何；先验收10 cm，再开放其余高度 | “换十五厘米高跷，往前走” | 每档匹配质量/惯量/接触，不能拉长普通鸭腿 |
| 第一批 | 低位叼取、嘴抛球、巨球踢 | static-grasp、beak-throw、300 mm巨球分别有发布策略 | “咬住、搬来、放下／把球抛出去” | 真接触或夹持代理要标注；jaw时序和限位不能省略 |
| 第一批 | 地面适应实验 | rough/slip/gale/step/stairs/slope有社区权重家族 | “换湿滑地面／加一点逆风” | 显示摩擦/外力与匹配策略，分别验收，不能只换皮肤 |
| 第一批 | 站姿与坐姿回桩对照 | Playground v1缺，v2已有部分；补休眠/唤醒链 | “回去休息，醒来再出来” | 仍是虚拟电量和仿真接通，不声称真实充电 |
| 第二批 | 轮滑绕锥与短单脚滑 | langli三套ONNX；长时间单脚滑尚不可靠 | “绕过路桩，再单脚滑一段” | 实际绕桩、碰撞、支撑与滑行时长 |
| 第二批 | 倒立、头旋、后滚翻连续技 | 两套社区实现；优先核验许可明确的 acrobatics | “来一段倒立杂技，随时停止” | 按阶段接触与最终站稳评分；延迟、handoff契约要匹配 |
| 第二批 | 爬梯上桌与跳台后空翻 | Playground有发布模型与场景；当前均缺 | “爬上桌／跳到软垫上” | 落台和恢复分段评分；后空翻不能删除软接触垫 |
| 第二批 | 双鸭拔河、红灯停偷袜子 | 官方活动源码和reference权重可查 | “开始拔河／红灯停” | 共享物理、绳连接、违规判定和有界回合 |
| 第二批 | 视觉射门/守门员、家具房间找物 | 视觉足球、室内搜索、取指定玩具有源码/权重基础 | “守住球门／把红色玩具拿过来” | 区分像素感知、真值基线、导航辅助与抓持代理 |
| 第二批 | 公寓、轮滑馆、八鸭可编辑舞台 | 官方场景与程序化视觉资产可复用 | “去厨房／让B独唱／换木地板” | 先复用现有技能，减少重复按钮；编辑编排属于产品能力 |
| 第三批 | 3v3足球、五鸭迷宫、跳房子 | 社区有物理游戏实现；引擎/上层算法不同 | “盯住对方／踢到第三格” | 多鸭共享物理、资源占用、比赛规则和感知假设 |
| 第三批 | 在线探索、建图与特定目标追踪 | ToF SLAM、未知探索与锁定目标源码可查 | “避开悬崖，找回刚才那颗球” | 不能用当前已知地图A*替代真实在线感知 |
| 第三批 | 物理钢琴键、Jenga、烟囱攀爬 | 有代码和部分权重，但严格验收/恢复仍弱 | “踩这个音／敲出这块／从缝隙爬上去” | 作为可失败实验；不得包装成保证成功的一键秀 |
| 研究保留 | MAPPO合作、VLA、侧手翻、音乐生成舞 | 代码/权重/许可/完成度各有缺口 | 可作为训练与对照课题 | 先解决缺口，不以名字或视频当成熟能力 |

这些批次不能成为新的删选器：下文中“研究保留”“相近能力对照”和“暂缺权重”的项目仍在总账里。产品界面可按身体技巧、轮上运动、感知导航、嘴部操作、多鸭游戏、音乐表达、生活自理、环境适应与训练实验分组；同族的高度、策略版本和难度放在场景内部，避免把八种高跷或齿隙变体机械地变成一排重复卡片。

## 2　官方与 Playground 都还有未接入的完整行为链

### 官方的基础恢复、六项活动和感知能力需要一起看

官方 RL 默认分支是 **develop `0daab160…`**，main 是 `1e79c29…`。本次静态核对得到 **13 个家族、33 个任务 ID**，其中含 Flat/Rough 和齿隙变体，不能称为33种成品动作。官方通用策略仓库当前有 **10 个 ONNX**，其中明确包含 `alpha_stand.onnx`；此前“自起只有任务、没有官方 ONNX”的判断应撤回。DuckKing 常规后端注册八个 session，使用 velstand 作为基础步态，但还没有显式翻倒恢复场景。两个分支的任务 ID 相同，环境资产却不同，本次 apartment/VSLAM 资产在默认 develop 可读，不能只查 main。（[任务注册](https://github.com/pollen-robotics/microduck_rl/blob/0daab160d3fb1c2cbaba16a4a19052f36709dd9e/src/mjlab_microduck/tasks/__init__.py)；[10个ONNX文件](https://huggingface.co/pollen-robotics/microduck-policies/tree/236d1835b03ac7b45d962efbf2fe3a6940206112)；[当前session](https://github.com/zhoutingunl/DuckKing/blob/9cac621484f87131b754b8e7a3303fa869af8e9c/src/duckking/simulation.py)）

| 官方家族 | 内容及现成资产证据 | DuckKing 现状 / 应纳入的工作 |
|---|---|---|
| Velocity | 速度与头部控制，alpha_walking 已发布 | 基础行走已有；不同步态作对照，避免重复新增按钮 |
| VelStand | 行走与摔后恢复合一，velstand 已发布 | 已作为基础步态使用；尚需明确“推倒/侧倒/仰躺→恢复”演示与真实恢复验收 |
| StandUp | 俯卧/仰卧/坐姿起立，alpha_stand 已发布 | **值得优先补显式摔倒自起场景**，并区分独立站起策略和 velstand 恢复 |
| SitStand | 坐下/站起，alpha_sitstand 已发布 | 已有，四鸭坐姿独唱等已使用 |
| GroundPick | 嘴触地后恢复，alpha_ground_pick 已发布 | 已有；“叼取物品”的夹持为 DuckKing 自建扩展，不能等同纯官方 GroundPick |
| BallKick | 盲踢 70 mm/15 g 球，左右策略已发布 | 已有，视觉找球为另加控制层 |
| Roulade | 头顶前滚翻 | 已有 |
| Rollers Velocity | 被动轮轮滑速度控制 | 已有 roller 场景 |
| Swizzle | 双脚对称葫芦形轮滑推进，独立训练任务 | 当前没有单独模式/对照；**不能仅按 roller.onnx 文件名断定已覆盖或未覆盖这种动作形态**，需比对该权重训练来源 |
| RollerCrouch | 下蹲滑行 | 已有 roller_crouch |
| RollerSlope | 坡道自由滚滑 | **缺真实坡道与其专用策略适配**；平地滑行不代表覆盖下坡 |
| RollerStandUp | 从地面站到轮上并保持 | **缺明确模式和匹配权重**；官方包未列同名独立 ONNX，不能以普通脚模型站起替代 |
| Spin | 轮上差速快速旋转 | **缺独立模式和匹配权重**；原地转向并非该轮滑技能 |

上述“有任务”与“有匹配的可发布权重”分别核验。RollerSlope、RollerStandUp、Spin 的专用成品版本仍需锁定；Swizzle 需要先核对现有 roller 权重谱系，不能只按文件名断言完全会或完全不会。其他官方层面的体验也值得纳入，它们不一定是PPO策略。（[任务定义](https://github.com/pollen-robotics/microduck_rl/blob/0daab160d3fb1c2cbaba16a4a19052f36709dd9e/README.md#tasks)；[官方操作手册](https://github.com/pollen-robotics/microduck/blob/15dae7f1df8182584f432361fbbb4af0e8bfb1c7/docs/robot/cheatsheet.md)）

| 能力 | 来源 / 与当前工程区别 | 建议 |
|---|---|---|
| 被抱起就收住腿，放下再继续 | robotd 的 picked_up 检测；DuckKing 没有对应演示 | 可做抓住躯干/抬起/放回物理交互；检测和阈值需适配 |
| 跟随红色激光点 | mediad 检亮点和相机几何，robotd 看/走向目标；当前寻彩球不是同一对象 | **高趣味、较低成本候选**：用户拖动光点、语音让小鸭追或停；RGB 必须真的看到点，不能直接把点世界坐标给控制器 |
| 摸头呼噜/个体嘎声 | 麦克风分类与 SoC 派生声线；MuJoCo 不会自动合成真实抓挠音 | 可在页面做触摸头部反应，明确“触摸触发演示”；若要音频分类须另接真实/录音输入 |
| 相机找同伴 | `microduck-duck-detector` 有 ONNX/PT/RKNN；现有发现同伴主要几何视野逻辑 | 可补真实相机检测框与置信度，同场距离只能作验收/测距，不混称模型看见 |
| 8×8 ToF 深度矩阵 | 官方 ToF 面板；当前功能页主要一条光轴射线 | 可补 64 条距离扫描、遮挡、最近障碍及相机对照 |
| 四鸭 chorale 的无线协议 | 官方 duck-sim boot 4 + duck-ether 模拟丢包延迟 BLE | 当前合唱为浏览器本地编排；真实协议可作进阶“同步/失联”实验，不宜重复称现有四声部为 BLE 实测 |
| 每鸭养成档案/分享卡 | 官方 Vetbook 记步程、跌倒、拥抱、技能并生成多款卡片 | 当前产品使用延迟统计不等于每鸭经历；可增仿真专属成长卡，明确数据来源 |
| 手柄/头身操纵、待机与情绪 | 官方基础输入和 13 种情绪 | DuckKing 基础动作/情绪/待机已有部分；整合现有入口比再造重复动作有价值 |

官方 Arena 现有 **六项活动**。此前只列四项，漏掉了最有明显互动性的拔河和红灯停偷袜子。其中五项有独立 reference 模型库，均查到 ONNX、checkpoint 与 manifest；拔河 reference 直接位于 Arena 资产中。它们的训练算力和CPU运行已有策略是两个问题；本次只核对公开资源，不把作者分数或Mac演示换算为官方Linux榜单成绩。（[挑战仓库](https://github.com/pollen-robotics/microduck-challenges/blob/5cee942d8b434aafd395070facb659034aac3b5e/README.md)；[Arena固定版本](https://huggingface.co/spaces/pollen-robotics/microduck-arena/tree/9305b754862c56b2b2ce512c063c34600efbf932)）

| 活动 | 真实玩法 / 成品资源 | DuckKing 差距 |
|---|---|---|
| sprint-2m | 2 m 竞速；官方 reference ONNX | 有快跑但无同一跑道/计时/多种子成绩；可做 2 鸭竞速 |
| roller-sprint-2m | 轮滑 2 m 竞速；独立 reference ONNX | 有轮滑但无竞赛赛制 |
| hill-climb-1m5 | 1.5 m、8° 上坡；独立 reference ONNX | 真实上坡体验尚缺，与 Playground 下坡区分 |
| got-a-talent | 20 s 舞台，timeline 控坐姿/头部/嘎声/曲谱；最多 8 鸭、各自策略和布局，观众投票 | 当前四鸭导演/剧场有重合；值得吸收为可编辑编排与用户作品，而非再加一个固定节目 |
| tug-of-war | 两鸭颈部连 1 m 绳，在 3 m 擂台上向后拉；跌入坑或中线判胜，45 s 回合 | **高价值缺口**。绳是颈部连接，并非嘴夹绳；代码和 `arena/assets/policies/tug-reference-t20-500.onnx` 都存在 |
| sock-heist-6m | 6 m 偷袜子；巨鸭转头红灯时要停，超过 3 cm 容差会被抓；reference ONNX | **高价值缺口**。actor 看到的是变成零的指令，不是从图像识别巨鸭；赛道另有中心线转向辅助，需在演示中说明 |

拔河是**颈部连绳**，不是嘴夹绳；偷袜子 actor 接收的是被置零的命令，并非从图像识别巨鸭的转头。got-a-talent 的最多八鸭分别有策略、时间线、声音与布局，可作为现有四鸭导演的可编辑作品模式。官方 WASM simulator 的多人“幽灵”只广播姿态，不能等同共享物理碰撞；滑板等 GLB 道具也不证明已有滑板策略。（[拔河规则](https://huggingface.co/spaces/pollen-robotics/microduck-arena/blob/9305b754862c56b2b2ce512c063c34600efbf932/arena/events/tug-of-war.toml)；[偷袜子规则](https://huggingface.co/spaces/pollen-robotics/microduck-arena/blob/9305b754862c56b2b2ce512c063c34600efbf932/arena/events/sock-heist-6m.toml)；[才艺规则](https://huggingface.co/spaces/pollen-robotics/microduck-arena/blob/9305b754862c56b2b2ce512c063c34600efbf932/arena/events/got-a-talent.toml)；[浏览器simulator](https://huggingface.co/spaces/pollen-robotics/microduck-simulator/blob/efedf47f4d4ae52d17ad2e108a5b8795d41537a3/README.md)）

### Playground 首页十项都应有明确的施工状态

Playground 当前 main 仍为 `052a249…`，与前次读取的是同一提交。它有 **1,023 个文件、49份相关原始文档、46个声明任务 ID（含17个Backlash）**。本次还核对了八个HF发布库，不能再把整仓压缩成“秋千和回桩”两个名字。下表保留全部十项；“已有”指 feature 分支代码适配，不能据此断言已在main或公网部署。（[固定仓库](https://github.com/Vottivott/microduck-playground/blob/052a2494dd6372289221c7a4f24a245b443dd75f/README.md)；[声明任务](https://github.com/Vottivott/microduck-playground/blob/052a2494dd6372289221c7a4f24a245b443dd75f/src/mjlab_microduck/tasks/__init__.py)）

| 首页实验 | DuckKing状态 | 资产与不能漏掉的范围 | 原始证据 |
|---|---|---|---|
| 自驱秋千 | 已有适配，完整验收未过 | 单ONNX、座椅、两根弹性绳；继续核验绳长而非只看摆幅 | [来源](https://github.com/Vottivott/microduck-playground/blob/052a2494dd6372289221c7a4f24a245b443dd75f/experiments/swing/README.md) |
| 篮球上盲平衡 | 最近接入 | LSTM记忆；原地与小步滚动；actor无球位置输入 | [来源](https://github.com/Vottivott/microduck-playground/blob/052a2494dd6372289221c7a4f24a245b443dd75f/experiments/basketball/README.md) |
| 快跑 | 最近接入 | iteration12195；不同checkpoint版本归同族 | [来源](https://github.com/Vottivott/microduck-playground/blob/052a2494dd6372289221c7a4f24a245b443dd75f/experiments/running/README.md) |
| 高跷 | 尚未接入 | 10/15/20/25/50cm、1/1.4/2m；八档各有ONNX和匹配形态 | [八档发布](https://github.com/Vottivott/microduck-playground/blob/052a2494dd6372289221c7a4f24a245b443dd75f/experiments/stilts/README.md) |
| 爬梯上桌 | 尚未接入 | 爬梯→落桌→恢复；27踏板/0.66m桌；两actor及监督切换 | [完整动作契约](https://github.com/Vottivott/microduck-playground/blob/052a2494dd6372289221c7a4f24a245b443dd75f/experiments/desk-climb/RUNTIME.md) |
| 烟囱攀爬 | 尚未接入 | enter/climb/exit三ONNX+官方恢复；12.5cm缝/3m为选中演示配置 | [分阶段契约](https://github.com/Vottivott/microduck-playground/blob/052a2494dd6372289221c7a4f24a245b443dd75f/docs/chimney-climb.md) |
| 跳台长跳 | 最近接入 | 固定0.30m间隙、0.25m落差；不代表任意平台 | [来源](https://github.com/Vottivott/microduck-playground/blob/052a2494dd6372289221c7a4f24a245b443dd75f/experiments/parkour/long-jump/README.md) |
| 跳台后空翻 | 尚未接入 | 0.8m台顶到垫顶落差，必须保留数值软接触垫 | [来源](https://github.com/Vottivott/microduck-playground/blob/052a2494dd6372289221c7a4f24a245b443dd75f/experiments/parkour/backflip/README.md) |
| 站姿回桩v1 | 尚未接入 | 官方velstand倒退回桩；标签定位与接通停止为仿真控制层 | [来源](https://github.com/Vottivott/microduck-playground/blob/052a2494dd6372289221c7a4f24a245b443dd75f/hardware/microdock/README.md) |
| 坐姿回桩v2 | 已有部分 | 已有入坞/离坞和虚拟电量；休眠断电/唤醒全链还须单列核验 | [来源](https://github.com/Vottivott/microduck-playground/blob/052a2494dd6372289221c7a4f24a245b443dd75f/hardware/microdock-v2/README.md) |

高跷必须按高度匹配质量、惯量、脚尖几何及策略，不能只把普通腿拉长。爬梯恢复要保持BAM延迟连续，头/腿滤波不同，观测回填上一步原始输出；切换监督器使用脚接触桌面和root进入边缘4cm的仿真真值。爬梯附带assessment的warm恢复成绩106/256与official105/256差别很小，不能只凭精选录像称为可靠上桌。烟囱发布说明记录了fresh复现到达出口后恢复未完成；后空翻fresh复现在站起后漂出垫，7.62秒摔倒。这些是**上游自己的失败/局限记录**，集成时应分阶段显示，不能删去失败让节目看起来全程成功。（[爬梯runtime](https://github.com/Vottivott/microduck-playground/blob/052a2494dd6372289221c7a4f24a245b443dd75f/experiments/desk-climb/RUNTIME.md)；[恢复对照](https://github.com/Vottivott/microduck-playground/blob/052a2494dd6372289221c7a4f24a245b443dd75f/experiments/desk-climb/evidence/ASSESSMENT.md)；[烟囱复现](https://github.com/Vottivott/microduck-playground/blob/052a2494dd6372289221c7a4f24a245b443dd75f/docs/chimney-climb.md)；[后空翻验证](https://github.com/Vottivott/microduck-playground/blob/052a2494dd6372289221c7a4f24a245b443dd75f/experiments/parkour/VERIFICATION.md)）

### 首页之外还有细分技能、教学对照和未发布研究

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

这里的“首页之外”不能全部当作新增成品。齿隙是对照模式，RunningFlight是跑步奖励消融，LongJump是两项跑酷的共享基础，DeskRecovery是攀爬子阶段。LongStairsBlind的64踏板、23.1mm/级和62°更接近长斜梯；旧FloorDesk的0.74m桌与当前发布0.66m桌也不同。降落柱源码/策略明确尚未发布，只能留在观察清单，不能进入保证可交付的实施承诺。

## 3　社区新增的不只是动作，还有感知、游戏和环境闭环

注册表已从旧统计的43项变成 **44项**，但仍不能只停在这44行。本次跟随其README链接的社区仓库，再从HF完整分页筛出新行为；逐项保留“已发布文件、控制方式、许可、当前缺口”。例如 registry 的 `source-only` 是消费方式，不代表没有外部权重，courier、headstand、beak-throw都不能据此被跳过。下表保留本轮发现的主要增量，完整44项逐条映射见附录。（[固定注册表](https://github.com/joeynyc/awesome-microduck/blob/9cfa5abca6f143b8af0048aeb6004dc5e67f81e8/policies.json)；[社区目录](https://github.com/joeynyc/awesome-microduck/blob/9cfa5abca6f143b8af0048aeb6004dc5e67f81e8/readme.md)）

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

**应降级而非从总账消失的项目。** “保龄球”“鸭棋”“躲子弹”等一些HF卡片只是基础perpetual gait配节目说明，未取得独立游戏/碰撞/编排实现，不能写成加载一个ONNX便会相应运动或棋类。`microduckapp`系列有许多卡名和权重，但源码、许可和物理验收不足，仍是待核实目录；Raghav操作套件涉及额外主动机构，不能归入原机身体能力。侧手翻卡有ONNX与训练revision，完整sim2sim验收仍待查。（[保龄球卡](https://huggingface.co/linkTheWorld/microduck-duck-bowling)；[鸭棋卡](https://huggingface.co/craigm26/microduck-kith-duck-chess)；[套件卡](https://huggingface.co/Raghav-16/Microduck_Manipulation)；[侧手翻卡](https://huggingface.co/JacoCronje/microduck-cartwheel)）

**模型接口不同也会改变交付判断。** TorchRL当前主卡已是九技能prior加football/tag selector，registry仍描述七技能GRU；当前主产物是 `checkpoint.ckpt`，并没有现成ONNX，football实验性、tag未解，须专门适配。官方red-cube-blue-box虽有pi05/diffusion权重，但配置是RGB加2维state到11维action、CUDA，尚缺与MicroDuck关节/嘴部的完整映射证据，不能作为已验证MicroDuck操作技能。双鸭MAPPO合作的部分checkpoint也不等于完成训练：V97暂停且未评估，源码链接本轮404。（[TorchRL当前卡](https://huggingface.co/torchrl/microduck-skills/blob/main/README.md)；[VLA配置](https://huggingface.co/pollen-robotics/red-cube-blue-box_pi05_best/blob/eb2127a8d110d987c45c18e25d58404561ceaf55/config.json)；[合作MAPPO](https://huggingface.co/npow/microduck-coop-mappo)）

已有相似行为的项目也保留价值：不同跳跃策略可比离地高度、落地冲击和恢复，不同步态可比直行漂移/低速死区，完整碰撞单脚站可检验“穿模换来的稳定”。它们应作为同一体验下的策略对照，而不是重复扩充首页入口。作者单轮、批量、真机与代理模型的指标分别注明；例如视觉足球的98/100是真值导航基线，物理钢琴的严格全门槛仅1/64，Jenga三块PPO尚未解，均不能换成DuckKing成功率。

## 4　地面可以换外观，也可以成为真正影响动作的实验条件

当前网页默认地面来自DuckKing自己的 **Three.js浅色Plane加GridHelper**。几何接口传顶点、面、尺寸和rgba，未完整传XML纹理、UV、材质原参数；渲染器支持mesh及类型2–6的基础形状，**缺MuJoCo类型1的heightfield**。所以直接换一个MJCF并不能自动得到正确的网页地面：可能物理中有坡，画面仍覆盖平地。这个问题应先于大规模粗糙地形集成解决。（[当前几何导出](https://github.com/zhoutingunl/DuckKing/blob/9cac621484f87131b754b8e7a3303fa869af8e9c/src/duckking/model_assets.py)；[当前渲染分支](https://github.com/zhoutingunl/DuckKing/blob/9cac621484f87131b754b8e7a3303fa869af8e9c/frontend/src/physics-view.js)）

| 可选内容 | 影响层 | 现成来源与范围 | 接入意义/限制 | 证据 |
|---|---|---|---|---|
| 浅色网格／纯色无网格 | 外观 | 当前前端已有网格；纯色可作为轻量新增开关 | 适合作清楚的基线；不改碰撞或摩擦 | [现有前端](https://github.com/zhoutingunl/DuckKing/blob/9cac621484f87131b754b8e7a3303fa869af8e9c/frontend/src/physics-view.js) |
| 原生棋盘格 | 外观 | 官方/Playground scene_walk 的builtin checker、重复纹理和渐变天空 | 可程序化重建，最接近原生MuJoCo观感 | [原生XML](https://github.com/Vottivott/microduck-playground/blob/052a2494dd6372289221c7a4f24a245b443dd75f/src/mjlab_microduck/robot/microduck/scene_walk.xml) |
| 体育跑道／彩色坡道 | 外观+真实赛道 | 官方Arena course.js有赛道线、颜色与roughness | 跑道颜色只影响外观；坡角必须和物理碰撞一致 | [course.js](https://huggingface.co/spaces/pollen-robotics/microduck-arena/blob/9305b754862c56b2b2ce512c063c34600efbf932/app/src/course.js) |
| 木地板轮滑馆 | 外观+场馆 | 官方Arena roller-hall.js有程序化parquet和roughness图 | 这是官方生态现成参考，不能说Playground自带；要测手机纹理和释放 | [roller-hall.js](https://huggingface.co/spaces/pollen-robotics/microduck-arena/blob/9305b754862c56b2b2ce512c063c34600efbf932/app/src/roller-hall.js) |
| 演出舞台／观众席／灯光 | 外观+场馆 | 官方Arena talent-stage.js | 可包住现有合唱；可站区域必须有真实支撑面 | [talent-stage.js](https://huggingface.co/spaces/pollen-robotics/microduck-arena/blob/9305b754862c56b2b2ce512c063c34600efbf932/app/src/talent-stage.js) |
| 公寓／VSLAM房间 | 真实场地 | 官方默认develop的apartment、vslam_room | 适合跨房间导航、遮挡和生活任务；载入房间不等于实现SLAM | [apartment](https://github.com/pollen-robotics/microduck_rl/blob/0daab160d3fb1c2cbaba16a4a19052f36709dd9e/src/mjlab_microduck/robot/microduck/apartment.xml)、[VSLAM](https://github.com/pollen-robotics/microduck_rl/blob/0daab160d3fb1c2cbaba16a4a19052f36709dd9e/src/mjlab_microduck/robot/microduck/vslam_room.xml) |
| 低金字塔台阶 | 真实地形 | Playground rough：步高0–15mm，步宽0.15m | 与当前25mm单门槛不同；不是家居大楼梯 | [rough配置](https://github.com/Vottivott/microduck-playground/blob/052a2494dd6372289221c7a4f24a245b443dd75f/src/mjlab_microduck/tasks/microduck_velocity_env_cfg.py) |
| 随机高低格／不平路 | 真实地形 | 块宽0.45m，高差0–10mm | 显示实际块几何；不照搬训练用数百张地图 | [rough配置](https://github.com/Vottivott/microduck-playground/blob/052a2494dd6372289221c7a4f24a245b443dd75f/src/mjlab_microduck/tasks/microduck_velocity_env_cfg.py) |
| 缓坡 | 真实高度场 | rise/run .03–.10，约1.7–5.7°，1mm竖向量化 | 补高度场传输/三角化；先核验可见面与碰撞面 | [rough配置](https://github.com/Vottivott/microduck-playground/blob/052a2494dd6372289221c7a4f24a245b443dd75f/src/mjlab_microduck/tasks/microduck_velocity_env_cfg.py) |
| 轮滑长下坡 | 真实地形 | 2m入口平台→3–8m长、2–20°坡→4m出口平台 | 需专用轮滑/坡道契约和跟随相机 | [坡道生成器](https://github.com/Vottivott/microduck-playground/blob/052a2494dd6372289221c7a4f24a245b443dd75f/src/mjlab_microduck/tasks/slope_terrain.py) |
| 官方8°上坡赛道 | 真实地形+规则 | hill-climb-1m5 reference与赛制 | 和轮滑下坡分开，保留1.5m目标与实际计时 | [官方挑战](https://github.com/pollen-robotics/microduck-challenges/blob/5cee942d8b434aafd395070facb659034aac3b5e/README.md) |
| 跳台／坑底／软垫 | 真实接触 | Playground平台长跳、后空翻场景 | 软垫是数值软接触，未经真实材料校准；不能换硬地还沿用成绩 | [后空翻边界](https://github.com/Vottivott/microduck-playground/blob/052a2494dd6372289221c7a4f24a245b443dd75f/experiments/parkour/backflip/README.md) |
| 湿滑／逆风／地毯近似 | 接触或外力实验 | 社区slip/gale有模型；Carpet Lab目前无trained policy | 摩擦/外力/柔顺近似要显示参数与策略；不是换图片 | [slip](https://huggingface.co/witcheer/microduck-walk-slip)、[Carpet Lab](https://github.com/yuecui0130-create/microduck-carpet-lab) |
| 草地／水泥／沙地／冰面皮肤 | 新增外观建议 | 本轮未核实为Playground现成通用材质包 | 可以新制轻量纹理；不能凭绿色或冰面贴图推断真实材料力学 | 本报告建议，尚未实现 |

建议先做“地面外观”五选项：浅色网格、原生棋盘格、体育跑道、木地板轮滑馆、演出舞台；它们只改变显示。另设“实验场地”：平地、低台阶、不平路、缓坡、轮滑坡道、公寓，切换时重新准备物理。摩擦、外力和接触刚度作为场景参数记录，不随皮肤暗中变化。程序化纹理优先于大图/HDR；本次没有新增手机加载、帧率或显存基准，不能把“资源可复用”说成“接上便不会卡”。

## 5　一站式应保存证据和失败，而不是继续堆相似入口

每个能力族需要一条长期维护的记录：原始来源与revision、权重路径/校验和、许可、机器人与电机模型、观察/动作语义、几何和接触、上层状态机、额外硬件、当前接入与验收状态。下载到模型不算支持，61→14形状相同不算兼容，开始运行也不算完成；上游视频、保存轨迹回放、脚本编排、实时策略和灵矽实连都应在界面有清楚来源。语音应调用同一套有界动作与状态工具，支持切换模式、开始、停止和询问结果；长任务只按pending/verified实际回答。（[当前控制边界](https://github.com/zhoutingunl/DuckKing/blob/9cac621484f87131b754b8e7a3303fa869af8e9c/src/duckking/feature_catalog.py)；[工作进程](https://github.com/zhoutingunl/DuckKing/blob/9cac621484f87131b754b8e7a3303fa869af8e9c/src/duckking/feature_worker.py)）

下表是本报告使用的准备程度，而非自动化“分数”。公开资产齐全的项目进入适配，源代码研究保留在实验区，许可或硬件有缺口的项目保留待解条件；不会因为未能马上上线就从清单删掉。

| 准备程度 | 能确认什么 | 下一步 |
|---|---|---|
| 公开策略+可读场景/契约 | 已查到权重文件、配置和源代码，不代表本项目已成功 | 锁定revision、复刻物理与控制契约，CPU基线、取消/失败验收，再做语音 |
| 有权重但源码/许可/硬件待解 | 存在可下载文件或媒体，尚不能保证可复用 | 补来源与许可；核验机器人模型、附加机构、动作限位和推理负载 |
| 只有训练代码或未完成研究 | 可以研究和续训，但没有可靠成品行为 | 建立可见环境和官方基线，明确CPU/GPU预算，展示真实学习曲线 |
| 编排/代理/回放 | 有产品体验或教学价值，但行为不全由新策略产生 | 原样标注控制来源；真值、weld、mocap、触发脚本与像素输入分别写清 |
| 已接入但验收欠缺 | 例如当前秋千/三鸭跳绳 | 继续修复接触与几何条件；不得用上游成功计数覆盖本轮失败 |

真正的一站式窗口可以让用户看到同一只鸭在不同环境、规则和策略下的差异：先由一句话触发，再看物理发生了什么、为何成功或失败。完整性来自每个来源都能查到处理结果；不是宣称所有公开项目都已移植，也不是把未完成研究藏起来。

## 附录A　注册表44项逐条核销

此表保留注册表全部44行，避免按主题合并后再次漏项。ONNX数量是本轮源树/文件元数据中的文件数，**不是独立技能数或可运行验收数**。GitHub树内没有ONNX，也不代表外部HF没有权重。许可列仅陈述本轮查到的仓库/模型卡信息，重分发还需逐资产核实；“未明确”不能从母项目许可推定。

| # | 注册条目 / 固定版本 | 源树ONNX数 | 许可证据 | DuckKing覆盖与后续处理 |
|---|---|---|---|---|
| 1 | [Lulzx/microduck-backflip](https://github.com/Lulzx/microduck-backflip/tree/8bde27eb141c8f14db05fc4370e536521203a98d) | 1 | Apache-2.0 | 缺：平地后空翻；与Playground高台后空翻不同；独立后空翻候选；需按本模型重新做着陆验收 |
| 2 | [selinayfilizp/microduck-courier](https://github.com/selinayfilizp/microduck-courier/tree/5764c5497f756f2a924a88aec9ba01abba0739c6) | 4 | Apache-2.0 | 部分：有脚本嘴夹取/搬运，无其学习版公寓送书；可用作学习版搬运与现有脚本对照 |
| 3 | [Liyucheng1997/318_lab-microduck-simulator](https://github.com/Liyucheng1997/318_lab-microduck-simulator/tree/512d4bec6fc3ba321d29c93312be72856ad21268) | 10 | 本轮未见明确顶层许可 | 相近：已有happy-hop；未接其跳跃策略；对照候选，非首要新增能力 |
| 4 | [pezzonovante7/microduck-sidekick-dance](https://github.com/pezzonovante7/microduck-sidekick-dance/tree/02c5d96704d3ac266acb29fbb29957335ee680bc) | 0 | 本轮未见明确顶层许可 | 缺：lateral sidekick 舞步；只有任务代码，无已训练模型，不能直接交付 |
| 5 | [bihaokun/microduck-step-up-policy](https://github.com/bihaokun/microduck-step-up-policy/tree/ec769571438c2558a2d847a164a91022971fceb0) | 2 | Apache-2.0 | 已接：25mm step-up pair；保留现有接入与实测，不重复实现 |
| 6 | [ThomasBurgess2000/microduck-max-height-jump](https://github.com/ThomasBurgess2000/microduck-max-height-jump/tree/7e5dc6028900f13d145e6710847378b007a675e9) | 2 | Apache-2.0 | 相近：有hop；无该策略和高度指标；作为跳跃对照，需落地冲击验收 |
| 7 | [alertform/microduck-walking](https://github.com/alertform/microduck-walking/tree/eebef0d7177fa37d39efe6fdc723ae7ba20cc109) | 0 | Apache-2.0 | 相近：有步态；无其yaw消融评测；步态质量评测，不算新动作 |
| 8 | [ros-claw/microduck](https://github.com/ros-claw/microduck/tree/1034ed000c352476cf213ebe1544eb8c7db8b0e7) | 8 | Apache-2.0 | 已接但未通过完整物理验收：三鸭跳绳；继续完成真实接触验收 |
| 9 | [RemiFabre/microduck-flamingo-cycle](https://huggingface.co/RemiFabre/microduck-flamingo-cycle/tree/a69e4f6103a70e355983eb5d4e919da76778a40f) | 1 | apache-2.0 | 已接：flamingo-cycle；保留，非新增 |
| 10 | [fffiloni/microduck-polite-bow-b1d864](https://huggingface.co/fffiloni/microduck-polite-bow-b1d864/tree/9a9d21a85cf7b5cbd1854c03ad58bd949502a5ea) | 1 | 本轮未见明确顶层许可 | 缺：学习版鞠躬；有policy.onnx；许可元数据未明确，待澄清 |
| 11 | [fffiloni/microduck-moonwalk-backward-55e6af](https://huggingface.co/fffiloni/microduck-moonwalk-backward-55e6af/tree/951073cb7791a898e3e5ecb242c5bcccf40aa72f) | 1 | 本轮未见明确顶层许可 | 缺：月步；普通后退不等价；有policy.onnx；许可元数据未明确，待澄清 |
| 12 | [torchrl/microduck-skills](https://huggingface.co/torchrl/microduck-skills/tree/d6766234b24bf9cff6a6a8c55011a4584a8995d5) | 0 | 本轮未见明确顶层许可 | 相近基础动作；缺九技能prior/football selector；现卡已九技能，ckpt而非ONNX；需要TorchRL适配 |
| 13 | [HannesVonEssen/microduck-basketball](https://huggingface.co/HannesVonEssen/microduck-basketball/tree/6e61a733aeff338bdd352148819bc99cf9a51491) | 1 | Apache-2.0（模型元数据） | 已接盲平衡/滚动；需保持LSTM契约 |
| 14 | [HannesVonEssen/microduck-swing](https://huggingface.co/HannesVonEssen/microduck-swing/tree/e7a603fa89a74b589608c5a026a7720339cb22e0) | 1 | Apache-2.0（模型元数据） | 已有适配，绳长完整验收未通过 |
| 15 | [HannesVonEssen/microduck-stilts](https://huggingface.co/HannesVonEssen/microduck-stilts/tree/371b7e0a8843d215afa768439b9e6ceab6248979) | 9 | Apache-2.0（模型元数据） | 八档高度专用策略；尚未接入，根文件/各高度文件不能当九个技能 |
| 16 | [HannesVonEssen/microduck-running](https://huggingface.co/HannesVonEssen/microduck-running/tree/9f45af1f4b04252f3aa1f4c056fa7fa0d4b35e4c) | 3 | Apache-2.0（模型元数据） | 已接当前快跑；root/lineage/legacy是版本 |
| 17 | [HannesVonEssen/microduck-climb](https://huggingface.co/HannesVonEssen/microduck-climb/tree/15723878fa5cc31e326ce522ab16e25d5142632e) | 3 | Apache-2.0（模型元数据） | 爬梯/恢复两模型及policy别名；尚未接入；烟囱另见正文 |
| 18 | [HannesVonEssen/microduck-backflip](https://huggingface.co/HannesVonEssen/microduck-backflip/tree/0aff1c74c8ad3953f331193a5a671257ef5aab37) | 1 | Apache-2.0（模型元数据） | 高台软垫后空翻尚未接入；长跳是另一发布模型 |
| 19 | [joanfox/microduck-happy-hop](https://huggingface.co/joanfox/microduck-happy-hop/tree/c0447da668255436eea070e862ad8eb89bad2ba1) | 1 | apache-2.0 | 已接：happy-hop；保留 |
| 20 | [llama/microduck-beak-throw](https://github.com/llama/microduck-beak-throw/tree/410ed2249d62cd7aa4c642cd2c4e9b56f9a0cbfd) | 0 | Apache-2.0 | 缺：嘴抛球；q2p发布权重；jaw独立时序和动作clamp必需 |
| 21 | [zhoumiaosen/microduck-rl](https://github.com/zhoumiaosen/microduck-rl/tree/750feb171b3a7b09e61fc01feea58c98a294b2e2) | 0 | Apache-2.0 | 相近：已有快跑，缺heading-hold直跑；可作为“跑得快/跑得直”对照 |
| 22 | [RemiFabre/microduck-rough-walk-e](https://huggingface.co/RemiFabre/microduck-rough-walk-e/tree/fa7b27eeb5610d3b351362f4bd71691ee8be3d7d) | 1 | apache-2.0 | 缺：rough terrain policy及场地；适合低台阶/碎石/缓坡对照 |
| 23 | [Teethyfish/microduck-collision-flamingo-ii](https://huggingface.co/Teethyfish/microduck-collision-flamingo-ii/tree/03942487841d384c82de05ebcc975bbfc7863ed1) | 1 | apache-2.0 | 相近：已有单脚站，缺完整外壳碰撞版本；实验对照，play和ONNXviewer结果不一致 |
| 24 | [chenp9527/microduck-jump](https://github.com/chenp9527/microduck-jump/tree/ace589eadd1be6aed4e39a27d8bd8e275b2b9cfe) | 1 | Apache-2.0 | 相近：已有hop，缺3–6cm目标与冲击指标；128N落地峰值未达40N门槛，不列稳定交付 |
| 25 | [QingMuLYL/microduck-standup](https://huggingface.co/QingMuLYL/microduck-standup/tree/7f8d01e9aae4ab005b8685677f16df1710d81bd8) | 1 | 本轮未见明确顶层许可 | 部分：步态可含恢复，无独立6s起身演示；导出自dirty checkout，需固定来源和许可 |
| 26 | [kramp/microduck-groove](https://huggingface.co/kramp/microduck-groove/tree/b94e53dfad4c277c48447d44c6b8c014820fcc89) | 1 | 本轮未见明确顶层许可 | 缺：学习版原地groove；126BPM而非目标100；缺许可元数据 |
| 27 | [drfonz-indigo/microduck-playdead](https://huggingface.co/drfonz-indigo/microduck-playdead/tree/7b49a6a70e781096c6a39fc3ce5cea25307e8565) | 1 | 本轮未见明确顶层许可 | 缺：装死后仰躺，再自起；5s episodic，需后续恢复及嘴部独立控制；缺许可元数据 |
| 28 | [cetiennec/microduck-on-sourccey-dome](https://huggingface.co/cetiennec/microduck-on-sourccey-dome/tree/d5e1ee4be90c1635f2d8b51ed2ef4c30ffd1e7c7) | 1 | 本轮未见明确顶层许可 | 缺：站在运动Sourccey穹顶上；需穹顶/移动底盘和低通/standing gain契约 |
| 29 | [Kyry10/microduck-arena-lab](https://huggingface.co/Kyry10/microduck-arena-lab/tree/dc9a7f892e014b6241b5ed2c398958e507cddfa7) | 5 | apache-2.0 | 相近：有快跑，缺受控竞速/坡道跑；可作为赛道公平对比，非全新动作 |
| 30 | [zachgarner/microduck-headstand](https://github.com/zachgarner/microduck-headstand/tree/ffc7148033e18a381395d8398bdfc96b702d7ba7) | 0 | 本轮未见明确顶层许可 | 缺：六策略串联倒立杂技；发布权重在HF；GitHub未见LICENSE，不可假定Apache |
| 31 | [toyhank/microduck-vision-soccer](https://github.com/toyhank/microduck-vision-soccer/tree/23cdfbce04083ff1883a2d6ceb7bb3b6b49e15c0) | 4 | NOASSERTION，需逐包核验 | 部分：有RGB找球踢球，无守门员比赛；增加射门/守门员状态机；98/100是GT基线 |
| 32 | [AungKaung1928/microduck-rl](https://github.com/AungKaung1928/microduck-rl/tree/3c25076a897daa4b202e60b776c37d4adf28c2f6) | 1 | MIT | 相近：已有PPO平衡，无其模型/CPU训练比较；训练方法和失败分析对照，不算独立新动作 |
| 33 | [KhushiJ2911/microduck-piano-learning](https://github.com/KhushiJ2911/microduck-piano-learning/tree/1692d4432c9a3833288b2aa763380d9cdeffdd62) | 2 | Apache-2.0 | 缺：双鸭踩物理钢琴键；有ONNX；1/64严格验收，实验而非任意乐曲演奏 |
| 34 | [langli11/microduck-tricks](https://huggingface.co/langli11/microduck-tricks/tree/ae7284e0dc54e6ae10e5f099f4a4d3b93aed7158) | 3 | apache-2.0 | 缺：助跑前滚翻/绕锥轮滑/短单脚滑；三套ONNX；持续长单脚滑未达标 |
| 35 | [hikarioyama/microduck-onefoot-skate](https://github.com/hikarioyama/microduck-onefoot-skate/tree/88025aab8dd1d8cb5559cf4cd31495f529a659ec) | 4 | Apache-2.0 | 缺：持续单脚轮滑；1/64达2秒；研究快照，不列稳定技能 |
| 36 | [pngwn/microduck-detector](https://huggingface.co/pngwn/microduck-detector/tree/356b98b671cc953a3cc4ccf8c8625e7315322acc) | 0 | 本轮未见明确顶层许可 | 部分：几何/颜色感知，未接YOLO鸭检测；感知模型，不是运动策略；先做像素发现同伴对照 |
| 37 | [Datawhale/Microduck-RL-4096x6000](https://huggingface.co/Datawhale/Microduck-RL-4096x6000/tree/c1cbc1a2f2255744225c20bb4cd16604c0f989f3) | 1 | other | 相近：已有步态/踢球，无该复现checkpoint；训练复现对照；无独立新增技能 |
| 38 | [wat-bill/microduck-action-pack](https://github.com/wat-bill/microduck-action-pack/tree/d3c78db49236e27608b49fb09db8ace23444954e) | 1 | Apache-2.0 | 相近：已有编排头部舞蹈，无其任务包；可复用动作调度，不声称新的RL能力 |
| 39 | [apirrone/microduck-footsteps](https://huggingface.co/apirrone/microduck-footsteps/tree/19c38fae6afabddf9c0821009028d0a37963f05f) | 2 | apache-2.0 | 已接：Footsteps + FootstepNet；保留 |
| 40 | [RemiFabre/microduck-static-grasp](https://huggingface.co/RemiFabre/microduck-static-grasp/tree/df50e6eddbbcbd05975b9308abd4b4e47c5e6960) | 1 | apache-2.0 | 部分：有嘴搬运，无低位static-grasp；新发布pick网络+jaw时序+runtime补丁；非单换ONNX |
| 41 | [witcheer/microduck-walk-flat](https://huggingface.co/witcheer/microduck-walk-flat/tree/3c1d91aabfc6fc05220b5cc838f88890ad96fbd4) | 1 | apache-2.0 | 缺：terrain walk family；rough/slope/step/stairs/slip/gale/recover，不应只列flat一项 |
| 42 | [witcheer/microduck-standup](https://huggingface.co/witcheer/microduck-standup/tree/3132d647121421adcd6d1cb9228ded4d210ae483) | 1 | apache-2.0 | 部分：有起身/前滚翻/踢球等效功能，缺该家族及巨球；300mm巨球踢球是明确新增；普通小球踢不覆盖 |
| 43 | [mindthink/microduck-policies-repro](https://huggingface.co/mindthink/microduck-policies-repro/tree/425396c6523a2dea6e781c7c32fefc6464f63103) | 4 | apache-2.0 | 相近：已有官方步态，无该复现修正；低速死区/质量对比工具，不算新动作 |
| 44 | [thejerrycheng/microduck_replication_feetech](https://github.com/thejerrycheng/microduck_replication_feetech/tree/cf45408dddfebb1d3a4432edd3e847de0ede58f4) | 25 | MIT | 不适配当前XL330硬件模型：HD1910 replica；需Feetech BAM和模型，不能直接装在当前鸭上 |

附录同时说明了不应重复实施的部分：happy-hop、flamingo、25mm step-up、Footsteps已有接入；跳绳虽已有适配但未完成严格物理验收。源码复现、硬件移植和控制面板仍在原目录可追溯，不能为了让报告变短就把它们说成“长尾无价值”。（[44条原始注册表](https://github.com/joeynyc/awesome-microduck/blob/9cfa5abca6f143b8af0048aeb6004dc5e67f81e8/policies.json)；[README目录](https://github.com/joeynyc/awesome-microduck/blob/9cfa5abca6f143b8af0048aeb6004dc5e67f81e8/readme.md)）

## 附录B　核对范围、版本和仍未完成的验证

| 范围 | 本轮实际完成 | 不能推导的结论 |
|---|---|---|
| 官方GitHub/HF | 13个RL家族、33个声明ID；10个通用ONNX；6项活动与5个独立reference模型；官方组织API返回24个模型库/55个Space，详查6个MicroDuck Space | 24个模型库不是24种MicroDuck动作；未运行全部权重 |
| Playground整仓 | 固定main 052a249；1023文件、49份相关MD；46声明ID含17Backlash；8个链接HF发布库逐一查metadata | 含历史源码、变体和子阶段；不代表46个成品技能 |
| awesome机器注册表 | 固定9cfa5abc；44行全部映射 | registry描述也有滞后，已对模型卡交叉检查 |
| awesome README社区链出 | 313条README目录项；207个非官方/非Playground/非DuckKing GitHub仓库尝试，206份primary README取得；29个重点树检查、27成功 | 不是206个全都深查每个文件或已经验收的项目 |
| HF公共模型搜索 | search=microduck完整next分页结束：1191条metadata、2页；65份详细模型卡；额外33个新颖名称卡均取得 | 没有逐份读取/运行全部1191权重；不能宣称未详查长尾没有增量 |
| 社区HF Space | 23个非官方Space，21套metadata+README取得 | 没有逐一运行浏览器，不把卡片可读当可用性验收 |
| 当前DuckKing | 9cac621 feature分支，18功能入口及旧页面/PPO源码对照 | 本次未确认main/公网升级，也未重跑所有既有场景 |

检索入口为 [awesome固定版本](https://github.com/joeynyc/awesome-microduck/blob/9cfa5abca6f143b8af0048aeb6004dc5e67f81e8/readme.md)、[HF模型分页API](https://huggingface.co/api/models?search=microduck&limit=1000&full=true)、[官方模型API](https://huggingface.co/api/models?author=pollen-robotics&limit=100&full=true) 与 [官方Space API](https://huggingface.co/api/spaces?author=pollen-robotics&limit=100)；这是本轮留存的检索快照计数，之后页面更新可能变化。本轮不可读的源包括 Harboria/harboria、npow/microduck-coop及尝试的Raghav GitHub路径；两个社区Space未完整取得metadata/README，不能补造其能力。

| 来源 | 本轮固定版本 | 核对入口 |
|---|---|---|
| 官方robotd/文档 | `15dae7f1df8182584f432361fbbb4af0e8bfb1c7` | [源码/资产](https://github.com/pollen-robotics/microduck/tree/15dae7f1df8182584f432361fbbb4af0e8bfb1c7) |
| 官方RL默认develop | `0daab160d3fb1c2cbaba16a4a19052f36709dd9e` | [源码/资产](https://github.com/pollen-robotics/microduck_rl/tree/0daab160d3fb1c2cbaba16a4a19052f36709dd9e) |
| 官方RL main | `1e79c29c97d8b38aee9eefde77a545860ba7658e` | [源码/资产](https://github.com/pollen-robotics/microduck_rl/tree/1e79c29c97d8b38aee9eefde77a545860ba7658e) |
| 官方通用策略 | `236d1835b03ac7b45d962efbf2fe3a6940206112` | [源码/资产](https://huggingface.co/pollen-robotics/microduck-policies/tree/236d1835b03ac7b45d962efbf2fe3a6940206112) |
| Arena | `9305b754862c56b2b2ce512c063c34600efbf932` | [源码/资产](https://huggingface.co/spaces/pollen-robotics/microduck-arena/tree/9305b754862c56b2b2ce512c063c34600efbf932) |
| Playground | `052a2494dd6372289221c7a4f24a245b443dd75f` | [源码/资产](https://github.com/Vottivott/microduck-playground/tree/052a2494dd6372289221c7a4f24a245b443dd75f) |
| awesome registry | `9cfa5abca6f143b8af0048aeb6004dc5e67f81e8` | [源码/资产](https://github.com/joeynyc/awesome-microduck/tree/9cfa5abca6f143b8af0048aeb6004dc5e67f81e8) |
| DuckKing对照 | `9cac621484f87131b754b8e7a3303fa869af8e9c` | [源码/资产](https://github.com/zhoutingunl/DuckKing/tree/9cac621484f87131b754b8e7a3303fa869af8e9c) |

这次纠正的关键结论是：官方自起已有ONNX；Arena有六个活动；TorchRL主卡已从七技能描述更新到九技能prior；HF长尾确实还有新方向；地面不止默认空地，但外观、几何、接触模型必须分别接入。静态审计不能给出DuckKing新增场景成功率、跨CPU/GPU一致性、手机性能、真实灵矽语言效果或实体安全结论。公共搜索也不能保证覆盖私库、已删除项目或未标MicroDuck的实现；完整的意思是对所声明的公开来源范围逐项核对并保留未知项，而不是声称穷尽互联网。
