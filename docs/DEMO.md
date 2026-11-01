# 演示与复现

## 当前版本视频

竞赛主题下的第 11 幕灵矽实连、《两只老虎》及真实统计见 [竞赛主演示视频](DEMO_VIDEO.md)；配色、PPO 等功能的公网按钮导览见 [功能导览](PRODUCT_TOUR_VIDEO.md)。[2026-10 竞赛视频](DEMO_VIDEO_ARCHIVE.md)及当时的本地／灵矽延迟样本独立保存，不作为新版功能验收。

## 当前演示入口与截图版本

运行步骤见 [README](../README.md)；打开 `/demos.html` 可依次点播十三幕，无需真人讲话。页面保留“自动演示 · 预录对白”与“灵矽实连 · 预录指令”；第 11 幕新增实连开演及结果查询，歌曲仍为本地合成，第 10、12 幕固定本地编排。新接线尚未部署，版本边界见 [主片说明](DEMO_VIDEO.md)。节目说明、三首桌上曲目、四鸭坐站独唱见 [演示剧场](DEMO_THEATRE.md)。手动动作、前滚翻与轮滑在 `/scenarios.html`，也支持服务器本地优先语音。

- [工作台截图](media/current-workbench.png)：当前四种配色与动画预览。
- [动作练习场截图](media/current-practice.png)：实际 MuJoCo 模型和动作结果。
- [四鸭互动截图](media/current-stage-lineup.png)：第十三幕本地点选、集结与成员选择。
- [互动工坊截图](media/current-studio.png)：受限动作的本地排练。
- [平衡对照截图](media/current-balance-result.png)、[训练曲线](media/current-training.png)：同种子对照及保存的 CPU 训练证据。
- [本次采集记录](media/current-demo-recording.json)：发布提交、操作、结果、截图和录制范围。

新版采集来自公网 `62c6784`，不拦截 API、不改写动作或画面状态。本次通过按钮和本地排练操作，没有把它们写成灵矽现场理解。录制当次结果与离线训练评估分开计数。旧的 `workbench.png`、`practice-current.png`、`theatre-current.png` 和 `current-screenshots.json` 继续保存 2026-10-25 的 `a8a6675` 来源；文件名中的 current 仅为当时命名。

平衡实验入口为 `/balance.html`，独立于五类物理实验室和十三幕节目。它提供三关、相同种子的左右对照与 6–33 秒本地试跑；参数、失败后的真实跌落展示和训练/评估口径见 [平衡教练](PPO_BALANCE_COACH.md)。公网默认不接受训练任务。本轮没有新增真人麦克风、云端平衡口令或实体机验收。

## 历史录制视频

- [闪身步与狗熊哆嗦毛编排、物理和真实语音演示](CHOREOGRAPHY.md)。
- [真实灵矽语音演示](media/live-linx-voice.mp4)：输入为系统合成中文语音，经过浏览器麦克风采集链路；STT、MCP 工具调用和 TTS 均来自真实灵矽。音轨由实际输入 WAV 与收到的 PCM 按近似采集时间重建。
- [真实灵矽回复音频](media/linx-response.wav)、[对应语音记录](media/live-linx-voice.json)。
- [本地工作台演示](media/local-preview.mp4)：按钮点头、前进、左右转向、Esc 停止、复位及真实执行记录。录制于早期程序化卡通外观版本，没有调用灵矽云端；当前首页已使用官方网格。
- [官方物理仿真演示](media/official-simulation.mp4)：从运行中的官方 MuJoCo body 读取真实关节和基座状态，使用同一官方场景重新渲染，记录点头、前进、转向与停止。不是用前端动画代替物理结果。
- [官方仿真对应记录](media/official-simulation.json)：动作执行结果、物理位置采样、最终状态和控制循环。

这些视频保留历史 UI，不用于说明当前页面布局。录制时间与准确验证结果见视频旁的 JSON 和 [VALIDATION.md](VALIDATION.md)。不把合成语音输入描述为真人现场讲话，也不把本地动画预览描述为实体机器人。

## 重录本地演示

新版全片使用 [record-current-demo.mjs](../frontend/scripts/record-current-demo.mjs) 和 [build_current_demo.py](../scripts/build_current_demo.py)。精确命令、依赖、配音与剪辑口径见 [新版视频说明](DEMO_VIDEO.md#重新录制)。下面的 `record:demo` 仍只生成历史用途的首页短片，不会自动覆盖新版全片。

在一个终端启动默认预览：

```bash
uv run duckking
```

在另一个终端录制，需要已安装 ffmpeg 和 Playwright Chromium：

```bash
cd frontend
npx playwright install chromium
npm run record:demo
```

脚本通过真实页面按钮调用本地后端，不向日志填入虚构的语音识别或云端回复。输出写入 `docs/media/`。

## 重录官方物理仿真

先按 README 启动官方仿真并保持终端运行，再启动适配后端：

```bash
uv run duckking --backend robotd --port 8767
```

使用 `microduck_rl` 的 Python 环境录制（它包含 MuJoCo 和 NumPy）：

```bash
external/microduck_rl/.venv/bin/python scripts/record_physics.py \
  --rl-root external/microduck_rl --api-port 8767
```

若上游源码在其他目录，替换两处路径。脚本只对本机官方 body 读取物理状态；动作全部通过 DuckKing API 发出。视频中的场景模型属于上游项目，许可见 [媒体说明](media/README.md)。

## 重录真实语音演示

已完成设备绑定后，准备一段单声道中文语音 WAV，末尾补充至少 5 秒静音；脚本使用前 3 秒作为按键录音。启动默认工作台后执行：

```bash
cd frontend
DUCKKING_TEST_AUDIO=/absolute/path/to/speech-with-silence.wav npm run record:live
```

这是显式的真实云端测试，会使用已绑定账号的额度；不属于 CI。输出视频、回复 WAV 和脱敏语音记录。输入音轨和真实返回 PCM 按采集时间重建，视频说明中保留这一点。

## 后续真人语音验收

1. 在工作台连接灵矽，使用激活码在控制台绑定到智能体。
2. 确认智能体启用支持工具调用的模型，并保存配置、重新连接。
3. 说“你是谁”，确认真实 STT、回答文本和下行语音。
4. 说“点点头”“向前走一点”“停止”，对照 MCP 结果和动作状态。
5. 连续执行十轮，验证断线提示、重新连接、停止和取消。
6. 录制真实语音版本，并通过新的 PR 更新验证记录；不要覆盖旧结果并冒称早已验证。

账号和绑定已完成，合成语音版本已经通过。连续十轮及真人环境测试仍需实际执行后再计入通过项。
