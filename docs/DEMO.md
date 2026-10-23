# 演示与复现

## 已录制视频

- [真实灵矽语音演示](media/live-linx-voice.mp4)：输入为系统合成中文语音，经过浏览器麦克风采集链路；STT、MCP 工具调用和 TTS 均来自真实灵矽。音轨由实际输入 WAV 与收到的 PCM 按近似采集时间重建。
- [真实灵矽回复音频](media/linx-response.wav)、[对应语音记录](media/live-linx-voice.json)。
- [本地工作台演示](media/local-preview.mp4)：按钮点头、前进、左右转向、Esc 停止、复位及真实执行记录。使用原创动画预览，没有调用灵矽云端。
- [官方物理仿真演示](media/official-simulation.mp4)：从运行中的官方 MuJoCo body 读取真实关节和基座状态，使用同一官方场景重新渲染，记录点头、前进、转向与停止。不是用前端动画代替物理结果。
- [官方仿真对应记录](media/official-simulation.json)：动作执行结果、物理位置采样、最终状态和控制循环。
- [工作台截图](media/workbench.png)。

录制时间与准确验证结果见视频旁的 JSON 和 [VALIDATION.md](VALIDATION.md)。不把合成语音输入描述为真人现场讲话，也不把本地动画预览描述为实体机器人。

## 重录本地演示

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
