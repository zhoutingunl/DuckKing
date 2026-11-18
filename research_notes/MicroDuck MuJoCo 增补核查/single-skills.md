# 单鸭新动作增量核查（2026-11-10）

## 哪些内容值得增补，哪些应纠正或保留为线索？

### Takeaway

建议真正新增 happy-hop、flamingo-cycle、footsteps，附条件新增 groove、playdead、polite-bow 与跳跃实验。不能把这些都列为“极低成本、即插即用”：61→14 只是张量形状，不保证命令语义、动作时延、滤波、站姿交接及执行器模型相同。本文仅核查上游文档、源码和文件；未运行推理、训练、MuJoCo 或实机。

### Cited Findings

| 条目／处理 | 可采纳的增量与建议报告措辞 | 证据级别及接入判断 |
|---|---|---|
| happy-hop：**新增＋纠正“极低成本”** | “发布了 Apache-2.0 ONNX；作者报告 Pollen 于 2026-09-01 在实体 MicroDuck 上演示成功，需恢复一控制步延迟。本文未独立复现。” | 最值得先做接入验证的单次跳跃；稳定站立入口、50 Hz、20 ms 动作延迟、无动作低通、零命令均为明确约束；不能只复制 ONNX。[卡片](https://huggingface.co/joanfox/microduck-happy-hop/blob/c0447da668255436eea070e862ad8eb89bad2ba1/README.md) |
| groove：**新增候选，降调推荐** | “10 秒舞蹈窗口；作者 CPU MuJoCo 测得约 126 BPM 膝部起伏与小幅头部摇摆。到时由 daemon 中途切回 stand，不是舞蹈网络主动收稳。” | ONNX、schema-2 manifest、视频存在；训练 fork 未公开，未发现明确许可，未实机测试。适合研究候选，不能直接等同低成本可再分发动作包。[卡片](https://huggingface.co/kramp/microduck-groove/blob/b94e53dfad4c277c48447d44c6b8c014820fcc89/README.md) |
| flamingo-cycle：**新增，优先** | “可命令左右单足抬起、保持、放下；这与现有报告的 collision-flamingo-ii 是不同模型。” | Apache-2.0；ONNX＋控制脚本＋CPU 路线较完整，但 twist 改作 flag/side，需专用控制角色；作者仅仿真。[卡片](https://huggingface.co/RemiFabre/microduck-flamingo-cycle/blob/a69e4f6103a70e355983eb5d4e919da76778a40f/README.md) |
| footsteps：**新增，系统集成候选** | “落足追踪 ONNX 配合 FootstepNet 规划器；作者称追踪策略已在机器人测试，仿真落足误差约 5–7 mm。” | Apache-2.0；需 runtime 的 footsteps 分支、支撑足里程计和坐标变换，非 walking 槽替换。硬件表述仅为作者报告，未找到本次可独立核验的测量记录。[卡片](https://huggingface.co/apirrone/microduck-footsteps/blob/19c38fae6afabddf9c0821009028d0a37963f05f/README.md) |
| playdead：**新增，带恢复条件** | “5 秒坐下并仰躺装死，结束姿态就是背部着地；后接可自起策略，嘴部动作另由 runtime 编排。” | 有 ONNX、schema-2；作者报告 256 鸭仿真未侧翻／面朝地，velstand 接管 32/32 起身；未实机，未发现明确许可。不能写成完整的‘装死并自行恢复’单策略。[卡片](https://huggingface.co/drfonz-indigo/microduck-playdead/blob/7b49a6a70e781096c6a39fc3ce5cea25307e8565/README.md) |
| polite-bow：**新增，谨慎措辞** | “Motion Lab 导出的头／身体命令条件姿态策略，附 ONNX、checkpoint、生成任务源码和 CPU 预演指标；可作为轻鞠躬候选。” | 有权重但无 manifest；命令含 head pitch 15°、body z −4 mm，不宜写成零命令自动 one-shot。指标质量门宣称通过，身体 pitch 目标却为 0，不能仅凭它证明明显躯干鞠躬；未发现明确许可。[源码载体](https://huggingface.co/fffiloni/microduck-polite-bow-b1d864/blob/9a9d21a85cf7b5cbd1854c03ad58bd949502a5ea/compiled_motion.json)、[指标](https://huggingface.co/fffiloni/microduck-polite-bow-b1d864/blob/9a9d21a85cf7b5cbd1854c03ad58bd949502a5ea/preview_metrics.json) |
| moonwalk：**未证实，不列完成动作** | “有导出权重及后退步态预演，但上游自动动作质量门未通过、月步语义未核实。” | `motion_quality_passed=false`、`semantic_quality_unverified=true`；仅证明一次 5 秒 CPU rollout 可运行，不能证明月步。无 manifest／明确许可。[指标](https://huggingface.co/fffiloni/microduck-moonwalk-backward-55e6af/blob/951073cb7791a898e3e5ecb242c5bcccf40aa72f/preview_metrics.json) |
| beak-throw：**新增实验，不列易接入** | “含 runtime 补丁与嘴部衬垫的 24 mm 球抛掷实验；作者仿真 50/50 通过依赖强制动作限幅，原始网络输出门全部失败。” | Apache-2.0；嘴部开合、抛出后 stand 接管由补丁处理；有 ONNX 与 checkpoint，硬件未验证。机械附件＋runtime 改造，成本高。[README](https://github.com/llama/microduck-beak-throw/blob/410ed2249d62cd7aa4c642cd2c4e9b56f9a0cbfd/README.md) |
| max-height-jump：**新增实验** | “作者在单种子 CPU MuJoCo 测得 31.67 mm；单独跳跃策略未达持续站稳标准，预览另混合站立策略完成收尾。” | Apache-2.0；有双 ONNX、checkpoint、交接合同、源树补丁；非物理极限、非随机鲁棒性证明、未实机。[README](https://github.com/ThomasBurgess2000/microduck-max-height-jump/blob/7e5dc6028900f13d145e6710847378b007a675e9/README.md) |
| chenp9527 jump：**新增实验，明确未通过项** | “128 次随机化仿真中 50.8% 落在 3–6 cm 区间、未跌倒；最大落地力 128.3 N，高于作者 40 N 目标。” | Apache-2.0；有 ONNX／PT／任务源码；全 13 命令必须置零。不是每次都达 3–6 cm，落地冲击尚未解决。[README](https://github.com/chenp9527/microduck-jump/blob/ace589eadd1be6aed4e39a27d8bd8e275b2b9cfe/README.md) |
| 318_lab jump：**已有线索，补证据** | “现有报告已列该仓库；现可补：实际 jump.onnx、训练任务及浏览器推理切换实现存在。” | 浏览器控制每步由 ONNX 写入关节目标后 `mj_step`，jump 触发清零动作历史，2 秒后直立交回 walk、3 秒超时；失败可 reset。没有新增本地运行证据，也未建立与 BAM/Backlash 执行器的一致性，不升级为实机就绪。[代码](https://github.com/Liyucheng1997/318_lab-microduck-simulator/blob/512d4bec6fc3ba321d29c93312be72856ad21268/app/src/game/game.js#L660)、[训练说明](https://github.com/Liyucheng1997/318_lab-microduck-simulator/blob/512d4bec6fc3ba321d29c93312be72856ad21268/training/README.md) |
| 社区 standup：**纠正／官方已覆盖** | “QingMuLYL 额外发布 6 秒起立策略，但 manifest 的入口为 sitting；训练导出来自 dirty checkout。不能据此声称任意推倒姿态恢复已验证。” | 有 ONNX、schema-2，无演示／评估文件／明确许可；现有报告已列官方 alpha_stand，故‘无官方 ONNX’错误。[社区 manifest](https://huggingface.co/QingMuLYL/microduck-standup/blob/7f8d01e9aae4ab005b8685677f16df1710d81bd8/manifest.json)、[官方 alpha_stand](https://huggingface.co/pollen-robotics/microduck-policies/blob/283771bcb3690a0a94a288c108365d9b630d21e4/alpha_stand.onnx) |
| electric-slide：**未证实／失败研究线索** | “最新作者说明明确尚非完成的舞蹈策略：新要求未过、CPU BAM 诊断跌倒、无完成的 25 鸭训练终演或实机部署。” | 存在脚本编舞叠加官方低层策略、早期命令学习与失败 ONNX；不能把早期视频或被撤回的质量结论当现成舞蹈策略。许可标为 other，资产需分层核对。[最新置顶声明](https://huggingface.co/Histochemichael/microduck-electric-slide-policy/blob/67eb1f1eaf5e3a91f027fe45b8b9bb4efaa6be04/README.md)、[失败审计](https://huggingface.co/Histochemichael/microduck-electric-slide-policy/blob/67eb1f1eaf5e3a91f027fe45b8b9bb4efaa6be04/experiments/2026-09-13/README.md) |

### Inferences

- **建议定点位置**：§4.2 加 happy-hop／flamingo-cycle／footsteps 及带限制的 groove、playdead、polite-bow、beak-throw、两个跳跃实验；§4.3 保留 moonwalk／electric-slide 为未过门槛线索并补强已有 318_lab 行；§2.1 保留 alpha_stand，§2.2“未发现官方 jump”后补社区跳跃交叉引用；§6.1 只把 happy-hop／flamingo-cycle 提为下一轮合同验收候选，footsteps 标系统改造；§7.3 补许可缺项。
- 对 DuckKing 的建议次序是：先验证 happy-hop 与 flamingo-cycle 的完整合同；footsteps 单列为新系统能力；groove／playdead／polite-bow 先解决许可及结束／恢复语义；抛球、高度优化跳跃、Electric Slide 留实验栏。此为基于上表的工程判断，不是实测工时。
- “官方未发布 jump”与“社区存在跳跃 ONNX”并不矛盾。既有报告关于官方注册表的范围结论可保留，补社区例外即可。官方 alpha_stand、playground 高台长跳／后空翻、collision-flamingo-ii 已有覆盖，不应再当成此轮新发现。

### Gaps

- 本次没有新推理、训练、视频逐帧测量或独立硬件复现；作者的仿真成功率／物理展示均按作者报告注明。
- 本轮只沿注册表定位指定单鸭动作，electric-slide 因注册表无匹配项而单独查到原 HF；没有重新遍历整个 Hub。

## 接入合同、源码与可下载制品具体支持什么？

### Takeaway

本次实际下载了 14 个 ONNX 文件（含重复发布的 FootstepNet），均为二进制而非 LFS 指针。仅静态解析 Protobuf 的图输入输出：12 个动作策略为 float32 `obs[1,61] → actions[1,14]`，两个相同 FootstepNet 文件为 `obs[N,8] → step[N,3]`；这不等于 ONNX checker、数值推理或闭环验证。

### Cited Findings

**可复查制品索引。** 以下 resolve/raw URL 在本轮成功下载；完整字节数、SHA-256 保存在缓存 `single/artifact-download-checks.json`，静态接口在 `single/onnx-static-interface.json`。这些是本轮文件检查结果，不是作者性能结果。

| 制品 | 固定版本下载 |
|---|---|
| happy-hop | [policy.onnx](https://huggingface.co/joanfox/microduck-happy-hop/resolve/c0447da668255436eea070e862ad8eb89bad2ba1/policy.onnx)，793,778 字节；SHA-256 `abd6db1bca2f2a583508cfd9a6fd144a7cce65b302827b9b9a0c5227fc2acae9`，与卡片声明一致 |
| groove | [policy.onnx](https://huggingface.co/kramp/microduck-groove/resolve/b94e53dfad4c277c48447d44c6b8c014820fcc89/policy.onnx) |
| playdead | [policy.onnx](https://huggingface.co/drfonz-indigo/microduck-playdead/resolve/7b49a6a70e781096c6a39fc3ce5cea25307e8565/policy.onnx) |
| flamingo-cycle | [policy.onnx](https://huggingface.co/RemiFabre/microduck-flamingo-cycle/resolve/a69e4f6103a70e355983eb5d4e919da76778a40f/policy.onnx) |
| polite-bow | [policy.onnx](https://huggingface.co/fffiloni/microduck-polite-bow-b1d864/resolve/9a9d21a85cf7b5cbd1854c03ad58bd949502a5ea/policy.onnx) |
| moonwalk | [policy.onnx](https://huggingface.co/fffiloni/microduck-moonwalk-backward-55e6af/resolve/951073cb7791a898e3e5ecb242c5bcccf40aa72f/policy.onnx) |
| standup | [policy.onnx](https://huggingface.co/QingMuLYL/microduck-standup/resolve/7f8d01e9aae4ab005b8685677f16df1710d81bd8/policy.onnx) |
| footsteps | [footsteps.onnx](https://huggingface.co/apirrone/microduck-footsteps/resolve/19c38fae6afabddf9c0821009028d0a37963f05f/footsteps.onnx)、[footstepnet.onnx](https://huggingface.co/apirrone/microduck-footsteps/resolve/19c38fae6afabddf9c0821009028d0a37963f05f/footstepnet.onnx) |
| beak-throw | [beak_throw.onnx](https://huggingface.co/q2p/microduck-beak-throw/resolve/f32dc673fa0dea71457a5fe716497d2d5483e087/beak_throw.onnx)；同树另列 alpha_stand.onnx、checkpoints/model_2150.pt，本轮未下载后二者 |
| max-height-jump | [max_height_jump.onnx](https://raw.githubusercontent.com/ThomasBurgess2000/microduck-max-height-jump/7e5dc6028900f13d145e6710847378b007a675e9/policy/max_height_jump.onnx) |
| chenp9527 jump | [policy.onnx](https://raw.githubusercontent.com/chenp9527/microduck-jump/ace589eadd1be6aed4e39a27d8bd8e275b2b9cfe/policy.onnx) |
| 318_lab jump | [jump.onnx](https://raw.githubusercontent.com/Liyucheng1997/318_lab-microduck-simulator/512d4bec6fc3ba321d29c93312be72856ad21268/app/public/policies/jump.onnx) |

**关键运行差异。**

- **happy-hop**：Backlash、BAM XL330、输出侧编码器视角、约 1.75 A 电流限制；训练入口为 Backlash walking 收到零速后站稳 1 秒。3 秒外部切换窗口，13-D 命令全零、HOME 周围 scale=1、归一化已烘焙、head/legs lowpass 均需 1.0。卡片的 `infer_policy.py --happy-hop ... --delay 1 --new-cmd-obs` 属实验集成，不能假设 DuckKing 当前 pin 已带此参数。卡片报告首次实机少一步延迟导致跳幅下降。[合同](https://huggingface.co/joanfox/microduck-happy-hop/blob/c0447da668255436eea070e862ad8eb89bad2ba1/README.md)、[机器合同](https://huggingface.co/joanfox/microduck-happy-hop/blob/c0447da668255436eea070e862ad8eb89bad2ba1/manifest.json)
- **happy-hop 内部矛盾**：相同 SHA 下 README 声称实机成功，而 manifest 仍是 `sim-only-hardware-candidate` 且 known_limits 留有未实机字样；manifest 也未完整写入 README 新增的一步动作延迟。报告应同时记录版本元数据滞后，不能无条件把它当完整的自动安装合同。[README](https://huggingface.co/joanfox/microduck-happy-hop/blob/c0447da668255436eea070e862ad8eb89bad2ba1/README.md)、[manifest](https://huggingface.co/joanfox/microduck-happy-hop/blob/c0447da668255436eea070e862ad8eb89bad2ba1/manifest.json)
- **groove / playdead / standup**：schema-2 均声明 XL330、50 Hz、constant 零命令。入口依次为 standing、standing、sitting；时长 10、5、6 秒。groove 前文“返回站立”与末尾“到时中途交回 stand”有冲突，应采用更具体限制；playdead 结束仰躺，jaw 不在 14 动作里；standup dirty=true 且缺未提交改动快照。[groove manifest](https://huggingface.co/kramp/microduck-groove/blob/b94e53dfad4c277c48447d44c6b8c014820fcc89/manifest.json)、[playdead manifest](https://huggingface.co/drfonz-indigo/microduck-playdead/blob/7b49a6a70e781096c6a39fc3ce5cea25307e8565/manifest.json)、[standup manifest](https://huggingface.co/QingMuLYL/microduck-standup/blob/7f8d01e9aae4ab005b8685677f16df1710d81bd8/manifest.json)
- **flamingo-cycle**：普通 allcollisions 模型＋BAM XL330 的 CPU MuJoCo 证据，`twist=[flag,side,0]`，perpetual、无固定结束时间；两侧切换约 1.5 秒、抬足约 9 cm。作者压力试验 24 次有 2 次跌倒，向后 ≥0.18 m/s 推扰是已知弱项。控制脚本暂占 walk、禁用 stand 和其他技能，cmd_alpha=1，并调整 fall 门限；自身声明只是测试工具，永久集成需专用 flamingo 角色。因此不是在现有 walk 槽长期无损安装。[manifest](https://huggingface.co/RemiFabre/microduck-flamingo-cycle/blob/a69e4f6103a70e355983eb5d4e919da76778a40f/manifest.json)、[控制脚本](https://huggingface.co/RemiFabre/microduck-flamingo-cycle/blob/a69e4f6103a70e355983eb5d4e919da76778a40f/control.py)
- **footsteps**：训练任务为 `Mjlab-Footsteps-Flat-Backlash-MicroDuck`；61-D 中的 twist 不再是速度，而是支撑足鞋底坐标中的 `(dx,dy,dyaw)` 落足目标。鞋底中心位于 foot site 前 7 mm；planner 的 8-D 含目标、左右支撑、障碍物信息，输出还需左右镜像、盒／椭球裁剪及 95 mm 中性脚间距变换。两处下载的 FootstepNet SHA-256 相同；这只证明制品同一，不证明跟踪器和 planner 在本地已接通。[追踪合同](https://huggingface.co/apirrone/microduck-footsteps/blob/19c38fae6afabddf9c0821009028d0a37963f05f/README.md)、[规划合同](https://huggingface.co/apirrone/microduck-footstepnet/blob/1132e672d261cb8520c296acaa06fac955424b14/README.md)
- **polite-bow / moonwalk**：生成源码内嵌于 compiled_motion.json，而不是只有宣传卡。前者从 StandUp 派生且始终站立初始化、head pitch 上限 15°、body z 下降最多 4 mm，仍需外部命令时间表；后者从 velocity 派生，vx 训练范围 −0.25…−0.08 m/s，预演 vx=−0.15，主要改足滑惩罚和对称性。二者无 manifest，原始 API 形状不能代替 one-shot 运行合同。[bow 生成源码](https://huggingface.co/fffiloni/microduck-polite-bow-b1d864/blob/9a9d21a85cf7b5cbd1854c03ad58bd949502a5ea/compiled_motion.json)、[moonwalk 生成源码](https://huggingface.co/fffiloni/microduck-moonwalk-backward-55e6af/blob/951073cb7791a898e3e5ecb242c5bcccf40aa72f/compiled_motion.json)
- **beak-throw**：公开训练 overlay 针对 upstream `d424a0c`，runtime patch 针对 `590b986`。2.4 秒网络身体动作之外，runtime 使嘴部由 +20° 在 phase 0.30–0.34 开到 +30°，随后切 alpha_stand；球依靠模拟柔性垫、唇边及挡块保持，不是 weld。下载的 HF manifest 是 schema-1 的双策略集合，不是一个可直接 `policy add` 的 schema-2 文件。[README](https://github.com/llama/microduck-beak-throw/blob/410ed2249d62cd7aa4c642cd2c4e9b56f9a0cbfd/README.md)、[HF manifest](https://huggingface.co/q2p/microduck-beak-throw/blob/f32dc673fa0dea71457a5fe716497d2d5483e087/manifest.json)、[runtime 补丁](https://github.com/llama/microduck-beak-throw/blob/410ed2249d62cd7aa4c642cd2c4e9b56f9a0cbfd/runtime/microduck-runtime.patch)
- **max-height-jump**：twist.x 是发射 flag，落地清零并有 0.75 秒后备截止；站立交接在触发后 0.22 秒开始、持续 0.14 秒，以 smoothstep 混合两个策略输出，不能只提供 jump ONNX。作者模型为 allcollisions、BAM M6 电压模型与电压跌落／延迟，明确非 Backlash；CPU 证据每个配置仅 seed=7、175 步。发布 eval 脚本可读到 ONNX Runtime session 及 action blend，但未在此运行。[交接 manifest](https://github.com/ThomasBurgess2000/microduck-max-height-jump/blob/7e5dc6028900f13d145e6710847378b007a675e9/handoff/manifest.json)、[评估范围](https://github.com/ThomasBurgess2000/microduck-max-height-jump/blob/7e5dc6028900f13d145e6710847378b007a675e9/evaluation/README.md)、[评估源码](https://github.com/ThomasBurgess2000/microduck-max-height-jump/blob/7e5dc6028900f13d145e6710847378b007a675e9/training/untracked/scripts/eval_jump_checkpoint.py)
- **chenp9527 jump**：任务继承 velocity 框架但把机器人换为 `MICRODUCK_STANDUP_ROBOT_CFG`（groundcontact），保留传感器，action scale=1，命令全零。它的正常态合同不等于官方 Backlash walking；README 的 train/play 路线仍要求 CUDA，本轮未证明 CPU play 即开即用。[任务源码](https://github.com/chenp9527/microduck-jump/blob/ace589eadd1be6aed4e39a27d8bd8e275b2b9cfe/src/mjlab_microduck/tasks/microduck_hop_env_cfg.py#L230)

### Inferences

- 相同输入输出形状下至少已经看到三种 twist 意义：速度、落足目标、单足 flag／side；另有跳跃 flag 和全零触发。自动把任意 61/14 制品塞入现有 walking 会产生错误命令。
- 对 318_lab，静态源码可支持“真实 ONNX 输出进入 MuJoCo 控制／正常跳跃分支没有给根节点施加起跳位移”的窄结论；它有跌倒后 reset 和手动鼠标外力，不应从录屏推导所有状态都由策略自主恢复。

### Gaps

- 未完整验证每个图的所有算子和内部 normalizer；“已烘焙”主要来自导出说明，静态形状核查不覆盖归一化数值。
- 不安装／执行上游测试、训练任务或新 inference；“CPU 路线存在”表示文档／代码可定位，非本机兼容性通过。
- 除有明确模型变体的项目外，本次未逐项核完 playdead／community standup 的完整训练源树；groove 则明确自述 fork 未公开。不能从 hw_rev=1、XL330 推断 Backlash 配置完全一致。

## 哪些许可证与实机说法应保留限定？

### Takeaway

happy-hop 的 Apache 标识可核实，实机演示属于作者发布的第一手报告；groove 的问题应准确写为“未找到明确授权”，不是断言作者禁止使用。多个其它动作同样缺明确模型许可，不能只对 groove 提醒。

### Cited Findings

- happy-hop、flamingo-cycle、footsteps／FootstepNet 的模型卡明确 `license: apache-2.0`；happy-hop 发布实体演示媒体 `media/PXL_20260901_133625139.TS~2.mp4`，但本轮未观看完整视频、未联系 Pollen、未独立复现实机。[happy-hop 文件树](https://huggingface.co/joanfox/microduck-happy-hop/tree/c0447da668255436eea070e862ad8eb89bad2ba1)、[flamingo 卡片](https://huggingface.co/RemiFabre/microduck-flamingo-cycle/blob/a69e4f6103a70e355983eb5d4e919da76778a40f/README.md)、[footsteps 卡片](https://huggingface.co/apirrone/microduck-footsteps/blob/19c38fae6afabddf9c0821009028d0a37963f05f/README.md)
- groove 固定版本文件树仅 `.gitattributes / README.md / manifest.json / policy.onnx / replay.mp4`，README front matter 无 license；playdead、QingMuLYL standup、fffiloni bow／moonwalk 同样在本轮所查固定版本无明确 license 文件或卡片许可字段。上游训练代码 Apache 不自动证明这些模型新制品的授权。[groove 树](https://huggingface.co/kramp/microduck-groove/tree/b94e53dfad4c277c48447d44c6b8c014820fcc89)、[playdead 树](https://huggingface.co/drfonz-indigo/microduck-playdead/tree/7b49a6a70e781096c6a39fc3ce5cea25307e8565)、[standup 树](https://huggingface.co/QingMuLYL/microduck-standup/tree/7f8d01e9aae4ab005b8685677f16df1710d81bd8)、[bow 树](https://huggingface.co/fffiloni/microduck-polite-bow-b1d864/tree/9a9d21a85cf7b5cbd1854c03ad58bd949502a5ea)、[moonwalk 树](https://huggingface.co/fffiloni/microduck-moonwalk-backward-55e6af/tree/951073cb7791a898e3e5ecb242c5bcccf40aa72f)
- beak-throw、max-height-jump、chenp9527 jump 各自仓库有 Apache-2.0 LICENSE；其机器人网格／上游素材不因此改授权。318_lab 固定源码树未发现顶层 LICENSE；electric-slide 模型卡标 `other`，代码／动作数据／上游机器人资产仍需逐层核实。[beak LICENSE](https://github.com/llama/microduck-beak-throw/blob/410ed2249d62cd7aa4c642cd2c4e9b56f9a0cbfd/LICENSE)、[max-height LICENSE](https://github.com/ThomasBurgess2000/microduck-max-height-jump/blob/7e5dc6028900f13d145e6710847378b007a675e9/LICENSE)、[chen LICENSE](https://github.com/chenp9527/microduck-jump/blob/ace589eadd1be6aed4e39a27d8bd8e275b2b9cfe/LICENSE)、[318 源码树](https://github.com/Liyucheng1997/318_lab-microduck-simulator/tree/512d4bec6fc3ba321d29c93312be72856ad21268)、[electric-slide](https://huggingface.co/Histochemichael/microduck-electric-slide-policy/blob/67eb1f1eaf5e3a91f027fe45b8b9bb4efaa6be04/README.md)

### Inferences

- 建议用“作者报告实机演示／作者仿真验证／本文静态制品核查／DuckKing 未接入”四个独立字段，避免把文件存在、视频存在、作者演示和本项目复现合并成一个已验证标记。
- 许可缺失影响可再分发集成的可评审性，因此不应把 groove 和其他缺授权模型排成马上能合入应用的最高优先级；仍可作为资料链接与后续技术研究候选。

### Gaps

- 无本轮新实机证据；footsteps 的硬件说法仅模型卡一句说明，不能把它升级为全面硬件验收。
- 本笔记未更改报告、应用或 Git 分支，也未执行部署、训练、推理或对外发消息；下游可按采纳表选择增补，事实范围到此停止扩展。
