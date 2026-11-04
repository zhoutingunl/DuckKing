# 当前 DuckKing 动作能力与演示场景评审

## 当前代码已经支持什么

### Takeaway

研究基线为本地 HEAD `477253f1b991d5b86b19438475a54c6328d18a23`，分支 `docs/demo-scenarios-top10`。本轮只读代码，没有运行任何硬件、云端或物理验收；既有验证仅作为历史记录引用。开始时工作区已有 `AGENTS.md` 修改和未跟踪的 `docs/DEMO_SCENARIOS_TOP10.md`，均未更改。用户最新明确将冻结时点更新为 2026-10-27 09:00 Asia/Shanghai。

动作已经相当丰富。当前缺口主要是“动作组成真实用户任务”“现场语言与身体反馈一致”“机载部署和实机证据”，而不是继续增加一串舞步。

### Cited Findings

| 能力 | 代码已有实现与限制 | 来源 |
|---|---|---|
| 前进、后退、左右转、左右横移 | 预览、robotd、MuJoCo 可复用速度接口；普通动作 0.2–3 秒，转向是速度×时间，不保证精确角度/距离；MuJoCo 后退横移额外验证实际方向位移 | [Action 边界](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/src/duckking/motion.py:85)、[通用执行](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/src/duckking/motion.py:302)、[平移验收](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/src/duckking/official_skills.py:157) |
| 点头、摇头、歪头、闪身步、抖毛 | 通用头部/身体意图编排，非新训练策略；已有 MCP 工具 | [MCP 基础工具](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/src/duckking/mcp.py:11)、[扩展基础工具](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/src/duckking/mcp.py:78)、[轨迹执行](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/src/duckking/motion.py:319) |
| 坐下/站起 | 使用官方坐站策略；ball、duo、skills 场景，支持 A/B/both 的场景限制；坐下后可头部动作，行走或踢球前必须站起；不能用于首页动画或当前 robotd 适配器 | [MCP 坐站](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/src/duckking/mcp.py:124)、[准备条件](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/src/duckking/simulation.py:394)、[后端隔离](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/src/duckking/motion.py:304) |
| 前滚翻、低头啄取姿态、打哈欠、自然待机 | 已有 skills 场景与工具。滚翻≤6秒，啄取姿态≤5秒，哈欠4.5秒；自然待机为本地行为。低头啄取明确返回 `object_grasped: False`，不是捡起物品 | [工具与限制](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/src/duckking/mcp.py:94)、[时长](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/src/duckking/motion_catalog.py:5)、[验收与明确未抓取](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/src/duckking/official_skills.py:99) |
| 轮滑、轮滑下蹲再站起 | 已有 rollers 场景，滑行3秒再收势总计≤5秒，下蹲≤6秒；轮子被动滚动，验证位移和轮子转动；其他场景动作不能直接套用 | [工具](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/src/duckking/mcp.py:108)、[场景门控](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/src/duckking/simulation.py:379)、[结果验收](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/src/duckking/official_skills.py:99) |
| 左右脚踢球 | 官方策略、实际接触/位移验收；每次在所选脚前直接设置球的状态，不能称为找球、追球或自主足球 | [摆球代码](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/src/duckking/simulation.py:459)、[工具说明](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/src/duckking/mcp.py:165) |
| 嘴部夹取→搬运→放下 | 已有固定取物架、小棒、接物台的接触闭环；不支持任意物体、任意摆放或从地面自主拾取；carry 场景禁止混入普通走路以免破坏夹持 | [工具说明](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/src/duckking/mcp.py:184)、[准备约束](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/src/duckking/simulation.py:333)、[历史证据与边界](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/docs/VALIDATION.md:138) |
| 双鸭发现、一起走、相向碰面、合唱 | 同一个 MuJoCo 世界的两个实例。发现依赖仿真坐标、距离≤1.2m、120°视野、射线遮挡，不是摄像头检测或无线发现；合唱为浏览器本地音频 | [发现算法](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/src/duckking/simulation.py:496)、[工具说明](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/src/duckking/mcp.py:199) |
| 四鸭桌上合唱、坐姿轮流独唱 | 四个真实物理实例，但整套本地固定节目；`table_show`/`seated_show` 在 HTTP 动作接口存在，MCP 的 `duck_set_scene` 和工具表不暴露 table/seated | [动作枚举](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/src/duckking/motion.py:16)、[MCP 可选场景](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/src/duckking/mcp.py:150)、[剧场边界](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/docs/DEMO_THEATRE.md:39) |

- `DeviceMCP` 基础清单为 13 个工具（8 个原基础工具+5个扩展）；只有 `backend.kind == "mujoco"` 时追加18个场景工具，合计31个。广告清单不代表任何场景都能执行全部动作，`prepare` 仍检查姿态与场景。[工具表与发现逻辑](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/src/duckking/mcp.py:258)
- robotd 目前只适配 `robot.move`、`robot.head`、`robot.pose`、`robot.stop`、`robot.subscribe`，会拒绝过期或 fallen/limp/picked_up 状态。没有把原生模式切换、恢复起身、嘴部控制等能力映射进来；`reset` 特意拒绝执行上电或断扭矩。[robotd 适配](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/src/duckking/robotd.py:58)、[停止与reset](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/src/duckking/robotd.py:105)
- 本地优先模式为服务器端 SenseVoice ASR+整句命令语法，不是机载已验收识别。35类命令别名覆盖基本动作、5类场景切换、坐站、技能和搬运；单次≤6动作、总时长≤20秒。问句、条件句、不匹配整句不会先执行其中一段，而是一次交给灵矽；实际本地动作失败后不会再转云端重做。[语法](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/src/duckking/local_commands.py:9)、[路由和执行](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/src/duckking/hybrid_voice.py:96)
- 本地命中结束只产生带 `source=local` 的文字，前端明确称“提示音和文字”；未实现离线本地自然语音回答。云端回退才走真实灵矽的 STT/MCP/TTS。[本地结束与回退](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/src/duckking/hybrid_voice.py:166)、[前端提示](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/frontend/src/voice.js:51)
- 云端当前仍用 `listen mode=manual`，头部只有认证、设备/客户端身份及协议版本，没有智能体选择 Header；录音15秒上限，浏览器按住说话，另支持按键打断。未找到唤醒词、机载音频 I/O、远场定位或自然全双工闭环。[listen](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/src/duckking/voice.py:176)、[握手](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/src/duckking/voice.py:123)、[浏览器采集](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/frontend/src/voice.js:84)

### Inferences

- 继续将“后退、横移、滚翻、坐站、轮滑”列为未来需引入动作会误报；这些应作为可复用基础，而不是新增卖点。
- 公平比较必须分四层：官方能力存在、本项目接口支持、当前后端可执行、实机实测成功。当前主要是前两三层。
- 受限的本地可靠控制可以作为云端灵矽产品的韧性设计，但竞赛主秀不宜只展示离线命令映射，否则会弱化“装上灵矽”的主题。

### Gaps

- 本轮没有运行测试、没有读取私有设备身份或凭据，没有获得实体设备照片/电气连接/机载部署证据。
- 现有验证文档有历史限制段落（例如早期“无按键打断”“单账号”等）需结合后续增量和代码判断，不能整段当作当前状态。报告宜引用明确仍成立的硬件缺口，不重复过时限制。

## 现有12幕应该如何取舍

### Takeaway

`frontend/src/demo-catalog.js` 当前恰好12幕，不是10幕。它们形成完整的“入职第一天”剧场，但多数是工程能力的趣味包装，还不是“用户反复需要它”的产品使用场景；第3/4幕和第9/10/11/12幕存在能力重叠。[完整节目清单](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/frontend/src/demo-catalog.js:4)

### Cited Findings

以下“取舍”是本次产品评审意见，不是代码事实或评委评分；每行的节目与实际步骤可在对应清单看到。

| 幕 | 已有看点与真实支撑 | 产品评审和建议 |
|---|---|---|
| 1 你是哪只鸭 | 读状态、点头、明确介绍仿真身份 | 保留为10–15秒开场，不独占主要使用场景。升级为真实“领养/开箱配对”，加入机载状态和用户命名才更贴题。[脚本](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/frontend/src/demo-catalog.js:5) |
| 2 反向招聘人类 | “打招呼表示认可”不直接说动作名，云端需选对 nod；紧张抖毛有笑点 | 最适合保留并让评委现场换说法，以区别按词遥控；预录模式只能证明脚本跑通。[脚本](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/frontend/src/demo-catalog.js:7)、[实际云端调用](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/frontend/src/demos.js:132) |
| 3 闭嘴，换我说 | 老动作和老回复被打断，新指令接管 | 高产品价值、适合作为每个场景的横向能力。与4合并成一次“临时改主意”的演示，不必连续演两幕。[脚本](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/frontend/src/demo-catalog.js:9)、[取消验收](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/frontend/src/demos.js:141) |
| 4 甲方又改需求了 | 取消整个旧序列，后续动作不得恢复 | 保留工程验收，主秀并入3。产品叙事应变为“中途改目的地/改服务”，而不是重复舞步。[脚本](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/frontend/src/demo-catalog.js:11) |
| 5 鸭界世界杯记者会 | 左右脚真实接触、位移计分，不乱报成绩 | 保留高互动性：由观众任选左右脚，按当次结果解说。明确是定点球，摆球过程不要隐藏。[脚本](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/frontend/src/demo-catalog.js:13)、[摆球](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/src/duckking/simulation.py:459) |
| 6 嘴硬快递员 | 抓取—搬运—释放，真实验收决定成功 | 现有节目中最接近“产品帮人完成工作”。优先保留，目标物只承诺固定轻棒，可拟为桌面传递签字笔/道具但不能声称已支持真实笔。[脚本](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/frontend/src/demo-catalog.js:15)、[实验边界](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/docs/VALIDATION.md:142) |
| 7 一屏双魂舞林争霸 | 两个独立房间并行动作，不串台 | 更适合答辩展示隔离性；不是两实体机器人通信或同世界协作。若做产品，应换成“两个家庭各自拥有一只鸭”，需要实际设备映射。[脚本](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/frontend/src/demo-catalog.js:17)、[两房实现](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/frontend/src/demos.js:171) |
| 8 孤独鸭寻友记 | 背向不发现、转回可发现；主动展示失败 | 保留失败透明度，措辞必须是“仿真视域检测”。朝向切换是固定脚本；升级找人/跟随需真实感知接口。[脚本](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/frontend/src/demo-catalog.js:19)、[真值算法](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/src/duckking/simulation.py:496) |
| 9 社恐鸭组团出道 | 同场发现、相向接触、双声部合唱 | 同时复用8和10的能力；和四鸭音乐节目择一呈现，未来改成设备间相互识别及用户许可的结伴任务。[脚本](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/frontend/src/demo-catalog.js:21) |
| 10 四声部谢幕 | 官方16拍乐谱；声部加入/离开留席 | 两只物理鸭+两个音频声部，并非四鸭物理或BLE。工程解释价值大，视觉记忆弱于11/12，降为答辩备选。[脚本](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/frontend/src/demo-catalog.js:23)、[精确边界](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/docs/DEMO_THEATRE.md:41) |
| 11 桌上不掉拍 | 四鸭真实物理，D预设走下桌沿，落地后直立才恢复歌舞 | 记忆点最强但与灵矽关系较弱，且历史有落地后不能恢复的失败。保留为可选仿真彩蛋，不能作为实体产品承诺或叫“任意摔倒自己爬起”。[剧场描述](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/docs/DEMO_THEATRE.md:58)、[恢复条件](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/src/duckking/table_choir.py:219)、[失败记录](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/docs/VALIDATION.md:220) |
| 12 轮到我开唱 | 四鸭真坐站，站稳后才独唱，唱后坐回 | 比坠落更适合实体迁移与自然轮流互动；适合作为唯一音乐收尾。现在是本地固定独唱顺序，不是语音点名即兴调度。[脚本](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/frontend/src/demo-catalog.js:27)、[编排机制](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/frontend/src/demos.js:195) |

- 默认模式是“自动演示·预录对白”；真云端模式也使用预录指令 WAV，只是 STT/MCP/TTS 为当轮真实灵矽。旁白/角色笑话两种模式都预录；10/11/12音乐都是本地应用编排。[模式说明](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/docs/DEMO_THEATRE.md:33)
- 云端实际动作必须严格匹配预期列表，失败、缺动作、多动作都终止，不本地补动作。这是较强可信度设计，应该保留并在新的现场产品演示中复用。[动作核验](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/frontend/src/demos.js:125)、[匹配条件](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/frontend/src/demo-runtime.js:35)
- 当前12幕目录没有新加入的 skills/rollers/离线语音专幕；新能力在工作台/物理实验室存在，不能说“自动剧场已覆盖所有动作”。[目录](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/frontend/src/demo-catalog.js:4)

### Inferences

- 推荐现有素材主秀骨架：现场意图理解（2）→可中断的多步实物任务（3+6）→任选脚踢球（5）→语音点名的坐姿轮唱（12，点名还需开发）；11作为可选惊喜彩蛋。别将12幕全播等同产品完整性。
- 每个新场景都应保留可观察链条：用户具体诉求→真实灵矽选择工具→实际状态变化→失败/完成说明，并允许用户临场更改，而不是只把一句口令作为播放完整剧本的按钮。

### Gaps

- 没有本轮连续演出成功率、真实评委反馈、现场声学或观众惊喜度数据；任何排序都是产品判断。
- 自动剧场默认不用真人麦克风输入；真实人声、噪声、迟到指令及多人说话仍需另行现场验收。

## 哪些缺失最值得引入

### Takeaway

优先顺序应由“对竞赛命题的证明力”决定。机载语音及真实设备动作桥接是最高价值证据；软件上优先做语言到任务、语言和身体表达一致，以及行为可打断的封装，再考虑新运动策略。

### Cited Findings

| 候选缺失 | 当前证据 | 建议复用与完成判据（设计建议） |
|---|---|---|
| 真机/机载语音入口 | 浏览器 `getUserMedia` 采集，Python 转灵矽；文档明确无实体舵机、电池、麦克风板 | 复用 VoiceSession/MCP/robotd，增加设备侧音频与启动服务；现场拔掉笔记本网页后，真实鸭麦克风接收指令、真实扬声器回应且舵机动作，才能声称“装在机内”。[采集代码](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/frontend/src/voice.js:84)、[硬件缺口](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/docs/VALIDATION.md:109) |
| 原生 robotd 策略切换/受控复位或起身 | robotd 仅通用接口；MuJoCo 新策略无法直接走该适配器，动作枚举无 get_up | 先由官方资料研究确认可用模式与条件，再暴露单独受限工具；禁止将普通 stop/reset 当起身。需确认fallen状态、恢复结果及中止行为。[适配器](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/src/duckking/robotd.py:58)、[动作枚举](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/src/duckking/motion.py:41) |
| 独立嘴部开合与语音联动、注视说话者 | 嘴部用于哈欠/夹取；接口无通用 mouth、gaze_at 或说话口型动作，摄像头输入不存在于当前采集路径 | 先做音频幅度驱动开合与聆听歪头，明确非音素级口型；说话者定位需传感器或显式选择目标，不能拿仿真位置假装视觉。[现有工具](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/src/duckking/mcp.py:94)、[发现实现](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/src/duckking/simulation.py:496) |
| 可检查、可保存的语音动作配方 | 本地只有固定语法，云端仅逐个现有动作，没命名宏/新配方存储工具 | 新增有界 routine schema，先复述/预览，用户确认后保存别名；每步都依赖完成，失败和新指令取消余项。称“组合已会动作”，不能称训练新技能。[语法上限](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/src/duckking/local_commands.py:60)、[工具执行](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/src/duckking/mcp.py:293) |
| 真实找球/追球、找人/跟随、避障停步 | 当前球是摆好后踢，发现使用真值射线，普通行走仅限时 | 先做可解释的传感器闭环和置信度，再谈高层自主任务。MVP可由用户摆球/指定方位并明确边界；不能以新文案取代开发。[摆球](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/src/duckking/simulation.py:459)、[发现](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/src/duckking/simulation.py:496) |
| 语音选择音乐/点名成员、设备间协作 | table/seated 全套演出只通过应用编排；MCP无点歌/点名solo工具；两房是隔离世界 | 将受限现有曲目和成员名单做工具，基于站稳状态切音轨；真实BLE协作须单独实现，不把一个AudioContext叫无线同步。[MCP表](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/src/duckking/mcp.py:150)、[本地编排](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/frontend/src/demos.js:195)、[BLE边界](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/docs/DEMO_THEATRE.md:47) |
| 情境化角色/音色/声音身份 | 当前握手无agent选择，listen无voice参数，角色台词由系统音离线生成 | 待官方灵矽研究确认后增加音色/智能体选择，保留完成后才说完成的行为契约；不要将音色参数称情绪识别。[握手与listen](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/src/duckking/voice.py:123)、[预录来源](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/docs/DEMO_THEATRE.md:37) |
| 断网仍可用的本地反馈 | 本地识别与受限执行已有，本地自然语音回答没有；默认配置不开ASR | 可加离线短反馈音或已标注本地TTS，同时在本地网络保持通的情况下断WAN演示。必须先预装模型与启用ASR。[默认配置](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/src/duckking/config.py:24)、[本地完成](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/src/duckking/hybrid_voice.py:166) |

### Inferences

- 最高优先级软件新增：`有界动作配方`、`语音点名/点歌`、`说话嘴部与聆听姿态`。它们将已存在的强大动作库转为更像硬件助手的体验，且易于从当轮证据验证。
- 新官方策略引入优先补 robotd 路由而非仅加 MuJoCo 按钮，否则当前“复刻智能硬件”证据缺口不缩小。
- 原有“反向招聘”“嘴硬快递”“坐姿合唱”可分别发展为家庭陪伴/办公微助手/亲子轮流游戏等用途，但必须有用户目标及可变输入，不只是改标题。

### Gaps

- 官方机器人原生可用的恢复、视觉、声音、BLE能力由其他研究员确认，本文件仅证明本项目当前缺失，不保证上游能力已成熟或可直接接入。
- 剩余工期、现有实体硬件与传感器库存未获用户信息；不能承诺上述扩展在固定工时内完成。

## 现有未提交策划稿有哪些事实风险

### Takeaway

`docs/DEMO_SCENARIOS_TOP10.md` 是用户工作区已有未提交设计稿，不是实现或验证证据。本轮未修改。稿中若干“已可演”将原语存在与完整产品流程存在混在一起，最终报告应独立核实。

### Cited Findings

- “拔掉Wi-Fi仍可指挥”需要限定浏览器—服务器链路仍通；当前本地ASR在服务器进程，非手机离线识别或机载已实装。若关闭手机到公网服务的唯一网络，指令无法上传。[稿件](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/docs/DEMO_SCENARIOS_TOP10.md:64)、[前端音频上传](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/frontend/src/voice.js:89)、[服务端识别](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/src/duckking/hybrid_voice.py:104)
- “拒绝了你”只有现成摇头/歪头/待机原语，尚没有根据任务、姿态、电量、环境做拒绝解释的完整产品策略；先摇头后照做也不等于有意义的拒绝。[稿件](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/docs/DEMO_SCENARIOS_TOP10.md:102)、[工具集合](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/src/duckking/mcp.py:78)
- “摔倒自己爬起来”不符合当前table_show：它等待落地后已直立0.4秒再跳舞，不包含从趴倒姿态主动起身的策略，且有未恢复失败记录。[稿件](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/docs/DEMO_SCENARIOS_TOP10.md:127)、[代码](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/src/duckking/table_choir.py:221)、[历史失败](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/docs/VALIDATION.md:220)
- “评委点歌台已可演”如果指点击现成按钮成立；若指说出歌名并自主调用，当前没有MCP点歌工具。坐姿轮唱固定《欢乐颂》，不是三首曲目都支持同一坐姿solo方案。[稿件](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/docs/DEMO_SCENARIOS_TOP10.md:150)、[坐姿节目](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/frontend/src/demos.js:195)、[工具表](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/src/duckking/mcp.py:115)
- 稿中“全场唯一”“必定让评委讨论”“极便宜”等没有评委/竞品/工时证据，不应作为调研事实。[稿件排序及估算](/Users/zhouting/Documents/QiNiuWork/github_base/DuckKing/docs/DEMO_SCENARIOS_TOP10.md:23)

### Inferences

- 产品场景的优先级建议调整为：硬件+真实灵矽闭环的证明力、用户价值、现场参与感、实现可信度，再看笑点；不应只按“0.5秒反应强度”排序。

### Gaps

- 稿中的灵矽新API精确字段与音色克隆许可需要官方资料核验，本代码审阅不为这些外部主张背书。
