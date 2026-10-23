# 本地环境与继续开发

## 安装和运行 demo

需要 `uv`、Node.js 22.12+ 和 npm。仓库的 `.python-version` 固定默认 Python 为 3.12，uv 可以下载该解释器，不必更换系统 Python。

在仓库根目录运行：

```bash
scripts/setup_local.sh
scripts/run_local.sh
```

打开 <http://127.0.0.1:8765>。初始化按 `uv.lock` 和 `frontend/package-lock.json` 安装依赖并构建页面，可重复运行；不会升级锁定版本、连接云端或创建平台智能体。Opus 不可用时提示安装方法，但不阻止动画预览。

启动脚本在前台运行，Ctrl+C 交给应用正常关闭、停止动作。它可从其他工作目录通过绝对路径启动。启动时不会安装依赖或重新构建；拉取更新后再次执行初始化脚本。

等价的手动安装命令为：

```bash
uv sync --frozen --python 3.12
cd frontend
npm ci
npm run build
cd ..
uv run --frozen duckking
```

## 前端热更新

保持上述后端运行，在第二个终端执行：

```bash
cd frontend
npm run dev
```

打开 <http://127.0.0.1:5173>。Vite 读取前端源文件，修改 JS / CSS 后自动更新页面；8765 仍提供上次构建的 demo。修改 Python 代码后需重启后端。希望将前端修改显示在 8765 时，执行 `cd frontend && npm run build`，然后刷新页面。

Vite 只监听 `127.0.0.1`；`/api`、`/ws`、`/voice` 转发到本地后端。Host 和 Origin 原样保留，因此后端继续检查同源请求。开发模式没有绕过安全校验，也不会在后端连接失败时创建另一个预览后端。实现参考 [Vite server.proxy 文档](https://vite.dev/config/server-options#server-proxy)。

自定义端口时，两个终端分别执行：

```bash
# 终端一：仓库根目录
scripts/run_local.sh --port 8766

# 终端二：frontend 目录
DUCKKING_API_PORT=8766 npm run dev -- --port 5174
```

随后访问 <http://127.0.0.1:5174>。开发端口被占用时会直接报错，不会悄悄切换。`DUCKKING_API_PORT` 只接受 1–65535 的整数。

## 检查

```bash
uv run ruff check src tests
uv run pytest --cov --cov-report=json --cov-report=html
uv run python scripts/check_coverage.py
cd frontend
npm run build
npm run test:unit
npx playwright install chromium
npm run test:e2e
npm run test:e2e:dev
```

正式构建测试使用独立后端端口 8875；开发测试额外使用 Vite 端口 8876。两个命令依次执行，不复用已经运行的工作台；需要改端口时设置 `DUCKKING_TEST_PORT` / `DUCKKING_TEST_DEV_PORT`。已有兼容 Chrome 时可通过 `PLAYWRIGHT_CHROMIUM_EXECUTABLE=/absolute/path/to/chrome` 指定浏览器。

开发测试重复动作、取消、移动端和音频测试，并验证真实代理的 HTTP / WebSocket 同源拒绝、动作时长限制、未连接云端时的语音协议错误，以及后端不可用时的明确失败。音频测试使用本地协议替身，不消耗真实灵矽额度。报告分别保存在 `frontend/playwright-report/production/` 和 `frontend/playwright-report/development/`，失败截图和 trace 位于对应的 `frontend/test-results/` 子目录。

## 排障与能力边界

| 现象 | 处理 |
|---|---|
| 缺少依赖 / 构建，或根页面返回 503 | 执行 `scripts/setup_local.sh`；确认 Node.js 版本满足要求 |
| 8765 被占用 | 关闭自己启动的旧服务，或通过 `--port` 指定其他端口 |
| 5173 页面能打开，但动作报错 / 状态持续重连 | 确认后端正在运行，且 `DUCKKING_API_PORT` 与后端端口相同 |
| 修改前端后 demo 未变化 | 使用 5173 开发页面，或重新构建后刷新 8765 页面 |
| 语音提示缺少 libopus | macOS：`brew install opus`；Ubuntu：`sudo apt-get install libopus0` |
| 浏览器测试缺少 Chromium | 执行 `npx playwright install chromium`，或配置上述浏览器可执行路径 |

默认 demo 为原创动画预览，不进行物理计算。官方仿真仍需单独按 README 安装和启动，再显式传入 `--backend robotd`。连接失败不会回退到预览。

真实语音必须由用户在界面显式连接，设备凭证仍在仓库外。启动环境或运行自动化测试不构成真实云端、官方物理仿真或实体机器人的本次验收。
