# 第三方来源与原创边界

`v0` 是空仓库基线；没有导入第三方应用 codebase。本项目新增应用、界面与协议适配代码在之后的 PR 中开发。

## 外部可选仿真

- [Pollen Robotics Microduck](https://github.com/pollen-robotics/microduck)，候选固定提交 `942e58e3aa6dbb28e7037203fff11866122c7567`。
- [Microduck RL](https://github.com/pollen-robotics/microduck_rl)，候选固定提交 `b02fdea4902c2b93b7d34a83a6f05da4ececb7d3`。
- 官方模型、机械文件和策略不进入本仓库的 Git 跟踪文件或 Python 包。本地开发通过脚本在外部目录获取；Linux 发布附件携带固定上游版本、来源清单及模型仓库原始许可，便于目标服务器离线加载。资源适用其上游许可；部分模型含非商业限制。本仓库 MIT 许可不会覆盖这些资源。

## 物理实验室的模型与策略

- Microduck RL 固定为上述 `b02fdea...`。运行时加载官方 MJCF 和 STL；球场使用官方 `scene_ball.xml`，双鸭由官方 `robot_allcollisions.xml` 组合。踢球和双鸭保留机器人几何；首页也复用这些官方视觉网格。嘴部搬运场景的改编见下一条。STL 遵循上游 [CC BY-NC-SA 4.0 模型许可](https://github.com/pollen-robotics/microduck_rl/blob/b02fdea4902c2b93b7d34a83a6f05da4ececb7d3/LICENSE-MODELS.md)，MJCF 与推理参考代码遵循 Apache-2.0。网页注明 Pollen Robotics 和许可。
- `grasp_model.py` 运行时将官方融合头部中的 `jaw` / `jaw_soft` / `bottom_head_shell` 分离到近似铰链，并增加显式接触垫、物品和支架；DuckKing 制作的机械外观改编继续遵循 CC BY-NC-SA 4.0。上游文件保持不变。角度边界参考固定 [官方控制代码](https://github.com/pollen-robotics/microduck/blob/942e58e3aa6dbb28e7037203fff11866122c7567/duck-control/src/model.rs) 的 mouth 开闭值；铰链位置、质量分配、惯量、接触参数不是官方实机标定。
- [官方 microduck-policies](https://huggingface.co/pollen-robotics/microduck-policies/tree/665ae4eb20bfe13bca1ef4ea6d4bb6b4a096e448) 固定提交 `665ae4eb20bfe13bca1ef4ea6d4bb6b4a096e448`，使用 `velstand.onnx`、`ball_kick_left.onnx`、`ball_kick_right.onnx`，许可 Apache-2.0。SHA-256 在 `scripts/fetch_scene_assets.py` 中固定；不重新训练、不声明为原创策略。
- `simulation.py` 的默认关节姿态、观测布局和推理时序参考官方 [`infer_policy.py`](https://github.com/pollen-robotics/microduck_rl/blob/b02fdea4902c2b93b7d34a83a6f05da4ececb7d3/scripts/infer_policy.py)，共享物理世界组合参考官方 `sim/body_server.py`。本项目自行实现动作编排、场景 API、接触验收和 Web 渲染接线，不声称复现完整硬件或电机数字孪生。
- 本地合唱是本项目用 Web Audio 合成的双声部短旋律；没有复制曲目或官方 BLE 合唱实现，不是云端语音。

## 自动演示的对白与四声部乐谱

- 演示场景的角色文案与自动编排由 DuckKing 编写；人类指令/旁白使用 macOS Tingting，小鸭使用 Eddy 中文系统语音加轻量升调和滤波生成，未克隆真人或官方鸭子音色。生成工具为 `scripts/build_demo_audio.py`，生成结果和逐句文本清单位于 `frontend/public/demo-audio/`。实时灵矽模式中的识别、工具调用与回复另由真实云端会话产生。
- 第十幕使用 Pollen Robotics Microduck 固定提交 `942e58e3aa6dbb28e7037203fff11866122c7567` 的原创 `sounds/scores/wistful.duckscore` 开头 16 拍。原谱与 Apache-2.0 许可保存在 `frontend/public/scores/`；声部编队规则参考同提交 `sounds/src/chorale/mod.rs`。DuckKing 自行编写浏览器合成与节目调度，不宣称官方音色、BLE 传输或硬件时钟同步。

## 协议参考

- [灵矽 OTA](https://linx.qiniu.com/docs/xrobot/platform/OTA)
- [灵矽 WebSocket](https://linx.qiniu.com/docs/xrobot/platform/websocket)
- [灵矽端侧 MCP](https://linx.qiniu.com/docs/xrobot/mcp/hardware-mcp)
- [灵矽智能体 API](https://linx.qiniu.com/docs/xrobot/api/agent)（提示词读取、更新与回读校验）

协议适配自行实现；不复制示例中的身份、token 或关闭 TLS 验证的设置。

依赖版本将记录在 `uv.lock` 和前端 `package-lock.json`。旧版程序化卡通预览保留在 Git 历史和旧演示视频中；当前首页使用官方模型网格，关节动画脚本仍由本项目实现，不是物理仿真结果。

- 第十一幕的《夜空中最亮的星》人声与器乐录音由项目用户直接提供。`frontend/public/demo-music/manifest.json` 记录源文件摘要、裁剪/响度/叠唱处理和输出摘要；原录音与歌曲的权利仍归原权利方，不随本仓库 MIT 许可授予。叠唱是用户混音的八度/齐唱处理，包含伴奏，不是独立录制的四声部或音色克隆。另选“原创排练”时由 DuckKing 的原创和弦序列本地合成，不含该歌曲旋律。

- 第十一幕新增《欢乐颂》SATB：依据 Peter Chubb 排印的 [Mutopia Ode to Joy](https://www.mutopiaproject.org/ftp/BeethovenLv/ode/ode.ly) 前八小节，重复一次并将速度改为 108 BPM。原 LilyPond 源文件随 `frontend/public/scores/ode.ly` 提供，声明 Public Domain（Mutopia-2009/08/05-528）。浏览器音色与平衡由 DuckKing 编写，不是官方 MicroDuck 乐谱。
- 《两只老虎》四鸭轮唱采用传统《Frère Jacques》旋律；四声叠置参考 Hautbois 的[公共领域谱例](https://commons.wikimedia.org/wiki/File:Fr_Jacques_4_Vx.jpg)。本项目采用 C 调常见等分节奏、每 8 拍入声、高低八度分配和末尾四拍收束；没有使用现代录音或第三方受限编曲。
