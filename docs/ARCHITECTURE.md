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
| 端侧 MCP | `mcp.py` | JSON-RPC → 工具结果 | 初始化 / 工具发现 / 白名单调用；结果关联原请求 ID |
| 浏览器音频 | `frontend/src/voice.js`、`audio-codec.js` | 麦克风 / 语音事件 | 录音权限、流式重采样、分帧、播放队列与释放麦克风 |
| 三维界面 | `frontend/src/duck.js`、`main.js` | 后端状态 → 画面 / 记录 | 程序化原创形象；连接与能力范围清楚标注 |

## 本地接口

生产 demo 由 FastAPI 提供 `frontend/dist`；开发模式由 Vite 在 5173 提供源文件和热更新，转发 `/api`、`/ws`、`/voice` 到同一 FastAPI 后端。代理保留 Host / Origin，沿用同源校验，不引入替代动作或语音实现。安装与端口配置见 [本地开发指南](DEVELOPMENT.md)。

| 接口 | 用途 |
|---|---|
| `GET /api/health` | 版本、后端类型与服务可达性 |
| `GET /api/state` | 当前动作、后端状态、近期事件 |
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

端侧 MCP 提供六个工具：

| 工具 | 参数 | 结果 |
|---|---|---|
| `duck_nod` | 无 | 点头任务的真实执行记录 |
| `duck_walk_short` | 可选 `duration` | 限时前进任务的执行记录 |
| `duck_stop` | 无 | 取消当前动作并发送停止 |
| `duck_get_status` | 无 | 后端类型、连接、当前动作 |
| `duck_flash_step` | 无 | 三秒闪身步编排及执行结果 |
| `duck_bear_shake` | 无 | 三秒狗熊哆嗦毛编排及执行结果 |

一次会话内按 JSON-RPC ID 去重，最多同时处理 32 个工具消息。工具调用不阻塞音频接收，使停止调用可以打断正在等待结果的前进调用。

## 身份与配置

默认私有配置路径是 `~/.secrets/duckking.env`，设备身份位于 `~/.local/share/duckking/identity.json`。设备 ID 使用主机网卡标识派生的稳定伪 MAC，Client ID 使用 UUIDv4；身份文件以 `0600` 权限创建。

没有手工设备凭证时，走 OTA 激活与控制台绑定。浏览器只接收激活码与必要状态，不接收设备 token；网络错误只输出错误类型，避免将含凭证的 URL 或请求头写入界面。

`duckking-setup` 可从 `~/.secrets/lingxi` 读取一行平台 API Key，用于显式创建/选择智能体和绑定。该 Key 不发往设备 OTA 接口，也不作为设备连接 token 使用。实测 OTA 返回官方网关的 `ws://` 地址；客户端仅对已知官方主机升级为 `wss://`，其他公网明文地址仍被拒绝。

## 分工与验证

实际参与者见 [TEAM.md](TEAM.md)，贡献边界见 [CONTRIBUTION_SCOPE.md](CONTRIBUTION_SCOPE.md)，测试与已知限制见 [VALIDATION.md](VALIDATION.md)。

本项目不把 AI 辅助开发记作额外参赛成员，也不把第三方步态策略或官方仿真器记作原创成果。
