# 第三方来源与原创边界

`v0` 是空仓库基线；没有导入第三方应用 codebase。本项目新增应用、界面与协议适配代码在之后的 PR 中开发。

## 外部可选仿真

- [Pollen Robotics Microduck](https://github.com/pollen-robotics/microduck)，候选固定提交 `942e58e3aa6dbb28e7037203fff11866122c7567`。
- [Microduck RL](https://github.com/pollen-robotics/microduck_rl)，候选固定提交 `b02fdea4902c2b93b7d34a83a6f05da4ececb7d3`。
- 官方模型、机械文件和策略不包含在本仓库中。由用户在外部目录获取，适用其上游许可；部分模型含非商业限制。本仓库 MIT 许可不会覆盖这些资源。

## 协议参考

- [灵矽 OTA](https://linx.qiniu.com/docs/xrobot/platform/OTA)
- [灵矽 WebSocket](https://linx.qiniu.com/docs/xrobot/platform/websocket)
- [灵矽端侧 MCP](https://linx.qiniu.com/docs/xrobot/mcp/hardware-mcp)
- [灵矽智能体 API](https://linx.qiniu.com/docs/xrobot/api/agent)（提示词读取、更新与回读校验）

协议适配自行实现；不复制示例中的身份、token 或关闭 TLS 验证的设置。

依赖版本将记录在 `uv.lock` 和前端 `package-lock.json`。应用中的程序化鸭子预览为原创示意形象，不是官方 CAD 模型，也不是物理仿真结果。
