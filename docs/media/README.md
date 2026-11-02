# 演示媒体来源

## 第 11 幕灵矽实连竞赛主片

`duckking-competition-live.mp4` 面向竞赛“复刻 Micro Duck 并通过灵矽语音交互”的主题：选择“灵矽实连 · 预录指令”，第 11 幕《桌上不掉拍》使用《两只老虎》，随后介绍本地离线识别、同种子转盘 PPO 对照、CPU 训练记录、持续使用体验、交互统计与测试覆盖率。删去核实后的 12.88 秒等待，末页保留 3 秒静默。各章版本与发布状态见 [主片说明](../DEMO_VIDEO.md)。

演出段保留浏览器实际播放的预录输入、真实灵矽下行声音和本地合成音乐；不是用剪辑旁白替代云端回答。新增的章节解说另标合成来源。截图中的“自动化 / 验收”表示录制方式，所记录的云端请求、工具受理和物理终态均为真实运行。模型及其改编仍遵循 CC BY-NC-SA 4.0；《两只老虎》为本地电子合成传统轮唱，不是灵矽生成歌声。

- `competition-live-selection.png`、`competition-live-running.png`、`competition-live-fall.png`、`competition-live-result.png`：主片录屏取帧，保留模式、曲目及实际状态。
- `competition-experience.png`、`competition-experience-server.png`：同一轮的浏览器/服务器持久化观测；不能相加当作用户数。
- `competition-statistics.png`、`competition-statistics-latency.png`：当前房间的真实识别、工具动作、逐轮时间线和延迟。
- `finals-local-asr-mode.png`、`finals-local-asr-actions.png`、`finals-local-asr-result.png`：新本地识别录屏，实际执行前滚翻和打哈欠，云端音频收发均为零；输入为披露的合成录音。
- `current-balance-running.png`、`current-balance-result.png`：复用原公网第 2 关、种子 0、标准 13 秒真实对照，保留原提交。
- `finals-training-curves.png`、`finals-training-reward.png`、`finals-training-ppo.png`：公网保存的第二关 CPU 训练记录、奖励及公式，新录屏未启动训练。
- `finals-coverage-current.png`、`finals-coverage-scope.png`：公网 62c6784 后端行 95.94%、分支 90.57%，包含单元与集成测试，绑定具体 CI。
- `duckking-competition-live-recording.json`：两轮实际云端调用、单独的本地识别、物理结果、脱敏工具事件、统计与覆盖率快照、逐章来源及媒体摘要；`duckking-competition-live.json`：章节、源片段、原声/解说来源与校验；`competition-live-script.json`：章节解说；`duckking-competition-live-audio-check.json`：当前主片逐章 PCM 与静音检查；`duckking-competition-live-audio-check-before-finals.json`：补充章节前的音轨修复记录，保留其独立文件摘要。


## 2026-11-02 功能导览录屏

`duckking-current-demo.mp4` 为当前公网发布 `62c6784` 的真实 Chrome 录屏剪辑，入口见 [功能导览说明](../PRODUCT_TOUR_VIDEO.md)。首页是脚本动画；物理实验室、四鸭互动、工坊和平衡对照读取实际 MuJoCo/官方策略状态。没有拦截 API、生成假成绩或以预设姿态替代物理结果。旁白单独合成，页面原声未收录；本次没有调用灵矽云端或使用真人麦克风。

- `current-workbench.png`、`current-physics.png`、`current-practice.png`：当前配色、实际踢球／翻滚页面。
- `current-theatre.png`、`current-stage-lineup.png`、`current-studio.png`：第十三幕现场点选与工坊本地排练。
- `current-balance-running.png`、`current-balance-result.png`、`current-balance-custom.png`：本次第 2 关、种子 0 的 13 秒／30 秒试跑，不是离线 100 种子统计。
- `current-training.png`、`current-learning.png`：保存的 CPU 训练曲线、奖励和 PPO 函数说明；不是录制期间新训练。
- `current-demo-recording.json`：版本、实际操作和结果；`duckking-current-demo.json`：章节时刻、源片段、停帧长度、配音来源、文件哈希和解码校验；`current-demo-script.json`：解说文案。

片段只剪去章节之间的准备等待，动作按录制时墙钟速度播放；解说超过片段时长时延长末帧，逐章记录延长量。底部另加 100 px 解说栏，不遮盖或修改网页中的数据。官方模型及改编画面遵循 CC BY-NC-SA 4.0；配色与材质映射来源见 [THIRD_PARTY.md](../../THIRD_PARTY.md)。历史媒体保留原日期，不覆盖成新版证据。

## 2026-10-26 竞赛视频与 2026-10-27 自然配音版

`hackathon-video.png` 是当时实际桌上合唱录屏截图；`hackathon-video.json` 包含源提交、动作验收、20 轮延迟样本、10 路真实云端会话与加载对比。完整 MP4 存放于 GitHub Release，入口和剪辑说明见 [竞赛视频存档](../DEMO_VIDEO_ARCHIVE.md)。视频中的官方模型及改编画面遵循 CC BY-NC-SA 4.0，不由根目录 MIT 许可替代。

`hackathon-video-natural.json` 记录自然配音版的文件摘要、章节起点、合成旁白及原演示保留校验。新版为 4 分 46 秒，使用 Microsoft `zh-CN-XiaoxiaoNeural` 合成章节旁白，不是真人配音或声音克隆。原演示片段、页面声音和实测样本保持来源不变，原始 `hackathon-video.json` 保留用于素材溯源；GitHub 仅提供新版 MP4，观看入口统一指向新版。

## 界面截图版本（2026-10-25）

2026-10-25 从应用提交 `a8a6675309738844caf8956fb669e71c8994ad7c` 的独立本地生产服务实际采集，没有拦截或伪造 API 响应。文件名中的 `current` 是当时的命名；后续新增 UI 不在这些截图中，不能据此推断最新页面逐项布局。

- `workbench.png`：官方模型外观、动作按钮与本地优先选项；首页仍是脚本动画，语音未连接。
- `practice-current.png`：动作练习场实际 MuJoCo 画面，完成一次打哈欠；本地优先已选择，未上传录音。
- `theatre-current.png`：第十二幕的实际运行，鸭 A 站稳独唱、B／C／D 坐着等待；使用随包对白与本地合成音乐，完整四次接唱随后验证完成。
- `current-screenshots.json`：应用代码提交、实际时间、视口和完成结果。截图不证明真实云端语音或实体手机扬声器验收。

上述图片中的模型／模型改编遵循 Pollen Robotics 的 CC BY-NC-SA 4.0。

## 历史媒体与验证资料

- `scene-ball.png`、`scene-duo.png`：物理实验室实际浏览器截图，显示来自 MuJoCo 的官方模型与姿态；模型来源为 Pollen Robotics，截图中的模型展示遵循下述 CC BY-NC-SA 4.0，不使用仓库 MIT 许可替代。
- `physics-scenes.json`：`scripts/verify_scenarios.py` 在本机实际执行的接触、球位移和双鸭动作记录；没有真实云端调用。合唱条目仅验证控制编排，不证明扬声器输出。
- `scene-voice-verification.json`：左右脚语音踢球的真实灵矽 STT / MCP / TTS 记录。输入为系统合成中文录音，动作来自 MuJoCo CPU + 官方 ONNX，不经过 robotd；不含设备身份或凭证。

- `local-preview.mp4`：早期 DuckKing 原创界面与程序化卡通鸭，由当时实际应用录制，没有灵矽云端对话。旧首页图可从 Git 历史查阅；`workbench.png` 为上方 2026-10-25 的官方外观截图。
- `official-simulation.mp4`：读取运行中的官方 MuJoCo body 状态，并用官方 Microduck 场景渲染。机械模型、纹理及场景来源于 [Pollen Robotics microduck_rl](https://github.com/pollen-robotics/microduck_rl)，固定提交 `b02fdea4902c2b93b7d34a83a6f05da4ececb7d3`。
- `official-simulation.json`：该次本地仿真实测记录，不含账号、token 或设备身份。
- `live-linx-voice.mp4`、`live-voice.png`、`live-linx-voice.json`：真实灵矽浏览器联调。输入为系统合成中文语音；识别、工具调用和回复来自实际云端请求。
- `linx-response.wav`：上述请求实际返回的 TTS 音频。视频音轨由实际输入 WAV 与返回 PCM 按近似采集时间重建，不是麦克风现场录音。
- `linx-nod-verification.json`、`linx-physics-verification.json`：分别验证真实灵矽调用预览点头、官方仿真前进；不包含凭证。
- `choreography-preview.mp4`、`choreography-preview.png`：两个机器人改编节目及取消操作的原创动画预览。
- `choreography-physics.mp4`、`choreography-physics.json`：从官方 MuJoCo 实际物理状态录制的组合动作，沿用下述官方模型许可。
- `live-flash-step.*`、`live-bear-shake.*` 及各自回复 WAV：系统合成中文输入经真实灵矽识别和工具调用，实际执行对应节目后的回复。不是本地假服务。

官方模型的许可证见上游 [LICENSE-MODELS.md](https://github.com/pollen-robotics/microduck_rl/blob/b02fdea4902c2b93b7d34a83a6f05da4ececb7d3/LICENSE-MODELS.md)，标注为 CC BY-NC-SA 4.0。官方模型演示视频遵循该许可，不由仓库根目录的原创代码 MIT 许可替代。

媒体录制工具位于 `frontend/scripts/record-demo.mjs`、`frontend/scripts/record-live-voice.mjs` 和 `scripts/record_physics.py`。官方视频是基于实时物理状态的渲染，没有替换成预设走路动画；它也不是实体机器人的录像。云端生成的语音标明其服务来源，不将其描述为真实人物录音。

- `official-home.png`：接入官方网格时的历史 Chrome 截图，使用官方模型网格和本项目脚本动画，不是 MuJoCo 物理画面。
- `beak-holding.png`、`beak-released.png`：嘴部搬运接入时的真实 Chrome 截图；嘴部为 DuckKing 在官方网格上增加的实验性铰链和接触垫，图片中的模型及改编遵循 CC BY-NC-SA 4.0。
- `beak-physics.json`：当时在本机运行 `scripts/verify_scenarios.py` 的 11 个实际动作记录；脚本后续已扩展，包括三步接触搬运，不是实体硬件结果。
- `beak-voice-verification.json`：系统合成中文单句命令经真实灵矽 STT / MCP / TTS，依次完成夹起、搬运、放下。仅验证后端和云端链路；不是人声录音或手机扬声器实听。此轮回复出现内部字段名，随后提示词增加了禁止口述内部字段的要求；本文件保留本轮原始事实。
