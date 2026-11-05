# 灵矽语言支持调研与平台级验证

研究日期：2026-11-04（竞赛冻结解除后，用户明确指示可修改仓库）。本笔记区分三个层次：官方文档声明、真实云端 API 实测、以及尚未实测的部分。验证使用本地密钥文件（`~/.secrets/lingxi`），Key 未写入任何仓库文件或命令输出。

## 结论

灵矽支持法语。智能体级平台配置已实测确认；语音端到端未实测；音色克隆按官方文档分套餐。

## 验证方法与真实结果

三步均在真实云端（`https://xrobo.qiniu.com`）执行：

1. `GET /v1/languages`（Bearer 平台 Key）返回 `code: 0`，共 **36 种语言**：
   `zh=中文, en=英文, ja=日语, es=西班牙语, yue=粤语, de=德语, fr=法语, hi=印地语, it=意大利语, ko=韩语, nl=荷兰语, pt=葡萄牙语, ru=俄语, tr=土耳其语, vi=越南语, km=柬埔寨语, th=泰语, id=印尼语, mn=蒙古语, ar=阿拉伯语, pl=波兰语, uk=乌克兰语, ro=罗马尼亚语, bg=保加利亚语, hu=匈牙利语, ms=马来语, he=希伯来语, sv=瑞典语, kk=哈萨克语, fa=波斯语, sr=塞尔维亚语, lt=立陶宛语, cs=捷克语, no=挪威语, sw=斯瓦希里语, ka=格鲁吉亚语`。
2. `POST /xiaozhi/agent` 创建临时智能体 `DuckKing-FR-langcheck`（`langCode: "fr"`），返回成功；`GET /xiaozhi/agent/{id}` 查询详情确认 `langCode: fr`、`language: 法语`。
3. `DELETE /xiaozhi/agent/{id}` 删除临时智能体，返回成功。既有 DuckKing 智能体、设备绑定与聊天历史未受影响。

## 官方文档佐证

文档开源仓库 [qiniu/Xrobot-docs](https://github.com/qiniu/Xrobot-docs)：

- `docs/xrobot/api/language.md`：`GET /v1/languages` 返回「语言名称 + 语言代码」，数据来自服务端 `language.json` 配置，可用于智能体语种选择。文档示例仅列 zh/en/ja/yue，实际列表以 API 实测为准（本次实测 36 种）。
- `docs/xrobot/api/agent.md`：创建/更新智能体的 `langCode` 字段说明「可通过 GET /v1/languages 获取可选语言」。
- `docs/xrobot/api/voice-clone.md`：音色克隆 `language` 字段分套餐——免费版仅 zh/en；付费版（lite/pro）支持 zh、en、**fr**、de、ja、ko、ru、pt、th、id、vi；付费商务版列出 zh、en、ko、es、ar、hi、it、tr、yue、ms、he（未列 fr，两档列表分离，如需商务版法语音色应向七牛确认）。
- 官网宣称「支持多语言切换、角色定制及拟人声音克隆」。

## 未验证与限制

- **法语语音端到端未实测**：未验证法语语音 STT → 工具调用（点头/前进/闪身步等）→ 法语 TTS 的完整链路；现有实测记录（[VALIDATION.md](../../docs/VALIDATION.md)）全部基于中文语音。
- 法语触发词映射（pas éclair → 闪身步、secoue ta fourrure → 抖抖毛等）是笔译草案，未经真实语音识别回路验证能否触发对应工具。
- 音色克隆免费版不支持法语音色；未核对任何账单消耗。
- 36 种语言列表是 2026-11-04 一次观测，服务端配置可能变化，以实时调用为准。

## 对应代码变更

分支 `feat/configurable-agent-language`（已合并 main 的 PR #55 后重做设计）：

- `src/duckking/onboarding.py`：行为规则只保留一份中文权威提示词 `PROMPT`（与已实测 live 记录对应，逐字不变）。非中文语言经 `agent_prompt(lang_code)` 只替换回答语言子句并追加触发词映射（当前内置 `fr`）；该子句在权威提示词中缺失时拒绝生成，不静默降级。`setup_device` 新增 `lang_code` 参数，CLI 新增 `--lang-code`（默认 `zh`）；无指令的语言在创建/同步前显式报错。
- `--sync-prompt` 按智能体自身 `langCode` 同步对应提示词并校验，避免把法语智能体覆盖回中文；对无指令语言（如 ja）拒绝同步且不产生备份文件。
- `tests/test_onboarding.py`：新增 5 项测试（默认中文、法语替换且规则保留、不支持语言提前失败、按语言同步、无指令语言拒绝同步且无备份）。
- 同步更新 `README.md` 与 `docs/VALIDATION.md`（新增 2026-11-04 平台级验证小节）。

设计取舍：曾考虑为法语维护完整翻译提示词，但 main 上的权威中文提示词已扩展到约 60 行、覆盖数十个工具与场景规则，双语全文重复维护成本高且未经验证，故改为「单一权威规则 + 语言指令」结构。

## 欧洲访客默认法语（分支 feat/region-default-french）

用户随后提出「访问 IP 在欧洲（非英国）默认法语」，并提供七牛内部使用的 ipdb 地址库（`neo.ipv4.ipdb` / `neo.ipv6.ipdb`，2024-12 构建）与参考查询代码（qiniu_tools/ip_db.py，经 `ipip-ipdb` 包的 `ipdb.city.City` 查询，含 `country_code` 字段）。

- 数据面：选择**本地进程内查询**而非外部地理 API——访客 IP 不出服务器、无限流依赖，与仓库「敏感信息不入库不出站」的隐私习惯一致；地址库文件本身不入仓库（体积与再分发许可），经 `DUCKKING_GEO_DB_DIR` 指定目录，缺文件时回退默认中文。网关已断言国家码时可用 `DUCKKING_GEO_COUNTRY_HEADER`（如 `CF-IPCountry`）直接采用，优先于本地库。
- 规则面：地理欧洲（ISO 国家码集合，含瑞士/北欧岛屿/皇家属地/TR/RU/CY/高加索三国，排除 GB）→ 默认 `fr`；私有、内网、畸形地址、查询失败一律回退 `zh`，不猜测。早先曾想用库内 `continent_code==EU` 判断，但网关头路径没有大洲码，统一为国家码集合更一致、可测。
- 交互面：`GET /api/ui-preferences` 返回 `{language, region, room}`（不含 IP）；前端 `ui-language.js` 以「精确中文字符串 → 法语」字典 + TreeWalker 替换主工作台界面，并监听语音状态事件重复应用——voice.js/main.js 的字符串赋值逻辑零改动，回归风险限制在新模块。欧洲访客未手动选房时默认进入 `DUCKKING_FRENCH_ROOM` 房间，把真实法语语音（依赖该房间智能体 `langCode=fr`）与法语界面组合起来；`?lang=` 与卡片开关可覆写。
- 边界：法语界面只覆盖主工作台页；语音转写、日志与云端回复保持原文；法语语音链路仍未端到端实测；地址库 2024-12 版本，个别边界 IP 归属可能过时。

验证：真实后端 + 真实地址库实测法国/英国/本机三种请求的接口响应；后端 11 项单测（注入假 lookup，真实库集成测试无库时自动跳过）、前端 3 项 node 测试、全量 pytest 与前端单测、生产构建通过。


## 三语区默认（2026-11-05，分支 feat/trilingual-region-default）

用户提出完整需求：美国/英国默认英语（英语识别，同时识别中文和法语），欧洲（非英国）默认法语（同时识别中文和法语），导航最右侧「源代码」改为「语言」菜单、「源代码」移到「部署记录」之后。落地时 main 已在 #56/#57 合入后被跟进修复（可信代理校验、法语房间池、房间认领语言参数），本分支在其上扩展：

- `ENGLISH_COUNTRY_CODES = {US, GB}`：欧洲集合不含 GB，GB/US → `en`；加拿大、澳大利亚等未指定国家仍回退 `zh`。
- `DUCKKING_ENGLISH_ROOMS` 与法语池同规则（互斥校验、独立申领、空闲回收保留）；`claim?language=en` 返回 `voice_language: en`，池满降级为 `default` 并由前端提示。
- `onboarding` 新增 `en` 指令：英语回答 + 触发词映射（flash step→闪身步等）+ 声明理解中文/法语并按用户所说语言回答；`fr` 指令同步补充多语理解声明。注意：多语识别是提示词层面的声明，灵矽云端 STT 对同一智能体的实际多语识别效果尚未实测。
- 前端字典重构为每键 `{en, fr}` 双译列（约 92 键），`applyInterface(language)` 按列替换；导航「语言」菜单（中文/English/Français）在所有页面可用，选择本地保存并刷新；「源代码 ↗」移入共享导航，10 个页面头部的固定链接移除。
- e2e 导航布局断言同步改写（源代码位于语言菜单左侧、语言菜单贴右缘）。

线上探测记录：功能部署前，带法国/英国/美国 XFF 与不带的请求全部返回 `zh`/`region:null`——OR 出口不在 `DUCKKING_GEO_TRUSTED_PROXIES`（默认仅 loopback），转发头按设计被忽略。需要部署配置补上 OR 来源网段，区域默认才会在线上生效；这是运维配置而非代码缺陷。
