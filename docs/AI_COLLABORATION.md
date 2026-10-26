# AI 协作说明

DuckKing 由周霆（[@zhoutingunl](https://github.com/zhoutingunl)）与陶纯堂（[@evanwooo](https://github.com/evanwooo)）围绕“复刻一台 Micro Duck，并在其内装上灵矽通过语音交互”合作开发。周霆主要负责目标、方案、开发集成与交付，陶纯堂主要通过 PR review、comment、改进反馈及界面代码参与；[团队分工](TEAM.md)提供实际协作记录。AI 辅助阅读代码、实现、排障、验证与整理材料，本轮维护使用 Codex。目前没有足够记录统计整个项目的 AI 生成代码比例、模型用量或节省工时，也不把 AI 算作额外参赛队员。

## 开发协作与产品中的 AI

| 对象 | 实际作用 | 可核对的位置 |
|---|---|---|
| 开发阶段的 AI 协作者 | 根据需求修改仓库、查日志、执行获授权的测试与发布工具；结果由代码、PR 和验证记录支持 | [分工](TEAM.md)、[贡献规则](../CONTRIBUTING.md)、[GitHub PR](https://github.com/zhoutingunl/DuckKing/pulls) |
| 产品中的灵矽 | 真实云端语音识别、对话、MCP 工具调用与语音回复 | `voice.py`、`mcp.py`、`opus.py`；当轮 STT / 工具 / TTS 诊断 |
| 产品中的离线识别 | SenseVoiceSmall 转写，固定整句规则决定本地动作或转交灵矽 | `asr_service.py`、`hybrid_voice.py`、`local_commands.py` |
| 官方机器人策略与演示脚本 | 复用官方 ONNX 策略；本项目编排动作、校验物理结果、播放本地音乐 | [架构](ARCHITECTURE.md)、[第三方来源](../THIRD_PARTY.md) |

AI 参与开发不等于每段演示都经过灵矽。本地规则匹配不是云端理解，脚本编排不是现场训练出新策略，预录鸭声与试听素材也不是已成功克隆的音色。实体硬件、摄像头识别和 BLE 同步仍不在当前验收范围内。

## 一次变更如何完成

1. **从可观察的问题开始。** 记录页面、房间、时间、输入和现象；先查相同轮次的识别文本、路由、动作结果和物理状态。截图可以描述体验，不能单独证明后端卡死。
2. **核对已有实现与边界。** 先读 [AGENTS.md](../AGENTS.md)、相关代码与文档，确认是否已修过同一问题；固定资产版本、设备身份与 ai_gateway 现有服务边界保持清楚。
3. **在功能分支形成可复验的改动。** AI 可以提出候选修复并运行实验，最终保留有证据的方案。取消、动作有界、协议和失败处理的变更补有意义的回归检查；文档修改核对代码、链接、图和历史证据。
4. **按影响范围验证。** 协议替身检查用于帧序和异常；真实 MuJoCo 检查用于接触与稳定性；浏览器检查用于操作和恢复。真实灵矽、公网和手机实听分别验收，不能互相冒充。
5. **通过 PR 与 CI 交付。** 不直接推应用变更到 main，不编造作者、日期或通过结果。CI 失败先读 trace 和日志；修改事件同步应保留原行为断言，不能靠删检查或放宽物理边界换取通过。
6. **需要发布时单独验收。** 已获授权的发布使用不可变 tag、准确提交和摘要。安装成功只到 `staged`，公网和真实语音验收后才记录 `success`；升级不清空体验库或历史覆盖率。仅文档变化不需要重启线上服务。
7. **把结论留在仓库。** 使用说明描述当前代码，版本性证据保留原版本；复用经验更新 [LESSONS_LEARNED.md](LESSONS_LEARNED.md)。不要依赖某次聊天上下文来维持项目知识。

## 已发生的协作案例

| 人反馈的问题 | 查到的机制与改动 | 证据与适用边界 |
|---|---|---|
| 按住说话容易漏掉前半句 | 原来每轮启动麦克风；改为连接时静音预备、按下立即采集，等待同步时保留首批帧 | [句首采集记录](VALIDATION.md#本次部署阻塞与句首采集修复2026-10-26)、`frontend/tests/audio-output.spec.js`；受控输入的帧序验证不是手机识别准确率 |
| 踢球完成后位移一直涨，以为语音卡住 | 对照日志确认当轮走本地路径且动作完成；物理球地接触原来没有滚动耗散。增加球地滚动摩擦、真实球速与本地完成提示 | [PR #36](https://github.com/zhoutingunl/DuckKing/pull/36)、[发布验收](VALIDATION.md#最近已发布应用的验证2026-10-27)；没有截断位移显示或重置球速 |
| 场景切换后需要刷新才恢复 | 对切换、失败重试和通道恢复做组合检查，并发现初始按钮早于房间和状态流就绪 | [PR #36](https://github.com/zhoutingunl/DuckKing/pull/36)、`frontend/tests/scenarios.spec.js`；已验收的操作组合不等于任意断网、并发时序都得到保证 |
| 部署页旧覆盖率变成“未记录” | 报告随旧发布目录清理而消失；改为独立持久化，按准确 SHA 恢复真实报告 | [PR #34](https://github.com/zhoutingunl/DuckKing/pull/34)、`tests/test_coverage_history.py`；缺失证据的版本继续显示未记录 |
| 自动化偶发错过指挥改序时机 | 外部轮询到下一次浏览器操作存在延迟；改为浏览器确认实际开唱后立即操作待唱队列 | [PR #36](https://github.com/zhoutingunl/DuckKing/pull/36)、`frontend/tests/studio.spec.js`；仍验证实际 C→B 物理与声部顺序 |

这些案例展示的是“反馈 → 取证 → 修改 → 验证”的协作过程，不是对 AI 能力的独立对照实验。历史失败及未通过候选方案保留原记录；最终结果不倒填为第一次就通过。

## 经验、规则和证据放在哪里

此前经验分散在开发指南、架构说明、验证记录和 PR；现在由 [工程经验与回归检查](LESSONS_LEARNED.md)集中索引，详细材料仍在各自适合的位置。

| 内容 | 保存位置 | 维护方式 |
|---|---|---|
| 协作硬约束 | [AGENTS.md](../AGENTS.md)、[CONTRIBUTING.md](../CONTRIBUTING.md) | 影响后续每次操作的规则在此明确；AI 不凭经验擅自更改用户授权 |
| 当前软件规格与能力 | [README](../README.md)、[ARCHITECTURE.md](ARCHITECTURE.md)、[TEAM.md](TEAM.md)及专题说明 | 与实现同一 PR 更新，尤其房间容量、接口、动作、取消与来源标识 |
| 排障步骤与经验 | [DEVELOPMENT.md](DEVELOPMENT.md)、[LESSONS_LEARNED.md](LESSONS_LEARNED.md) | 经验写现象、机制、修复、回归入口，链接实际证据 |
| 版本性测试与发布证据 | [VALIDATION.md](VALIDATION.md)、PR、CI artifacts、GitHub Release 附件 | 绑定提交、环境和输入；旧测量不贴新版本，CI artifact 不承诺永久保存 |
| 本机调试材料 | 忽略跟踪的 `.duckking/` | 保存脚本输出、trace、候选结果；私有临时目录，不是公共交付或自动永久档案 |
| 线上诊断与验收 | YZH737 的 `/var/lib/duckking/`：分房间 `voice.jsonl`、`verification/` | 保留私有权限；公开前挑选、脱敏，不直接上传原始诊断包 |
| 跨版本使用体验与发布历史 | `experience.sqlite3`、`deployments.jsonl`、`release-coverage.json`，位于服务数据目录 | 程序持久化；统计库只存白名单技术指标，不是 AI 的经验记忆库 |

经验整理需要在修复后显式更新，并不会自动从所有聊天和日志中提炼。后续协作者应读这些仓库文件，再查对应版本证据，而不是假设 AI 还记得上一轮会话。
