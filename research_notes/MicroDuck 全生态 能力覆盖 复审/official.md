# 官方 MicroDuck 全生态与 DuckKing 缺口审计

> 静态来源审计保留当时 `9cac621` 基线。当前41项实现与未移植范围见 [施工核销](../../docs/SCENE_DISCOVERY_ROLLOUT.md)。原始第三方抓取缓存未入库，保留在本地 `.duckking/`。

## 官方训练任务、发布策略和当前工程究竟覆盖了什么

### Takeaway

检索日期为 **2026-11-13（Asia/Shanghai）**。独立核对官方 GitHub 当前分支、完整文件树、HF 官方组织模型/Space 元数据和具体源文件，未以旧报告为结论。官方常规 RL 是 **13 个任务家族、33 个注册 ID（18 个普通 Flat/Rough ID 加 15 个 Backlash ID）**；这些数量不能当作 33 个独立成品技能。DuckKing 已有多数基础能力，但仍缺显式自起、轮滑下坡、轮上自起、轮上旋转、粗糙地形试验及官方场景载入；不能再说“StandUp 没有官方 ONNX”。 [官方注册源](https://github.com/pollen-robotics/microduck_rl/blob/0daab160d3fb1c2cbaba16a4a19052f36709dd9e/src/mjlab_microduck/tasks/__init__.py) [当前 DuckKing 控制器](https://github.com/zhoutingunl/DuckKing/blob/9cac621484f87131b754b8e7a3303fa869af8e9c/src/duckking/simulation.py)

### Cited Findings

**审计边界与版本。** `microduck` main 为 `15dae7f1df8182584f432361fbbb4af0e8bfb1c7`；`microduck_rl` 默认分支 develop 为 `0daab160d3fb1c2cbaba16a4a19052f36709dd9e`，main 为 `1e79c29c97d8b38aee9eefde77a545860ba7658e`；两分支注册任务 ID 集合相同，但资产不相同：本次 main 固定提交下直接取 apartment.xml / vslam_room.xml 返回缺失，而 develop 完整文件树有这两个文件，并成功读取；环境清单应以默认 develop 为准，不应只读 main。官方 HF 组织 API 返回 **24 个模型仓库、55 个 Space**，其中此次逐项详查 **6 个 MicroDuck Space**（simulator、arena、console、vision-demo、policy-playground、vetbook）与下列相关模型；24 并非“24 个 MicroDuck 模型”。本地保留原始元数据与文件树在 `.duckking/official-audit-20261113/`。 [官方 runtime](https://github.com/pollen-robotics/microduck/tree/15dae7f1df8182584f432361fbbb4af0e8bfb1c7) [默认训练分支](https://github.com/pollen-robotics/microduck_rl/tree/0daab160d3fb1c2cbaba16a4a19052f36709dd9e) [官方模型 API](https://huggingface.co/api/models?author=pollen-robotics&limit=100&full=true) [官方 Space API](https://huggingface.co/api/spaces?author=pollen-robotics&limit=100)

**官方策略确有 10 个 ONNX 文件。** `microduck-policies` revision `236d1835b03ac7b45d962efbf2fe3a6940206112` 的文件清单包含 `alpha_ground_pick`、`alpha_sitstand`、`alpha_stand`、`alpha_walking`、左右 `ball_kick`、`roller`、`roller_crouch`、`roulade`、`velstand`。其中 **alpha_stand 是现成恢复策略**；当前 DuckKing 常规后端只注册 8 个 session，没有独立 alpha_stand/alpha_walking session，但其步态使用 velstand。资源存在不等于当前界面有明确可验收的翻倒恢复节目。 [固定 HF 文件列表](https://huggingface.co/pollen-robotics/microduck-policies/tree/236d1835b03ac7b45d962efbf2fe3a6940206112) [DuckKing session 表](https://github.com/zhoutingunl/DuckKing/blob/9cac621484f87131b754b8e7a3303fa869af8e9c/src/duckking/simulation.py#L129)

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

上表任务定义来源统一为 [官方 RL Tasks](https://github.com/pollen-robotics/microduck_rl/blob/0daab160d3fb1c2cbaba16a4a19052f36709dd9e/README.md#tasks)、[注册代码](https://github.com/pollen-robotics/microduck_rl/blob/0daab160d3fb1c2cbaba16a4a19052f36709dd9e/src/mjlab_microduck/tasks/__init__.py)，当前工程映射来源为 [运动动作白名单](https://github.com/zhoutingunl/DuckKing/blob/9cac621484f87131b754b8e7a3303fa869af8e9c/src/duckking/motion.py)、[仿真控制器](https://github.com/zhoutingunl/DuckKing/blob/9cac621484f87131b754b8e7a3303fa869af8e9c/src/duckking/simulation.py)、[18 项功能目录](https://github.com/zhoutingunl/DuckKing/blob/9cac621484f87131b754b8e7a3303fa869af8e9c/src/duckking/feature_catalog.py)。以上是静态源码映射，未在本次重新跑全部动作。

**不要遗漏 runtime 层可做成体验的能力。** 官方机器人已有抬起检测、自动待机看头、摸头声音反馈、个体声线、chorale、ToF theremin、激光点跟随、相机鸭检测及 8×8 ToF 面板等，不都属于 PPO 动作。[官方完整操作手册](https://github.com/pollen-robotics/microduck/blob/15dae7f1df8182584f432361fbbb4af0e8bfb1c7/docs/robot/cheatsheet.md)

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

来源分别见 [picked_up / laser / voice / ToF 操作手册](https://github.com/pollen-robotics/microduck/blob/15dae7f1df8182584f432361fbbb4af0e8bfb1c7/docs/robot/cheatsheet.md)、[独立鸭检测模型](https://huggingface.co/pollen-robotics/microduck-duck-detector/tree/da261782ed87dbc465e67d46a5ec86ed31fc807f)、[官方多机仿真与相机](https://github.com/pollen-robotics/microduck/blob/15dae7f1df8182584f432361fbbb4af0e8bfb1c7/docs/robot/simulation.md)、[Vetbook 源码说明](https://github.com/pollen-robotics/microduck/blob/15dae7f1df8182584f432361fbbb4af0e8bfb1c7/spaces/vetbook/README.md)。

### Inferences

- P0 可交付顺序建议：显式摔倒恢复 → 激光点跟随/深度矩阵 → 官方 apartment 场地 → 下述拔河与红灯停。它们给用户新的交互闭环，而非再多一个前进按钮。依据上述公开资源与当前缺口做工程判断，未声称已移植成功。
- 轮上站起、Spin、Swizzle 的“有环境”与“有可锁定成品权重”必须分列；不宜直接把所有训练注册 ID 做成可点成功的卡片。

### Gaps

- 本次仅核实权重文件存在、manifest/源码和静态接口；未下载所有大权重、执行全部 ONNX，未做 Linux/Mac 物理一致性、真实灵矽或实体机器人验证。
- 未核实独立 RollerSlope / RollerStandUp / Spin / Swizzle 成品 checkpoint 的可再发布版本；当前官方通用模型仓库没有对应同名文件，不代表整个互联网绝无社区导出。
- 未核实当前手机触摸头部能否合理触发与真机 pet classifier 一致的语义；不能据此宣称仿真有麦克风硬件。

## 还有哪些官方项目和现成场景此前被漏掉

### Takeaway

最大的漏项不是 Playground 之外又几段动作视频，而是 **官方 microduck-challenges / Arena 的完整游戏规则与可重放物理实现**。当前是 **6 个活动**，旧的“四项”说法不完整。尤其是双鸭拔河和红灯停偷袜子，现有 DuckKing 没有同等规则体验；它们都有公开源码，拔河参考 ONNX 直接在 Arena 资产内，偷袜子有官方独立 reference 模型。[六活动 README](https://github.com/pollen-robotics/microduck-challenges/blob/5cee942d8b434aafd395070facb659034aac3b5e/README.md) [Arena 固定源](https://huggingface.co/spaces/pollen-robotics/microduck-arena/tree/9305b754862c56b2b2ce512c063c34600efbf932)

### Cited Findings

`microduck-challenges` main `5cee942d8b434aafd395070facb659034aac3b5e` 每个活动都有训练环境、参数与检查脚本。训练需 NVIDIA GPU 或 HF Jobs，**已有权重的 CPU 推理/评分与重新训练是两件事**。Arena 服务端使用固定种子、速度扫描评分，Mac 与其 Linux x86 结果可能分歧；网页可以体验但不能偷换为可比官方榜单分数。[官方挑战仓库](https://github.com/pollen-robotics/microduck-challenges/tree/5cee942d8b434aafd395070facb659034aac3b5e) [Arena 运行与复现说明](https://huggingface.co/spaces/pollen-robotics/microduck-arena/blob/9305b754862c56b2b2ce512c063c34600efbf932/README.md)

| 活动 | 真实玩法 / 成品资源 | DuckKing 差距 |
|---|---|---|
| sprint-2m | 2 m 竞速；官方 reference ONNX | 有快跑但无同一跑道/计时/多种子成绩；可做 2 鸭竞速 |
| roller-sprint-2m | 轮滑 2 m 竞速；独立 reference ONNX | 有轮滑但无竞赛赛制 |
| hill-climb-1m5 | 1.5 m、8° 上坡；独立 reference ONNX | 真实上坡体验尚缺，与 Playground 下坡区分 |
| got-a-talent | 20 s 舞台，timeline 控坐姿/头部/嘎声/曲谱；最多 8 鸭、各自策略和布局，观众投票 | 当前四鸭导演/剧场有重合；值得吸收为可编辑编排与用户作品，而非再加一个固定节目 |
| tug-of-war | 两鸭颈部连 1 m 绳，在 3 m 擂台上向后拉；跌入坑或中线判胜，45 s 回合 | **高价值缺口**。绳是颈部连接，并非嘴夹绳；代码和 `arena/assets/policies/tug-reference-t20-500.onnx` 都存在 |
| sock-heist-6m | 6 m 偷袜子；巨鸭转头红灯时要停，超过 3 cm 容差会被抓；reference ONNX | **高价值缺口**。actor 看到的是变成零的指令，不是从图像识别巨鸭；赛道另有中心线转向辅助，需在演示中说明 |

规则引用 [6 个活动源目录](https://huggingface.co/spaces/pollen-robotics/microduck-arena/tree/9305b754862c56b2b2ce512c063c34600efbf932/arena/events)；具体拔河权重 [固定 ONNX](https://huggingface.co/spaces/pollen-robotics/microduck-arena/resolve/9305b754862c56b2b2ce512c063c34600efbf932/arena/assets/policies/tug-reference-t20-500.onnx)，规则 [tug-of-war.toml](https://huggingface.co/spaces/pollen-robotics/microduck-arena/blob/9305b754862c56b2b2ce512c063c34600efbf932/arena/events/tug-of-war.toml)、[sock-heist-6m.toml](https://huggingface.co/spaces/pollen-robotics/microduck-arena/blob/9305b754862c56b2b2ce512c063c34600efbf932/arena/events/sock-heist-6m.toml)、[got-a-talent.toml](https://huggingface.co/spaces/pollen-robotics/microduck-arena/blob/9305b754862c56b2b2ce512c063c34600efbf932/arena/events/got-a-talent.toml)。

已逐一核实以下参考模型既有 `policy.onnx` 又有 `checkpoint.pt` 和 `manifest.json`：

| 官方模型 | 固定 revision |
|---|---|
| [sprint-2m](https://huggingface.co/pollen-robotics/microduck-sprint-2m-reference/tree/62afcc461f1d4a5ac22bfbff55ce4900c1afba32) | `62afcc461f1d4a5ac22bfbff55ce4900c1afba32` |
| [roller-sprint-2m](https://huggingface.co/pollen-robotics/microduck-roller-sprint-2m-reference/tree/c72fb92594e8b415487e87dfeed509141afc5e25) | `c72fb92594e8b415487e87dfeed509141afc5e25` |
| [hill-climb-1m5](https://huggingface.co/pollen-robotics/microduck-hill-climb-1m5-reference/tree/d319208d92896353f581be754f6325d01f5e3732) | `d319208d92896353f581be754f6325d01f5e3732` |
| [got-a-talent](https://huggingface.co/pollen-robotics/microduck-got-a-talent-reference/tree/0454fe8a848526338ba6edf72b8358fbf51d6b21) | `0454fe8a848526338ba6edf72b8358fbf51d6b21` |
| [sock-heist-6m](https://huggingface.co/pollen-robotics/microduck-sock-heist-6m-reference/tree/ee81c1368572753528c01ee493c938c6aaac3ed0) | `ee81c1368572753528c01ee493c938c6aaac3ed0` |

**其余官方项目要区分“借鉴体验”和“新的机器人技能”。**

- 官方 `microduck-simulator` revision `efedf47f4d4ae52d17ad2e108a5b8795d41537a3` 是浏览器 WASM MuJoCo + ONNX，支持脚/轮切换、手柄/触控、追随相机、围栏球场和多人“幽灵”。幽灵广播各自鸭/球的姿态，**不是共享物理互相碰撞**。DuckKing 已有真共享物理双鸭，不能把幽灵算作更强物理交互。其街机、音箱、CRT、飞镖盘、熔岩灯、游戏机、滑板、鞋、随身听 GLB 可作场景外观参考，**有滑板模型不代表训练了滑板技能**。[Space README](https://huggingface.co/spaces/pollen-robotics/microduck-simulator/blob/efedf47f4d4ae52d17ad2e108a5b8795d41537a3/README.md) [道具目录](https://huggingface.co/spaces/pollen-robotics/microduck-simulator/tree/efedf47f4d4ae52d17ad2e108a5b8795d41537a3/app/public/assets/props)
- `microduck-policy-playground` 是连接实体鸭、从 HF 下载策略并运行的图库，不是独立的 MuJoCo 演示集合；适合借鉴来源、兼容性与安装状态提示。[源码说明](https://github.com/pollen-robotics/microduck/blob/15dae7f1df8182584f432361fbbb4af0e8bfb1c7/spaces/policy-playground/README.md)
- `microduck-vision-demo` 接实际相机 H.264/JPEG，再用 OpenCV 处理；不是预先验证所有视觉行为的导航策略库。可借鉴相机管线，不能把网页滤镜卡当作新 RL 技能。[源码说明](https://github.com/pollen-robotics/microduck/blob/15dae7f1df8182584f432361fbbb4af0e8bfb1c7/spaces/vision-demo/README.md)
- `microduck-console` 是实体/仿真 robotd 控制界面；`microduck-vetbook` 是成长档案分享，均是周边产品能力，不能计为新增动作。[官方 Space 列表](https://huggingface.co/api/spaces?author=pollen-robotics&limit=100) [Vetbook 文档](https://github.com/pollen-robotics/microduck/blob/15dae7f1df8182584f432361fbbb4af0e8bfb1c7/spaces/vetbook/README.md)
- 官方 `red-cube-blue-box` 的 pi05/diffusion 确有 safetensors，但核实 config 后是 **RGB + 2 维 state → 11 维 action，device=cuda**，不是 61→14 ONNX。模型卡没有给出它和 MicroDuck 身体/嘴部的完整控制映射；暂应列“需要核实的视觉操作研究”，**不应当作可直接接入的 MicroDuck 已验证技能**。[pi05 配置](https://huggingface.co/pollen-robotics/red-cube-blue-box_pi05_best/blob/eb2127a8d110d987c45c18e25d58404561ceaf55/config.json) [diffusion 配置](https://huggingface.co/pollen-robotics/red-cube-blue-box-30fps_diffusion-best/blob/710824c83f212c069a8be9ce450f726897e2d420/config.json)

### Inferences

- 双鸭拔河可直接服务“语音+物理因果”的产品目标，优先于重复竞速按钮；红灯停游戏适合用户语音当裁判或与策略 PK。需要保留训练/评分规则，并验证停止、坑底接触与超时。
- 八鸭舞台应作为现有演示编排器扩展：用户布置、选择技能、安排音轨、导出作品；不应把扩大数量简单计为八种新技能。
- Arena 的可重放回合、五种子评分、成绩和录制机制适合后续奖励函数 PK 产品；训练仍需独立算力和资源隔离。

### Gaps

- 没有在本次运行拔河/偷袜子或下载所有 reference 权重；“资源齐全”的证据来自源文件和元数据，不能转述为 DuckKing 已集成或已验收。
- 参考模型的独立模型卡未必都有清晰 license 字段，落地时须逐包核实许可/NOTICE，不仅沿用源码仓库许可。
- VLA 数据/动作映射未核实，不能推断真实 11 维动作意义；也没有做 NPU/CPU 可用性测试。

## 地面外观、真实地形和环境还有哪些可选

### Takeaway

当前 DuckKing 浏览器自己创建统一浅色 `PlaneGeometry` 加网格，没有把所有 MJCF 纹理/场地主题自动带到 Three.js。因此“可以换地面”至少有三类：只换外观、换实际几何、换接触物理。官方生态已存在棋盘格、体育跑道/坡道、轮滑馆和舞台等视觉参考，以及公寓、VSLAM 房间、低台阶/不平路/缓坡等真实场地；不必始终使用默认空地。[当前前端](https://github.com/zhoutingunl/DuckKing/blob/9cac621484f87131b754b8e7a3303fa869af8e9c/frontend/src/physics-view.js) [官方纹理平面](https://github.com/pollen-robotics/microduck_rl/blob/0daab160d3fb1c2cbaba16a4a19052f36709dd9e/src/mjlab_microduck/robot/microduck/scene_walk.xml)

### Cited Findings

| 可选内容 | 类型与证据 | 接入时的边界 |
|---|---|---|
| 官方棋盘格平面 | MJCF `builtin=checker`、重复纹理、天空渐变 | 可做轻量默认替代；当前几何传输保留 rgba，但没完整传送 texture/material，因此要在前端重建或扩展模型协议 |
| 哑光橡胶跑道与彩色坡道 | Arena `course.js` 使用不同颜色、粗糙度和赛道线 | 换颜色/roughness 不应暗中更改摩擦；坡道应跟实际碰撞角度一致 |
| 轮滑馆程序化地板 | Arena `roller-hall.js` 有 Canvas 纹理/粗糙度图与馆体 | 现成代码参考；需测试手机纹理大小、GPU 内存和释放 |
| 演出舞台/观众席/灯光 | Arena `talent-stage.js` | 可以包住现有合唱场景，避免平地空旷；视觉舞台不得制造无碰撞的可站立区域 |
| 街机游戏室 | 官方 Sandbox 的围栏、街机/音箱等 GLB | 道具多是视觉，只有源码明确加的碰撞才算物理障碍 |
| apartment | RL develop 有 `scene_apartment.xml` / `apartment.xml`；官方 duck-sim 可选六房间 7×6m 公寓 | **值得完整纳入**；能串起语音导航、回窝、物品搬运；不是只换一张木纹贴图 |
| VSLAM 测试房间 | RL develop 有 `scene_vslam.xml` / `vslam_room.xml` | 用于相机、遮挡、颜色地标实验；“加载了房间”不代表已有 SLAM 算法 |
| 粗糙地形 | RL rough 配置有 flat、低金字塔台阶、随机格状起伏、heightfield 缓坡 | 必须加载真实碰撞几何，不能用 normal map 冒充；原 flat 策略不保证可用 |
| 接触变化 | 摩擦、solref/solimp 等是 MuJoCo 参数 | 需要单独实验、记录参数和复测；不能把视觉“草地/冰面”直接宣称为校准真实材质 |

来源：[官方 scene_walk](https://github.com/pollen-robotics/microduck_rl/blob/0daab160d3fb1c2cbaba16a4a19052f36709dd9e/src/mjlab_microduck/robot/microduck/scene_walk.xml)、[Arena course](https://huggingface.co/spaces/pollen-robotics/microduck-arena/blob/9305b754862c56b2b2ce512c063c34600efbf932/app/src/course.js)、[roller-hall](https://huggingface.co/spaces/pollen-robotics/microduck-arena/blob/9305b754862c56b2b2ce512c063c34600efbf932/app/src/roller-hall.js)、[talent-stage](https://huggingface.co/spaces/pollen-robotics/microduck-arena/blob/9305b754862c56b2b2ce512c063c34600efbf932/app/src/talent-stage.js)、[apartment](https://github.com/pollen-robotics/microduck_rl/blob/0daab160d3fb1c2cbaba16a4a19052f36709dd9e/src/mjlab_microduck/robot/microduck/apartment.xml)、[VSLAM room](https://github.com/pollen-robotics/microduck_rl/blob/0daab160d3fb1c2cbaba16a4a19052f36709dd9e/src/mjlab_microduck/robot/microduck/vslam_room.xml)、[rough 参数](https://github.com/pollen-robotics/microduck_rl/blob/0daab160d3fb1c2cbaba16a4a19052f36709dd9e/src/mjlab_microduck/tasks/microduck_velocity_env_cfg.py)、[当前几何协议](https://github.com/zhoutingunl/DuckKing/blob/9cac621484f87131b754b8e7a3303fa869af8e9c/src/duckking/model_assets.py)。

**高度场的具体接入缺口。** 当前 `model_assets.geometry()` 为 mesh 导出顶点/面、为 geom 导出类型/尺寸/颜色，没有 heightfield 的采样高度、行列与范围；`physics-view.js` 只建立 mesh 及 2–6 类型的球/胶囊/椭球/圆柱/盒子，没有 MuJoCo type 1（hfield）的绘制分支。因此官方粗糙地形里的 heightfield 缓坡不能仅“加载 XML”就认为网页正确显示；应增加 hfield 导出与网格生成，或者先把训练几何等价三角化并校验碰撞一致性。[当前模型导出](https://github.com/zhoutingunl/DuckKing/blob/9cac621484f87131b754b8e7a3303fa869af8e9c/src/duckking/model_assets.py) [当前绘制分支](https://github.com/zhoutingunl/DuckKing/blob/9cac621484f87131b754b8e7a3303fa869af8e9c/frontend/src/physics-view.js)

**UI 建议（推断，不是已有选项）**：先提供“浅色网格 / 官方棋盘格 / 体育跑道 / 轮滑馆 / 演出舞台”的外观切换；再提供独立“平地 / 缓坡 / 台阶 / 不平路 / 公寓”的实验场地选择。外观切换可不重建物理，地形切换应重置并重新准备，成绩须带场地参数。木地板可参考 Arena 现成 `parquet()` 与 `parquetRoughness()`；草地、沙地、冰面若要新增，应注明需新制作或另找资产，不能说本次已在 Playground 发现了完整材质包。建议来源为上表实物代码和当前 renderer 边界。

### Inferences

- 场景外观优先选择程序化纹理和少量几何，能减少模型下载；浏览器当前只有 rgba 路径，完整搬运高分辨率 PBR 包会扩大手机加载负担。
- 最有价值的环境落地是“公寓生活路线”和“有规则的运动场”，它们能让同一个动作在不同目标/规则下产生新体验。

### Gaps

- 未对上述场地在 DuckKing 的碰撞、模型大小、渲染时间和内存进行本次基准测试；目录存在和代码可读不代表可直接上线。
- 未搜到官方现成一键选择的通用“草地/沙地/冰面”物理材料库；不能按视觉贴图推断摩擦系数。
