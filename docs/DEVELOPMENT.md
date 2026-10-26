# 本地环境与继续开发

## YZH737 HTTPS 入口

`https://ztmonitor.qbox.net/duckking/` 通过 ai_gateway 转发至独立的 DuckKing loopback 服务。网关只需首次发布新增路由，后续 DuckKing 发布沿用 8765 端口，重启 `duckking.service` 即可，无需重启 ai_gateway。

当前域名前置代理移除了 WebSocket Upgrade。前端读取 `_gateway/capabilities`，在该入口使用 HTTPS 长轮询通道；网关内部依然连接真实 DuckKing WebSocket，PCM 逐帧 base64 传输，命令按序发送，不重试已发送的录音或动作。本地与支持 Upgrade 的入口继续使用原生 WebSocket。通道失败按原有状态恢复逻辑处理，不切换为伪造云端响应。HTTP 通道增加一次请求调度开销，交互统计中的后端耗时不包含完整浏览器网络往返。

发布验证脚本 `scripts/release_smoke.py --url https://ztmonitor.qbox.net/duckking/ --commit <commit>` 自动识别传输方式，检查页面资源、真实状态与语音通道握手、有限停止动作；不会连接灵矽云端。服务重启后状态流可重连，语音由用户重新点击连接，未完成录音不重放。服务器独立设备绑定与真实云端语音验收仍需单独完成。

物理场景使用无损压缩的 `/api/scenes/model.dkm.gz`，按场景 revision 在当前页面复用几何；重置不重复下载。旧 JSON 接口约 10 MB、曾耗时约 21 秒的结果属于优化前记录。模型请求单独允许 60 秒；冷启动仍包含原生模型编译与实际网络传输，这个超时不改变语音看门狗或场景状态确认期限。

首页官方外观采用独立的无损压缩资源，约 3.6 MB，所有房间共享浏览器持久缓存。页面“交互记录”的“模型加载”行显示本次耗时；浏览器控制台搜索 `DuckKing:model-load` 可查看分阶段时间和缓存来源。Linux 服务日志可用 `journalctl -u duckking.service --since '10 minutes ago' | rg 'official_model_(load|asset_built)'` 查看客户端上报与服务端准备时间。浏览器存储受限时仍能正常加载，但后续访问可能重新下载。强制刷新页面不一定清除 CacheStorage；内容版本更新会自动更换模型，开发排障可在浏览器应用面板删除 `duckking-official-model-v1` 缓存。

## 安装和运行 demo

需要 `uv`、Node.js 22.12+ 和 npm。仓库的 `.python-version` 固定默认 Python 为 3.12，uv 可以下载该解释器，不必更换系统 Python。

在仓库根目录运行：

```bash
scripts/setup_local.sh
scripts/run_local.sh
```

打开 <http://127.0.0.1:8765>。初始化按 `uv.lock` 和 `frontend/package-lock.json` 安装依赖并构建页面，可重复运行；不会升级锁定版本、连接云端或创建平台智能体。Opus 不可用时提示安装方法，但不阻止动画预览。

启动脚本在前台运行，Ctrl+C 交给应用正常关闭、停止动作。它可从其他工作目录通过绝对路径启动。启动时不会安装依赖或重新构建；拉取更新后再次执行初始化脚本。

等价的手动安装命令为：

```bash
uv sync --frozen --python 3.12 --extra simulation
uv run --frozen python scripts/fetch_scene_assets.py
cd frontend
npm ci
npm run build
cd ..
uv run --frozen duckking
```

首页官方外观和物理实验室均需要上述固定模型资源。资源缺失时页面明确提示安装失败，不会退回旧卡通形象。

## 前端热更新

保持上述后端运行，在第二个终端执行：

```bash
cd frontend
npm run dev
```

打开 <http://127.0.0.1:5173>。Vite 读取前端源文件，修改 JS / CSS 后自动更新页面；8765 仍提供上次构建的 demo。修改 Python 代码后需重启后端。希望将前端修改显示在 8765 时，执行 `cd frontend && npm run build`，然后刷新页面。

Vite 只监听 `127.0.0.1`；`/api`、`/ws`、`/voice` 转发到本地后端。Host 和 Origin 原样保留，因此后端继续检查同源请求。开发模式没有绕过安全校验，也不会在后端连接失败时创建另一个预览后端。实现参考 [Vite server.proxy 文档](https://vite.dev/config/server-options#server-proxy)。

自定义端口时，两个终端分别执行：

```bash
# 终端一：仓库根目录
scripts/run_local.sh --port 8766

# 终端二：frontend 目录
DUCKKING_API_PORT=8766 npm run dev -- --port 5174
```

随后访问 <http://127.0.0.1:5174>。开发端口被占用时会直接报错，不会悄悄切换。`DUCKKING_API_PORT` 只接受 1–65535 的整数。

## 检查

```bash
uv run ruff check src tests
scripts/setup_local_asr.sh
uv run pytest --cov --cov-report=json --cov-report=html
uv run python scripts/check_coverage.py
cd frontend
npm run build
npm run test:unit
npx playwright install chromium
npm run test:e2e
npm run test:e2e:dev
```

正式构建测试使用独立后端端口 8875；开发测试额外使用 Vite 端口 8876。两个命令依次执行，不复用已经运行的工作台；需要改端口时设置 `DUCKKING_TEST_PORT` / `DUCKKING_TEST_DEV_PORT`。已有兼容 Chrome 时可通过 `PLAYWRIGHT_CHROMIUM_EXECUTABLE=/absolute/path/to/chrome` 指定浏览器。

开发测试重复动作、取消、移动端和音频测试，并验证真实代理的 HTTP / WebSocket 同源拒绝、动作时长限制、未连接云端时的语音协议错误，以及后端不可用时的明确失败。音频测试使用本地协议替身，不消耗真实灵矽额度。报告分别保存在 `frontend/playwright-report/production/` 和 `frontend/playwright-report/development/`，失败截图和 trace 位于对应的 `frontend/test-results/` 子目录。

## 排障与能力边界

| 现象 | 处理 |
|---|---|
| 缺少依赖 / 构建，或根页面返回 503 | 执行 `scripts/setup_local.sh`；确认 Node.js 版本满足要求 |
| 8765 被占用 | 关闭自己启动的旧服务，或通过 `--port` 指定其他端口 |
| 5173 页面能打开，但动作报错 / 状态持续重连 | 确认后端正在运行，且 `DUCKKING_API_PORT` 与后端端口相同 |
| 修改前端后 demo 未变化 | 使用 5173 开发页面，或重新构建后刷新 8765 页面 |
| 语音提示缺少 libopus | macOS：`brew install opus`；Ubuntu：`sudo apt-get install libopus0` |
| 工作台持续重连 / 场景连接未建立 / 本地语音通道连接失败 | 用 Chrome 无痕窗口直接打开本地地址；检查是否有扩展或代理改写 `Origin` 请求头，同源检查不会自动放宽。场景加载和按钮操作无需连接灵矽 |
| 灵矽显示等待绑定 | 本机设备身份与其他机器不同，需按 README 绑定本机设备；已有平台 Key 可显式运行 `uv run duckking-setup` |
| 浏览器测试缺少 Chromium | 执行 `npx playwright install chromium`，或配置上述浏览器可执行路径 |

默认 demo 为使用官方外观的脚本动画预览，不进行物理计算。官方仿真仍需单独按 README 安装和启动，再显式传入 `--backend robotd`。连接失败不会回退到预览。

真实语音必须由用户在界面显式连接，设备凭证仍在仓库外。启动环境或运行自动化测试不构成真实云端、官方物理仿真或实体机器人的本次验收。

## 语音诊断与恢复

默认预览服务提供两个独立房间。首页未指定房间时，按当前画面连接和语音占用分配空闲房间，并将 `?room=1` 或 `?room=2` 写入地址；短暂的 10 秒预留避免同时开页分配到同一房间。顶部可以显式选择房间，工作台、物理实验室、统计及诊断链接保留房间号。房间是公开演示空间，不是登录隔离的私人账户；知道房间号的页面可以查看同一房间。

房间按需创建，默认最多 10 个，页面提供“新建房间”和已有房间链接；未指定 `room` 的新页面优先分配空闲房间。各房间有独立预览控制器、语音、设备身份、日志和统计。物理场景另设并发上限，默认 4 个；达到上限明确拒绝新增世界，首页预览和语音仍可使用。场景页“释放场景”停止并释放本房间世界，必须先断开语音。默认无人查看、没有语音且没有执行中动作超过 5 分钟后回收；房间 1/2 保留入口但释放物理世界，新增房间释放整个运行状态。共享链接可加入同一公开房间，不是私人账户；robotd 仅支持房间 1。

配置 `DUCKKING_MAX_ROOMS`（默认 10，最大 32）、`DUCKKING_MAX_PHYSICS_ROOMS`（默认 4）和 `DUCKKING_ROOM_IDLE_SECONDS`（默认 300）。空房间只创建轻量控制器，不初始化 MuJoCo。离线 ASR 工作进程仍限制两个未完成任务；拥塞或超时会明确转交灵矽，不保证十人同时离线推理。

房间 1 保留已有设备绑定，其余身份和日志位于数据目录 `rooms/<编号>/`。管理员逐个运行 `uv run duckking-setup --room 3` 等初始化命令，最多到配置的房间上限；独立设备可关联同一个 DuckKing 智能体，身份和 token 不复制。手工配置使用该目录的 `linx.env`，权限 600。回收运行房间不删除私有身份，所以编号再次创建仍可使用已绑定设备；统计从新的运行实例开始。页面不会读取平台管理 Key 或自动创建云端设备。

主动断开会关闭浏览器语音通道并释放名额；云端连接失败或结束也会释放，原页面可以继续打开。活跃浏览器每 10 秒发一次心跳；45 秒没有收到浏览器消息时回收失联会话，并取消语音工具和动作。关闭页面会立即请求释放；浏览器崩溃、冻结或网络中断无法发送关闭时由超时兜底。这个期限独立于云端回答看门狗，恢复后不会自动开始或重发录音。

页面「交互记录」显示当前页的语音状态、转写和动作；页面记录不跨刷新保留。识别文本同时脱敏写入后端日志，并可从「交互统计」查看。「连接诊断」打开 `/api/voice/diagnostics`，显示当前语音状态、停留秒数、上/下行帧数和本进程最近 200 条诊断事件。关闭页面后，诊断事件仍留在后端。

场景握手被同源校验拒绝时，后端日志标记 `scene_ws_rejected: origin_mismatch`（HTTP 403）；30 秒未收到状态确认时标记 `scene_ws_closed: acknowledgement_timeout`。两者不同，延长确认超时不能解决握手被拒绝。日志不输出原始请求头。页面在收到有效状态前禁用场景操作，提示本地服务、地址与浏览器扩展检查；重试间隔逐步延长至 10 秒，恢复后清理连接提示并启用操作。

跨重启查看事件与识别文本日志：

```bash
tail -n 50 ~/.local/share/duckking/voice.jsonl
```

若设置 `DUCKKING_DATA_DIR`，日志位于对应目录。日志权限为 `0600`，单文件最多 256 KiB，另保留一个 `voice.jsonl.1` 备份。`stt.text` 保存识别内容（最多 2000 字符）；过滤当前连接的 token、设备/云端标识、常见 MAC/UUID、URL 及带标签的凭据。正常口语保留，不能将这种规则过滤当成任意个人信息识别器。其他事件不保存转写正文，不保存录音、激活码或原始异常内容；异常类型使用白名单。磁盘写入失败时内存诊断继续工作，接口返回 `storage_ok=false`。早期只记长度的日志无法补回识别原文。

| 事件 / 字段 | 排查含义 |
|---|---|
| `listen_start` → `uplink_first_frame` → `listen_stop` | 是否实际收到麦克风数据；结束时 `uplink_frames=0` 表示没有完整音频帧 |
| `stt` / `text` / `text_chars` | 脱敏识别文本与原文本长度，便于核对“听错”还是“选错工具” |
| `tool_start` / `tool_end` | 白名单工具名、协议方法和结果类别，不保存参数或调用 ID |
| `action_start` / `action_end` | 去重后真正受理的动作及执行结果，本地 `call` 序号关联起止 |
| `tts_start` / `downlink_first_frame` / `tts_stop` | 是否开始回答、实际收到音频、正常结束 |
| `timeout` / `reason` | `response_idle` 等待无进展；`playback_idle` 回答无进展；`turn_limit` 整轮超时；`recording_limit` 达到录音上限 |
| `state=recovering` → `ready` 或 `error` | 自动/手动重建连接的实际结果 |

等待回答 20 秒无有效进展、回答 15 秒无新数据，或整轮超过 60 秒，会关闭旧会话并自动重连一次。重连不重发录音、不继续录音；工具任务会被取消，动作先停止，再等待网络关闭。连接整体最多等待 35 秒。仍失败时界面显示错误，用户可手动连接；「重置语音」可立即结束卡住的一轮。

浏览器自动化测试使用 `.duckking/browser-tests/` 的独立数据目录和无云端凭证的本地测试配置，不把协议替身记录混入用户的语音日志。

## 移动端声音排查

麦克风权限只说明可以采集输入；小鸭能执行语音命令，不代表手机已经允许或正确路由回复声音。iPhone 的 Chrome / 企业微信中，刷新到当前版本后，在页面前台点「启用 / 测试声音」。这个按钮播放本地短提示音，无需连接灵矽，不上传录音。

- 本地提示音也听不到：播放时调高手机媒体音量，检查静音开关 / 静音模式、蓝牙耳机及声音输出位置；回到前台后再点一次。
- 提示音有声、回复无声：展开「声音诊断」，查看收到、提交播放、播放结束的帧数和音频峰值。`suspended` / `interrupted` 表示浏览器声音上下文尚未恢复；再点启用按钮，随后重新说一轮命令。
- 收到帧数为零：检查「连接诊断」的云端下行计数与语音错误。收到帧数大于零但未提交播放，通常还在等待播放恢复或正在录音。播放结束计数增长且峰值非零，说明非静音数据已经过浏览器播放链路，仍需确认手机实际输出。

服务器 `/api/voice/diagnostics?room=1`（或 `2`）包含最近的 `browser_audio` 快照和事件。它是客户端报告，不能替代手机扬声器实听；断开后保留最后报告，新的语音拥有者连接时清空。音频因播放受限积压超过 12 秒 / 300 帧会丢弃并明确提示，打断、重置、断开同时清理待播内容。系统切后台或锁屏后仍可能暂停音频，项目不保证后台对话。从浏览器前进 / 后退缓存恢复时会重新加载页面，仍需用户主动连接，不会自动录音。

实现参考 [Chrome Web Audio 自动播放策略](https://developer.chrome.com/blog/autoplay) 与 [W3C Audio Session 草案](https://www.w3.org/TR/audio-session/)。Audio Session API 为可选能力，未支持的浏览器不会因此无法录音或连接。自动化中的受控暂停状态和桌面 Chrome 移动视口不等于真实 iPhone / 企业微信测试；手机最终出声需在真机确认。

## 交互统计

主页「交互统计」在新标签页打开 `/statistics.html`，保留工作台的语音连接。8765 正式页面和 5173 开发页面均支持此入口；统计页面只读取 `/api/voice/statistics`，不连接或消费云端语音。每 5 秒刷新，支持按后端筛选、选中某轮查看时间线。API 不可达时保留旧值并明确提示过期，不展示伪造的零值。

统计覆盖本次后端进程启动后的最近 500 轮，重启清空；连接异常、重置和重连计数覆盖整个进程，恢复耗时保留最近 500 次成功样本。轮次号跨浏览器会话连续，同一轮的工具结果不会串入下一轮。未提交录音不进入返回率分母；已提交但尚未结束的轮次单独显示。

| 指标 | 口径 |
|---|---|
| 识别返回率 | 非空 STT 的已结束提交轮次 / 全部已结束提交轮次；不是识别准确率 |
| 回复结束率 | 收到正常云端 TTS 结束的轮次 / 已结束的云端提交轮次；本地命中不计入分母，也不是浏览器播放完成率 |
| 动作完成率 | `completed` 动作 / 已结束的已受理动作；包含取消、失败；重试不重复计数 |
| 识别、动作、首音频、回复结束延迟 | 本地收到结束录音 → 对应阶段；以单调时钟计算 P50/P95 和样本数 |
| 动作执行耗时 | 控制器受理 → 本地任务结束，包含配置动作时长和停止确认；不是纯网络延迟 |
| 超时 / 中断 / 异常轮次 | 分开显示；15 秒自动结束录音不算回答超时 |
| 重连成功 / 尝试、恢复耗时 | `recovering` → `ready`；失败不计入成功延迟分布 |

P50/P95 使用最近秩法；缺失数据不补零，结束录音前出现的识别或动作只在时间线显示，避免负延迟扭曲分位数。小样本结果仅供逐轮排查。

识别 CER/WER、意图正确率、动作顺序符合率需要人工标注原话和目标动作，当前不自动打分。页面可核对识别文字和实际动作。这里不测量麦克风、扬声器、浏览器画面呈现、MuJoCo 首次物理响应延迟；动画预览、官方 robotd 与物理实验室 `mujoco` 样本明确区分。

左右转工具新增后，已有 DuckKing 可执行 `uv run duckking-setup --sync-prompt` 同步串行动作约束。只更新提示词，原文备份为数据目录下 `prompt-backup-*.txt`（0600）。同步后断开旧语音连接再重连以重新发现工具。

## 本地物理实验室

运行 `scripts/setup_scenarios.sh` 安装锁定的 `simulation` 可选依赖、获取官方模型与策略并构建前端，然后运行 `scripts/run_local.sh`。已有服务需要重启以加载新增后端路由；页面入口 `/scenarios.html`。依赖就绪时在 CPU 推理，不安装 CUDA 训练环境。`setup_local.sh` 现在也安装这些资源，以显示首页官方模型；只启动首页不会运行物理循环。

`scripts/fetch_scene_assets.py` 固定 Microduck RL 提交与 Hugging Face 策略提交，并校验策略 SHA-256；拒绝覆盖修改过的上游目录。`DUCKKING_SIM_DIR` 可替换默认 `external/`，下设 `microduck_rl/` 和 `policies/`。上游模型及许可证保持原样，不提交到本仓库。

全量后端测试需要先安装场景依赖和资产；CI 自动执行。只复测场景：

```bash
uv run --frozen --no-sync pytest tests/test_simulation.py
uv run --frozen --no-sync python scripts/verify_scenarios.py
cd frontend
npx playwright test scenarios.spec.js
```

实测脚本默认输出 `.duckking/physics-scenes.json`，包含实际脚球接触、位移、双鸭接触与感知结果，不调用灵矽。真实云端验收需另行连接灵矽；现有证据标明使用系统合成录音，不是人工麦克风录音。

浏览器若显示“物理场景未就绪”，检查安装与资产目录后重启服务；不会自动回退。动作返回“未确认所选脚踢中球”时检查姿态并重置场景。运行速度低于 1× 表示物理时间慢于墙钟时间，不要把仿真耗时当作真人交互的完整端到端延迟。场景物理保持运行，动作限时；停止清零移动意图，不停止重力和惯性；嘴部搬运会保留已建立的夹持，重置才恢复初始物品布置。灵矽等待超时也会取消场景动作。

### 打断回复并说新命令

思考、回答或本地仍有待播音频时，原说话按钮显示“打断并说话”。按住按钮或空格会立即清空当前页面播放队列，再采集新命令，松开后发送；无需先点击重置语音。这是显式按键打断，不是持续监听或自动检测人声的全双工。

后端发送官方 `abort`，取消旧工具、停止本房间动作并关闭旧云端连接，再建立新连接。采用新连接是因为下行二进制音频与设备工具调用没有可用于逐轮判别的 generation，单独发送 abort 无法可靠丢弃迟到的旧动作。浏览器和后端另有本地 generation，屏蔽已在 HTTPS 通道中排队的旧音频、文字及状态。

切换期间只在内存中暂存新录音，最多 250 帧 / 15 秒 PCM16（480 KB）；新连接就绪后按顺序发送一次。断开、连接失败或需要重新绑定时立即丢弃，不重放旧录音。开始录音无需等待新握手，但回复会增加一次云端重连开销，旧会话上下文不保证保留；麦克风仍需用户授权。日志将被打断轮次记为 interrupted，另一个房间的会话与动作不受影响。

HTTP API 用 `room=<房间编号>` 查询参数选择房间（省略时兼容房间 1）。四个 WebSocket 的首帧为 `{"type":"join_room","room":"2"}`，须在 5 秒内发送；本地协议客户端也可显式使用 `?room=2`。因此无需修改 ai_gateway 的固定端点白名单或重启网关。旧浏览器页面需刷新以使用此握手。

嘴部搬运专项：`uv run --frozen --no-sync pytest tests/test_grasp.py`。包含实际接触、不同等待时间的完整流程、抓空、执行器意外张嘴后的滑落、取消、推进超时、无接物台和非法参数；不是用预设轨迹替代刚体接触。浏览器验收在 `frontend/tests/official-model.spec.js`，同时检查首页官方网格加载 / 失败重试与真实搬运按钮。

## 可选服务器离线语音

运行 `scripts/setup_local_asr.sh` 安装固定版本 sherpa-onnx 和校验过的 SenseVoiceSmall INT8 权重。在一个终端运行 `uv run --frozen --no-sync duckking-asr`，另一个运行 `DUCKKING_LOCAL_ASR=1 scripts/run_local.sh`，页面选择“本地优先”。worker 仅监听 127.0.0.1:8768；模型只需首次下载，日常识别不联网。未匹配的指令仍需已配置的灵矽设备和网络。

`uv run --extra local-asr python scripts/verify_local_asr.py` 对披露来源的合成录音做真实推理验证。可说“向前走再向左转再向右转”“后退两秒然后点头”。“不要前进”“前进然后去火星”整句交云端。动作练习场的具体步骤是：打开 `/scenarios.html` → 加载“动作练习场” → 选择“本地优先” → 点“启用语音” → 按住说“前滚翻，再打个哈欠”。“向后退，再向左挪，再向右挪”也可整句匹配。场景未加载时明确提示先加载；无需先建立灵矽云端连接。本地确认是提示音和文字，聊天回复由灵矽提供。

## CI 并行分组

本地完整回归命令保持不变。定位慢项可在 `frontend` 中执行 `npx playwright test --grep @journey`（完整十二幕），或 `npx playwright test --grep-invert @journey`（其余检查）；设置 `DUCKKING_TEST_DEV=1` 切到开发模式。`node scripts/verify-ci-groups.mjs` 仅枚举两种模式的测试，确认两组并集等于全量且没有交集。

GitHub Actions 的四组浏览器检查在四台独立 runner 上运行，避免在同一个物理世界增加 workers 导致冲突。后端与前端单元检查同时启动，`quality` 汇总检查拒绝失败、取消或跳过的依赖。`backend-coverage` artifact 保存后端报告及绑定提交的摘要，其余四个 artifact 分别保留对应浏览器 HTML、截图和 trace。固定模型会缓存，但每次仍运行现有摘要／版本校验。

串行基准 [CI 40192976186](https://github.com/zhoutingunl/DuckKing/actions/runs/40192976186) 总耗时 33 分 35 秒（约 34 分钟）：后端约 5.2 分钟，生产／开发浏览器约 13.6／13.8 分钟。首轮并行实测 [CI 40202356453](https://github.com/zhoutingunl/DuckKing/actions/runs/40202356453) 全部通过，总耗时 **9 分 21 秒**（14:27:58—14:37:19 UTC），约缩短 72%。后端 6:03、前端 0:12，生产完整十二幕／其余检查 5:12／6:20，开发完整十二幕／其余检查 6:08／9:11。当前最长路径是开发模式其余浏览器检查；模型准备分别约数秒到十余秒，不是主要瓶颈。

这是一次不同提交的实际运行对照，并非固定硬件基准；runner 调度、冷缓存与物理仿真负载会影响后续耗时。没有删减测试、放宽物理验收条件或跳过失败项。发布包上传是 CI 之外的部署步骤，不包含在上述时间中。

## 持续统计的运维

[使用体验页面](EXPERIENCE_METRICS.md)使用数据目录下 `experience.sqlite3`，与发布包分离，普通重启和升级保留。备份使用 SQLite backup API；恢复时先停止 DuckKing，保留文件 0600 权限及服务用户所有权。页面会报告写盘错误和本次启动丢弃量。自动化验收使用 `measurement=verification`（Playwright 自动标记），旧脚本无上下文则进入“未标记的调用”；不要向日常分组灌入固定合成口令基准。
