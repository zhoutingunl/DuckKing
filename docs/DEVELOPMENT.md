# 本地环境与继续开发

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
uv sync --frozen --python 3.12
cd frontend
npm ci
npm run build
cd ..
uv run --frozen duckking
```

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
| 工作台持续重连 / 本地语音通道连接失败 | 用 Chrome 无痕窗口直接打开本地地址；检查是否有扩展或代理改写 `Origin` 请求头，同源检查不会自动放宽 |
| 灵矽显示等待绑定 | 本机设备身份与其他机器不同，需按 README 绑定本机设备；已有平台 Key 可显式运行 `uv run duckking-setup` |
| 浏览器测试缺少 Chromium | 执行 `npx playwright install chromium`，或配置上述浏览器可执行路径 |

默认 demo 为原创动画预览，不进行物理计算。官方仿真仍需单独按 README 安装和启动，再显式传入 `--backend robotd`。连接失败不会回退到预览。

真实语音必须由用户在界面显式连接，设备凭证仍在仓库外。启动环境或运行自动化测试不构成真实云端、官方物理仿真或实体机器人的本次验收。

## 语音诊断与恢复

页面「交互记录」显示当前页的语音状态、转写和动作；页面记录不跨刷新保留。识别文本同时脱敏写入后端日志，并可从「交互统计」查看。「连接诊断」打开 `/api/voice/diagnostics`，显示当前语音状态、停留秒数、上/下行帧数和本进程最近 200 条诊断事件。关闭页面后，诊断事件仍留在后端。

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

## 交互统计

主页「交互统计」在新标签页打开 `/statistics.html`，保留工作台的语音连接。8765 正式页面和 5173 开发页面均支持此入口；统计页面只读取 `/api/voice/statistics`，不连接或消费云端语音。每 5 秒刷新，支持按后端筛选、选中某轮查看时间线。API 不可达时保留旧值并明确提示过期，不展示伪造的零值。

统计覆盖本次后端进程启动后的最近 500 轮，重启清空；连接异常、重置和重连计数覆盖整个进程，恢复耗时保留最近 500 次成功样本。轮次号跨浏览器会话连续，同一轮的工具结果不会串入下一轮。未提交录音不进入返回率分母；已提交但尚未结束的轮次单独显示。

| 指标 | 口径 |
|---|---|
| 识别返回率 | 非空 STT 的已结束提交轮次 / 全部已结束提交轮次；不是识别准确率 |
| 回复结束率 | 收到正常云端 TTS 结束的轮次 / 全部已结束提交轮次；不是浏览器播放完成率 |
| 动作完成率 | `completed` 动作 / 已结束的已受理动作；包含取消、失败；重试不重复计数 |
| 识别、动作、首音频、回复结束延迟 | 本地收到结束录音 → 对应阶段；以单调时钟计算 P50/P95 和样本数 |
| 动作执行耗时 | 控制器受理 → 本地任务结束，包含配置动作时长和停止确认；不是纯网络延迟 |
| 超时 / 中断 / 异常轮次 | 分开显示；15 秒自动结束录音不算回答超时 |
| 重连成功 / 尝试、恢复耗时 | `recovering` → `ready`；失败不计入成功延迟分布 |

P50/P95 使用最近秩法；缺失数据不补零，结束录音前出现的识别或动作只在时间线显示，避免负延迟扭曲分位数。小样本结果仅供逐轮排查。

识别 CER/WER、意图正确率、动作顺序符合率需要人工标注原话和目标动作，当前不自动打分。页面可核对识别文字和实际动作。这里不测量麦克风、扬声器、浏览器画面呈现、MuJoCo 首次物理响应延迟；动画预览与官方 robotd 样本明确区分。

左右转工具新增后，已有 DuckKing 可执行 `uv run duckking-setup --sync-prompt` 同步串行动作约束。只更新提示词，原文备份为数据目录下 `prompt-backup-*.txt`（0600）。同步后断开旧语音连接再重连以重新发现工具。

## 本地物理实验室

运行 `scripts/setup_scenarios.sh` 安装锁定的 `simulation` 可选依赖、获取官方模型与策略并构建前端，然后运行 `scripts/run_local.sh`。已有服务需要重启以加载新增后端路由；页面入口 `/scenarios.html`。依赖就绪时在 CPU 推理，不安装 CUDA 训练环境。普通 `setup_local.sh` 只保证基础预览与语音依赖，若执行后物理依赖缺失，请重新运行场景安装脚本。

`scripts/fetch_scene_assets.py` 固定 Microduck RL 提交与 Hugging Face 策略提交，并校验策略 SHA-256；拒绝覆盖修改过的上游目录。`DUCKKING_SIM_DIR` 可替换默认 `external/`，下设 `microduck_rl/` 和 `policies/`。上游模型及许可证保持原样，不提交到本仓库。

全量后端测试需要先安装场景依赖和资产；CI 自动执行。只复测场景：

```bash
uv run --frozen --no-sync pytest tests/test_simulation.py
uv run --frozen --no-sync python scripts/verify_scenarios.py
cd frontend
npx playwright test scenarios.spec.js
```

实测脚本默认输出 `.duckking/physics-scenes.json`，包含实际脚球接触、位移、双鸭接触与感知结果，不调用灵矽。真实云端验收需另行连接灵矽；现有证据标明使用系统合成录音，不是人工麦克风录音。

浏览器若显示“物理场景未就绪”，检查安装与资产目录后重启服务；不会自动回退。动作返回“未确认所选脚踢中球”时检查姿态并重置场景。运行速度低于 1× 表示物理时间慢于墙钟时间，不要把仿真耗时当作真人交互的完整端到端延迟。场景物理保持运行，动作限时；停止仅清零意图，不停止重力和惯性。灵矽等待超时也会取消场景动作。
