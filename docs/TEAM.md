# 团队与模块分工

目前确认的 GitHub 账号：[@zhoutingunl](https://github.com/zhoutingunl)，负责项目需求、方案决策、仓库维护与交付验收；开发过程中使用 AI 辅助。下面记录当前责任归属，不把尚未加入的成员或建议分工写成已经发生的贡献。

其他实际成员与分工尚待确认，不能提前写成已经参与的贡献者。

模块编号对应 [架构规格](ARCHITECTURE.md#模块规格)。表中的测试是可复验入口，不表示每次文档修改都重新执行了全部测试；具体通过记录见 [VALIDATION.md](VALIDATION.md)。

| 模块 | 当前负责人 | 交付与验收责任 | 主要验证入口 |
|---|---|---|---|
| M01 浏览器音频与传输 | @zhoutingunl | 句首采集、打断、手机声音、HTTPS 通道与资源释放 | `frontend/tests/audio-output.spec.js`、`voice.spec.js`、`prefix.spec.js` |
| M02 页面、外观与物理渲染 | @zhoutingunl | 入口、模型来源标识、加载失败恢复、状态与模型一致 | `frontend/tests/scenarios.spec.js`、`model-loader.test.js`；`tests/test_model_assets.py` |
| M03 应用与房间 | @zhoutingunl | 容量、语音独占、房间隔离、回收与同源校验 | `tests/test_rooms.py`、`test_app.py`、`test_voice_app.py` |
| M04 本地优先识别 | @zhoutingunl | 完整计划匹配、取消与一次云端转交、真实 ASR 输入 | `tests/test_local_voice.py`；`scripts/verify_local_asr.py` |
| M05 灵矽与设备协议 | @zhoutingunl | 设备绑定、Opus、MCP 关联、恢复与真实云端验收 | `tests/test_voice.py`、`test_mcp.py`、`test_voice_interrupt.py`、`test_voice_recovery.py`；独立公网语音验收 |
| M06 动作调度与后端适配 | @zhoutingunl | 动作有界、取消、幂等、后端失败不伪装成功 | `tests/test_motion.py`、`test_motion_edges.py`、`test_robotd.py`、`test_choreography.py` |
| M07 官方物理与实验机构 | @zhoutingunl | 策略接入、接触和稳定性验收、模型改编边界 | `tests/test_simulation.py`、`test_grasp.py`、`test_posture.py`、`test_official_skills.py`；`scripts/verify_scenarios.py` |
| M08 演示与现场任务 | @zhoutingunl | 十三幕、工坊、音乐、选中目标、停止与切换 | `tests/test_stage.py`、`test_table_choir.py`、`test_studio.py`、`test_studio_failures.py`；`frontend/tests/studio.spec.js` 与 CI journey / stage 分组 |
| M09 诊断与体验统计 | @zhoutingunl | 指标起止点、脱敏、持久化、来源区分与缺失样本 | `tests/test_diagnostics.py`、`test_statistics.py`、`test_experience.py`；`frontend/tests/experience.test.js` |
| M10 质量与发布 | @zhoutingunl | PR / CI、不可变发布、回滚、公网验收、文档与来源 | `.github/workflows/ci.yml`；`tests/test_deployment.py`、`test_release_metadata.py`、`test_coverage_history.py`；`scripts/release_smoke.py` |

Python 短文件名沿用该格的 `tests/`，前端短文件名沿用 `frontend/tests/`。仓库当前的 [CODEOWNERS](../.github/CODEOWNERS)也由同一维护者负责。

## 人与 AI 的工作分工

| 角色 | 实际承担的工作 | 责任边界 |
|---|---|---|
| 人类维护者 | 提出竞赛目标和体验问题、选择方案与音色方向、提供音源、手机实听、决定发布范围 | 负责需求取舍和最终交付；实际手机体验不能由服务器日志替代 |
| AI 开发协作者（本轮使用 Codex） | 阅读代码与日志、提出并实现修复、补回归检查、执行获授权的工具与发布流程、整理文档 | 结果必须有代码、工具输出或验证记录支持；未执行就不能写已通过，不计作额外人类成员 |
| CI 与验收脚本 | 重复执行覆盖率、协议、浏览器、物理和发布检查 | 是验证机制，不是成员或独立人工评审；受控云端替身不等于真实灵矽验收 |

协作过程、实例和经验存放规则见 [AI 协作说明](AI_COLLABORATION.md)。没有统计过的 AI 代码占比、节省工时和模型使用量不填估算值。

真实队员加入时，在独立 PR 中更新本表与 CODEOWNERS；使用各自账号提交、评审。当前不能宣称满足“团队作品有多人代码提交记录”这一项，协作机制与真实参与记录需分别验收。
