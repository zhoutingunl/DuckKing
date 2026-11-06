# YZH737 独立部署

DuckKing 与 ai_gateway 使用不同目录、虚拟环境、端口和 systemd 服务，按指定使用 root 运行。DuckKing 安装脚本不修改 ai_gateway、18345/18346 端口或前置 Nginx。YZH737 现改为通过服务器地址的 `8765` 端口直接访问，不依赖 ai_gateway。主机上的 systemd drop-in 保留独立入口配置，后续 DuckKing 升级无需重启 ai_gateway。

- 代码与虚拟环境：`/root/zt_dir/hackathon_base/DuckKing/releases/<version>`，同目录下 `current` 原子切换。
- 官方模型：每个版本包的 `external/`，从固定上游 Git commit 导出，策略校验 SHA-256。
- 私有状态与部署流水：`/var/lib/duckking`，不在静态目录中。
- 可选语音配置：`/var/lib/duckking/voice.env`，0600，所有者跟随状态目录；禁止提交密钥或设备身份。
- 运行进程：`duckking.service`，root 用户。基础 unit 默认为 CPUQuota=400%、MemoryMax=8G、TasksMax=128；YZH737 当前通过主机覆盖配置使用 CPUQuota=1200%、MemoryMax=32G、TasksMax=256。无需修改系统账户文件。
- 全新安装默认监听：`127.0.0.1:8765`。YZH737 通过下述主机配置覆盖为 `0.0.0.0:8765`；安装器仍保留 loopback 默认值。

## 版本与发布包

先在功能分支完成验证和 PR，提交并推送代码，再对该 commit 创建新的 `deploy-yzh737-<UTC时间>` tag。不得移动 `v0`，也不得覆盖已有 tag 或发布包。

```sh
uv run --frozen --no-sync python scripts/build_release.py --ref <已提交commit> --version <tag>
```

构建脚本通过 `git archive` 获取已提交源码，在临时目录 `npm ci && npm run build`，打包跟踪文件、重新构建的前端和 `release.json`。官方模型另外从固定上游 Git commit 导出，包含原始许可，策略文件逐个验证 SHA-256；因此服务器无需访问 GitLab 或 Hugging Face。不包含本地 `.env`、设备身份、日志、工作区未提交内容、node_modules 或模型仓库 `.git`。输出 tar.gz 与 SHA-256 文件，作为 GitHub Release 附件，或通过发布页中已校验的 CDN 下载链接供 YZH737 下载。

部署页的“变更提交”来自发布包内 `release-commits.json`：只提取该发布提交可达的 Git 历史（最多 2000 项，SHA、父提交和摘要，不含作者邮箱）。页面按同一目标上一次成功部署计算新增提交；暂存／失败不推进基准，同版本的暂存与成功记录使用同一基准。每次最多展示 50 项并链接 GitHub 对比；回退、同提交重发、历史不完整分别明确标注，服务器不需要联网查询 GitHub。

“行覆盖率 / 分支覆盖率”明确限定为 Python 后端测试，包含单元及集成检查。CI 输出 `coverage-summary.json`，绑定 PR head／提交 SHA、覆盖计数和 CI URL。构建时可重复传入 `--coverage-summary <从已完成CI下载的coverage-summary.json>`，将当前及历史版本的已核验报告写入 `release-coverage.json`；服务器只给完全相同的提交展示报告。不传报告或旧版本缺少证据时显示“未记录”，不复用工作目录可能过期的 `coverage.json`。构建前需确认对应 CI 完整成功，且报告 SHA 与准备发布的提交一致。

目标机先核对 SHA-256，再从已验证的包中取出安装脚本：

```sh
bash scripts/install_release.sh <archive> <sha256> <tag> <完整commit>
```

安装使用 YZH737 已有的 `/usr/local/bin/python3.12` 和 `/root/.local/bin/uv`，只创建 DuckKing 自己的 venv，不修改系统 Python 包。系统账户文件的 immutable 属性保持不变。systemd 通过 StateDirectory 管理 root 所有的 `/var/lib/duckking`，源代码与虚拟环境在服务中只读。

依赖首次下载可能超过 SSH 会话等待时限。远程执行时将安装作为独立后台任务启动，保存日志及退出状态，再通过短 SSH 会话查询；不要把 SSH 超时当作成功。若需要重试一个从未启动成功的版本，先确认安装进程已退出及部署锁已释放，将失败目录归档后，再用同一已校验发布包安装；不修改发布包、commit 或 tag。

安装期间会执行真实 MuJoCo 左右脚、双鸭接触、嘴部搬运、四鸭桌沿跌落与坐站轮唱检查，然后验证运行版本、页面资源、状态/语音本地握手和有界停止动作。源码包验证后的安装失败会保留失败记录；已切换版本则恢复旧链接与服务配置，并核对旧版本健康响应。首次安装失败会停止并禁用新服务。

## 直接访问 8765

对外入口为 `https://duck.qbox.net/`：域名指向前置 OpenResty（OR），OR 上游为 YZH737 的 `8765`，不经过 ai_gateway。应用启动参数必须包含 `--allowed-host duck.qbox.net`；仅开放监听地址仍会返回 `Invalid host header`。OR 应保留 Host / Origin，并传递 WebSocket Upgrade / Connection。

区域默认语言依赖可信代理转发。DuckKing 的 Uvicorn 保留原 socket peer；只有来源 IP 命中 DUCKKING_GEO_TRUSTED_PROXIES 时才信任 X-Forwarded-For 或网关国家码。默认只信任 loopback。代理上游地址尚未核实或转发头未到达时回退中文，不根据访客自带的 XFF/国家码选房。

```sh
# 只在确认 OR→YZH737 上游源地址后加入该地址；不要使用任意网段。
# 将 OR 到 YZH737 的真实上游源 IP 替换 OR_UPSTREAM_IP；不要填写未经核实的网段。
# DUCKKING_GEO_TRUSTED_PROXIES=127.0.0.1/32,::1/128,OR_UPSTREAM_IP/32
# OR 应配置：proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
# 从公网经 OR 请求 /api/ui-preferences 验证；客户端自带 XFF 不能证明代理身份。
```

未加入可信代理地址时，代理请求会回退中文；直连且不含转发头的请求根据 socket peer 查询，带未受信任转发头时回退中文。每个房间均可通过连接时选择语言智能体使用中英法语；先在实际服务数据目录分别运行 `duckking-setup --language-profile --lang-code zh`、`en`、`fr`（见根目录 README）。对应私有 `voice-profiles.json` 必须在版本目录外持久保存，不能入库。无需重绑设备；每个房间仍保持独立身份与语音独占。旧 `DUCKKING_FRENCH_ROOMS` / `DUCKKING_ENGLISH_ROOMS` 仅作为分房偏好，不能代替该配置。未配置的语言会报错，不回退中文。


分享链接时使用完整的 HTTPS 地址。微信内打开裸域名可能进入 HTTP；此前体验统计直接调用仅安全上下文可用的 `crypto.randomUUID()`，会中断模型初始化。当前构建在应用模块启动前，将 `duck.qbox.net` 的 HTTP 页面自动切换为 HTTPS，保留页面、房间参数和锚点；同时兼容旧的 `ztmonitor.qbox.net/duckking/` 页面入口。不修改 ai_gateway 的其他页面，也不重定向 localhost、局域网地址或自定义端口。请求与统计 ID 同时兼容只有 `crypto.getRandomValues()` 的环境；远程 HTTP 页面仍不能因此获得麦克风权限。

也可从获准的网络访问 `http://<服务器IP>:8765/`。路径从 `/` 开始，不带 `/duckking/`。页面、API 和原生 WebSocket 都由 DuckKing 提供。ASR worker 仍只监听 `127.0.0.1:8768`。

将 [duckking-direct.conf.example](duckking-direct.conf.example) 中的 `SERVER_IP` 替换为实际访问 IP 或域名，保存到 `/etc/systemd/system/duckking.service.d/20-direct-access.conf`；需要多个地址时重复添加 `--allowed-host`。该文件显式覆盖启动命令，监听所有 IPv4 接口并取消代理路径前缀，优先于基础 unit 及其 `DUCKKING_BIND_HOST` 设置。保留精确 Host 白名单与同源检查。

```sh
systemctl daemon-reload
systemctl restart duckking.service
systemctl --no-pager is-active duckking.service
ss -ltn 'sport = :8765'
```

从服务器外部检查健康状态，并使用当前 `release.json` 的完整提交运行验收：

```sh
curl --fail https://duck.qbox.net/api/health
python scripts/release_smoke.py --url https://duck.qbox.net/ --commit <运行中的完整commit>
```

验收包含页面资源、状态与语音 WebSocket 握手、有界停止动作；不表示真实云端语音已通过。非 localhost 的 HTTP 页面不具备浏览器麦克风所需的安全上下文；需要网页录音时，应在独立 HTTPS 入口直接代理 DuckKing 并保留 WebSocket Upgrade，无需经过 ai_gateway。

外部访问保护由现有基础设施负责，本次未修改防火墙或上游访问控制。只有外部实测成功才能报告该网络入口可达。安装器只替换主 unit，不删除此 drop-in，因此普通发布和应用版本回滚均保留直连配置。撤销这次入口调整时，删除本次新增的 drop-in，再执行 `daemon-reload` 和重启；若 `/etc/duckking/runtime.env` 仍为原始 loopback 设置，将恢复原入口。

2026-11-02 配置验证：运行版本仍为 `deploy-yzh737-20261102T065603Z`（`3f943bf26a08bc9b719bb9af929b4d328aeccbb6`），systemd 配置校验通过，监听为 `0.0.0.0:8765`。在 YZH737 上通过非 loopback 网卡地址运行完整 release smoke，页面资源、原生状态/语音 WebSocket 握手与有界停止均通过；错误 Host 返回 400，跨来源写请求返回 403。ASR 保持 `127.0.0.1:8768`，ai_gateway 的 18345 监听进程未变。操作端电脑直连各公网 IP 及私网 IP 的 8765 均超时，未将服务器自检记作外部连通成功，也未验收真实云端语音。

随后接入 `duck.qbox.net`：初次访问返回 400 `Invalid host header`，在上述 drop-in 追加 `--allowed-host duck.qbox.net` 并重启后，操作端电脑通过 OR 访问首页与健康 API 返回 200。release smoke 的页面和资源阶段通过，但原生 WebSocket 握手返回 404，完整验收未通过；需要核对 OR 的 WebSocket 转发。不能将页面恢复记作语音/状态连接已恢复。

2026-11-03 复核：`https://duck.qbox.net/` 的首页、模型资源可用，`wss://duck.qbox.net/` 下 `ws`、`scene-ws`、`voice`、`scene-voice` 均完成握手并返回对应状态消息，早先的握手 404 未再复现。该检查不包含真实灵矽识别与合成语音验收。

OR 的现有代理 location 需要包含以下设置，并保留既有访问保护；修改后先校验配置再平滑 reload：

```nginx
proxy_http_version 1.1;
proxy_set_header Host $http_host;
proxy_set_header Origin $http_origin;
proxy_set_header Upgrade $http_upgrade;
proxy_set_header Connection "upgrade";
```

## 原有 HTTPS 网关入口

原有 ai_gateway 应用路由：`/duckking/` 的 API 与资源固定转发到 `127.0.0.1:8765`，不依赖 DuckKing release 目录。域名前置代理实测移除了 Upgrade，浏览器根据 `_gateway/capabilities` 使用 HTTPS 长轮询转发到同一个真实后端 WebSocket。PCM 保持原始字节，队列、帧大小与空闲时间有上限，发送顺序校验且不自动重试语音。服务升级后状态流重连，用户重新连接语音。

ai_gateway 的 yzh737 档案设置 `duckking_upstream=http://127.0.0.1:8765`、`duckking_public_host=ztmonitor.qbox.net`、`duckking_transport=https-poll`。首次网关发布使用其 GitLab main 正式部署流程；DuckKing 自身继续使用本仓库 GitHub Release。该旧入口本身无需额外开放 DuckKing 私网或公网端口。

如将来能修改前置 Nginx，也可使用原生 WebSocket 方案：

需要确认前置 Nginx 所在主机、YZH737 私网地址及入口访问控制。将 `nginx-duckking.conf.example` 中的两个 location 加到现有 HTTPS server 中，继承已有证书和访问限制；原 ai_gateway location 保留。对外路径为 `/duckking/`，代理去掉该前缀，保留 Host / Origin，并显式传递 WebSocket Upgrade / Connection。先检查 Nginx 配置，再平滑 reload。

不同服务器之间不能连接 YZH737 的 loopback。确认路由与访问范围后，再单独配置 DuckKing 的私网监听；不要改 ai_gateway 的监听或把其端口换成其他代理。未确认这一步前，`staged` 记录只表示独立后端就绪，不能当作公网发布成功。

```sh
python scripts/release_smoke.py --url https://ztmonitor.qbox.net/duckking/ --commit <完整commit>
```

还需在 HTTPS 页面实测浏览器安全上下文、麦克风授权、上行音频，以及真实灵矽 STT/MCP/TTS。后端 Linux 物理自检和本地语音握手不能替代云端语音验收；服务器使用独立设备身份，不复制本机设备身份并同时连接。全部验收后才能追加 `status=success`、`selftest=passed` 的记录。部署记录入口在 DuckKing 自己的 `/duckking/deploys.html`。

前置 Nginx 的 WebSocket 配置参考 [Nginx 官方文档](https://nginx.org/en/docs/http/websocket.html)，浏览器麦克风的安全上下文要求参考 [MDN getUserMedia](https://developer.mozilla.org/en-US/docs/Web/API/MediaDevices/getUserMedia)。

## 独立离线识别服务

发布包包含校验过的 SenseVoiceSmall INT8 权重、模型许可和两个合成回归录音。安装器先做真实 ASR 推理及物理自检，再安装 `duckking-asr.service`；仅监听 127.0.0.1:8768，单线程、CPUQuota=100%、MemoryMax=1G、最多两个未完成任务。DuckKing 主服务保留自己的 CPU/内存额度，通过 `DUCKKING_LOCAL_ASR=1` 开启模式选择。无新增公网端口，不改 ai_gateway 路由，不重启 ai_gateway。

worker 健康检查通过后才重启 DuckKing 主服务。部署失败恢复旧链接与两个服务配置；首次增加 worker 的回滚会停止、禁用并移除新增 worker 单元。`/var/lib/duckking/verification/asr-<version>.json` 保存真实推理结果与实测耗时，不包含用户录音。最终公网验收还需检查本地命中、真实灵矽回退、打断与动态房间隔离。


## 动态房间容量

房间现在默认按匿名浏览器会话隔离。发布验收应使用两个独立 Cookie 容器验证：列表互不可见、改编号的读写请求返回404、四个 WebSocket 不返回他人状态、回收后旧 Cookie 不能访问新访客的同编号房间。`release_smoke.py` 会先申领自己的房间，并在 HTTP 和 WebSocket 使用同一会话。勿把房间号当成访问凭证。

发布包可先用 `qup-cdn-upload` 上传至 CDN，再在 YZH737 下载。上传文件名带本机秒级时间戳，GitHub Release 记录永久 URL、字节数和完整 SHA-256；服务器校验 SHA 后才提取安装脚本。仅上传从已提交源码构建的公开包，不包含 `.env`、身份或运行数据。

基础默认最多 10 个房间、4 个同时加载的物理世界，空闲 300 秒后回收。2026-11-02 容量测试后，YZH737 使用 [duckking-audience.conf.example](duckking-audience.conf.example) 作为 `/etc/systemd/system/duckking.service.d/30-audience-capacity.conf`，将轻量房间提高到 32、CPU 时间上限提高到 1200%、内存提高到 32 GiB，空闲回收改为 60 秒。物理准入仍为 4；这不是四路重场景的稳定性能保证。汇报建议每批 20–24 人语音体验，重物理演示限定 1–2 房间；原始测试与公网限制见 [容量实测](../docs/PERFORMANCE.md)。该配置与直连域名 drop-in 分开保存，安装器不会删除。

此次已为房间 11–32 初始化各自私有设备；没有复制其他房间身份。新环境管理员先为需要的房间独立绑定设备，例如在发布目录以 `DUCKKING_DATA_DIR=/var/lib/duckking` 运行 `duckking-setup --room 3`；管理 Key 只供初始化读取，页面不触发绑定。不要复制其他房间的身份或 token。配置变量见 `.env.example`。容量验证应包含多房间真实云端连接和独立动作；仅创建十个空房间不能当作十路云端或物理性能验收。


## 预热与重启后的体验恢复

服务模板通过 `DUCKKING_PHYSICS_PREWARM=1` 开启最多一个备用物理世界。它只在无物理世界／构建及语音占用时准备，首次常规场景领用，其他场景类型会释放不适用的备用实例；也可在 `/etc/duckking/runtime.env` 设置为 `0`。预热不提高既有物理并发准入值，也不代表网络模型加载已完成。

新页面能识别服务实例更新，提供一键换房并保留节目／场景选择；语音与演出必须手动重新开始。逐轮指标从保留的私有日志恢复，历史文本不公开。当前没有发布排空或跨进程物理会话迁移；首个修复版本发布后，旧版页面仍需刷新。边界见 [体验评审核验](../docs/UX_REVIEW.md)。
