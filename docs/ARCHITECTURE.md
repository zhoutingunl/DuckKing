# DuckKing 架构与模块规格

## 交付范围

DuckKing 是本地运行的语音与动作工作台。原创动画预览可直接运行；官方物理仿真通过独立的 robotd/MuJoCo 进程接入。已完成真实灵矽设备绑定、语音识别、MCP 动作调用与语音回复联调，测试输入为系统合成中文语音。

它不等于实体硬件复刻，是否满足原竞赛题的实物要求仍需主办方认可。

## 架构

```mermaid
flowchart LR
    Mic[浏览器麦克风] --> PCM[AudioWorklet / PCM16 分帧]
    PCM -->|本地 WebSocket| Voice[VoiceSession]
    Voice <-->|OTA / WSS / Opus / MCP| Cloud[灵矽云端]
    Voice -->|PCM16| Speaker[Web Audio 播放]
    Voice --> MCP[DeviceMCP]
    Buttons[动作按钮 / Esc] --> Motion[MotionController]
    MCP --> Motion
    Motion --> Preview[原创动画状态]
    Motion --> Adapter[RobotdBackend]
    Adapter <-->|Unix socket / NDJSON| Robot[官方 robotd]
    Robot <--> Physics[官方 MuJoCo body]
    Preview --> UI[Three.js 示意界面]
    Adapter -->|遥测和连接状态| UI
```

物理计算在官方 MuJoCo body 中完成，官方 robotd 运行已有策略。浏览器原创模型不是官方 CAD 模型；在 robotd 模式下也只作为示意，不冒充官方物理画面。

## 模块规格

| 模块 | 文件 | 输入 / 输出 | 责任边界 |
|---|---|---|---|
| 本地应用 | `src/duckking/app.py` | HTTP API、状态 WS、语音 WS | 默认只绑定 loopback；同源校验；一个页面独占语音 |
| 动作调度 | `motion.py` | Action → 执行记录 / 状态 | 限时、取消、去重、失败反馈；不直接控制舵机 |
| 组合动作 | `choreography.py` | 动作名 / 时间 → 高层意图帧 | 闪身步与狗熊哆嗦毛；有界、连续的阶段编排 |
| 预览后端 | `motion.py:PreviewBackend` | 速度 / 头部意图 → 动画状态 | 运动学示意，不计算接触、平衡与真实步态 |
| 官方适配 | `robotd.py` | NDJSON → 官方状态 | 订阅 20 Hz 遥测；发送连续意图；拒绝使用过期状态 |
| 设备配置 | `config.py` | 私有配置、OTA → 设备连接参数 | 设备身份持久化；凭证留在后端；公网连接要求 TLS |
| 显式初始化 | `onboarding.py` | 平台 API Key 文件 → 智能体/设备绑定 | 仅在运行 setup 命令时创建或复用 DuckKing，不迁移已有设备历史 |
| 音频编解码 | `opus.py` | PCM16 ↔ Opus | 原生 libopus；16 kHz 上行；按服务器协商解码下行 |
| 灵矽会话 | `voice.py` | 浏览器音频 ↔ 云端事件 | 激活、握手、半双工、音频、工具转发、断线清理 |
| 语音诊断 | `diagnostics.py` | 阶段 / 计数 / STT → 有界日志 | 字段白名单、STT 脱敏与长度限制、内存最近 200 条、私有轮转文件；不保存录音或设备标识 |
| 交互统计 | `statistics.py`、`frontend/src/statistics.js` | 脱敏事件 → 最近 500 轮、百分位、统计页 | 单调时钟、进程内唯一轮次；缺失不补零、不同后端可筛选；不推断物理或扬声器延迟 |
| 端侧 MCP | `mcp.py` | JSON-RPC → 工具结果 | 初始化 / 工具发现 / 白名单调用；结果关联原请求 ID |
| 浏览器音频 | `frontend/src/voice.js`、`audio-codec.js` | 麦克风 / 语音事件 | 录音权限、流式重采样、分帧、播放队列与释放麦克风 |
| 三维界面 | `frontend/src/duck.js`、`main.js` | 后端状态 → 画面 / 记录 | 程序化原创形象；连接与能力范围清楚标注 |

## 本地接口

生产 demo 由 FastAPI 提供 `frontend/dist`；开发模式由 Vite 在 5173 提供源文件和热更新，转发 `/api`、`/ws`、`/voice` 到同一 FastAPI 后端。代理保留 Host / Origin，沿用同源校验，不引入替代动作或语音实现。安装与端口配置见 [本地开发指南](DEVELOPMENT.md)。

| 接口 | 用途 |
|---|---|
| `GET /api/health` | 版本、后端类型与服务可达性 |
| `GET /api/state` | 当前动作、后端状态、近期事件 |
| `GET /api/voice/diagnostics` | 语音阶段、停留时间、音频帧数和脱敏诊断事件 |
| `GET /api/voice/statistics?backend=all` | 本进程最近 500 轮统计；可筛选 `preview` / `robotd`；同源检查、禁止缓存 |
| `GET /statistics.html` | 主页链接打开的独立统计页面；不创建语音连接 |
| `POST /api/actions` | 提交受限动作，返回 202 和请求 ID |
| `GET /api/actions/{id}` | 查询完成、取消或失败结果 |
| `WS /ws` | 推送工作台状态 |
| `WS /voice` | 浏览器录音、连接控制、语音事件与下行音频 |

动作请求示例：

```json
{"name":"walk","duration":1.2,"request_id":"caller-generated-unique-id"}
```

动作名称：`nod`、`walk`、`turn_left`、`turn_right`、`stop`、`reset`、`flash_step`、`bear_shake`。普通动作时长范围 0.2–3 秒；两个组合动作默认 3 秒，范围 2.4–3 秒。普通移动的可选速度范围为 0.02–0.4 m/s；不提供时，预览后端使用 0.12，官方仿真适配器使用实测可启动步态的 0.35。组合动作使用固定速度编排，不接受 `speed`。速度指令不保证固定距离。

`reset` 只支持动画预览。官方适配器不会把它映射成实体机器人上电、断扭矩或未知重置指令。

执行记录状态为 `running`、`completed`、`cancelled`、`failed`。`completed` 表示本地指令序列完成、停止请求获确认，不保证机械位移达到某个目标值；实际运动需看官方遥测和物理状态。MCP 会将取消或失败结果标为错误，不返回虚构成功。

## 动作与取消

一个控制器同一时刻执行一个动作。新动作先取消旧动作；前进和转向每 50 ms 发送一次意图，到本地期限自动停止。浏览器串行提交请求的接收过程，不等待整个动作完成，因此快速点击“前进→停止”不会因两个 HTTP 请求乱序而先停后走。

相同请求 ID 和参数重试复用原结果；相同 ID 配不同参数会拒绝。历史与事件数量有上限。官方后端在状态超过 1 秒未更新时拒绝开始移动，不悄悄回退到动画模式。

点头使用小幅轨迹，并保留动作开始时的头部姿态；不假设所有模型或版本的机械零位相同。

组合动作额外控制横向速度、头部偏航/侧倾和身体姿态。站姿模式和步行分段互斥；结束或取消时关闭站姿模式并恢复头部目标。详细阶段及幅度见 [CHOREOGRAPHY.md](CHOREOGRAPHY.md)。

## 语音与工具

按键说话时，浏览器采集单声道音频，转换为 16 kHz、PCM16、60 ms 一帧。后端编码 Opus 后上传。服务端下行可能使用不同采样率，后端按握手参数解码，再让浏览器按正确采样率播放。

每次录音最多 15 秒。播放时不继续录音；非打断的 TTS 结束会等待已有音频播放完成。断线后停止相关动作、释放音频资源并提示用户重新连接。首版不做唤醒词、全双工或自动恢复录音。

后端独立监控录音时限，即使浏览器不再发音频也会在 15 秒结束录音。思考阶段 20 秒没有 STT / MCP / TTS / 音频等有效进展，或回答阶段 15 秒没有新进展时，关闭旧云端会话并重连一次；包括录音在内的整轮另有 60 秒上限。重连前取消工具任务、停止动作、关闭编解码器并通知浏览器清空播放队列。旧录音不重发，恢复到 ready 后需重新按键说话；重连失败会进入 error，不无限重试。

云端连接整体限时 35 秒，发送/关闭云端 socket 限时 5 秒。连接任务与浏览器指令接收分离，用户可以在连接或恢复期间断开，也可以用「重置语音」取消卡住的一轮并重建会话。日志接收枚举字段、整数计数、本地产生的时间/序号及脱敏 STT 文字（最多 2000 字符）；不写入云端 session ID、原始工具调用 ID、原始异常正文或音频。统计直接消费过滤后的事件，独立于最近 200 条事件窗口，不从旧文件回放。

端侧 MCP 提供八个工具：

| 工具 | 参数 | 结果 |
|---|---|---|
| `duck_nod` | 无 | 点头任务的真实执行记录 |
| `duck_walk_short` | 可选 `duration` | 限时前进任务的执行记录 |
| `duck_turn_left` | 可选 `duration` | 限时原地左转任务的执行记录 |
| `duck_turn_right` | 可选 `duration` | 限时原地右转任务的执行记录 |
| `duck_stop` | 无 | 取消当前动作并发送停止 |
| `duck_get_status` | 无 | 后端类型、连接、当前动作 |
| `duck_flash_step` | 无 | 三秒闪身步编排及执行结果 |
| `duck_bear_shake` | 无 | 三秒狗熊哆嗦毛编排及执行结果 |

一次会话内按 JSON-RPC ID 去重，最多同时处理 32 个工具消息。工具调用不阻塞音频接收，使停止调用可以打断正在等待结果的前进调用。

提示词要求多动作按用户顺序串行调用，失败/取消后停止后续步骤，不将普通转向替换为舞步。这是云端指令约束，不是本地语义规划器；模型仍可能选错工具，统计页显示实际调用供核对。`action_start/end` 仅在去重后的真实调度处产生，使用本地序号关联并捕获原轮次，避免重连和新录音串轮。控制器受理时间不代表首帧物理动作或浏览器画面出现时间。

## 共享物理场景

`simulation.py` 在 Python 进程中运行 MuJoCo CPU 与官方 ONNX 推理，`kind=mujoco`、`physics=true`、`runtime=mujoco_cpu_onnx`；它不是 robotd 适配器，也不复用原创预览的姿态动画。原工作台控制器与场景控制器相互独立。

`POST /api/scenes/start` 显式惰性加载模型；模型文件和策略在外部目录，不打包进应用。球场使用官方 `scene_ball.xml`，双鸭场景用 `MjSpec.attach` 将两个官方 `robot_allcollisions.xml` 放到同一个模型中。控制频率 50 Hz，每次推进 4 个 5 ms 物理步，双鸭共用一次 `mj_step`。策略采用官方 61 维观测、14 维关节输出、默认姿态与 0.5 秒踢球时长；沿用 MJCF 的位置执行器参数，没有接入训练时的动态 BAM 电机模型。

`/api/scenes/actions` 与原工作台共用有界、可取消、按请求 ID 去重的 `MotionController`。场景动作结束前会验证所选脚接触和位移，或者双鸭接触；失败不会返回完成。正常动作的 `target` 可为 a/b/both；停止与场景切换总是清零两只鸭的运动、头部和身体意图。标准动作最长 3 秒；物理场景等待按仿真时间计时，另有「目标时长 + 3 秒」墙钟超时。清零命令不冻结物理世界。

`GET /api/scenes/model` 提供编译后的官方网格和外观，顶点 float32、索引 uint32 以小端 base64 传输，按场景缓存。`/scene-ws` 只发送实际 `geom_xpos/geom_xmat`、接触计数、球位移、双鸭姿态和合唱节拍。浏览器处理后发送文本 `next` 请求最新快照，频率上限 20 Hz；每个连接只保留一帧待确认数据，30 秒没有确认就关闭并由页面重连，避免慢客户端积压旧物理状态。非法确认帧以 1008 关闭。模型响应与状态流使用 revision 配对，避免切换时套用旧模型；revision 属于编译模型，同场景重置复用几何，重启进程重新生成。

Three.js 渲染官方几何，不会用预设踢球动画替换实际关节结果。每次绘制后留出至少 33 ms 空闲时间；检测到 SwiftShader / llvmpipe 等软件渲染器或连续慢帧时关闭阴影，将画布宽度限制为 640 像素，并延长绘制间隔至 100 ms。这样可以为输入、语音和状态处理留出时间，不改变物理步进和接触判定。

`/scene-voice` 复用真实 `VoiceSession`，连接场景控制器，按同源规则保护。和 `/voice` 共用单一语音所有权，不能同时连接同一设备。新增 MCP 工具仅对 MuJoCo 控制器公布：`duck_set_scene`、`duck_kick`（必填 left/right）、`duck_find_companion`、`duck_duo_walk`、`duck_collide`、`duck_chorus`。状态工具剔除渲染网格，避免将大量图形数据送入模型上下文。统计按 `mujoco` 单独筛选。

发现同伴使用仿真真值：距离 ≤1.2 m、相对朝向 ±60°、`mj_ray` 检查遮挡。合唱为应用自己的 3 秒双声部旋律，两只鸭收到相同点头节拍，浏览器两个声部共享 AudioContext；声音依赖用户启用，工具成功表示控制编排完成，不承诺扬声器播放或跨设备同步。不是官方 BLE/duckether 合唱实现。

## 身份与配置

默认私有配置路径是 `~/.secrets/duckking.env`，设备身份位于 `~/.local/share/duckking/identity.json`。设备 ID 使用主机网卡标识派生的稳定伪 MAC，Client ID 使用 UUIDv4；身份文件以 `0600` 权限创建。

没有手工设备凭证时，走 OTA 激活与控制台绑定。浏览器只接收激活码与必要状态，不接收设备 token；网络错误只输出错误类型，避免将含凭证的 URL 或请求头写入界面。

`duckking-setup` 可从 `~/.secrets/lingxi` 读取一行平台 API Key，用于显式创建/选择智能体和绑定。该 Key 不发往设备 OTA 接口，也不作为设备连接 token 使用。实测 OTA 返回官方网关的 `ws://` 地址；客户端仅对已知官方主机升级为 `wss://`，其他公网明文地址仍被拒绝。

## 分工与验证

实际参与者见 [TEAM.md](TEAM.md)，贡献边界见 [CONTRIBUTION_SCOPE.md](CONTRIBUTION_SCOPE.md)，测试与已知限制见 [VALIDATION.md](VALIDATION.md)。

本项目不把 AI 辅助开发记作额外参赛成员，也不把第三方步态策略或官方仿真器记作原创成果。
