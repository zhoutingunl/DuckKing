# 灵矽语言支持调研与平台级验证

研究日期：2026-11-04（竞赛冻结解除后，用户明确指示可修改仓库）。本笔记区分三个层次：官方文档声明、真实云端 API 实测、以及尚未实测的部分。验证使用本地密钥文件（`~/.secrets/lingxi`），Key 未写入任何仓库文件或命令输出。

## 结论

灵矽支持法语。平台级已实测确认；语音端到端未实测；音色克隆按官方文档分套餐。

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
- 法语提示词中的触发词（« pas éclair »、« l'ours qui frissonne » 等）是笔译草案，未经过真实语音识别回路验证能否触发对应工具。
- 音色克隆免费版不支持法语音色；未核对任何账单消耗。
- 36 种语言列表是 2026-11-04 一次观测，服务端配置可能变化，以实时调用为准。

## 对应代码变更

分支 `feat/configurable-agent-language`：

- `src/duckking/onboarding.py`：`PROMPTS` 内置中/法双语提示词（zh 保持原文逐字不变），`setup_device` 新增 `lang_code` 参数，CLI 新增 `--lang-code`；未内置提示词的语言在创建前显式报错，不用中文提示词冒充其他语言。
- `tests/test_onboarding.py`：新增默认中文、法语文案选择、不支持语言提前失败三项测试。
- 同步更新 `README.md` 与 `docs/VALIDATION.md`。
