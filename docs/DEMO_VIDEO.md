# 灵矽实连竞赛演示视频

[观看／下载 MP4（约 2 分 58 秒）](media/duckking-competition-live.mp4) · [章节与哈希](media/duckking-competition-live.json) · [音轨校验](media/duckking-competition-live-audio-check.json) · [真实调用及物理结果](media/duckking-competition-live-recording.json) · [解说文案](media/competition-live-script.json)

[![第 11 幕：灵矽实连指挥四鸭演出，鸭 D 落地后继续踏步](media/duckking-competition-live.png)](media/duckking-competition-live.mp4)

围绕竞赛题目“智能硬件：复刻一台 Micro Duck，并在其内装上灵矽通过语音交互”，本片选择 **灵矽实连 · 预录指令 → 第 11 幕《桌上不掉拍》→《两只老虎》**，随后展示并解说持续使用体验和交互统计。项目目前只有仿真，没有实体机；视频验证真实灵矽与 MuJoCo 的软件链路。

## 录制版本与声音来源

2026-11-02（北京时间）在本地候选服务录制，应用提交 `c834335044d0e126aa76e4bfc1dbc3a8b72eff55`。真实灵矽 STT、MCP 工具调用和 TTS 均来自实际联网会话，没有使用云端替身。当前公网仍为 `deploy-yzh737-20261101T160751Z` / `62c6784`；**第 11 幕新接线尚未推送或部署**。发布前不能把此片称作当前公网上已可用的新能力。开发服务在持续体验中显示 `development`，精确应用提交由本片记录另行绑定。

- 预录输入是两条 macOS Tingting 系统合成中文口令，不是真人麦克风录音。
- 演出章节保留浏览器实际播放的输入、真实灵矽回复及《两只老虎》原声。歌曲为浏览器合成传统四声部轮唱，没有演唱歌词；开场／收尾角色对白为本地素材。
- 其他章节为 Microsoft `zh-CN-XiaoxiaoNeural` 合成解说，`edge-tts 7.3.1`、`-3%` 语速。解说与灵矽回答分别保留来源。

全片 177.600 秒，1600 × 1100、25 fps、H.264 / AAC（48 kHz、双声道）。网页视口 1600 × 1000，采集帧等比缩放到这一画幅，另加 100 px 章节说明，不改写网页数据。Chrome 每帧原始墙钟时间戳决定帧间隔，再与实际页面音频对齐；画面采样不足时保留上一帧，不补造中间动作。演出不加速，章节之间剪去准备等待；解说超过素材时延长末帧，时长逐章披露。此剪辑不能用于测量精确声画延迟，性能读数应取实际采集记录。

音轨拼接时各章节先独立解码，按时间戳补齐静音间隔，统一为 48 kHz 双声道 PCM 后再合成 AAC，避免单／双声道切换使后续旁白损坏。修复版沿用同一次真实录制及原始旁白，没有重新调用灵矽或更换云端回答。逐章内容比对与静音段检查结果见上方音轨校验。

## 章节

| 时间 | 内容 |
|---|---|
| 00:00 | 让灵矽，真的指挥小鸭开演。 |
| 00:17 | 01 灵矽实连 · 预录指令：桌上不掉拍 |
| 01:45 | 02 持续使用体验：等待有多长，长期留记录 |
| 02:12 | 03 交互统计：从识别原话，追到实际动作结果 |
| 02:37 | 语音指令、物理结果、真实记录，连成一条链。 |

精确切点、源片段和停帧长度见剪辑 JSON。配色、工坊、平衡教练与训练课堂的公网按钮演示另见 [功能导览](PRODUCT_TOUR_VIDEO.md)，旧竞赛片见 [历史存档](DEMO_VIDEO_ARCHIVE.md)。

## 这次真实发生了什么

1. 输入“请开始桌上四鸭合唱表演。”。灵矽选择 `duck_table_show`，工具立即返回 running／受理；浏览器根据真实运行状态播放所选音乐，没有自行补发开演动作。
2. 同一 MuJoCo 世界实际完成 36 秒四鸭表演。鸭 D 在第 17.38 仿真秒离桌、第 17.50 秒接触地面，第 19.12 秒恢复地面舞步；其余三鸭保持桌面支撑。结果为 `completed`、`verified=true`。失足时机是剧情编排，落地及恢复由真实接触和重力验收，不是实体机器人跌落测试。
3. 表演结束后输入“请读取当前状态，告诉我桌上表演的真实结果。”。灵矽实际调用 `duck_get_status` 并据状态回复；两轮均正常 completed，下行音频共 412 帧。开演受理、语音回复结束与物理完成是不同事件，统计保留实际执行终态。
4. 打开持续使用体验，筛选最近 1 小时、自动化／验收、自动剧场、房间 1、MuJoCo。本次为 5 条观测：一条浏览器加载、两条浏览器语音、两条服务器语音；这只对应两轮云端调用，不能说成五次使用或五个用户。随后展示交互统计中的识别原话、工具结果和逐轮时间线。

自动化／验收标签来自 Playwright 触发方式，所用云端服务是真实的。持久化页面用于累计观察等待与失败；本次样本很少，不能据此给出稳定性能承诺。交互统计为本服务会话中的轮次，不能与持久化样本行数混用。两页的时延口径见 [持续使用体验](EXPERIENCE_METRICS.md)。

以下为服务器本轮观测，均以结束录音为零点，不含预录输入时长：

| 轮次 | 识别原话 | 云端识别返回 | 动作受理 | 首段声音 | 状态 |
|---|---|---|---|---|---|
| 1 | 请开始桌上四鸭合唱表演。 | 320 ms | 1730 ms | 2827 ms | completed |
| 2 | 请读取当前状态，告诉我桌上表演的真实结果。 | 264 ms | — | 3515 ms | completed |

物理动作实际耗时约 36.008 秒；受理等待不是该耗时。第二轮状态查询没有新动作，动作受理留空，不补成零。识别返回时间不等于服务商纯计算时间，首段声音也不是扬声器实听延迟。声音帧数只证明实际下行，不代表识别正确率或实体手机体验。

## 重新录制

先按 [README](../README.md) 完成本地构建、原生 Opus 和灵矽设备绑定，用正常配置启动生产服务。录制需要 Chrome、项目的 Playwright 依赖、Python、uv、FFmpeg/ffprobe；房间须空闲并可使用已有绑定。录制器会发送两次真实云端请求，领取所指定的空闲房间，结束时只释放本次使用的物理世界。

```bash
# 仓库根目录；服务示例为本机 8765 端口。
cd frontend
DUCKKING_DEMO_URL=http://127.0.0.1:8765/ \
  DUCKKING_DEMO_ROOM=1 \
  DUCKKING_DEMO_OUTPUT=../.duckking/competition-live-new \
  node scripts/record-tabletop-live.mjs
cd ..
python3 scripts/build_current_demo.py \
  --recording .duckking/competition-live-new/recording.json \
  --script docs/media/competition-live-script.json \
  --work .duckking/competition-live-new-edit \
  --output docs/media/duckking-competition-live.mp4
```

macOS 默认使用 Metal；其他平台使用 Chrome 默认渲染。可用 `DUCKKING_CAPTURE_ANGLE` 显式选择已支持的渲染器、`DUCKKING_BROWSER_CHANNEL` 选择浏览器。录制器检查两轮真实完成、桌上动作终态、云端状态查询、无页面异常及演出采样质量；失败保留原始证据，不用于成功视频。新文案使用新的剪辑工作目录，避免复用旧解说缓存。解说服务不可用时 macOS 可回退 `say / Tingting`，实际来源写入每章记录。

原始帧、页面音频、WebM 和私有配置留在被忽略的本机目录，不提交设备身份或凭证。公开 JSON 去除机器路径，保留动作结果、工具事件、媒体摘要和统计快照。完成后检查模式、曲目、云端回复与物理终态，再更新本页当次读数和海报，不照抄上次结果。失败联调、相关测试和本次录制过程见 [验证记录](VALIDATION.md)。

## 来源与校验

模型及模型改编画面来自 Pollen Robotics，遵循 CC BY-NC-SA 4.0；《两只老虎》为传统 Frère Jacques 旋律的本地电子合成，未复用商业演唱录音。其他来源见 [媒体说明](media/README.md) 和 [THIRD_PARTY.md](../THIRD_PARTY.md)。本片不代表已在实体 Micro Duck 内安装灵矽。

成片通过 FFmpeg 全量音视频解码、逐章音轨内容比对与静音段检查。SHA-256：`3508d5ee04e993f9949bbed6887327f35c5ad36a56c62e92cf961126f1d40572`。
