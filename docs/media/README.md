# 演示媒体来源

- `workbench.png`、`local-preview.mp4`：DuckKing 原创界面与程序化鸭子形象，由真实本地应用录制。没有灵矽云端对话。
- `official-simulation.mp4`：读取运行中的官方 MuJoCo body 状态，并用官方 Microduck 场景渲染。机械模型、纹理及场景来源于 [Pollen Robotics microduck_rl](https://github.com/pollen-robotics/microduck_rl)，固定提交 `b02fdea4902c2b93b7d34a83a6f05da4ececb7d3`。
- `official-simulation.json`：本次本地仿真实测记录，不含账号、token 或设备身份。
- `live-linx-voice.mp4`、`live-voice.png`、`live-linx-voice.json`：真实灵矽浏览器联调。输入为系统合成中文语音；识别、工具调用和回复来自实际云端请求。
- `linx-response.wav`：上述请求实际返回的 TTS 音频。视频音轨由实际输入 WAV 与返回 PCM 按近似采集时间重建，不是麦克风现场录音。
- `linx-nod-verification.json`、`linx-physics-verification.json`：分别验证真实灵矽调用预览点头、官方仿真前进；不包含凭证。
- `choreography-preview.mp4`、`choreography-preview.png`：两个机器人改编节目及取消操作的原创动画预览。
- `choreography-physics.mp4`、`choreography-physics.json`：从官方 MuJoCo 实际物理状态录制的组合动作，沿用下述官方模型许可。
- `live-flash-step.*`、`live-bear-shake.*` 及各自回复 WAV：系统合成中文输入经真实灵矽识别和工具调用，实际执行对应节目后的回复。不是本地假服务。

官方模型的许可证见上游 [LICENSE-MODELS.md](https://github.com/pollen-robotics/microduck_rl/blob/b02fdea4902c2b93b7d34a83a6f05da4ececb7d3/LICENSE-MODELS.md)，标注为 CC BY-NC-SA 4.0。官方模型演示视频遵循该许可，不由仓库根目录的原创代码 MIT 许可替代。

媒体录制工具位于 `frontend/scripts/record-demo.mjs`、`frontend/scripts/record-live-voice.mjs` 和 `scripts/record_physics.py`。官方视频是基于实时物理状态的渲染，没有替换成预设走路动画；它也不是实体机器人的录像。云端生成的语音标明其服务来源，不将其描述为真实人物录音。
