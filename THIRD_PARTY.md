# 第三方来源与原创边界

`v0` 是空仓库基线；没有导入第三方应用 codebase。本项目新增应用、界面与协议适配代码在之后的 PR 中开发。

## 外部可选仿真

- [Pollen Robotics Microduck](https://github.com/pollen-robotics/microduck)，候选固定提交 `942e58e3aa6dbb28e7037203fff11866122c7567`。
- [Microduck RL](https://github.com/pollen-robotics/microduck_rl)，候选固定提交 `b02fdea4902c2b93b7d34a83a6f05da4ececb7d3`。
- 官方模型、机械文件和策略不包含在本仓库中。由用户在外部目录获取，适用其上游许可；部分模型含非商业限制。本仓库 MIT 许可不会覆盖这些资源。

## 物理实验室的模型与策略

- Microduck RL 固定为上述 `b02fdea...`。运行时加载官方 MJCF 和 STL；球场使用官方 `scene_ball.xml`，双鸭由官方 `robot_allcollisions.xml` 组合。机器人几何未修改。STL 遵循上游 [CC BY-NC-SA 4.0 模型许可](https://github.com/pollen-robotics/microduck_rl/blob/b02fdea4902c2b93b7d34a83a6f05da4ececb7d3/LICENSE-MODELS.md)，MJCF 与推理参考代码遵循 Apache-2.0。网页注明 Pollen Robotics 和许可。
- [官方 microduck-policies](https://huggingface.co/pollen-robotics/microduck-policies/tree/665ae4eb20bfe13bca1ef4ea6d4bb6b4a096e448) 固定提交 `665ae4eb20bfe13bca1ef4ea6d4bb6b4a096e448`，使用 `velstand.onnx`、`ball_kick_left.onnx`、`ball_kick_right.onnx`，许可 Apache-2.0。SHA-256 在 `scripts/fetch_scene_assets.py` 中固定；不重新训练、不声明为原创策略。
- `simulation.py` 的默认关节姿态、观测布局和推理时序参考官方 [`infer_policy.py`](https://github.com/pollen-robotics/microduck_rl/blob/b02fdea4902c2b93b7d34a83a6f05da4ececb7d3/scripts/infer_policy.py)，共享物理世界组合参考官方 `sim/body_server.py`。本项目自行实现动作编排、场景 API、接触验收和 Web 渲染接线，不声称复现完整硬件或电机数字孪生。
- 本地合唱是本项目用 Web Audio 合成的双声部短旋律；没有复制曲目或官方 BLE 合唱实现，不是云端语音。

## 协议参考

- [灵矽 OTA](https://linx.qiniu.com/docs/xrobot/platform/OTA)
- [灵矽 WebSocket](https://linx.qiniu.com/docs/xrobot/platform/websocket)
- [灵矽端侧 MCP](https://linx.qiniu.com/docs/xrobot/mcp/hardware-mcp)
- [灵矽智能体 API](https://linx.qiniu.com/docs/xrobot/api/agent)（提示词读取、更新与回读校验）

协议适配自行实现；不复制示例中的身份、token 或关闭 TLS 验证的设置。

依赖版本将记录在 `uv.lock` 和前端 `package-lock.json`。应用中的程序化鸭子预览为原创示意形象，不是官方 CAD 模型，也不是物理仿真结果。
