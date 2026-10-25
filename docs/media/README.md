# 演示媒体来源

## 当前界面截图

2026-10-25 从当前代码的独立本地生产服务实际采集，没有拦截或伪造 API 响应。

- `workbench.png`：官方模型外观、动作按钮与本地优先选项；首页仍是脚本动画，语音未连接。
- `practice-current.png`：动作练习场实际 MuJoCo 画面，完成一次打哈欠；本地优先已选择，未上传录音。
- `theatre-current.png`：第十二幕的实际运行，鸭 A 站稳独唱、B／C／D 坐着等待；使用随包对白与本地合成音乐，完整四次接唱随后验证完成。
- `current-screenshots.json`：应用代码提交、实际时间、视口和完成结果。截图不证明真实云端语音或实体手机扬声器验收。

上述图片中的模型／模型改编遵循 Pollen Robotics 的 CC BY-NC-SA 4.0。

## 历史媒体与验证资料

- `scene-ball.png`、`scene-duo.png`：物理实验室实际浏览器截图，显示来自 MuJoCo 的官方模型与姿态；模型来源为 Pollen Robotics，截图中的模型展示遵循下述 CC BY-NC-SA 4.0，不使用仓库 MIT 许可替代。
- `physics-scenes.json`：`scripts/verify_scenarios.py` 在本机实际执行的接触、球位移和双鸭动作记录；没有真实云端调用。合唱条目仅验证控制编排，不证明扬声器输出。
- `scene-voice-verification.json`：左右脚语音踢球的真实灵矽 STT / MCP / TTS 记录。输入为系统合成中文录音，动作来自 MuJoCo CPU + 官方 ONNX，不经过 robotd；不含设备身份或凭证。

- `local-preview.mp4`：早期 DuckKing 原创界面与程序化卡通鸭，由当时实际应用录制，没有灵矽云端对话。旧首页图可从 Git 历史查阅；`workbench.png` 已更新为上方当前截图。
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
