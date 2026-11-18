# MicroDuck 社区场景、动作和自治能力核查

调研日期：2026-11-10，Asia/Shanghai。范围为公开 GitHub 仓库、作者 Hugging Face 工件和公开问题/PR；没有运行任何社区策略、训练、物理验收或真机实验。下面的数值均为作者发布结果，不能作为 DuckKing 成绩。代码、README、文件树和固定提交已只读保存在 `.duckking/microduck-survey-20261110/`。未下载全部大模型或 Git LFS 权重，不把“目录存在”等同于“在本机复现成功”。

## 1. “自动充电”已有可用的 MicroDuck 仿真吗？

### Takeaway

**有两个值得区分的社区实现：MicroDock v2 发布了坐姿后蹭/脱离策略、打印件和 MuJoCo 机械对接；duckmind 发布了低电量回家、找标签、倒车入坞及虚拟充电状态机。两者都不能写成已经完成真实 MicroDuck 电气充电验收。** MicroDock v2 的标签位置来自仿真真值加噪声，USB/充满/睡醒的外围流程是脚本；duckmind 的接触是传感器代理，电池以软件数值变化，真实电气设计仍是假设。[MicroDock v2](https://github.com/Vottivott/microduck-playground/blob/052a2494dd6372289221c7a4f24a245b443dd75f/hardware/microdock-v2/README.md)；[duckmind 设计规范](https://github.com/joseyarashio/duckmind/blob/719e139b03bb2dd934b07561d0eb4a90def91863/docs/dock-hardware.md)

### Cited Findings

#### MicroDock / MicroDock v2：机械接触与坐姿移动，证据完整度较高

- 作者项目是 **Vottivott/microduck-playground**，`main` 固定到 `052a2494dd6372289221c7a4f24a245b443dd75f`，2026-11-05 合并 MicroDock v2。它是 `microduck_rl` 的独立实验延伸；v2 使用官方 RL `bae39f59` 的 BAM XL330 模型。不是 Open Duck Mini、Reachy，也不是仅转发一段真机视频。[提交](https://github.com/Vottivott/microduck-playground/commit/052a2494dd6372289221c7a4f24a245b443dd75f)；[项目说明](https://github.com/Vottivott/microduck-playground/blob/052a2494dd6372289221c7a4f24a245b443dd75f/README.md)
- 已发布 `hardware/microdock-v2/policy/scoot_dock.onnx`、`scoot_undock.onnx`，另有实验版双向策略；61 维输入、14 维输出、50 Hz，归一化打包进 ONNX。已发布训练 patch、环境源码、CAD 生成程序、STL、3mf、装配图、评估 JSON 和可重放脚本。**核心坐姿策略工件确实存在**；其低层训练任务是坐姿速度跟踪，不能由文件名推断为端到端视觉回充。[策略目录](https://github.com/Vottivott/microduck-playground/tree/052a2494dd6372289221c7a4f24a245b443dd75f/hardware/microdock-v2/policy)；[训练契约](https://github.com/Vottivott/microduck-playground/blob/052a2494dd6372289221c7a4f24a245b443dd75f/hardware/microdock-v2/training/README.md)
- 仿真闭环边界如下；“USB connected”是仿真端口/接头接近条件，不是电源仪表读数。源码 `connected(e)` 检查轴向误差 `-4 < e[0] < 2 mm`、横向与竖向绝对误差各 `<2.5 mm`；`magnet()` 以 `mj_applyFT` 给接头和浮动罩施加相反力，属于简化磁力模型。[接触/磁力模型](https://github.com/Vottivott/microduck-playground/blob/052a2494dd6372289221c7a4f24a245b443dd75f/hardware/microdock/source/dock.py)；[入坞实现](https://github.com/Vottivott/microduck-playground/blob/052a2494dd6372289221c7a4f24a245b443dd75f/hardware/microdock-v2/sim/docking_seated.py)；[脱离实现](https://github.com/Vottivott/microduck-playground/blob/052a2494dd6372289221c7a4f24a245b443dd75f/hardware/microdock-v2/sim/undocking_seated.py)

| 阶段 | 已发布实现 | 尚未证明的部分 |
|---|---|---|
| 找坞、走近、转身 | 标签真值加高斯噪声驱动控制；官方 `velstand` 行走 | 渲染图像 AprilTag 检测、真实视觉定位、全屋导航 |
| 坐下并倒入 | 官方 `alpha_sitstand` + 新 `scoot_dock`；滑动罩、导向斜壁和磁吸接触 | 实物打印容差、表面摩擦、真实磁力与 USB-C 对准 |
| 对接后停下、睡眠 | 仿真连接条件触发零指令；可关闭伺服 | 电气 power-good、充电电流、热管理和真实低功耗 |
| 充满后离开 | 脚本唤醒 + `scoot_undock` + 官方站起/行走 | 真实满电检测、机载自主调度、真实传感/执行延迟 |

上表依据同一固定版本的[作者边界说明](https://github.com/Vottivott/microduck-playground/blob/052a2494dd6372289221c7a4f24a245b443dd75f/hardware/microdock-v2/README.md)。

- 作者报告 4 N 磁力下入坞/脱离各 30/30；8 N 下脱离仅 2/10，最终站起走开仅 1/10。脱离依赖匹配训练延迟；去掉延迟仅 1/10 脱离。真实磁力和实际机器人延迟未测。仿真坞座固定，罩为滑轨机构，不能外推到未固定塑料底座。这里的数值必须与条件一起引用。[脱离结果](https://github.com/Vottivott/microduck-playground/blob/052a2494dd6372289221c7a4f24a245b443dd75f/hardware/microdock-v2/results/undock_magnet.json)；[完整限制](https://github.com/Vottivott/microduck-playground/blob/052a2494dd6372289221c7a4f24a245b443dd75f/hardware/microdock-v2/README.md)
- 软件、策略、训练环境 Apache-2.0；打印件 CC BY-NC-SA 4.0，官方机器人网格仍受其自己的非商业许可约束。复现需官方模型/策略、Python/uv/MuJoCo/ONNX/BAM；头部无显示渲染需 EGL/OSMesa 等环境，训练需要 mjlab GPU 路径。[硬件许可](https://github.com/Vottivott/microduck-playground/blob/052a2494dd6372289221c7a4f24a245b443dd75f/LICENSE-HARDWARE)；[复现命令](https://github.com/Vottivott/microduck-playground/blob/052a2494dd6372289221c7a4f24a245b443dd75f/hardware/microdock-v2/README.md#reproduce)

#### duckmind：低电量“回家充电”的认知与导航流程更完整，电气是代理

- `joseyarashio/duckmind` 的 `main` 固定为 `719e139b03bb2dd934b07561d0eb4a90def91863`（2026-11-09）。它具有性格、记忆、年龄和电池状态，仿真中能低电量回坞。发布 `world/dock.py` 几何生成、`neuro/dock.py`、`duckbody/dockexec.py`、测试与 DIY 规范，使用官方身体/策略；不是另一个新的“自充电低层 ONNX”。[README](https://github.com/joseyarashio/duckmind/blob/719e139b03bb2dd934b07561d0eb4a90def91863/README.md)；[对接控制](https://github.com/joseyarashio/duckmind/blob/719e139b03bb2dd934b07561d0eb4a90def91863/src/duckmind/duckbody/dockexec.py)
- 作者设计包含真实图像标签接口（tag36h11 id 17、低照度指示）、里程计 J 形转向、倒车、坐下、读取 `pg`、重试上限与求助；与 MicroDock 的“标签真值加噪声”不是同一实现。接触几何在 `world/dock.py` 标注 sensor-only、`contype=0`、质量为零探针；脑只能接收 `pg`，其它接触细节留给评估器。虚拟充电按每分钟 1.25% 更新，清醒时另减 0.2%。[几何与传感代理源码](https://github.com/joseyarashio/duckmind/blob/719e139b03bb2dd934b07561d0eb4a90def91863/src/duckmind/world/dock.py)；[状态机](https://github.com/joseyarashio/duckmind/blob/719e139b03bb2dd934b07561d0eb4a90def91863/src/duckmind/neuro/dock.py)；[设计中的充电规则](https://github.com/joseyarashio/duckmind/blob/719e139b03bb2dd934b07561d0eb4a90def91863/docs/dock-hardware.md)
- 该规范明确 electrical part 是 design assumption、没有真机验收。规范对早期样机“外部充电”的描述不能直接替代 2026-11 的官方硬件状态；它引用的官方 #174 应作为历史电源讨论阅读，而不是证明最新量产机接口不变。[规范](https://github.com/joseyarashio/duckmind/blob/719e139b03bb2dd934b07561d0eb4a90def91863/docs/dock-hardware.md)；[官方问题 #174](https://github.com/pollen-robotics/microduck/issues/174)
- 代码 Apache-2.0，官方身体网格/衍生画面 CC BY-NC-SA 4.0；是整套脑、身体桥接和世界环境，移植成本高于单场景控制器。[许可说明](https://github.com/joseyarashio/duckmind/blob/719e139b03bb2dd934b07561d0eb4a90def91863/README.md#licence)

### Inferences

- **优先做“累了，回窝歇会儿”仿真节目**：最小范围是复用 MicroDock v2 的已发布坐姿策略和机械环境，语音发起/取消；阶段显示“找坞→坐下→后蹭→仿真连接→休息→离开”。这比宣称“低电量自动充电”更贴合现成工件。预计中等至偏高接入成本：模型合成、4 策略切换、延迟和磁力控制、取消/失败处理均需验收；本次没有给出未经测量的工期。
- duckmind 更适合借鉴重试、求助、没找到窝、低电量返航等交互。若将其电池条引入 DuckKing，必须清楚标成虚拟电量；不要把仿真充满计时器显示成设备电源遥测。

### Gaps

- 未发现上述两个项目已完成真实充电电流、长期热管理、实物导向/磁力、断电恢复的公开验证；这里是“本次核查未找到”，不是证明任何人都没做过。
- 本次没有下载并执行 scoot ONNX，没有检查真实控制器逐帧时序，没有复刻作者成功率；仅检查发布文件和源码。

## 2. 哪些社区项目真正增加了可展示的技能，工件与限制是什么？

### Takeaway

除基础走路、踢球、轮滑和滚翻外，已找到**目标搜索/导航、低矮门槛、秋千、篮球平衡、高跷、爬梯/夹缝、受控积木击打、球队行为、视觉跟随**等明确社区工件。其成熟度差异很大：有完整 MuJoCo 场景与已导出策略，有依赖 CUDA 的 mjlab 重放，有仅训练定义，还有利用真值/辅助力的演示。不能把所有项目名称合并成“MicroDuck 已会这些技能”。[社区作者目录](https://github.com/joeynyc/awesome-microduck/blob/b99984a56182525598c4187cc0138c89bc1c7c79/readme.md)；[Playground 目录](https://github.com/Vottivott/microduck-playground/blob/052a2494dd6372289221c7a4f24a245b443dd75f/README.md)

### Cited Findings

以下每一行均**未在本轮执行**。“已发布”指本次查到代码、文件树或作者工件页，不保证可直接装入 DuckKing。表中的“成本”是研究者判断，非实测。

| 项目与固定证据 | 已发布什么 | 缺什么／诚实边界 | 运行、许可与接入判断；语音点子 |
|---|---|---|---|
| **bihaokun/microduck-step-up-policy**；`main@ec769571438c2558a2d847a164a91022971fceb0`。[README](https://github.com/bihaokun/microduck-step-up-policy/blob/ec769571438c2558a2d847a164a91022971fceb0/README.md) | 25 mm 方门槛 MJCF、walk/recovery 两个 ONNX、完整训练源码快照、`infer_policy.py`、视频和记录；作者网格 13/14 稳定 | 需人或外部感知在双脚上台后置零切换恢复；头临时撑地刹车；不是任意楼梯/自主找台阶；恢复演员的原 PPO checkpoint 未保留 | Python3.12/uv/CPU MuJoCo 推理；代码 Apache-2.0，机器人网格仍上游条款；中成本。“慢点过门槛，站稳再走”。 |
| **andreagenovese/quacknav**；`main@9a56a6ceea3ca1212dadf4b42c65d16c9ce60e43`。[README](https://github.com/andreagenovese/quacknav/blob/9a56a6ceea3ca1212dadf4b42c65d16c9ce60e43/README.md)；[twin](https://github.com/andreagenovese/quacknav/blob/9a56a6ceea3ca1212dadf4b42c65d16c9ce60e43/scripts/twin/README.md) | ToF 建图、定位、悬崖防护、命名地点、探索、go_to、JSON-RPC daemon；发布 pilot ONNX/JSON，MuJoCo twin 和快速运动学 paper twin | 所有结果为仿真；paper twin 成绩不能当 MuJoCo 成绩；pilot 按步态/daemon版本匹配；没有硬件验收 | Rust + 官方 robotd/RL twin；Apache-2.0，外取模型条款独立；高成本。“记住这是客厅，回厨房找我”。 |
| **lightorigins/LightNav-0**；`main@3015508b70fb6e30bbd66701e94c9b916dcb8df8`。[MuJoCo README](https://github.com/lightorigins/LightNav-0/blob/3015508b70fb6e30bbd66701e94c9b916dcb8df8/mujoco_demo/README.md)；[MicroDuck adapter](https://github.com/lightorigins/LightNav-0/blob/3015508b70fb6e30bbd66701e94c9b916dcb8df8/mujoco_demo/vln_mujoco/robots/microduck.py) | 真正 optional MicroDuck：ProcTHOR val_2 多房间 MJCF、RGB→VLN waypoint→MPC→官方 ONNX 步态，50Hz 真实重力接触；HF 有 9.7GB safetensors 及 action tokenizer | 机器人 MJCF/网格/alpha_walking 外取；MPC反馈用真值躯干位姿/速度；固定初态、固定物体；没有地图/全局规划/碰撞响应；论文其它身体基准不能算 MicroDuck 成功率 | 客户端 Python3.11+/MuJoCo/CasADi/ONNX 可CPU；VLN GPU服务另需资源。代码/权重 Apache-2.0，场景与网格各自许可；高成本。“去白桌旁边停下”。[权重目录](https://huggingface.co/LightOriginsHQ/LightNav-0/tree/main) |
| **Bravo-Robots/microduck-indoor-object-search-rl**；`main@5f087e452b970c6405a3d61f7badb0ac450f2d1a`，发布 v0.2.1。[README](https://github.com/Bravo-Robots/microduck-indoor-object-search-rl/blob/5f087e452b970c6405a3d61f7badb0ac450f2d1a/README.md)；[模型契约](https://github.com/Bravo-Robots/microduck-indoor-object-search-rl/blob/5f087e452b970c6405a3d61f7badb0ac450f2d1a/outputs/release/MODEL_CARD.md) | 房间/家具/机器人资产、场景生成、45→6 搜索 supervisor ONNX/PT、61→14 motor策略、RGB检测、深度护栏与评测 | 仅红球/蓝箱/黄柱三色；理想里程计；在SE(2)代理训练，MuJoCo全身评估；49/60作者结果含9次跌倒；不是开放词汇模型，也不能将supervisor直接塞入robotctl walk槽 | Linux x86-64/Python3.12/CPU可演示、CUDA训练更快；代码/自建道具Apache-2.0，机器人/混合blend CC BY-NC-SA；中高成本。“帮我找到蓝箱子”。 |
| **atlasmarkz/microduck-qwen**；`main@2f7872d2460aa42df7985796e84419b27302120f`。[README](https://github.com/atlasmarkz/microduck-qwen/blob/2f7872d2460aa42df7985796e84419b27302120f/README.md) | 中文指令→Qwen3-VL-4B+LoRA技能JSON；深度建图、前沿探索、A*、回起点，源码与实验记录 | README明确LoRA权重不分发，先训练；位姿/安全真值来自仿真；69/80是作者单一世界级别结果；本次根目录未确认项目自有LICENSE | 作者环境 Windows/Python3.12/CUDA，称RTX3060 8GB可用；复用许可未定，高成本。“去别的房间找蓝球，再回来”。 |
| **Vottivott Playground：自驱秋千**。[固定实验说明](https://github.com/Vottivott/microduck-playground/blob/052a2494dd6372289221c7a4f24a245b443dd75f/experiments/swing/README.md) | 秋千环境、`alpha050.pt`、评估/导出/续训脚本，HF ONNX；作者严格全程门槛71/100 | 坐垫、材料、硬件载荷仍未验；是秋千，不是DuckKing现有跷跷板 | mjlab/BAM，训练CUDA；代码Apache-2.0，网格独立；中高成本。“荡高一点，停在中间”。 |
| **Vottivott Playground：篮球平衡**。[实验与LSTM契约](https://github.com/Vottivott/microduck-playground/blob/052a2494dd6372289221c7a4f24a245b443dd75f/experiments/basketball/README.md)；[HF文件](https://huggingface.co/HannesVonEssen/microduck-basketball/tree/main) | 自由滚动7号篮球、b11策略、ONNX/PT/config/source包；本体感知+1层LSTM，actor不看球真值 | 不会自行登球或跌落自救；需维护/重置循环隐状态；部署时延/真机未验 | 非普通无状态walk替换；Apache-2.0工件+网格条款；高成本。“球上向我挪半步，稳住”。 |
| **Vottivott Playground：高跷**。[说明](https://github.com/Vottivott/microduck-playground/blob/052a2494dd6372289221c7a4f24a245b443dd75f/experiments/stilts/README.md)；[HF文件](https://huggingface.co/HannesVonEssen/microduck-stilts/tree/main) | 10/15/20/25/50/100/140/200cm分高度策略、生成器、视频/续训checkpoint；10cm有打印质量审计 | 每高度独立模型，不是换长腿仍通用；极端高度仅仿真，非结构可制造性证明 | MJCF拓扑/质量同步，固定策略；中高成本。“高跷巡游，慢慢转一圈”。 |
| **Vottivott Playground：爬梯到桌面／夹缝攀爬**。[爬桌](https://github.com/Vottivott/microduck-playground/blob/052a2494dd6372289221c7a4f24a245b443dd75f/experiments/desk-climb/README.md)；[夹缝](https://github.com/Vottivott/microduck-playground/blob/052a2494dd6372289221c7a4f24a245b443dd75f/experiments/chimney-climb/README.md) | 定制梯/支架生成器、爬升/恢复策略配对、源码快照和HF权重链接；夹缝有进入/爬升/退出配套 | 爬桌切换读脚-桌接触及root位置真值；夹缝是选中完整成功序列，非稳健全链成功率；本轮未独立下载HF包 | 定制场景/姿态/切换契约，成本高。“爬上小梯子再跟我打招呼”。 |
| **Vottivott Playground：高台跳远／后空翻**。[实验与验证边界](https://github.com/Vottivott/microduck-playground/blob/052a2494dd6372289221c7a4f24a245b443dd75f/experiments/parkour/README.md)；[后空翻模型卡](https://huggingface.co/HannesVonEssen/microduck-backflip) | 2个独立ONNX/PT、config、重放脚本、场景/软接触垫、parity记录 | 不是平地原地后空翻；无视觉；软垫未标定且不模拟结构损坏；选定后空翻能站起随后7.62s跌出垫；descending-pillar策略仍未发 | mjlab，作者推荐CUDA；61/14但命令语义不同，非walk即插即用；高成本。适合标明“高台特技实验”。 |
| **Vottivott Playground：快跑**。[固定说明](https://github.com/Vottivott/microduck-playground/blob/052a2494dd6372289221c7a4f24a245b443dd75f/experiments/running/README.md) | 迭代12195选定策略、HF ONNX/full PPO、评估与续训配方 | 作者标 simulation-only hardware candidate；不是实体跑速成绩；本次未下载/运行 | 原机器人快速步态变体，通常中成本。“计时冲刺，到了就停”。 |
| **speccy88/microduck-jenga-sim**；`main@0f977eaf989fff819bdcb75d303c6805505ebe69`。[README](https://github.com/speccy88/microduck-jenga-sim/blob/0f977eaf989fff819bdcb75d303c6805505ebe69/README.md) | MuJoCo两块自由积木、CEM头部轨迹、冻结VelStand平衡、`checkpoint_100.json`、重放/接触检查；作者25/30严格成功 | 从受控14cm位置、理想方位起步；不是搭塔；另一个三块PPO实验没有成立的成功策略；第三方平衡权重/网格需另恢复 | Linux/WSL2、Python3.12、CUDA（作者RTX2060S）；代码Apache-2.0、模型/录像CC BY-NC-SA，权重条款需核查；中高成本。“只碰上面橙色那块”。 |
| **jonathanhawkins/microduck-lab**；`main@8dad9218062f7b0ad29ae6d564305411f5a117c2`。[README](https://github.com/jonathanhawkins/microduck-lab/blob/8dad9218062f7b0ad29ae6d564305411f5a117c2/README.md) | CPU MuJoCo+SB3训练/ONNX、房间/玩具/1v1至3v3足球、follow-v1至v5 ONNX、find_ball与左右kick权重、场景生成/评估与浏览器 | 摄像头检测器是感知代理，噪声有档位；不是开放视觉识别；后空翻展示有spotter起跳辅助；多身体仓库中的G1/MARS/MOSS/Asimov技能不属于MicroDuck；嘴部搬运约束需另查代码才能声称无辅助夹持 | Apple Silicon CPU也可；Apache-2.0代码、各机器人各自许可；高成本集成或中成本借鉴球队编排。“两队开球，倒下先爬起来”。 |
| **first-it-consulting/duckophila**；`main@6da8c1c87f40b2922a04448242037256fd106e94`。[README](https://github.com/first-it-consulting/duckophila/blob/6da8c1c87f40b2922a04448242037256fd106e94/README.md)；[桥接](https://github.com/first-it-consulting/duckophila/blob/6da8c1c87f40b2922a04448242037256fd106e94/bridge.py) | 果蝇连接组闭环：受惊、视动反射、目标跟随、抚摸偏好；MuJoCo道具/实验/记录、官方daemon桥接 | 感觉编码、读出增益、受惊动作形状和学习规则包含手写部分；跟人并不稳定；FlyWire列数据需登录取，不随仓库；原说明依赖官方PR513 | Mac/Linux、uv、外部连接组、官方duck-sim；代码Apache-2.0，数据独立条款；高成本。“轻轻摸它，再让它跟着喜欢的玩具”。 |
| **notwitcheer/microduck-lab / witcheer walk系列**；`main@0073595d1282a0d5cee649a9c961a8ff1305f93d`。[工具仓库](https://github.com/notwitcheer/microduck-lab/blob/0073595d1282a0d5cee649a9c961a8ff1305f93d/README.md)；[stairs模型卡](https://huggingface.co/witcheer/microduck-walk-stairs) | Hermes工具、地形patch、训练/评估；Hub发布flat/rough/slope/step/stairs/slip/gale/recover变体 | stairs预定25mm台阶强干扰测试3/15存活，基线5/15，无可测提升；训练导出工作树有未提交改动，不能只用上游sha还原 | Apache-2.0；需固定overlay/模型/策略；中成本，作为“地形策略对照”而非保证爬楼。 |
| **Teethyfish/collision-flamingo-ii**。[作者模型卡](https://huggingface.co/Teethyfish/microduck-collision-flamingo-ii) | 单足支撑ONNX和全壳碰撞overlay，明确推理契约 | safe ONNX infer路径观察成功，训练play Native/Viser未复现，差异未解决；本次未下载整个HF树 | Apache-2.0代码/策略、网格独立；中成本但先排差异。“金鸡独立三秒”。 |
| **Lulzx/microduck-backflip**；`main@8bde27eb141c8f14db05fc4370e536521203a98d`。[状态](https://github.com/Lulzx/microduck-backflip/blob/8bde27eb141c8f14db05fc4370e536521203a98d/README.md#backflip-training-and-evaluation) | mjlab任务、实验/评估管线、checkpoint/ONNX、辅助吊带场景与视频 | 作者明确当前是有辅助完整翻转；不是自主平地后空翻；大量task名不代表每项有已收敛策略 | mjlab/CUDA路径，Apache-2.0+网格CC条款；高成本，不建议决赛先接。 |
| **dreamerarun/isaaclab_microduck**；`main@deb10a39e59504a8093a30bf8376b853020fa0ee`。[README](https://github.com/dreamerarun/isaaclab_microduck/blob/deb10a39e59504a8093a30bf8376b853020fa0ee/README.md) | IsaacLab/PhysX的37个环境注册、BAM、模型转换、train/play/export | 预览是两次PPO更新的model_1 smoke，非收敛步态；有源MJCF不等于任务可在DuckKing MuJoCo直接播放 | Linux/Python3.12/NVIDIA/IsaacSim6.0；框架BSD、扩展Apache、网格CC；高迁移成本，训练基础设施而非新增成熟技能。 |
| **lgtkgtv/microduck_sim**；`main@b7a50acee420029af3d0dbc01b01fd2fb982f0de`。[路线图](https://github.com/lgtkgtv/microduck_sim/blob/b7a50acee420029af3d0dbc01b01fd2fb982f0de/README.md) | 教育viewer、官方旧策略、PPO示例、简化教育机器人模型 | README把rough/stairs/push recovery、网页WASM及视觉导航标为Planned；搜索摘要删除状态后会造成“已经支持”的误读；教育60/15与官方61/14契约不同 | README声称MIT，但本轮文件树未确认根LICENSE；不能自动视为可再授权；不算新增已完成楼梯技能。 |

#### 已发现、但本轮不升级为“核实可运行”的线索

下列链接来自版本固定的[社区目录](https://github.com/joeynyc/awesome-microduck/blob/b99984a56182525598c4187cc0138c89bc1c7c79/readme.md)。没有在本轮逐一检查全部模型/控制器，许可证和运行需求因此仍待核查；不要把目录描述当作实测证据。

| 线索 | 可继续核验的方向 | 本轮状态 |
|---|---|---|
| [selinayfilizp/microduck-courier](https://github.com/selinayfilizp/microduck-courier) | 公寓pick-carry-place | 未核验嘴部接触/焊接辅助、完整权重与终止条件 |
| [Liyucheng1997/318_lab-microduck-simulator](https://github.com/Liyucheng1997/318_lab-microduck-simulator) | 自训垂直跳跃、浏览器sandbox fork | 未核验训练/导出及自由动力学条件 |
| [pezzonovante7/microduck-sidekick-dance](https://github.com/pezzonovante7/microduck-sidekick-dance) | 侧踢舞步任务 | 目录明确task only、尚未训练，不能算现成舞步 |
| [jjshdbndg/MotrixLab-MicroDuck](https://github.com/jjshdbndg/MotrixLab-MicroDuck) | 被动轮交替蹬地、转向 | MotrixLab环境，尚未核查MuJoCo兼容性；不能和官方roller重复计数 |
| [zakiyamaaaaa/microduck-ppo-navigation](https://github.com/zakiyamaaaaa/microduck-ppo-navigation) | 前进1m、转身、回原点的上层策略 | 未核验checkpoint与真值反馈边界 |
| [toyhank/microduck-vision-soccer](https://github.com/toyhank/microduck-vision-soccer) | 相机前锋与门将 | 真值导航98/100不得移作相机闭环成绩；本轮仅索引级证据 |
| [wat-bill/microduck-action-pack](https://github.com/wat-bill/microduck-action-pack) | 头/身体命令的节奏舞蹈 | 编排而非新运动RL；与DuckKing现有演出对比后才算增量 |
| [RemiFabre rough-walk-e](https://huggingface.co/RemiFabre/microduck-rough-walk-e)、[g](https://huggingface.co/RemiFabre/microduck-rough-walk-g) | 粗糙地面、台阶、坡度步态 | 未读完整卡/下载；下降台阶限制需复核，不能宣称通用楼梯 |
| [cetiennec/on-sourccey-dome](https://huggingface.co/cetiennec/microduck-on-sourccey-dome) | MicroDuck站在移动Sourccey穹顶 | MicroDuck+另一机器人联合场景；作者页本轮打开失败，保留未证实线索 |
| [Nirav-Madhani/microduck-racer](https://huggingface.co/spaces/Nirav-Madhani/microduck-racer) | 四鸭轮滑路线赛 | 目录称复用官方轮滑策略；未检查障碍回避/比赛重置机制 |
| [craigm26 stairs challenge](https://huggingface.co/datasets/craigm26/microduck-stairs-challenge) | 有界关节关键帧门槛挑战 | 已读数据卡：数据集不是runnable harness；作者60mm最好5/9，要求7/9未达；不可说“挑战已解决” |
| [AlexWortega/flywire-microduck](https://huggingface.co/spaces/AlexWortega/flywire-microduck)、[ChristianNHill/micro-garden](https://github.com/ChristianNHill/micro-garden) | 连接组目标到达/多鸭花园 | 未核验模型与刺激/读出；不能与duckophila混成一个成果 |
| [tailong-wu/microduck-mjbatch](https://github.com/tailong-wu/microduck-mjbatch)、[NV-DLI/Microduck-Workshop](https://github.com/NV-DLI/Microduck-Workshop) | CPU训练、Newton/Isaac足球课程 | 本轮索引级；课程框架不能直接视为MuJoCo新技能包 |

#### 工具型项目与相邻机器人隔离

- **rokbenko/quackd** 固定 `4ba2d0dc6cf9c591a7c7897bc9d80301d5a187b3` 有 MicroDuck adapter/sim3d，Apache-2.0；其多机器人、LLM/MCP任务编排可供交互设计参考，不能把 LeRobot、Open Duck、AlohaMini 的动作算成 MicroDuck 动作。[MicroDuck adapter](https://github.com/rokbenko/quackd/blob/4ba2d0dc6cf9c591a7c7897bc9d80301d5a187b3/adapters/microduck/README.md)
- **knowlin-ai/knowlin** 固定 `f8b092081f26e3e8ce864caade505751f1868966` 同时面向 MicroDuck、Open Duck Mini、Reachy Mini；应按身体分别核验。其外层 Apache-2.0 不覆盖首次启动下载的 Pollen STL；本轮没有验证其所有交互是否真实 MuJoCo闭环。[README与来源表](https://github.com/knowlin-ai/knowlin/blob/f8b092081f26e3e8ce864caade505751f1868966/README.md)
- **StephenForte/microduck-challenges** 固定 `6155860d63491ff30fa8be73d165b2deac12dd47` 是Arena训练/评测工作坊；`duck-dreams` 固定 `58da60270b617699d2c914d894d25ce7deb84b9d` 是计划任务生成的梦境文字/漫画，不是新增身体技能。[challenges](https://github.com/StephenForte/microduck-challenges/blob/6155860d63491ff30fa8be73d165b2deac12dd47/README.md)；[dreams](https://github.com/StephenForte/duck-dreams/blob/58da60270b617699d2c914d894d25ce7deb84b9d/README.md)
- **rahilmehta-dev/microduck-aiprobe** 固定 `076ba37a9715fe18db24154a391695dade505f73` 是改变世界参数检查官方策略的评测框架；不把其1000任务覆盖和完成率算成新技能训练。源码也说明其仿真未包含相应backlash。[README](https://github.com/rahilmehta-dev/microduck-aiprobe/blob/076ba37a9715fe18db24154a391695dade505f73/README.md)

### Inferences

建议先按“增量清楚、语音好解释、工件可检查”排：**MicroDock v2 → 三色物体搜索 → 25mm门槛 → 秋千 → quacknav命名地点 → 球上平衡 → 两块积木击打**。LightNav是很有表现力的第二阶段，但服务、模型、感知与MPC链条长；qwen候选缺公开LoRA；高台空翻、夹缝/爬梯、高跷应保留实验标签。以上排序是工程判断，不能代替 DuckKing 本地合同/物理测试。

如果目标是最快可审查演示，优先复用已发布策略，给场景增加语音任务、停止、失败解释和重试；不把脚本编排改名为“云端自主决策”。所有策略导入前核对 observation/action顺序、command语义、backlash、BAM、滤波、递归状态和重置协议；61/14一致仅是第一步，不能保证兼容。

### Gaps

- 对项目源码的深度不一致：dock做了跨文件核查，主要导航/动作做了README、文件树、部分核心源码核查；表格后段仅索引级。没有运行本地MuJoCo，没有下载/校验每个ONNX哈希，没有对每段视频做逐帧物理真伪审计。
- 全壳单足、ball-balance和特技模型可能要求不同碰撞/执行器/滤波，不宜直接导入当前 DuckKing room。具体工作量只有隔离重放后才能估算。
- 除表中特别说明，不假定项目MIT/Apache外壳覆盖上游STL；没有发现许可证的项目只可作为技术线索，不能直接判定可复用。

## 3. 搜索覆盖、去重与负面结果怎样表达才准确？

### Takeaway

本次是**有边界的广覆盖调查，不是全 GitHub 穷尽审计**。搜索索引规模远大于可逐库验证范围；同项目镜像、未改动fork、官方策略再包装、其它机器人能力都应去重。

### Cited Findings

- GitHub repository search 实际查询 `microduck`、`microduck in:name fork:true`、`microdock`、`microduck_rl in:name fork:true`，按updated排序、`per_page=100`。保存的响应中，前两项分别报告635与3993个命中，每个只取第一页100条；`microdock`主要命中同名非机器人软件。它们是搜索结果计数，不是独立MicroDuck技能计数。[可重复查询入口](https://api.github.com/search/repositories?q=microduck&per_page=100&sort=updated)；[含fork入口](https://api.github.com/search/repositories?q=microduck%20in%3Aname%20fork%3Atrue&per_page=100&sort=updated)
- 后续 API 多次 403 rate limit，于是改用公开git只读浅克隆/文件树和raw源文件。没有逐一比较3993个仓库，也没有遍历所有fork分支、issues、PR、releases。`microduck_rl` fork专门搜索未成功，不能报告“所有fork已查”。
- 获取并固定了15个重点候选的git HEAD，另有GitHub树API固定的 quacknav、microduck-qwen、quackd、duckophila、lgtkgtv。用原始作者的代码/文档支撑结论；AwesomeDucks、awesome-microduck、Reddit只作发现入口。[固定社区索引](https://github.com/joeynyc/awesome-microduck/blob/b99984a56182525598c4187cc0138c89bc1c7c79/readme.md)
- 去重样例：Bravo-Robots与david2526IA在README中明确互为镜像，计为一个搜索项目；Playground的后空翻、秋千、球平衡等是同一项目不同任务，不把GitHub+HF双算；官方ONNX再打包到`microduck_sim`不计新技能；fork名字相同不证明有变更。[Bravo镜像关系](https://github.com/Bravo-Robots/microduck-indoor-object-search-rl/blob/5f087e452b970c6405a3d61f7badb0ac450f2d1a/README.md)；[Playground任务目录](https://github.com/Vottivott/microduck-playground/blob/052a2494dd6372289221c7a4f24a245b443dd75f/README.md)
- 原始PR确实能揭示兼容性陷阱：duckophila引用的官方[PR513](https://github.com/pollen-robotics/microduck/pull/513)讨论duck-sim默认旧策略、backlash模型与新velstand匹配。引用历史README时要核对当前运行基线，不能按旧启动命令推断今日行为。
- HF公共文件页核验 LightNav safetensors、basketball ONNX/checkpoint/source包、stilts分高度文件；本机HF API/raw尝试均connection reset，因而使用web工具读公开页。没有下载大权重；不能报告“权重可在本地加载”。[LightNav工件](https://huggingface.co/LightOriginsHQ/LightNav-0/tree/main)；[篮球工件](https://huggingface.co/HannesVonEssen/microduck-basketball/tree/main)；[高跷工件](https://huggingface.co/HannesVonEssen/microduck-stilts/tree/main)

### Inferences

- “没找到”应按查询和证据等级表达：本轮未找到一个经过核实的、可直接替换 DuckKing 当前跷跷板任务的社区 MicroDuck 跷跷板完整发布包；已有秋千/球平衡不能改名为跷跷板。未找到真实自主电气充电闭环验收；已找到仿真机械对接，因此也不能沿用旧结论“社区完全没有自充电”。
- 自充电项目、物体搜索、导航都在快速迭代。建议报告列检索日+固定SHA，后续新增另起增量，不静默把浮动main作为2026-11-10事实。
- Open Duck Mini/v2、Reachy、G1、MARS、MOSS、Asimov以及四足SkateNav仅作为相邻机器人迁移思路。即使同一repo出现，仍按身体分栏，不计入MicroDuck已支持能力。

### Gaps

- 未登录或搜索 Discord、私人模型、X完整回复/视频、所有GitHub branch/tag、已删除工件；搜索排名会漏掉名字不含MicroDuck的项目。
- fork去重仅按明确项目关系、发布物与README来源，不是全网逐提交diff；未检查的fork既不能称“无变化”，也不能凭fork计数增加覆盖。
- 没有发现可用的社区通用“任意楼梯”“自主安装轮滑/上篮球”“无需外部感知的全屋真实回充”证据；这是一份公开材料调查的缺口，不能作为机器人能力不可能实现的论断。
