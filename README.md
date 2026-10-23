# DuckKing

用灵矽语音控制虚拟 Micro Duck 的本地交互项目。支持直接运行的原创动画预览，以及已实测的官方 robotd / MuJoCo 适配。

![DuckKing 工作台](docs/media/workbench.png)

[真实灵矽语音演示](docs/media/live-linx-voice.mp4) · [本地演示](docs/media/local-preview.mp4) · [官方物理仿真演示](docs/media/official-simulation.mp4) · [架构与模块规格](docs/ARCHITECTURE.md) · [验证记录](docs/VALIDATION.md) · [演示复现](docs/DEMO.md)

新增「闪身步」「狗熊哆嗦毛」两个三秒小节目，可通过按钮或灵矽语音触发。[查看编排与演示](docs/CHOREOGRAPHY.md)。

## 本地运行

需要 Python 3.12+、[uv](https://docs.astral.sh/uv/) 和 Node.js 22.12+。

```bash
git clone git@github.com:zhoutingunl/DuckKing.git
cd DuckKing
uv sync --python 3.12
cd frontend
npm ci
npm run build
cd ..
uv run duckking
```

打开 <http://127.0.0.1:8765>。可直接使用点头、前进、左右转向、闪身步、狗熊哆嗦毛、停止和复位；Esc 可取消动作。

默认运行原创动画预览，不进行物理计算。语音需另外连接灵矽，不会把本地按钮操作冒充为识别结果。

## 连接灵矽

安装原生 Opus 库：macOS 使用 `brew install opus`；Ubuntu 使用 `sudo apt-get install libopus0`。

如果已有平台 API Key，将原始 Key 单独放在 `~/.secrets/lingxi`，可显式运行一次初始化：

```bash
chmod 600 ~/.secrets/lingxi
uv run duckking-setup --key-file ~/.secrets/lingxi
```

该命令创建或复用名为 DuckKing 的智能体，并通过 OTA 激活码绑定本地设备；不会改写其他智能体或迁移已有设备的聊天历史。已有特定智能体时可传 `--agent-id`。平台初始化不会在打开页面时自动执行。

打开工作台点击「连接灵矽」，首次连接会显示设备激活码。在灵矽控制台将此设备绑定到支持工具调用的智能体，再点击重新连接。连接就绪后按住按钮或空格说话，松开后等待回答。首版为半双工，每次录音最多 15 秒。

如果已有设备连接凭证，将 `.env.example` 中对应项填入 `~/.secrets/duckking.env`；设置文件权限为 `600`。设备 token 不等于平台管理 API Key。后端读取凭证，浏览器不接触 token；本地设备身份保存于 `~/.local/share/duckking/identity.json`。文件填好后重新打开页面连接。

可用工具：`duck_nod`、`duck_walk_short`、`duck_stop`、`duck_get_status`、`duck_flash_step`、`duck_bear_shake`。可以说“来一段闪身步”或“来一段狗熊哆嗦毛”。新增工具需要断开旧语音会话后重连。断线后界面明确提示；首版不会自动恢复录音。

**真实云端联调已完成。** 已使用系统合成中文语音验证灵矽 STT → MCP 工具调用 → 本地动作 → 真实 TTS，也验证了灵矽调用官方仿真前进。浏览器演示中的输入为合成语音，识别、工具调用和回复均来自真实灵矽服务；没有伪造回复。验收范围与记录见 [VALIDATION.md](docs/VALIDATION.md)。

## 连接官方物理仿真

此路径需要 Rust/Cargo、pkg-config、uv、Python 3.12，首次会下载较大的上游依赖并编译 Rust。

```bash
scripts/setup_simulator.sh
scripts/run_simulator.sh
```

保持此终端开启，在另一终端启动 DuckKing：

```bash
uv run duckking --backend robotd --socket ~/.cache/duck-sim/duck-a.sock
```

`DUCKKING_SIM_DIR` 可指定已有的外部仓库目录；`DUCK_SIM_VIEWER=0` 可运行无窗口仿真。上游固定版本及许可见 [THIRD_PARTY.md](THIRD_PARTY.md)。

本机已运行官方 robotd + MuJoCo，验证了站立、点头指令、前进和停止；低速指令不足以触发明显步态，因此仿真端默认前进指令为 0.35 m/s，动作限时 0.2–3 秒。指令速度不等于实际位移速度；一次 1.2 秒实测位移约 14 cm，不作为固定距离保证。动画预览默认仍为 0.12 m/s。

连接 robotd 时，本页模型保持为原创示意图，物理画面应查看官方 MuJoCo 窗口。不会在连接失败时悄悄切回动画预览。适配器仅在上述仿真环境中测试，未验证实体机器人。

## 测试与覆盖率

```bash
uv run ruff check src tests
uv run pytest --cov --cov-report=term-missing --cov-report=json --cov-report=html
uv run python scripts/check_coverage.py
cd frontend
npx playwright install chromium
npm run test:e2e
npm run test:unit
```

CI 硬性要求所有后端模块行覆盖率 ≥90%、分支覆盖率 ≥85%；不达标不能合入。每次检查上传 HTML/XML/JSON 覆盖报告和浏览器测试报告。

浏览器流程验证桌面动作、停止取消和移动端布局；单元测试重点覆盖限时、取消、去重、错误反馈和同源保护。新增协议模块也须遵守相同门槛，不从覆盖统计中排除。

目标：电脑麦克风 → 灵矽 → MCP 工具调用 → 本地动作控制 → 虚拟鸭子。提供无需账号的明确标注的动画预览，以及连接官方 robotd / MuJoCo 的适配路径。

## 开发基线

- `v0` 指向不包含任何文件的开发前基线，未导入现成应用代码。
- 空仓库必须先建立基础分支才能创建 PR；唯一直接初始化提交仅建立空基线。
- 所有后续文档、代码及修复通过功能分支和 Pull Request 进入 `main`。
- 官方 Microduck 是外部可选依赖；不会把它的代码、模型或策略声明为本项目原创。

参见 [贡献指南](CONTRIBUTING.md)、[团队与分工](docs/TEAM.md)、[第三方说明](THIRD_PARTY.md)。

## 交付计划

1. PR：协作规范、开发前基线、CI 与贡献说明。
2. PR：可运行的本地界面、受限动作控制与自动化测试。
3. PR：灵矽设备接入、音频、MCP 和官方仿真适配。
4. PR：演示视频、运行说明、架构与验收记录。

实现进度与验证以各 PR 的说明和 CI 为准。

## 许可

本项目原创代码使用 [MIT](LICENSE)；第三方代码和资源遵循其各自许可。
