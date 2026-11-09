# MicroDock、官方计数与本地场景增补核查

## 1. MicroDock 有哪些应补、应纠正或仍未证实的内容？

### Takeaway

2026-11-10 的增量核查：原报告 §3.2 已准确覆盖 v2 的主要成果和失败边界，真正缺少的是 v1 站姿倒退入坞对照，以及 v2 的 6 N 结果与精度分轴说明。以下成功率、时间和误差均来自作者固定在 `052a2494dd6372289221c7a4f24a245b443dd75f` 的资料；本轮只读源码、解析既有 JSON，没有运行仿真、推理、训练或实机测试。[v1](https://github.com/Vottivott/microduck-playground/blob/052a2494dd6372289221c7a4f24a245b443dd75f/hardware/microdock/README.md)；[v2](https://github.com/Vottivott/microduck-playground/blob/052a2494dd6372289221c7a4f24a245b443dd75f/hardware/microdock-v2/README.md)

### Cited Findings

| 判定 | 增补内容 | 核查结果与建议 |
|---|---|---|
| **add** | v1 倒退站姿入坞 | 原报告正文未独立说明 v1。作者用未修改官方 velstand，脚本接近标签→转 180°→`vx=-0.4` 倒退→几何连接后停止；BAM、4 N 磁力、真值标签加噪声下，`backin30.json` 为 30/30、无电源按钮接触。可作为“不需新训练策略”的机械入坞对照，不能称免适配、真实 AprilTag 或实机充电。[说明](https://github.com/Vottivott/microduck-playground/blob/052a2494dd6372289221c7a4f24a245b443dd75f/hardware/microdock/README.md)；[脚本](https://github.com/Vottivott/microduck-playground/blob/052a2494dd6372289221c7a4f24a245b443dd75f/hardware/microdock/sim/docking.py)；[30 次记录](https://github.com/Vottivott/microduck-playground/blob/052a2494dd6372289221c7a4f24a245b443dd75f/hardware/microdock/results/backin30.json) |
| **already covered + add** | v2 4 N／6 N | 原报告已有 4 N 入／离坞 30/30。补 6 N 的 10/10 入坞、脱离、站起和走开；4 N 脱离中位 1.06 s／最大 1.34 s，6 N 中位 1.49 s／最大 5.26 s。40 次中两次起身擦罩，最大 5.6 N。都是作者条件内记录。[4 N JSON](https://github.com/Vottivott/microduck-playground/blob/052a2494dd6372289221c7a4f24a245b443dd75f/hardware/microdock-v2/results/undock30.json)；[6／8 N JSON](https://github.com/Vottivott/microduck-playground/blob/052a2494dd6372289221c7a4f24a245b443dd75f/hardware/microdock-v2/results/undock_magnet.json) |
| **correct supplement** | “8 N 出不来” | 应改为 8 N 入坞 10/10、脱离 2/10、站起及走开各 1/10。原报告数值已正确；不要改坏。该批最大起身罩接触力 92.6 N，也支持不可用“坐姿绝不会危险”概括。[JSON](https://github.com/Vottivott/microduck-playground/blob/052a2494dd6372289221c7a4f24a245b443dd75f/hardware/microdock-v2/results/undock_magnet.json) |
| **correct supplement** | “入坞精度 0.1 mm 级” | `seated30.json` 的三轴最大绝对误差为轴向 0.11、横向 0.64、竖向 0.46 mm（本轮对作者 JSON 做静态取最大值）；README 约写 0.1／0.6／0.5 mm。不能称三维 0.1 mm、相机定位精度或实机精度；可省略精度宣传，只保留条件内接触成功率。[JSON](https://github.com/Vottivott/microduck-playground/blob/052a2494dd6372289221c7a4f24a245b443dd75f/hardware/microdock-v2/results/seated30.json) |
| **already covered + nuance** | 无匹配延迟时仅 1/10 | 原报告已注明。作者 README 报告该对照；固定结果目录没有单独延迟消融 JSON，不能把它称为本轮重算结果。`latency.py` 为 scoot 加入 3–6 个物理步的动作延迟（5 ms 步长即 15–30 ms），关节速度和 IMU 观测延迟一个 20 ms 控制步；正式离坞批次调用 `official=False, scoot=True`。真实硬件延迟尚未测量。[训练说明](https://github.com/Vottivott/microduck-playground/blob/052a2494dd6372289221c7a4f24a245b443dd75f/hardware/microdock-v2/training/README.md)；[延迟实现](https://github.com/Vottivott/microduck-playground/blob/052a2494dd6372289221c7a4f24a245b443dd75f/hardware/microdock-v2/sim/latency.py)；[批次脚本](https://github.com/Vottivott/microduck-playground/blob/052a2494dd6372289221c7a4f24a245b443dd75f/hardware/microdock-v2/sim/undocking_seated.py) |
| **unproven** | 61／14／50 Hz 所以“集成低成本” | 形状属实：48 本体感知＋13 命令，14 未滤波动作，50 Hz，normalizer 在 ONNX 内；但坐姿命令语义、模型／接触、BAM、延迟和切换状态均需保留。DuckKing 当前 `PolicyDriver.step` 把目标直接写入 XML position actuators，读当前观测，不是原作者 BAM＋延迟管线。原报告“独立适配／中高投入”更稳妥。[训练契约](https://github.com/Vottivott/microduck-playground/blob/052a2494dd6372289221c7a4f24a245b443dd75f/hardware/microdock-v2/training/README.md)；[BAM 场景构建](https://github.com/Vottivott/microduck-playground/blob/052a2494dd6372289221c7a4f24a245b443dd75f/hardware/microdock/sim/docking.py)；[DuckKing driver](https://github.com/zhoutingunl/DuckKing/blob/5d9b92cb8c096814fae311d6700ac829792df687/src/duckking/simulation.py#L77) |
| **unproven** | 坐姿低功耗、无热／磨损、不会倒 | 这是作者的设计动机，不是已证明的安全、热或能效结论；本轮未见硬件对照或能量积分。作者训练说明还报告早期坐姿策略顶髋关节限位，CPU rehearsal 估计约 18 W 电机热，后以奖励约束改善；说明“坐下”本身不能证明零发热。[设计动机](https://github.com/Vottivott/microduck-playground/blob/052a2494dd6372289221c7a4f24a245b443dd75f/hardware/microdock-v2/README.md)；[训练失败记录](https://github.com/Vottivott/microduck-playground/blob/052a2494dd6372289221c7a4f24a245b443dd75f/hardware/microdock-v2/training/README.md) |

v1 的复现锚点比“官方策略”更具体：RL `bae39f59`；MuJoCo 3.10.0、onnxruntime 1.24.4、better-actuator-models 1.0.1；velstand SHA-256 `2fc7f8ee6acd7d0d3f66a99927b5d5a56589aeed02ec714de329b252d5ccf492`，sitstand `a6f102d9fd655782ba85bfffe18175c34621da719cffcdd673be7982a06fc254`。正式 v1 结果命令显式带 `--stop_gap 0`，脚本默认值 14 不等价。v2 原目录有两份正式 scoot ONNX 和一份 experimental ONNX，各 793942 bytes；该固定目录没有 `.pt` 完整训练 checkpoint，训练配方和 ONNX 不能写成完整续训工件已齐备。[v1 复现说明](https://github.com/Vottivott/microduck-playground/blob/052a2494dd6372289221c7a4f24a245b443dd75f/hardware/microdock/README.md#reproduce)；[固定全树](https://api.github.com/repos/Vottivott/microduck-playground/git/trees/052a2494dd6372289221c7a4f24a245b443dd75f?recursive=1)

### Inferences

- 建议 §3.2 加一段 v1 对照、将 v2 成功率写成 4／6／8 N 小表；不要把 v1 升格为完整离坞／休眠闭环。原报告对视觉真值、USB 几何、固定坞座、未上实机的限定应原样保留。
- Changelog 建议写：“补充 MicroDock v1 站姿倒退入坞基线；细化 v2 6 N 结果、分轴误差与延迟依赖；所有数值为上游作者记录，本次未运行仿真。”

### Gaps

- 未做任何本地 replay；不能证明这些成功率在 DuckKing 的旧 pin、XML 伺服或新场景成立。
- 没有核实实机磁力、电气接通、充电电流、电池 SOC、热／能效或整夜稳定性。不要导入“安全不倒”“无热磨损”“低成本即插即用”。

## 2. 官方计数与 apartment／vslam 的增量是什么？

### Takeaway

原报告的 10 个部署 ONNX、13 家族／33 注册 ID，以及 StandUp 有 alpha_stand 均无需改正。可补“七槽位不是七个模型”与“两个场景已经存在本地旧 pin，但尚未接入产品入口”，同时纠正增补的五柱描述。[官方 manifest](https://huggingface.co/pollen-robotics/microduck-policies/blob/283771bcb3690a0a94a288c108365d9b630d21e4/manifest.json)；[注册表](https://github.com/pollen-robotics/microduck_rl/blob/bae39f5900b318f7e87fc485c30a31213cfa14eb/src/mjlab_microduck/tasks/__init__.py)

### Cited Findings

| 判定 | 项目 | 核查与正文建议 |
|---|---|---|
| **already covered / correct supplement** | StandUp“有任务无官方 ONNX” | 官方固定 manifest 确有 `alpha_stand.onnx`，原报告 §2.1 和 §2.2 已注明；只是 DuckKing 当前八项下载未包含。不能将“当前应用未接”写成“官方未发”。[manifest](https://huggingface.co/pollen-robotics/microduck-policies/blob/283771bcb3690a0a94a288c108365d9b630d21e4/manifest.json)；[下载表](https://github.com/zhoutingunl/DuckKing/blob/5d9b92cb8c096814fae311d6700ac829792df687/scripts/fetch_scene_assets.py) |
| **already covered / correct supplement** | “各主任务均有 Backlash” | 实际 18 基础 ID＋15 Backlash＝33；Roulade、Spin、RollerStandUp 无已注册 Backlash 变体。原报告精确表正确。[注册实现](https://github.com/pollen-robotics/microduck_rl/blob/bae39f5900b318f7e87fc485c30a31213cfa14eb/src/mjlab_microduck/tasks/__init__.py) |
| **add nuance** | 七槽位 vs 十模型 | 七槽位是 runtime 的 walk／stand／sitstand／ground_pick／kick_left／kick_right／roulade 接口；10 是 HF manifest 的部署文件计数，含旧 alpha_walking／alpha_stand 与 roller／roller_crouch。计数单位不同，不互相否定。[runtime 槽位](https://github.com/pollen-robotics/microduck/blob/da34a2212ae12eddfd73d0dfbf924f291aaf1dc9/docs/robot/cheatsheet.md#the-slots-and-four-things-worth-knowing)；[manifest](https://huggingface.co/pollen-robotics/microduck-policies/blob/283771bcb3690a0a94a288c108365d9b630d21e4/manifest.json) |
| **add** | 本地已有 apartment／vslam | 本轮只读确认 `external/microduck_rl` HEAD 为 `b02fdea4902c2b93b7d34a83a6f05da4ececb7d3`，四个 XML 文件实际存在。两 scene 均 include `robot_allcollisions.xml`；DuckKing `_build` 无 apartment／vslam 分支。可把 §2.3 表注补为“旧 pin 本地已带、尚未接入”。[旧 pin apartment scene](https://github.com/pollen-robotics/microduck_rl/blob/b02fdea4902c2b93b7d34a83a6f05da4ececb7d3/src/mjlab_microduck/robot/microduck/scene_apartment.xml)；[旧 pin vslam scene](https://github.com/pollen-robotics/microduck_rl/blob/b02fdea4902c2b93b7d34a83a6f05da4ececb7d3/src/mjlab_microduck/robot/microduck/scene_vslam.xml)；[应用构建器](https://github.com/zhoutingunl/DuckKing/blob/5d9b92cb8c096814fae311d6700ac829792df687/src/duckking/simulation.py#L157) |
| **correct supplement** | “11.2 m 房间＋5 彩柱” | XML 有六个 `vs_pil_*`：红绿蓝黄四方柱、青紫两圆柱。11.2 m 是 `size=5.6` 的地板边长；墙中心 ±5.5 m、厚度 0.16 m，内侧净宽约 10.84 m。正文用“约 11 m 房间、六个彩色地标柱”足够，避免伪精确。[旧 pin 几何](https://github.com/pollen-robotics/microduck_rl/blob/b02fdea4902c2b93b7d34a83a6f05da4ececb7d3/src/mjlab_microduck/robot/microduck/vslam_room.xml) |
| **already covered / unproven** | 加载即得家居漫游 | apartment 确有多房间、家具、楼梯和物体；dock 四个 geom 都禁碰撞。加载 XML 只提供环境，不能证明避障、SLAM、自动导航或爬楼梯；原报告已准确限制。[旧 pin apartment 几何](https://github.com/pollen-robotics/microduck_rl/blob/b02fdea4902c2b93b7d34a83a6f05da4ececb7d3/src/mjlab_microduck/robot/microduck/apartment.xml) |

### Inferences

- Changelog 可写：“补充 runtime 七槽位与十个部署模型的统计口径；确认本地旧 pin 已包含 apartment／vslam；更正 vslam 为六地标柱，保持场景资产与导航能力的区分。”
- 无需因这份增补降低官方 StandUp 的工件等级，也无需把未接入的场景描写为新训练策略。

### Gaps

- 未编译、渲染或运行两个场景；“文件存在”不等于产品接入验收完成。
- 不采纳“接入构建器即得自主漫游”“七槽位＝七份现成策略”“所有主任务都具备 Backlash”三种合并口径。

## 3. 板载 USB 充电的官方证据能支持到哪里？

### Takeaway

原报告 §3.1 的硬件措辞比增补更可靠，应保留。2026-11-10 重新读取官方仓库问题页：#174 只足以支持官方参与者称最终量产单元将有 onboard charging；#470 仍未给出电流、电源路径和断电自启的官方答案。[#174](https://github.com/pollen-robotics/microduck/issues/174)；[#470](https://github.com/pollen-robotics/microduck/issues/470)

### Cited Findings

| 判定 | 声明 | 证据边界 |
|---|---|---|
| **already covered** | 最终量产单元有机载充电计划 | #174 中 apirrone 于 2026-09-06 作此答复；不是硬件版本化规格，也不是自主回桩功能声明。[官方讨论](https://github.com/pollen-robotics/microduck/issues/174) |
| **unproven as official claim** | “beta 板 USB-C 一律不充电、只到 5 V” | 此具体措辞出现在 MicroDock 社区 README；#174 的官方答复未逐板确认该负面结论。不能将它冒充 #174 的官方原话，亦不能外推所有 beta／生产批次。[社区 README 的实际来源](https://github.com/Vottivott/microduck-playground/blob/052a2494dd6372289221c7a4f24a245b443dd75f/hardware/microdock/README.md#what-it-relies-on)；[官方答复范围](https://github.com/pollen-robotics/microduck/issues/174) |
| **unproven** | USB 接电即自动唤醒、可同充同放、已电气闭环 | #470 明确提出这些问题，本轮页面只见提问与另一社区作者跟问，无具体官方参数。不要用模拟 `connected()` 和脚本 wake 替代电路验收。[#470](https://github.com/pollen-robotics/microduck/issues/470) |

### Inferences

- 对正文不必增加“beta USB-C 不充电”的硬件警告；若保留为研究线索，必须写成“社区作者对其目标 beta 板的描述，尚缺本轮可引用的官方逐版规格”。
- 本轮核查记录的改动建议集中于 v1、v2 精确结果及本地场景；硬件段保留已有边界，不宣称新的电气能力。

### Gaps

- 未找到能够把 USB 充电限制精确对应到具体 beta／量产硬件版本的官方规格。本轮没有测量电路，不作接线、充电电流或安全认证推断。
- 取回的固定上游 JSON、延迟源码、完整 tree 和官方 manifest 已缓存于 `.duckking/microduck-survey-review-20261110/dock/`；它们是文献审计材料，不是本站测试产物。
