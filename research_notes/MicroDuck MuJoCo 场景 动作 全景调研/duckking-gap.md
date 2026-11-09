# DuckKing 当前能力、接入缺口与一站式集成建议

## 1. 当前源码已经实现什么，哪些结果可以复用？

### Takeaway

截至本次 2026-11-10 源码审计，DuckKing 已经有坐站、前滚翻、啄地姿态、足轮滑行、嘴部搬运、四鸭发布会，以及转盘和自由配重跷跷板 PPO。新增方案应优先把已有能力组织成可解释、可验证的体验，不能把 sit 改名“自充电”，也不能把既有 A*、足轮动作或编排重新包装为新训练成果。以下“已实现”指在固定提交中有完整接线与验收代码，并不表示本轮重跑或实体测试通过。[动作契约](https://github.com/zhoutingunl/DuckKing/blob/5d9b92cb8c096814fae311d6700ac829792df687/src/duckking/motion.py#L18) [物理后端](https://github.com/zhoutingunl/DuckKing/blob/5d9b92cb8c096814fae311d6700ac829792df687/src/duckking/simulation.py#L116) [训练任务](https://github.com/zhoutingunl/DuckKing/blob/5d9b92cb8c096814fae311d6700ac829792df687/src/duckking/balance.py#L170) [跷跷板](https://github.com/zhoutingunl/DuckKing/blob/5d9b92cb8c096814fae311d6700ac829792df687/src/duckking/seesaw.py#L1)

### Cited Findings

**审计锚点与证据等级**

- 本次实际读取工作树 HEAD 为 `5d9b92cb8c096814fae311d6700ac829792df687`；应用引用固定官方 Microduck `942e58e3aa6dbb28e7037203fff11866122c7567`、Microduck RL `b02fdea4902c2b93b7d34a83a6f05da4ececb7d3`、策略仓库 `665ae4eb20bfe13bca1ef4ea6d4bb6b4a096e448`。本地 RL checkout 的 HEAD 也核实为 b02fdea。**这些是当前应用的依赖 pin，不是 2026-11-10 官方最新版本的断言。** [安装 pin](https://github.com/zhoutingunl/DuckKing/blob/5d9b92cb8c096814fae311d6700ac829792df687/scripts/setup_simulator.sh#L23) [策略 pin 与 SHA-256](https://github.com/zhoutingunl/DuckKing/blob/5d9b92cb8c096814fae311d6700ac829792df687/scripts/fetch_scene_assets.py#L9)
- 证据强弱须分开：本轮是源码/工件阅读；仓库测试证明存在相应检查；历史 report/test JSON 提供当时评估记录；本轮没有启动云端、MuJoCo 回放、硬件或部署检查。README 的截屏和主视频另有各自日期/版本，因此代码 HEAD 不能直接代替公网发布版本。[README 素材版本说明](https://github.com/zhoutingunl/DuckKing/blob/5d9b92cb8c096814fae311d6700ac829792df687/README.md#L9) [历史训练原始报告](https://github.com/zhoutingunl/DuckKing/blob/5d9b92cb8c096814fae311d6700ac829792df687/training/seesaw_results/report.json)

**能力与缺口矩阵**

| 能力 | 当前状态 | 源码实际行为与不可越界之处 |
|---|---|---|
| 步行、转向、倒退、左右横移 | 已实现 | 共用有界 Action；基础动作最长 3 秒、speed 字段 0.02–0.4。转向是固定 yaw 命令，不保证精确角度；物理倒退/横移另做真实位移判定。不是“精确到点导航”的通用 API。[Action](https://github.com/zhoutingunl/DuckKing/blob/5d9b92cb8c096814fae311d6700ac829792df687/src/duckking/motion.py#L54) [执行](https://github.com/zhoutingunl/DuckKing/blob/5d9b92cb8c096814fae311d6700ac829792df687/src/duckking/motion.py#L382) [位移验收](https://github.com/zhoutingunl/DuckKing/blob/5d9b92cb8c096814fae311d6700ac829792df687/src/duckking/official_skills.py#L158) |
| 点头、摇头、歪头、左右/前/下看 | 已实现，入口覆盖不一致 | 有界头部轨迹与固定朝向动作；head-only 编排也已存在。单独定向看已经在 Action/工坊中，不应再列“完全缺失”；是否暴露每项独立语音按钮是产品接线问题。[头部动作](https://github.com/zhoutingunl/DuckKing/blob/5d9b92cb8c096814fae311d6700ac829792df687/src/duckking/motion.py#L413) [工坊 Step/HEAD](https://github.com/zhoutingunl/DuckKing/blob/5d9b92cb8c096814fae311d6700ac829792df687/src/duckking/studio.py#L22) |
| 坐下、坐稳保持、站起 | 已实现 | 官方 alpha_sitstand；身体高度、膝角、接触支撑、upright 和持续 0.3 秒稳定状态共同验收，偏移过大/超时失败；坐着可点头，走动前须站起。已有双鸭目标和坐姿四鸭编排，不是待接入动作。[posture.py](https://github.com/zhoutingunl/DuckKing/blob/5d9b92cb8c096814fae311d6700ac829792df687/src/duckking/posture.py#L8) [坐站/取消测试](https://github.com/zhoutingunl/DuckKing/blob/5d9b92cb8c096814fae311d6700ac829792df687/tests/test_posture.py#L27) |
| 前滚翻、低头啄取 | 已实现 | roulade/ground_pick 官方 ONNX，测量翻转角、嘴尖最低高度和恢复站稳。ground_pick 明确仅为啄地姿态，`object_grasped:false`，不能声称从地上拾起物品。[实际判分](https://github.com/zhoutingunl/DuckKing/blob/5d9b92cb8c096814fae311d6700ac829792df687/src/duckking/official_skills.py#L91) [工具说明](https://github.com/zhoutingunl/DuckKing/blob/5d9b92cb8c096814fae311d6700ac829792df687/src/duckking/mcp.py#L103) |
| 足轮滑行、轮滑下蹲 | 已实现 | roller/roller_crouch，四个被动轮的真实接触转动；滑行位移与轮轴转角达标且恢复稳定才成功。当前不是独立滑板、不是蹬地上板、更不是有把手滑板车。[模型](https://github.com/zhoutingunl/DuckKing/blob/5d9b92cb8c096814fae311d6700ac829792df687/src/duckking/skills_model.py#L10) [控制/验收](https://github.com/zhoutingunl/DuckKing/blob/5d9b92cb8c096814fae311d6700ac829792df687/src/duckking/official_skills.py#L105) |
| 自然待机、哈欠 | 已实现，本地编排 | skills 场景 opt-in 的平滑看四周、歪头、张嘴；新动作优先，显式停止关闭待机，跌倒退出。设计受官方 idle_head 启发，非官方完整自主/感知栈，无视觉输入。[idle.py](https://github.com/zhoutingunl/DuckKing/blob/5d9b92cb8c096814fae311d6700ac829792df687/src/duckking/idle.py#L1) |
| 闪身步、狗熊哆嗦毛 | 已实现，本地编排 | 定时 head/body/velocity 高层轨迹；复用底层策略，不是新训练策略，也不是精确人体舞蹈复现。[choreography.py](https://github.com/zhoutingunl/DuckKing/blob/5d9b92cb8c096814fae311d6700ac829792df687/src/duckking/choreography.py#L1) |
| 左右脚踢球 | 已实现 | 普通 kick 会明确摆球到指定脚前，再调用官方策略、验脚球接触与位移；工坊已有 observe→prepare→kick 分离流程。尚不是自主找球、连续盘带或比赛策略。[踢球与摆球](https://github.com/zhoutingunl/DuckKing/blob/5d9b92cb8c096814fae311d6700ac829792df687/src/duckking/simulation.py#L694) [工坊教练](https://github.com/zhoutingunl/DuckKing/blob/5d9b92cb8c096814fae311d6700ac829792df687/frontend/src/studio-catalog.js#L15) |
| 双鸭相向行走、碰撞、发现同伴 | 已实现 | 双鸭同一物理世界；发现依仿真真值、120°视野、1.2 m 范围和射线遮挡，不是摄像头检测或 BLE；碰面可能不发生，按接触样本判分。[discover](https://github.com/zhoutingunl/DuckKing/blob/5d9b92cb8c096814fae311d6700ac829792df687/src/duckking/simulation.py#L572) [动作](https://github.com/zhoutingunl/DuckKing/blob/5d9b92cb8c096814fae311d6700ac829792df687/src/duckking/simulation.py#L758) |
| 嘴部夹起→搬运→放下 | 已实现，实验性模型 | 夹取架上的轻棒，要求上下嘴持续接触、离架，搬到固定接物台，放下须脱离嘴部并落稳。嘴铰链是对官方融合模型的近似改编；质量分配/惯量/接触未做官方实机标定。不能把它称为通用物体抓取或地面视觉拾取。[模型](https://github.com/zhoutingunl/DuckKing/blob/5d9b92cb8c096814fae311d6700ac829792df687/src/duckking/grasp_model.py#L140) [夹取状态机](https://github.com/zhoutingunl/DuckKing/blob/5d9b92cb8c096814fae311d6700ac829792df687/src/duckking/grasp.py#L132) [来源与边界](https://github.com/zhoutingunl/DuckKing/blob/5d9b92cb8c096814fae311d6700ac829792df687/THIRD_PARTY.md#L14) |
| 双声部/四声部音乐 | 已实现，音频仍本地 | duo chorus 为 2 声部；第10幕 `choir` 为 A–D **四个真实物理实例**，官方乐谱片段+浏览器本地合成；不是两鸭+视觉替身，不是 BLE 或云端歌声。第11桌上与第12坐姿舞台也各有四个物理根节点。[四实例生成](https://github.com/zhoutingunl/DuckKing/blob/5d9b92cb8c096814fae311d6700ac829792df687/src/duckking/simulation.py#L202) [声部名单/合成](https://github.com/zhoutingunl/DuckKing/blob/5d9b92cb8c096814fae311d6700ac829792df687/frontend/src/chorale-demo.js#L1) [四根节点回归测试](https://github.com/zhoutingunl/DuckKing/blob/5d9b92cb8c096814fae311d6700ac829792df687/tests/test_simulation.py#L332) |
| 桌上四鸭、跌落恢复剧情 | 已实现，可能失败 | TableChoir 控制真实物理，节目是作者编排；音乐可来自本地合成或指定音源。不能宣称任意跌落保证自救。[table_choir.py](https://github.com/zhoutingunl/DuckKing/blob/5d9b92cb8c096814fae311d6700ac829792df687/src/duckking/table_choir.py) [曲目与音源](https://github.com/zhoutingunl/DuckKing/blob/5d9b92cb8c096814fae311d6700ac829792df687/frontend/src/table-choir.js) |
| 坐姿轮唱、点名独唱 | 已实现 | 四鸭坐姿，轮到指定成员站稳独唱再坐回；工坊支持 C→A 等顺序及临时队列修改。[seated_choir.py](https://github.com/zhoutingunl/DuckKing/blob/5d9b92cb8c096814fae311d6700ac829792df687/src/duckking/seated_choir.py) [conductor](https://github.com/zhoutingunl/DuckKing/blob/5d9b92cb8c096814fae311d6700ac829792df687/frontend/src/studio-catalog.js#L7) |
| 第13幕四鸭发布会 | 已实现，场景编排+规则导航 | 随机散落、哈欠、集结排队、碰撞触发一次坐站反应、选中多鸭翻滚后就地坐下、选中鸭齐舞；有屏幕最左/点选集合/语音轮次目标快照。是中文改编，非原现场系统或声音复刻。[剧目](https://github.com/zhoutingunl/DuckKing/blob/5d9b92cb8c096814fae311d6700ac829792df687/frontend/src/demo-catalog.js) [stage.py](https://github.com/zhoutingunl/DuckKing/blob/5d9b92cb8c096814fae311d6700ac829792df687/src/duckking/stage.py) [多选与取消测试](https://github.com/zhoutingunl/DuckKing/blob/5d9b92cb8c096814fae311d6700ac829792df687/tests/test_stage.py#L442) |
| 路径规划/到点 | 部分已实现 | stage 中 0.1 m 网格有界 A*、周期重规划、MuJoCo 位置闭环绕开其他鸭体、排队槽位与姿态验收。尚未抽为通用“任意地形/相机避障/真实世界导航”接口；不是 PPO 导航。[A*](https://github.com/zhoutingunl/DuckKing/blob/5d9b92cb8c096814fae311d6700ac829792df687/src/duckking/stage.py#L89) [闭环导航](https://github.com/zhoutingunl/DuckKing/blob/5d9b92cb8c096814fae311d6700ac829792df687/src/duckking/stage.py#L240) |
| 互动工坊 | 已实现 | 10 项：临场小导演、递送暂停续送、评委指挥、声音身份、暗号配方、足球教练、鸭王说、橡皮鸭追问、专注搭子、换班人格。编排最多6步/20秒、可限定仅头/原地；这些通常是状态/工具编排，不需要新运动策略。[工坊目录](https://github.com/zhoutingunl/DuckKing/blob/5d9b92cb8c096814fae311d6700ac829792df687/frontend/src/studio-catalog.js) [严格任务契约](https://github.com/zhoutingunl/DuckKing/blob/5d9b92cb8c096814fae311d6700ac829792df687/src/duckking/studio.py#L22) |

**场景、13幕与 PPO 的独立口径**

- 常规 MuJoCo 场景实际有 9 个：`ball, duo, carry, skills, rollers, stage, choir, table, seated`。转盘 `balance` 和跷跷板 `seesaw` 使用各自 backend/API，共享显示资源，合计可整理成 11 个物理场景族；不能把13幕剧本数当作13种新策略。[常规模型/驱动](https://github.com/zhoutingunl/DuckKing/blob/5d9b92cb8c096814fae311d6700ac829792df687/src/duckking/simulation.py#L157) [平衡后端](https://github.com/zhoutingunl/DuckKing/blob/5d9b92cb8c096814fae311d6700ac829792df687/src/duckking/balance_backend.py) [跷跷板后端](https://github.com/zhoutingunl/DuckKing/blob/5d9b92cb8c096814fae311d6700ac829792df687/src/duckking/seesaw_backend.py)
- 13幕依次为：身份介绍、反向招聘、打断旧回复、改需求、世界杯记者会、嘴硬快递、一屏双房间舞蹈、寻友、双鸭出道、四声部谢幕、桌上不掉拍、坐姿轮唱、四鸭发布会。第7幕是两个独立物理房间，其他“双鸭/四鸭同场”才是共享物理世界。第10幕源码 scene 已为 choir。[完整剧目](https://github.com/zhoutingunl/DuckKing/blob/5d9b92cb8c096814fae311d6700ac829792df687/frontend/src/demo-catalog.js)
- 转盘 PPO 当前是 25→64→64→3 网络，10 Hz 学三个非负反馈强度，显式中心/朝向反馈律再生成有界速度，底层 50 Hz 冻结官方 velstand、物理 200 Hz；不是从零训练走路，也不是已部署关节残差 PPO。关卡为随盘站稳、保持朝向、偏心回中。[动作映射](https://github.com/zhoutingunl/DuckKing/blob/5d9b92cb8c096814fae311d6700ac829792df687/src/duckking/balance.py#L321) [工件契约检查](https://github.com/zhoutingunl/DuckKing/blob/5d9b92cb8c096814fae311d6700ac829792df687/src/duckking/balance_policy.py)
- 历史固定13秒/100个未见环境种子，转盘三个任务 PPO 为100/100、89/100、59/100；同种子官方基线为100/100、0/100、0/100。第一关不是新增PPO必要性的证据，二三关未达到连续两次验证≥18/20门槛。原始 test JSON 已在本轮直接读取，但没有本轮复跑。[L1原始结果](https://github.com/zhoutingunl/DuckKing/blob/5d9b92cb8c096814fae311d6700ac829792df687/training/results/level1-cpu-v4/test.json) [L2原始结果](https://github.com/zhoutingunl/DuckKing/blob/5d9b92cb8c096814fae311d6700ac829792df687/training/results/level2-cpu-v4/test.json) [L3原始结果](https://github.com/zhoutingunl/DuckKing/blob/5d9b92cb8c096814fae311d6700ac829792df687/training/results/level3-cpu-v4/test.json) [口径/基线](https://github.com/zhoutingunl/DuckKing/blob/5d9b92cb8c096814fae311d6700ac829792df687/training/results/README.md)
- 跷跷板当前契约 `seesaw-v4-passive-docking`：板面、配重均无电机，PPO 17维观测、3个离散动作（站定/前进/后退），固定步速0、0.25、−0.35 m/s，再叠加已有横向/朝向反馈，底层仍官方步态。任务是鸭子走位压板、使自由配重移动并反向制动到中央±4cm停靠；并非“让鸭站中间”的旧任务。[物理与动作](https://github.com/zhoutingunl/DuckKing/blob/5d9b92cb8c096814fae311d6700ac829792df687/src/duckking/seesaw.py#L1) [观测/反馈](https://github.com/zhoutingunl/DuckKing/blob/5d9b92cb8c096814fae311d6700ac829792df687/src/duckking/seesaw.py#L335)
- 当前跷跷板历史原始记录100回合98成功；零步速、回中规则、仅配平规则三基线均0/100。actor 迁移自旧驱动v3，本阶段131072步，导出累计来源311296步；`early.json`是迁移后、当前阶段学习前，**不是随机零步网络**。旧88/100和99/100属于不同契约，不能用于当前场景；macOS历史结果也不保证Linux逐种子一致。[原始report](https://github.com/zhoutingunl/DuckKing/blob/5d9b92cb8c096814fae311d6700ac829792df687/training/seesaw_results/report.json) [工件/限制](https://github.com/zhoutingunl/DuckKing/blob/5d9b92cb8c096814fae311d6700ac829792df687/training/seesaw_results/README.md)
- 语音/手动“真人vsAI”已在跷跷板实现，真人移动限时后可用显式工程辅助站定；语音延迟包含在实际对局中，不是去延迟后的算法公平评测。[当前交互范围](https://github.com/zhoutingunl/DuckKing/blob/5d9b92cb8c096814fae311d6700ac829792df687/docs/SEESAW_COACH.md)

### Inferences

- 所谓“新场景”应至少明确新增哪一项：环境、目标、用户决策、可验证结果、或策略；复用已有模型和策略的故事编排完全有展示价值，但应标“新编排/新控制任务”，不称新运动学习。依据已有 Action、场景与PPO映射可作此产品划分。[动作层](https://github.com/zhoutingunl/DuckKing/blob/5d9b92cb8c096814fae311d6700ac829792df687/src/duckking/motion.py) [任务PPO层](https://github.com/zhoutingunl/DuckKing/blob/5d9b92cb8c096814fae311d6700ac829792df687/src/duckking/balance.py#L349)
- 第13幕已提供多鸭交互/调度/目标绑定的良好底座；后续交通警察、队形老师、动作接龙可先复用此状态机，只有新增动力学或观测任务时再评估训练。[stage状态机](https://github.com/zhoutingunl/DuckKing/blob/5d9b92cb8c096814fae311d6700ac829792df687/src/duckking/stage.py)

### Gaps

- 没有本轮的运行时验收、CPU/GPU耗时比较、云端可用性或实体测量；不得据此写“2026-11-10全部实测通过”。旧报告只用于定位背景，本轮结论以固定源码/工件为依据。
- 公网发布 SHA、最新视频覆盖范围应由协调者另外核实；本轮不将本地工作树、历史视频和线上实例混为同一版本。

## 2. 固定依赖还藏着哪些选项，哪些边界必须显式保留？

### Takeaway

八个已固定下载的官方ONNX都已接入，不存在“这些动作全没用”的大空白。真正低成本缺口集中在动作目录、参数/语音入口、控制接口覆盖和结果说明；视觉、充电、任意坐高、独立滑板等则不能由现有参数换名字完成。[下载清单](https://github.com/zhoutingunl/DuckKing/blob/5d9b92cb8c096814fae311d6700ac829792df687/scripts/fetch_scene_assets.py#L9) [加载映射](https://github.com/zhoutingunl/DuckKing/blob/5d9b92cb8c096814fae311d6700ac829792df687/src/duckking/simulation.py#L128) [当前MCP工具](https://github.com/zhoutingunl/DuckKing/blob/5d9b92cb8c096814fae311d6700ac829792df687/src/duckking/mcp.py#L163)

### Cited Findings

**固定资源及参数的已用/未用**

| 项目 | 核实结果 | 集成判断 |
|---|---|---|
| velstand、sitstand、roulade、ground_pick、roller、roller_crouch、左右kick | 八个已用 | 对应 walk/sitstand/roulade/ground_pick/roller/roller_crouch/kick_left/kick_right，不能再把“接入这八个”列新增任务。[加载表](https://github.com/zhoutingunl/DuckKing/blob/5d9b92cb8c096814fae311d6700ac829792df687/src/duckking/simulation.py#L128) |
| alpha_walking、alpha_stand | pin manifest 另列出，但应用不加载 | 本地 alpha_walking 文件存在，alpha_stand 不在脚本下载八项中；manifest 的旧选项不等于推荐升级。可作为明确的历史比较器，但须单独下载、hash/契约验证和运行评估。[固定策略manifest](https://huggingface.co/pollen-robotics/microduck-policies/blob/665ae4eb20bfe13bca1ef4ea6d4bb6b4a096e448/manifest.json) [应用列表](https://github.com/zhoutingunl/DuckKing/blob/5d9b92cb8c096814fae311d6700ac829792df687/scripts/fetch_scene_assets.py#L11) |
| 坐高 | 非当前可调API | pinned训练配置 STAND_Z=.115、SIT_Z=.060 是训练目标常量；runtime command[0] 是0/1坐站标志。不能凭修改验收高度或发送任意flag就宣称学会任意坐高。[训练配置](https://github.com/pollen-robotics/microduck_rl/blob/b02fdea4902c2b93b7d34a83a6f05da4ececb7d3/src/mjlab_microduck/tasks/microduck_sitstand_env_cfg.py#L91) [runtime](https://github.com/zhoutingunl/DuckKing/blob/5d9b92cb8c096814fae311d6700ac829792df687/src/duckking/simulation.py#L85) |
| 步速 | 有后端字段、语音暴露不足 | Action已有speed，但 `duck_walk_short`只接duration，本地 grammar解析时长、不解析速度；场景动作明确拒绝speed。可以先做已验证速度档，不需要重训；不能假设输入0.4就实际走到0.4 m/s。[Action参数](https://github.com/zhoutingunl/DuckKing/blob/5d9b92cb8c096814fae311d6700ac829792df687/src/duckking/motion.py#L117) [MCP](https://github.com/zhoutingunl/DuckKing/blob/5d9b92cb8c096814fae311d6700ac829792df687/src/duckking/mcp.py#L35) [本地grammar](https://github.com/zhoutingunl/DuckKing/blob/5d9b92cb8c096814fae311d6700ac829792df687/src/duckking/local_commands.py#L60) [上游跟踪误差说明](https://github.com/pollen-robotics/microduck_rl/blob/b02fdea4902c2b93b7d34a83a6f05da4ececb7d3/docs/velstand_policy.md#L185) |
| 站立body姿态 | 部分使用 | body z/roll/pitch 已用于舞蹈、robotd robot.pose；不是全部body x/y/yaw自由可控。上游infer脚本的最大slider常量和未暴露槽位不能当已验证策略包络，DuckKing robotd又有更窄的边界检查。[编排](https://github.com/zhoutingunl/DuckKing/blob/5d9b92cb8c096814fae311d6700ac829792df687/src/duckking/choreography.py) [robotd限制](https://github.com/zhoutingunl/DuckKing/blob/5d9b92cb8c096814fae311d6700ac829792df687/src/duckking/robotd.py#L94) [上游命令槽位](https://github.com/pollen-robotics/microduck_rl/blob/b02fdea4902c2b93b7d34a83a6f05da4ececb7d3/scripts/infer_policy.py#L461) |
| 坐姿头动、目光/哈欠 | 已有，可细化体验 | sitstand保留head四槽；普通头动作和自然待机已接。但当前不是注视相机检测目标的闭环视觉行为。[head保留](https://github.com/zhoutingunl/DuckKing/blob/5d9b92cb8c096814fae311d6700ac829792df687/src/duckking/simulation.py#L85) [本地idle](https://github.com/zhoutingunl/DuckKing/blob/5d9b92cb8c096814fae311d6700ac829792df687/src/duckking/idle.py) |
| 空气键盘/钢琴、官方音乐RPC | 未集成专用接口 | 当前Action/MCP目录无空气键盘/逐音演奏工具；现有chorale是本地Web Audio+固定谱面，不是官方robotd声音栈。能否直接接最新官方能力由官方研究笔记确认版本和入口，不能从现有音乐页面推导已集成。[当前工具目录](https://github.com/zhoutingunl/DuckKing/blob/5d9b92cb8c096814fae311d6700ac829792df687/src/duckking/mcp.py) [本地合成](https://github.com/zhoutingunl/DuckKing/blob/5d9b92cb8c096814fae311d6700ac829792df687/frontend/src/chorale-demo.js) |
| 感知 | 仿真真值有，摄像头流水线未接 | companion依真值FOV/raycast；转盘/跷跷板 manifest明确“MuJoCo ground truth, not camera vision”；stage路径用世界坐标和其他鸭位置。[发现同伴](https://github.com/zhoutingunl/DuckKing/blob/5d9b92cb8c096814fae311d6700ac829792df687/src/duckking/simulation.py#L572) [平衡契约](https://github.com/zhoutingunl/DuckKing/blob/5d9b92cb8c096814fae311d6700ac829792df687/src/duckking/balance.py#L484) [跷跷板契约](https://github.com/zhoutingunl/DuckKing/blob/5d9b92cb8c096814fae311d6700ac829792df687/src/duckking/seesaw.py#L484) |

**三条执行边界与语音边界**

- **原创动画预览**：PreviewBackend 是运动学积分；官方外形网格也不会把它变成物理。首页 duck.js 明言无物理与策略推理。[PreviewBackend](https://github.com/zhoutingunl/DuckKing/blob/5d9b92cb8c096814fae311d6700ac829792df687/src/duckking/motion.py#L251) [首页绘制](https://github.com/zhoutingunl/DuckKing/blob/5d9b92cb8c096814fae311d6700ac829792df687/frontend/src/duck.js#L9)
- **官方 robotd 连接**：当前适配 Unix NDJSON/JSON-RPC `robot.move, robot.head, robot.pose, robot.stop, robot.subscribe`。要求新鲜状态，拒绝 fallen/limp/picked_up，stop需响应确认；首页只是示意图，真实物理画面归官方viewer。它没有世界坐标可供网页假造。[robotd.py](https://github.com/zhoutingunl/DuckKing/blob/5d9b92cb8c096814fae311d6700ac829792df687/src/duckking/robotd.py#L26) [状态输出](https://github.com/zhoutingunl/DuckKing/blob/5d9b92cb8c096814fae311d6700ac829792df687/src/duckking/robotd.py#L170)
- **robotd动作覆盖比MuJoCo小**：MotionController 将 sit、roll、所有场景动作限制为 `kind == mujoco`，robotd尚未映射对应官方动作RPC；reset也明确拒绝用网页对机器人上电/断扭矩。因此“官网或MuJoCo中有动作”不等于“本项目robotd已具备同等硬件接口”。[分流拒绝](https://github.com/zhoutingunl/DuckKing/blob/5d9b92cb8c096814fae311d6700ac829792df687/src/duckking/motion.py#L382) [reset限制](https://github.com/zhoutingunl/DuckKing/blob/5d9b92cb8c096814fae311d6700ac829792df687/src/duckking/robotd.py#L132)
- **DuckKing MuJoCo**：CPU原生MuJoCo读取官方MJCF与ONNX，独立于robotd；自行编排、做接触测量并传输场景数据给浏览器。不能叫“官方完整robotd仿真栈复现”或硬件数字孪生。[模块定义](https://github.com/zhoutingunl/DuckKing/blob/5d9b92cb8c096814fae311d6700ac829792df687/src/duckking/simulation.py#L1) [第三方边界](https://github.com/zhoutingunl/DuckKing/blob/5d9b92cb8c096814fae311d6700ac829792df687/THIRD_PARTY.md)
- **Linx云端语音**：真实会话经WebSocket/音频帧/MCP，工具按场景允许表暴露；会话generation隔离旧回复/旧工具。**local-first**另有明确route/source标签，整句grammar全匹配才本地执行，未执行前才能把原录音送云端；不能把本地确认音或预录剧本叫实时云回复。[VoiceSession](https://github.com/zhoutingunl/DuckKing/blob/5d9b92cb8c096814fae311d6700ac829792df687/src/duckking/voice.py#L1) [generation/中断](https://github.com/zhoutingunl/DuckKing/blob/5d9b92cb8c096814fae311d6700ac829792df687/src/duckking/voice.py#L520) [本地优先路由](https://github.com/zhoutingunl/DuckKing/blob/5d9b92cb8c096814fae311d6700ac829792df687/src/duckking/hybrid_voice.py#L98)
- **失败不降级冒充**：MotionController遇到物理/停止确认失败记录failed；robotd缺socket保持断开；云实连演出失败测试明确不能暗跑local动作。新增场景应保持这条既有契约。[动作结果/停止](https://github.com/zhoutingunl/DuckKing/blob/5d9b92cb8c096814fae311d6700ac829792df687/src/duckking/motion.py#L445) [robotd测试](https://github.com/zhoutingunl/DuckKing/blob/5d9b92cb8c096814fae311d6700ac829792df687/tests/test_robotd.py#L119) [云失败浏览器测试](https://github.com/zhoutingunl/DuckKing/blob/5d9b92cb8c096814fae311d6700ac829792df687/frontend/tests/demos.spec.js#L67)

**不应承诺的功能**

- **充电/电池**：在当前动作、场景与robotd映射中未发现充电座几何/定位、充电触点状态、SOC/耗能仿真、充电协议或自主返航充电闭环。sit只是姿态任务。可以提出“回休息区坐下”的明确模拟故事；若增加电量条，须标教学状态模型，不能声称读取实际电池或真实自充电。[现有动作全集](https://github.com/zhoutingunl/DuckKing/blob/5d9b92cb8c096814fae311d6700ac829792df687/src/duckking/motion.py#L54) [场景生成](https://github.com/zhoutingunl/DuckKing/blob/5d9b92cb8c096814fae311d6700ac829792df687/src/duckking/simulation.py#L157) [硬件适配全集](https://github.com/zhoutingunl/DuckKing/blob/5d9b92cb8c096814fae311d6700ac829792df687/src/duckking/robotd.py)
- **视觉/导航**：仿真真值、射线和A*不证明相机识人、目标检测、SLAM或复杂障碍导航；现有stage障碍主要是其他鸭体的位置。增加道具绕行需新的碰撞几何、占据图/规划接线、失败判定；若换成相机观测则是新的感知工程。[发现真值](https://github.com/zhoutingunl/DuckKing/blob/5d9b92cb8c096814fae311d6700ac829792df687/src/duckking/simulation.py#L572) [stage A*](https://github.com/zhoutingunl/DuckKing/blob/5d9b92cb8c096814fae311d6700ac829792df687/src/duckking/stage.py#L89)
- **实体抓取/足轮/恢复**：夹取近似铰链、足轮接触、表演跌落都只有此仿真建模与验收范围，未找到本项目实体测试记录支撑可直接执行于硬件。[模型改编披露](https://github.com/zhoutingunl/DuckKing/blob/5d9b92cb8c096814fae311d6700ac829792df687/THIRD_PARTY.md) [抓取接触验收](https://github.com/zhoutingunl/DuckKing/blob/5d9b92cb8c096814fae311d6700ac829792df687/src/duckking/grasp.py#L132)
- **许可按资源版本核对**：当前固定pin的第三方说明区分MJCF/代码/策略与模型网格的来源/许可；未来升级到官方更新commit，应重新读取该commit的LICENSE、LICENSE-MODELS及资产清单。不要把未来官方某次新增说明自动解释为追溯改变旧pin许可，也不要因项目MIT而覆盖上游模型。本条是工程来源管理要求，不作法律结论。[当前来源说明](https://github.com/zhoutingunl/DuckKing/blob/5d9b92cb8c096814fae311d6700ac829792df687/THIRD_PARTY.md) [固定RL模型许可](https://github.com/pollen-robotics/microduck_rl/blob/b02fdea4902c2b93b7d34a83a6f05da4ececb7d3/LICENSE-MODELS.md)

### Inferences

- “坐高调节”应拆成两个不同提案：先暴露并验证已有**站立身体高度**能力；真正“任意坐高/中间姿态”需先证实上游策略支持，若没有条件化坐高训练，则需要新控制器/重训。仅修改SIT_Z训练常量还涉及重新训练与评估，不是网页slider接线。[pinned sitstand目标与二值契约](https://github.com/pollen-robotics/microduck_rl/blob/b02fdea4902c2b93b7d34a83a6f05da4ececb7d3/src/mjlab_microduck/tasks/microduck_sitstand_env_cfg.py#L91)
- 速度档、头部态度、固定谱面/交互琴键通常可用wrapper实现；真实地面拾物、独立自由滑板平衡、通用视觉导航、充电对接不能据当前源码承诺为wrapper。前者已有命令/音乐合成底座，后者改变观测、接触或任务闭环。[Action](https://github.com/zhoutingunl/DuckKing/blob/5d9b92cb8c096814fae311d6700ac829792df687/src/duckking/motion.py) [grasp模型](https://github.com/zhoutingunl/DuckKing/blob/5d9b92cb8c096814fae311d6700ac829792df687/src/duckking/grasp_model.py) [共享音乐](https://github.com/zhoutingunl/DuckKing/blob/5d9b92cb8c096814fae311d6700ac829792df687/frontend/src/chorale-demo.js)

### Gaps

- 本地未安装 `external/microduck` checkout；官方robotd的最新版空气键盘、音乐、perception、charging等真实上游能力请引用官方研究员的当日源码证据。本笔记“未集成”只指DuckKing固定提交。
- 本轮没有搜索账户凭据、设备身份或私有运行日志；也没有推断用户有哪些实体设备。
- 本轮未核验所有历史上游策略权重是否仍可下载；本地残留alpha_walking不代表当前下载脚本完整支持它。

## 3. 怎样组成一站式体验，并优先交付哪些新增内容？

### Takeaway

建议扩展现有共享渲染和动作/场景契约，建立统一能力目录与证据标记，让用户从“看演示→说一句→检查结果→学习控制原理”顺序进入。优先把已有运动变成参数明确、有状态反馈的互动；新接触环境与新感知任务放入独立实验入口。以下是依据代码结构提出的设计建议和相对投入估计，不是已实现功能或工时承诺。[共享renderer](https://github.com/zhoutingunl/DuckKing/blob/5d9b92cb8c096814fae311d6700ac829792df687/frontend/src/physics-view.js) [已有目录](https://github.com/zhoutingunl/DuckKing/blob/5d9b92cb8c096814fae311d6700ac829792df687/frontend/src/demo-catalog.js) [工坊任务](https://github.com/zhoutingunl/DuckKing/blob/5d9b92cb8c096814fae311d6700ac829792df687/src/duckking/studio.py)

### Cited Findings

- 当前已经共享 `physicsView`、`createPhysicsModelLoader`、`renderScheduler`：scenarios、demos、balance、seesaw导入同一物理视图；模型按revision缓存、校验DKM1 source/physics、过期版本拒绝；隐藏视图不持续渲染。新场景无需导入旧DuckKing_PPO渲染器。[视图](https://github.com/zhoutingunl/DuckKing/blob/5d9b92cb8c096814fae311d6700ac829792df687/frontend/src/physics-view.js) [缓存与验证](https://github.com/zhoutingunl/DuckKing/blob/5d9b92cb8c096814fae311d6700ac829792df687/frontend/src/model-loader.js#L8) [调度](https://github.com/zhoutingunl/DuckKing/blob/5d9b92cb8c096814fae311d6700ac829792df687/frontend/src/render-scheduler.js) [训练页面复用](https://github.com/zhoutingunl/DuckKing/blob/5d9b92cb8c096814fae311d6700ac829792df687/frontend/src/seesaw.js#L6)
- 当前目录散在Action、MCP、local_commands、demo-catalog、studio-catalog与统计枚举中；例如源码已有choir场景，而experience统计scene白名单未列choir。统一能力目录有实际同步价值，但迁移应先保留兼容契约。[动作](https://github.com/zhoutingunl/DuckKing/blob/5d9b92cb8c096814fae311d6700ac829792df687/src/duckking/motion.py#L18) [本地grammar](https://github.com/zhoutingunl/DuckKing/blob/5d9b92cb8c096814fae311d6700ac829792df687/src/duckking/local_commands.py) [统计scene白名单](https://github.com/zhoutingunl/DuckKing/blob/5d9b92cb8c096814fae311d6700ac829792df687/src/duckking/app.py#L307)
- 已有安全/验收基础可复用：request_id重放幂等、同ID不同参数拒绝、cancel替换旧任务、finally stop、scene前置条件、ONNX非有限输出拒绝、物理失败可见，以及坐站/夹取/翻滚的实测判据。[MotionController](https://github.com/zhoutingunl/DuckKing/blob/5d9b92cb8c096814fae311d6700ac829792df687/src/duckking/motion.py#L337) [策略输出校验](https://github.com/zhoutingunl/DuckKing/blob/5d9b92cb8c096814fae311d6700ac829792df687/src/duckking/simulation.py#L100) [posture](https://github.com/zhoutingunl/DuckKing/blob/5d9b92cb8c096814fae311d6700ac829792df687/src/duckking/posture.py)
- 已有测试分别覆盖motion cancellation、bounded actions、robotd socket响应、MCP重放、语音generation、四鸭多选、物理场景停止/失败，适合作为新能力接入验收清单。这里只确认测试源码存在，不报告本轮通过数。[运动测试](https://github.com/zhoutingunl/DuckKing/blob/5d9b92cb8c096814fae311d6700ac829792df687/tests/test_motion_edges.py) [协议测试](https://github.com/zhoutingunl/DuckKing/blob/5d9b92cb8c096814fae311d6700ac829792df687/tests/test_robotd.py) [MCP测试](https://github.com/zhoutingunl/DuckKing/blob/5d9b92cb8c096814fae311d6700ac829792df687/tests/test_mcp.py) [语音隔离](https://github.com/zhoutingunl/DuckKing/blob/5d9b92cb8c096814fae311d6700ac829792df687/tests/test_voice_interrupt.py) [四鸭取消](https://github.com/zhoutingunl/DuckKing/blob/5d9b92cb8c096814fae311d6700ac829792df687/tests/test_stage.py)

### Inferences

**建议架构（拟议，未实施）**

| 层 | 新增/整理工作 | 复用依据 |
|---|---|---|
| 来源与版本 | 每项能力固定模型/策略/应用commit、许可、运行后端、感知来源、音频来源、测试日期；区分当前现场/历史录像/候选实验。对用户常驻显示“动画/实时MuJoCo/robotd”“本地/灵矽实连”，高级信息另放展开区。 | 已有source字段与pin/hash可复用。[资产脚本](https://github.com/zhoutingunl/DuckKing/blob/5d9b92cb8c096814fae311d6700ac829792df687/scripts/fetch_scene_assets.py) [source示例](https://github.com/zhoutingunl/DuckKing/blob/5d9b92cb8c096814fae311d6700ac829792df687/src/duckking/stage.py#L602) |
| 能力目录 | 单一记录描述capability_id、场景、目标鸭、前置姿态、允许参数、最长时间、观测/动作接口、验收与取消语义、训练/脚本分类；从中生成按钮/MCP/local grammar提示/节目卡和兼容检查。 | 现有Action/MCP/工坊是分别手写目录。[Action](https://github.com/zhoutingunl/DuckKing/blob/5d9b92cb8c096814fae311d6700ac829792df687/src/duckking/motion.py) [MCP](https://github.com/zhoutingunl/DuckKing/blob/5d9b92cb8c096814fae311d6700ac829792df687/src/duckking/mcp.py) |
| 场景+控制器 | 场景资产注册和策略加载分开：同一模型可以选官方基线/任务策略/规则；训练环境与在线控制共用物理引擎，保持模型hash/观测动作契约锁定。新的道具只扩充场景，不默认要求重训。 | balance/seesaw已有此结构。[balance.py](https://github.com/zhoutingunl/DuckKing/blob/5d9b92cb8c096814fae311d6700ac829792df687/src/duckking/balance.py) [seesaw_policy.py](https://github.com/zhoutingunl/DuckKing/blob/5d9b92cb8c096814fae311d6700ac829792df687/src/duckking/seesaw_policy.py) |
| 语音交互 | 先确定当前场景与实体，再接受有界目标；显式本地/云route；单条复合指令先完整校验，结果来自实际终态；高层“演一个…”映射到已批准动作序列。速度/高度等新增参数先做已验证离散档。 | 本地grammar全句匹配，工坊Routine限制6步/20秒。[grammar](https://github.com/zhoutingunl/DuckKing/blob/5d9b92cb8c096814fae311d6700ac829792df687/src/duckking/local_commands.py#L60) [Routine](https://github.com/zhoutingunl/DuckKing/blob/5d9b92cb8c096814fae311d6700ac829792df687/src/duckking/studio.py#L46) |
| 执行/停止/验收 | 全部动作接统一任务生命周期和request_id；中断清掉所有成员控制、嘴/外力/音频；物理停止与暂停/重置分开，不能靠瞬移或速度钳制制造成功；抓取停止保持已夹物，松嘴另显式命令；转盘减速/跷跷板暂停保留场景特定语义。 | 已有stop与夹取保留、stage finally清外力。[stop](https://github.com/zhoutingunl/DuckKing/blob/5d9b92cb8c096814fae311d6700ac829792df687/src/duckking/simulation.py#L487) [grasp stop](https://github.com/zhoutingunl/DuckKing/blob/5d9b92cb8c096814fae311d6700ac829792df687/src/duckking/grasp.py#L124) [stage finally](https://github.com/zhoutingunl/DuckKing/blob/5d9b92cb8c096814fae311d6700ac829792df687/src/duckking/stage.py#L581) |
| 展示/学习 | 统一physicsView+model-loader；选场景不默认启动云会话。结果面板把“目标/观测/动作/是否完成/失败原因/控制器来源”并列；动画仍使用独立预览标签。PPO页支持基线/早期/已评估策略，历史结果与本轮结果分开。 | 共享视图及训练工件已经存在。[loader](https://github.com/zhoutingunl/DuckKing/blob/5d9b92cb8c096814fae311d6700ac829792df687/frontend/src/model-loader.js) [训练记录](https://github.com/zhoutingunl/DuckKing/blob/5d9b92cb8c096814fae311d6700ac829792df687/training/results/README.md) |

**建议优先级与投入估计**

相对投入只用低/中/高，依据现有复用程度判断；不换算为未经实际排期的小时/天数。“交付/清晰/趣味/学习”是调研判断，不是用户实验打分。

| 优先级 | 方案 | 交付/清晰/趣味/学习价值判断 | 新工作类型与验收 |
|---|---|---|---|
| P0 | 统一11场景能力入口、版本与来源卡 | 交付高、清晰高；避免重复演示和能力误读 | 低—中；目录/路由/结果文案。先保留共享renderer；验证所有入口与取消一致，不增加训练。 |
| P0 | “动作参数实验室”：慢/中/快前进，头部态度、坐站与站立高度对照 | 交付高、清晰高、学习高 | 低—中；现有命令wrapper+允许包络实测；展示命令速度与测得位移，坐高不假装连续可调。 |
| P1 | 四鸭“你当导演”：选成员、接龙、队形/节拍/点名 | 交付高、趣味高、清晰高 | 中；复用demo13/坐姿轮唱/工坊；新增编排，验多选、目标快照、取消无残余。不是新PPO。 |
| P1 | “鸭子乐器台/空气键盘” | 趣味高、交付有条件、学习中 | 本地琴键+明确音源可以低—中投入；官方空气键盘/声音栈须先核实当日RPC与资源许可，按独立集成验证。仅按键发音不需要新运动策略。 |
| P1 | “走到指定休息点，再坐下”/简单障碍迷宫 | 清晰高、学习高、趣味中 | 中；抽取stage导航并新增道具/安全余量/超时；开始用仿真真值。名称是“到点休息”，不称充电/视觉导航。 |
| P1 | 把转盘/跷跷板做成一屏挑战课堂 | 学习高、趣味高；已有训练证据 | 中；复用当前策略和基线，增加目标解释/因果回放/语音纠正；成绩按当前契约原样展示，提升可靠性才是后续训练目标。 |
| P2 | 连续控球/盘带、自由滑板平衡、真实地面拾物 | 趣味高，交付不确定 | 高；新的动力学/持续目标/观测，通常要新控制器或新训练与课程；现有踢球、足轮、架上夹棒只当基线，不能直接改名。 |
| P2 | 相机感知找物/避障、充电闭环、实体迁移 | 学习与研究价值高，交付风险高 | 高；需要感知数据/估计、充电座与电气接口/电池模型或真机资源、故障/安全与任务验证。没有现成演示保证。 |

这些排序来自当前可复用动作/控制器与未接入边界的比较，属本次集成建议；基于：[动作与参数](https://github.com/zhoutingunl/DuckKing/blob/5d9b92cb8c096814fae311d6700ac829792df687/src/duckking/motion.py)、[stage导航](https://github.com/zhoutingunl/DuckKing/blob/5d9b92cb8c096814fae311d6700ac829792df687/src/duckking/stage.py)、[音乐](https://github.com/zhoutingunl/DuckKing/blob/5d9b92cb8c096814fae311d6700ac829792df687/frontend/src/chorale-demo.js)、[现有训练任务](https://github.com/zhoutingunl/DuckKing/blob/5d9b92cb8c096814fae311d6700ac829792df687/src/duckking/balance.py)、[跷跷板任务](https://github.com/zhoutingunl/DuckKing/blob/5d9b92cb8c096814fae311d6700ac829792df687/src/duckking/seesaw.py)、[近似嘴模型](https://github.com/zhoutingunl/DuckKing/blob/5d9b92cb8c096814fae311d6700ac829792df687/src/duckking/grasp_model.py)。

### Gaps

- 尚无各候选的实际开发排期、资源预算、多人并发容量增量或用户实验，不给虚构工期与吸引力数值。
- 新引入官方/社区资产仍需逐项核验commit、许可、输入输出契约、模型形态、观测来源和复现结果；这不能由原仓库star数、视频效果或ONNX文件存在替代。
- 本轮只输出调研笔记，没有修改应用、测试、训练、发布或远程分支。
