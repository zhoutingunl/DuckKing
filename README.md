# DuckKing

用灵矽语音控制虚拟 Micro Duck 的本地交互项目。竞赛初版开发中。

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

打开 <http://127.0.0.1:8765>。当前可直接使用点头、前进、左右转向、停止和复位；Esc 可取消动作。

此版本默认运行原创动画预览，不进行物理计算。语音按钮尚未启用，不能把本地按钮操作称为灵矽识别结果。

## 测试与覆盖率

```bash
uv run ruff check src tests
uv run pytest --cov --cov-report=term-missing --cov-report=json --cov-report=html
uv run python scripts/check_coverage.py
cd frontend
npx playwright install chromium
npm run test:e2e
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
