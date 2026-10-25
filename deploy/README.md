# YZH737 独立部署

DuckKing 与 ai_gateway 使用不同目录、虚拟环境、端口和 systemd 服务，按指定使用 root 运行。DuckKing 安装脚本不修改 ai_gateway、18345/18346 端口或前置 Nginx。用户已授权在 ai_gateway 首次发布固定 `/duckking/` 转发路由，以共享 `ztmonitor.qbox.net` 的 HTTPS 入口；后续 DuckKing 升级无需重启 ai_gateway。

- 代码与虚拟环境：`/root/zt_dir/hackathon_base/DuckKing/releases/<version>`，同目录下 `current` 原子切换。
- 官方模型：每个版本包的 `external/`，从固定上游 Git commit 导出，策略校验 SHA-256。
- 私有状态与部署流水：`/var/lib/duckking`，不在静态目录中。
- 可选语音配置：`/var/lib/duckking/voice.env`，0600，所有者跟随状态目录；禁止提交密钥或设备身份。
- 运行进程：`duckking.service`，root 用户，CPUQuota=150%、MemoryMax=4G、TasksMax=128。无需修改系统账户文件。
- 初始监听：`127.0.0.1:8765`。默认只完成本机暂存部署，不会自动开放网络入口。

## 版本与发布包

先在功能分支完成验证和 PR，提交并推送代码，再对该 commit 创建新的 `deploy-yzh737-<UTC时间>` tag。不得移动 `v0`，也不得覆盖已有 tag 或发布包。

```sh
uv run --frozen --no-sync python scripts/build_release.py --ref <已提交commit> --version <tag>
```

构建脚本通过 `git archive` 获取已提交源码，在临时目录 `npm ci && npm run build`，打包跟踪文件、重新构建的前端和 `release.json`。官方模型另外从固定上游 Git commit 导出，包含原始许可，策略文件逐个验证 SHA-256；因此服务器无需访问 GitLab 或 Hugging Face。不包含本地 `.env`、设备身份、日志、工作区未提交内容、node_modules 或模型仓库 `.git`。输出 tar.gz 与 SHA-256 文件，作为 GitHub Release 附件供 YZH737 下载。

目标机先核对 SHA-256，再从已验证的包中取出安装脚本：

```sh
bash scripts/install_release.sh <archive> <sha256> <tag> <完整commit>
```

安装使用 YZH737 已有的 `/usr/local/bin/python3.12` 和 `/root/.local/bin/uv`，只创建 DuckKing 自己的 venv，不修改系统 Python 包。系统账户文件的 immutable 属性保持不变。systemd 通过 StateDirectory 管理 root 所有的 `/var/lib/duckking`，源代码与虚拟环境在服务中只读。

依赖首次下载可能超过 SSH 会话等待时限。远程执行时将安装作为独立后台任务启动，保存日志及退出状态，再通过短 SSH 会话查询；不要把 SSH 超时当作成功。若需要重试一个从未启动成功的版本，先确认安装进程已退出及部署锁已释放，将失败目录归档后，再用同一已校验发布包安装；不修改发布包、commit 或 tag。

安装期间会执行真实 MuJoCo 左右脚、双鸭接触、嘴部搬运、四鸭桌沿跌落与坐站轮唱检查，然后验证运行版本、页面资源、状态/语音本地握手和有界停止动作。源码包验证后的安装失败会保留失败记录；已切换版本则恢复旧链接与服务配置，并核对旧版本健康响应。首次安装失败会停止并禁用新服务。

## HTTPS 接入

当前使用 ai_gateway 应用路由：`/duckking/` 的 API 与资源固定转发到 `127.0.0.1:8765`，不依赖 DuckKing release 目录。域名前置代理实测移除了 Upgrade，浏览器根据 `_gateway/capabilities` 使用 HTTPS 长轮询转发到同一个真实后端 WebSocket。PCM 保持原始字节，队列、帧大小与空闲时间有上限，发送顺序校验且不自动重试语音。服务升级后状态流重连，用户重新连接语音。

ai_gateway 的 yzh737 档案设置 `duckking_upstream=http://127.0.0.1:8765`、`duckking_public_host=ztmonitor.qbox.net`、`duckking_transport=https-poll`。首次网关发布使用其 GitLab main 正式部署流程；DuckKing 自身继续使用本仓库 GitHub Release。无需额外开放 DuckKing 私网或公网端口。

如将来能修改前置 Nginx，也可使用原生 WebSocket 方案：

需要确认前置 Nginx 所在主机、YZH737 私网地址及入口访问控制。将 `nginx-duckking.conf.example` 中的两个 location 加到现有 HTTPS server 中，继承已有证书和访问限制；原 ai_gateway location 保留。对外路径为 `/duckking/`，代理去掉该前缀，保留 Host / Origin，并显式传递 WebSocket Upgrade / Connection。先检查 Nginx 配置，再平滑 reload。

不同服务器之间不能连接 YZH737 的 loopback。确认路由与访问范围后，再单独配置 DuckKing 的私网监听；不要改 ai_gateway 的监听或把其端口换成其他代理。未确认这一步前，`staged` 记录只表示独立后端就绪，不能当作公网发布成功。

```sh
python scripts/release_smoke.py --url https://ztmonitor.qbox.net/duckking/ --commit <完整commit>
```

还需在 HTTPS 页面实测浏览器安全上下文、麦克风授权、上行音频，以及真实灵矽 STT/MCP/TTS。后端 Linux 物理自检和本地语音握手不能替代云端语音验收；服务器使用独立设备身份，不复制本机设备身份并同时连接。全部验收后才能追加 `status=success`、`selftest=passed` 的记录。部署记录入口在 DuckKing 自己的 `/duckking/deploys.html`。

前置 Nginx 的 WebSocket 配置参考 [Nginx 官方文档](https://nginx.org/en/docs/http/websocket.html)，浏览器麦克风的安全上下文要求参考 [MDN getUserMedia](https://developer.mozilla.org/en-US/docs/Web/API/MediaDevices/getUserMedia)。

## 发布冻结

遵守仓库 `AGENTS.md`：2026-10-25 23:59 Asia/Shanghai 后，未经明确解除冻结的新指令，不得修改远程仓库。

## 独立离线识别服务

发布包包含校验过的 SenseVoiceSmall INT8 权重、模型许可和两个合成回归录音。安装器先做真实 ASR 推理及物理自检，再安装 `duckking-asr.service`；仅监听 127.0.0.1:8768，单线程、CPUQuota=100%、MemoryMax=1G、最多两个未完成任务。DuckKing 主服务保留自己的 CPU/内存额度，通过 `DUCKKING_LOCAL_ASR=1` 开启模式选择。无新增公网端口，不改 ai_gateway 路由，不重启 ai_gateway。

worker 健康检查通过后才重启 DuckKing 主服务。部署失败恢复旧链接与两个服务配置；首次增加 worker 的回滚会停止、禁用并移除新增 worker 单元。`/var/lib/duckking/verification/asr-<version>.json` 保存真实推理结果与实测耗时，不包含用户录音。最终公网验收还需检查本地命中、真实灵矽回退、打断与两个房间隔离。
