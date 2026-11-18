# 官方 MicroDuck / MuJoCo 能力与资产核查

调研截点：2026-11-10（Asia/Shanghai）。本轮只读取公开源码、官方网页、Hub 文件树、已有 DuckKing 资产入口；没有运行模拟、推理、训练、硬件试验或部署。GitHub 缓存在 `.duckking/microduck-survey-20261110/official-cache/`。本文中的“可运行”指存在可审计的程序/公开权重路径，并不等于本轮执行成功。

证据分层：**A**＝源码 + 可公开定位的部署权重/资产；**B**＝官方实现或训练任务，但未确认公开完整 checkpoint 或本机复现；**C**＝官方文字/演示/计划，缺少完整可运行链路；**N**＝本次已检索范围未找到，不能推广成“不存在”。

## 1. 官方究竟公开了哪些能力、场景和策略？

### Takeaway

官方已有 13 类 RL 任务、10 个公开部署 ONNX，以及独立的情绪、音频、感知和多机仿真代码；“官网 7 policies”是产品口径，不是当前文件数。官方 MuJoCo 不止白色地板，也有球、轮滑、反向间隙、室内公寓与视觉 SLAM 房间；某个训练任务存在不保证相应已训练权重已发布。[任务注册](https://github.com/pollen-robotics/microduck_rl/blob/bae39f5900b318f7e87fc485c30a31213cfa14eb/src/mjlab_microduck/tasks/__init__.py)；[Hub 文件树](https://huggingface.co/pollen-robotics/microduck-policies/tree/283771bcb3690a0a94a288c108365d9b630d21e4)；[官网](https://pollen-robotics.com/microduck/)

### Cited Findings

#### 检查过的版本与入口

| 资源 | 本轮检查分支/提交与日期 | 检查内容 |
|---|---|---|
| `pollen-robotics/microduck` | `main`，`da34a2212ae12eddfd73d0dfbf924f291aaf1dc9`，2026-11-06 17:00:14 UTC | 完整浅克隆；README、Cargo、robotd、duck-control、kinematics、spaces、docs、scripts。[commit](https://github.com/pollen-robotics/microduck/commit/da34a2212ae12eddfd73d0dfbf924f291aaf1dc9) |
| `pollen-robotics/microduck_rl` | `develop`，`bae39f5900b318f7e87fc485c30a31213cfa14eb`，2026-10-27 15:00:04 UTC | 完整浅克隆；任务注册、任务配置、脚本、模型 XML、仿真 body server、许可证。[commit](https://github.com/pollen-robotics/microduck_rl/commit/bae39f5900b318f7e87fc485c30a31213cfa14eb) |
| `pollen-robotics/microduck_emotions` | 默认分支浅克隆，`431c73df8a9d3cb6b6067d09ced6c169fdfa59fd`，2026-10-07 13:45:06 +02:00 | emotions.json、全部关键帧/声音/preview 文件清单、README；不把视频当作 RL 模型。[commit](https://github.com/pollen-robotics/microduck_emotions/commit/431c73df8a9d3cb6b6067d09ced6c169fdfa59fd) |
| `pollen-robotics/duck_detector` | 默认分支浅克隆，`cc1b52eb3ace9643c8948320e63f46a85cf6fb65`，2026-09-10 15:32:43 UTC | README、文件树及训练/导出路径。[commit](https://github.com/pollen-robotics/duck_detector/commit/cc1b52eb3ace9643c8948320e63f46a85cf6fb65) |
| `pollen-robotics/microduck_yocto` | 默认分支 API 树，`63b47a8a25428d3c6fc55c23b0016931176d5236`，2026-11-06 14:26:58 UTC | README/递归树；不是新增运动库。树仍有 `microduck-policies_v8.bb`，不能把不同仓库分支 pin 混成统一版本。[tree](https://github.com/pollen-robotics/microduck_yocto/tree/63b47a8a25428d3c6fc55c23b0016931176d5236) |
| HF `pollen-robotics/microduck-policies` | `main` 当前 `283771bcb3690a0a94a288c108365d9b630d21e4`，v9 | 浏览文件树、manifest、变更 diff；页面未提供可稳定读出的绝对 commit 日期，记录访问日而不猜日期。[commit](https://huggingface.co/pollen-robotics/microduck-policies/commit/283771bcb3690a0a94a288c108365d9b630d21e4) |
| HF `pollen-robotics/microduck-simulator` | `main` 页面短 SHA `efedf47` | 读取 Space 文件树、app/ 文件树和原始 README；未下载完整源码/二进制，故不声称全面代码审计。[tree](https://huggingface.co/spaces/pollen-robotics/microduck-simulator/tree/main) |
| HF `pollen-robotics/microduck-duck-detector` | `main` 页面短 SHA `da26178`，提交文字为 v2 | 文件树确认 `duck_detect.pt/.onnx/.rknn`；runtime 当前 minimum pin 却为 `duck-v1`，集成需明确选哪版。[tree](https://huggingface.co/pollen-robotics/microduck-duck-detector/tree/main)；[runtime pin](https://github.com/pollen-robotics/microduck/blob/da34a2212ae12eddfd73d0dfbf924f291aaf1dc9/Cargo.toml) |

GitHub API/tree 与 clone 都实际读取了源码；对 HF 直连 `curl`/Python API 多次出现连接被重置，因此 Hub 权重本轮只核对文件树/manifest/diff，没有重新下载并 hash 全部权重。`external/sources.json` 当前不存在；本地入口为 `scripts/fetch_scene_assets.py`，其 RL pin=`b02fdea4902c2b93b7d34a83a6f05da4ececb7d3`、policy pin=`665ae4eb20bfe13bca1ef4ea6d4bb6b4a096e448`。这是本地只读观察，不是对远程最新版本的推测。

#### 已发布部署策略：10 个 ONNX

所有条目在当前官方 policy 树可见，每个约 794 kB，遵循 61 维输入、14 维关节动作、50 Hz、XL330 契约；嘴部为额外控制，不占 14 维 policy 输出。[manifest](https://huggingface.co/pollen-robotics/microduck-policies/blob/283771bcb3690a0a94a288c108365d9b630d21e4/manifest.json)；[运行时 policy 契约](https://github.com/pollen-robotics/microduck/blob/da34a2212ae12eddfd73d0dfbf924f291aaf1dc9/docs/policy-manifest.md)

| 行为/证据 | 文件及运行含义 | 训练入口/关键限制 |
|---|---|---|
| 行走＋零命令站立/恢复，A | [`velstand.onnx`](https://huggingface.co/pollen-robotics/microduck-policies/blob/283771bcb3690a0a94a288c108365d9b630d21e4/velstand.onnx)，当前默认 walk，无独立 stand 网络；v7/v9 可站立时调 body roll/pitch | [`microduck_velstand_env_cfg.py`](https://github.com/pollen-robotics/microduck_rl/blob/bae39f5900b318f7e87fc485c30a31213cfa14eb/src/mjlab_microduck/tasks/microduck_velstand_env_cfg.py)，Flat/Rough；当前发布模型源自 Rough-Backlash 任务。恢复能力不应描述为任何姿态/任何地面的保证。 |
| 传统行走，A | [`alpha_walking.onnx`](https://huggingface.co/pollen-robotics/microduck-policies/blob/283771bcb3690a0a94a288c108365d9b630d21e4/alpha_walking.onnx)，保留的旧默认/教师，可独立比较，当前默认并不选它 | [`microduck_velocity_env_cfg.py`](https://github.com/pollen-robotics/microduck_rl/blob/bae39f5900b318f7e87fc485c30a31213cfa14eb/src/mjlab_microduck/tasks/microduck_velocity_env_cfg.py)，Flat/Rough；速度与头部命令。 |
| 独立站立/起身＋身体控制，A | [`alpha_stand.onnx`](https://huggingface.co/pollen-robotics/microduck-policies/blob/283771bcb3690a0a94a288c108365d9b630d21e4/alpha_stand.onnx)，仍公开；用于旧 walk/stand 双策略组合和教师 | [`microduck_standup_env_cfg.py`](https://github.com/pollen-robotics/microduck_rl/blob/bae39f5900b318f7e87fc485c30a31213cfa14eb/src/mjlab_microduck/tasks/microduck_standup_env_cfg.py)，面朝上/下及坐姿起身任务。 |
| 坐下/起立，A | [`alpha_sitstand.onnx`](https://huggingface.co/pollen-robotics/microduck-policies/blob/283771bcb3690a0a94a288c108365d9b630d21e4/alpha_sitstand.onnx)，`twist.vx` 位置借作二值 posture flag：0=站、1=坐；2 s settle，1 s rise；头部仍可控 | [`microduck_sitstand_env_cfg.py`](https://github.com/pollen-robotics/microduck_rl/blob/bae39f5900b318f7e87fc485c30a31213cfa14eb/src/mjlab_microduck/tasks/microduck_sitstand_env_cfg.py)。不是连续坐高旋钮，不代表充电。 |
| 地面啄取，A | [`alpha_ground_pick.onnx`](https://huggingface.co/pollen-robotics/microduck-policies/blob/283771bcb3690a0a94a288c108365d9b630d21e4/alpha_ground_pick.onnx)，相位编码 cos/sin 进入 vx/vy，周期4 s，至0.7即结束，共2.8 s | [`microduck_ground_pick_env_cfg.py`](https://github.com/pollen-robotics/microduck_rl/blob/bae39f5900b318f7e87fc485c30a31213cfa14eb/src/mjlab_microduck/tasks/microduck_ground_pick_env_cfg.py)。任务是嘴尖触地后回站立；“找到任意目标并可靠抓起”需要额外视觉、闭嘴和物体接触逻辑。 |
| 左/右踢球，A | [`ball_kick_left.onnx`](https://huggingface.co/pollen-robotics/microduck-policies/blob/283771bcb3690a0a94a288c108365d9b630d21e4/ball_kick_left.onnx)、[`ball_kick_right.onnx`](https://huggingface.co/pollen-robotics/microduck-policies/blob/283771bcb3690a0a94a288c108365d9b630d21e4/ball_kick_right.onnx)，各0.5 s one-shot | [`microduck_ball_kick_env_cfg.py`](https://github.com/pollen-robotics/microduck_rl/blob/bae39f5900b318f7e87fc485c30a31213cfa14eb/src/mjlab_microduck/tasks/microduck_ball_kick_env_cfg.py)。actor 不看球；训练球70 mm/15 g。不是视觉找球/自主足球。 |
| 前滚翻，A | [`roulade.onnx`](https://huggingface.co/pollen-robotics/microduck-policies/blob/283771bcb3690a0a94a288c108365d9b630d21e4/roulade.onnx)，1 s，可 chain | [`microduck_roulade_env_cfg.py`](https://github.com/pollen-robotics/microduck_rl/blob/bae39f5900b318f7e87fc485c30a31213cfa14eb/src/mjlab_microduck/tasks/microduck_roulade_env_cfg.py)。越过头顶回脚，须有地面碰撞，不能用精简 walking 模型替代。 |
| 轮滑速度控制，A | [`roller.onnx`](https://huggingface.co/pollen-robotics/microduck-policies/blob/283771bcb3690a0a94a288c108365d9b630d21e4/roller.onnx)，roller 模式，action_scale 0.8 | [`microduck_velocity_rollers_env_cfg.py`](https://github.com/pollen-robotics/microduck_rl/blob/bae39f5900b318f7e87fc485c30a31213cfa14eb/src/mjlab_microduck/tasks/microduck_velocity_rollers_env_cfg.py)，必须轮滑 MJCF 的被动轮。 |
| 下蹲滑行，A | [`roller_crouch.onnx`](https://huggingface.co/pollen-robotics/microduck-policies/blob/283771bcb3690a0a94a288c108365d9b630d21e4/roller_crouch.onnx)，5 s phase、0.7截止，共3.5 s；roller mode、scale0.8 | [`microduck_roller_crouch_env_cfg.py`](https://github.com/pollen-robotics/microduck_rl/blob/bae39f5900b318f7e87fc485c30a31213cfa14eb/src/mjlab_microduck/tasks/microduck_roller_crouch_env_cfg.py)。是完整 crouch-glide，不是静态坐姿。 |

**v9 是当前 DuckKing pin 的实质更新线索。** v9 commit 只改 `velstand.onnx` 和 manifest；其说明为回到 v7，因为 v8 在真机更差。v8 权重 SHA256=`2fc7f8ee6acd7d0d3f66a99927b5d5a56589aeed02ec714de329b252d5ccf492`，与 DuckKing 下载脚本一致；v9=`ce894d30b3343036d499bfac1102bdaa58d59a21c1b58401ecb70fb6a2f63e0a`。它是应当评测的替换候选，不能仅凭新版本直接宣布仿真一定更稳。[官方精确 diff](https://huggingface.co/pollen-robotics/microduck-policies/commit/283771bcb3690a0a94a288c108365d9b630d21e4)

v9 manifest 指向 velstand 训练 `improve_velstand2@53fb7d1`、`j4i6yoq2`、checkpoint1250；sitstand 指向 `sitstand_no_fall_back@77ffadf`、`vfhxgrum`、checkpoint2250。对应 RL 文档 `docs/velstand_policy.md` 仍写 v8“current”，这是已发现的文档滞后，应以当前 HF 集合 diff 和 runtime Cargo v9 为准。[manifest](https://huggingface.co/pollen-robotics/microduck-policies/blob/283771bcb3690a0a94a288c108365d9b630d21e4/manifest.json)；[滞后说明](https://github.com/pollen-robotics/microduck_rl/blob/bae39f5900b318f7e87fc485c30a31213cfa14eb/docs/velstand_policy.md)；[runtime](https://github.com/pollen-robotics/microduck/blob/da34a2212ae12eddfd73d0dfbf924f291aaf1dc9/Cargo.toml)

#### 有训练任务、未在上述官方集合找到独立部署权重的能力（B）

| 任务 | 已发布源代码 | 不能跳过的缺口 |
|---|---|---|
| Swizzle 对称蹬轮 | `Mjlab-Velocity-Swizzle-MicroDuck`，[cfg](https://github.com/pollen-robotics/microduck_rl/blob/bae39f5900b318f7e87fc485c30a31213cfa14eb/src/mjlab_microduck/tasks/microduck_velocity_swizzle_env_cfg.py) | 10 个发布 ONNX 中没有单列 swizzle；不能因 roller.onnx 存在就断言它是这个任务的权重。 |
| 下坡滑行 | `Mjlab-RollerSlope-Flat-MicroDuck`，[cfg](https://github.com/pollen-robotics/microduck_rl/blob/bae39f5900b318f7e87fc485c30a31213cfa14eb/src/mjlab_microduck/tasks/microduck_roller_slope_env_cfg.py)、[`slope_terrain.py`](https://github.com/pollen-robotics/microduck_rl/blob/bae39f5900b318f7e87fc485c30a31213cfa14eb/src/mjlab_microduck/tasks/slope_terrain.py) | 平台→斜坡→缓冲区、零 twist 的被动下滑，不是通用自主坡地导航；未确认独立公开 checkpoint。 |
| 穿轮滑起身 | `Mjlab-RollerStandUp-Flat-MicroDuck`，[cfg](https://github.com/pollen-robotics/microduck_rl/blob/bae39f5900b318f7e87fc485c30a31213cfa14eb/src/mjlab_microduck/tasks/microduck_roller_standup_env_cfg.py)、[训练设计与已知问题](https://github.com/pollen-robotics/microduck_rl/blob/bae39f5900b318f7e87fc485c30a31213cfa14eb/docs/roller_standup_policy_summary.md) | 有设计/训练配方，不代表 main `roller.onnx` 已具备相同恢复能力；文档提到早期训练依赖不现实摩擦。 |
| 轮上原地旋转 | `Mjlab-Spin-Flat-MicroDuck`，[cfg](https://github.com/pollen-robotics/microduck_rl/blob/bae39f5900b318f7e87fc485c30a31213cfa14eb/src/mjlab_microduck/tasks/microduck_spin_env_cfg.py) | 阶段命令驱动约一圈逆时针旋转；需要相位适配，不是给所有 one-shot 同一零命令即可。 |
| 跳跃 | N：当前 registry、官方 policy 10文件及脚本未找到 jump task/权重 | 更新系统设计文档里的 `model-jump` 只是架构举例，不能据此列成官方可用跳跃。[registry](https://github.com/pollen-robotics/microduck_rl/blob/bae39f5900b318f7e87fc485c30a31213cfa14eb/src/mjlab_microduck/tasks/__init__.py)；[设计例子](https://github.com/pollen-robotics/microduck/blob/da34a2212ae12eddfd73d0dfbf924f291aaf1dc9/docs/design/updater-design.md) |

Registry 的**精确数量**为18个基础任务ID＋15个 Backlash ID＝33（13个任务家族）。Flat/Rough 双版本：Velocity、VelStand、StandUp、SitStand、GroundPick；其余8个单版本。Backlash 覆盖前五家族的 Flat/Rough（10个）及 BallKick、Velocity-Rollers、Swizzle、RollerCrouch、RollerSlope（5个），**没有注册** Roulade/Spin/RollerStandUp 的 Backlash 版本；README“every main task”不能代替实际表。[注册实现](https://github.com/pollen-robotics/microduck_rl/blob/bae39f5900b318f7e87fc485c30a31213cfa14eb/src/mjlab_microduck/tasks/__init__.py)

#### 模型与场景清单（静态 XML 核查）

| 资产 | 实际用途/内容 |
|---|---|
| `robot_walk.xml` / `_backlash.xml` | 减少躯干/头部碰撞的训练行走模型；不适合直接证明趴地/翻滚/抓取接触。[model](https://github.com/pollen-robotics/microduck_rl/blob/bae39f5900b318f7e87fc485c30a31213cfa14eb/src/mjlab_microduck/robot/microduck/robot_walk.xml) |
| `robot_groundcontact.xml` / `_backlash.xml` | 为落地姿态挑选碰撞体的完整身体接触模型。[model](https://github.com/pollen-robotics/microduck_rl/blob/bae39f5900b318f7e87fc485c30a31213cfa14eb/src/mjlab_microduck/robot/microduck/robot_groundcontact.xml) |
| `robot_groundcontact_rollers.xml` / `_backlash.xml` | 加4被动轮的模型；任务输出仍只管14个伺服关节。[model](https://github.com/pollen-robotics/microduck_rl/blob/bae39f5900b318f7e87fc485c30a31213cfa14eb/src/mjlab_microduck/robot/microduck/robot_groundcontact_rollers.xml) |
| `robot_allcollisions.xml` / `_backlash.xml` | 所有部件的碰撞模型；README 说“no task uses it yet”并不完全匹配 registry 中 VelStand Backlash 的 `_BL_ALLCOLLISIONS` 映射，集成要按实际配置选择。[model](https://github.com/pollen-robotics/microduck_rl/blob/bae39f5900b318f7e87fc485c30a31213cfa14eb/src/mjlab_microduck/robot/microduck/robot_allcollisions.xml)；[registry](https://github.com/pollen-robotics/microduck_rl/blob/bae39f5900b318f7e87fc485c30a31213cfa14eb/src/mjlab_microduck/tasks/__init__.py) |
| `scene.xml`、`scene_backlash.xml` | 包 groundcontact 对应模型；INIT/STAND/SIT/FOLD关键帧。[scene](https://github.com/pollen-robotics/microduck_rl/blob/bae39f5900b318f7e87fc485c30a31213cfa14eb/src/mjlab_microduck/robot/microduck/scene.xml) |
| `scene_walk.xml`、`scene_walk_backlash.xml` | 包 walk 对应模型；同四个关键帧。[scene](https://github.com/pollen-robotics/microduck_rl/blob/bae39f5900b318f7e87fc485c30a31213cfa14eb/src/mjlab_microduck/robot/microduck/scene_walk.xml) |
| `scene_allcollisions.xml` | 全碰撞机器人与地板；同四个关键帧。[scene](https://github.com/pollen-robotics/microduck_rl/blob/bae39f5900b318f7e87fc485c30a31213cfa14eb/src/mjlab_microduck/robot/microduck/scene_allcollisions.xml) |
| `scene_rollers.xml` | groundcontact_rollers＋地板/关键帧。[scene](https://github.com/pollen-robotics/microduck_rl/blob/bae39f5900b318f7e87fc485c30a31213cfa14eb/src/mjlab_microduck/robot/microduck/scene_rollers.xml) |
| `scene_ball.xml`＋`ball.xml` | groundcontact机器人＋物理球；scene_ball本身未定义四姿态关键帧。[scene](https://github.com/pollen-robotics/microduck_rl/blob/bae39f5900b318f7e87fc485c30a31213cfa14eb/src/mjlab_microduck/robot/microduck/scene_ball.xml)；[ball](https://github.com/pollen-robotics/microduck_rl/blob/bae39f5900b318f7e87fc485c30a31213cfa14eb/src/mjlab_microduck/robot/microduck/ball.xml) |
| `scene_apartment.xml`＋`apartment.xml` | 全碰撞机器人与公寓：房间、门、家具、视觉地标、禁碰撞 dock；可渲染 RGB/ToF，不自带自主回充控制器。[scene](https://github.com/pollen-robotics/microduck_rl/blob/bae39f5900b318f7e87fc485c30a31213cfa14eb/src/mjlab_microduck/robot/microduck/scene_apartment.xml)；[apartment](https://github.com/pollen-robotics/microduck_rl/blob/bae39f5900b318f7e87fc485c30a31213cfa14eb/src/mjlab_microduck/robot/microduck/apartment.xml) |
| `scene_vslam.xml`＋`vslam_room.xml` | 为视觉定位提供纹理/物体的室内场景；场景文件存在不等于 SLAM 或导航闭环已跑通。[scene](https://github.com/pollen-robotics/microduck_rl/blob/bae39f5900b318f7e87fc485c30a31213cfa14eb/src/mjlab_microduck/robot/microduck/scene_vslam.xml) |
| `xl330_test_bench/scene.xml` | 电机模型标定/比较台，不是机器人娱乐动作。[scene](https://github.com/pollen-robotics/microduck_rl/blob/bae39f5900b318f7e87fc485c30a31213cfa14eb/src/mjlab_microduck/robot/xl330_test_bench/scene.xml) |

#### 训练 / play / 推理 / 发布脚本（按真实入口列出）

- `uv run train <TASK>`→`src/mjlab_microduck/train_cli.py`；`uv run play <TASK>` 和 `list-envs` 来自 mjlab；`scripts/play_latest.py` 选最近 run；`scripts/export.py` 烘焙 normalizer 导出；`scripts/infer_policy.py` 为 CPU MuJoCo/ONNX 键盘回放（可 walking/standing/sitstand/roulade/ground-pick/kick，支持debug、csv、record）；`duck-body`→`sim/body_server.py` 接真实 robotd；`publish` / `share-training`→`publish/cli.py` / `publish/training.py`。[pyproject](https://github.com/pollen-robotics/microduck_rl/blob/bae39f5900b318f7e87fc485c30a31213cfa14eb/pyproject.toml)；[infer](https://github.com/pollen-robotics/microduck_rl/blob/bae39f5900b318f7e87fc485c30a31213cfa14eb/scripts/infer_policy.py)；[export](https://github.com/pollen-robotics/microduck_rl/blob/bae39f5900b318f7e87fc485c30a31213cfa14eb/scripts/export.py)；[body](https://github.com/pollen-robotics/microduck_rl/blob/bae39f5900b318f7e87fc485c30a31213cfa14eb/src/mjlab_microduck/sim/body_server.py)
- 云训练为 `train_hook.py` 拦截 `--hf-jobs`、`hf_jobs.py` 提交、`scripts/hf/train_hf.py` / `uploader.py`。本轮没有提交云任务。[HF Jobs instructions](https://github.com/pollen-robotics/microduck_rl/blob/bae39f5900b318f7e87fc485c30a31213cfa14eb/scripts/hf/README.md)
- 相关工具：`crouch_pose_editor.py`、`view_slope_terrain.py`、`find_onnx_source.py`、`plot_observations_comparison_plotly.py`、`testbench_sim2real.py`、`validate_bam_testbench.py`、`odom_anchor_points.py` / `odom_anchor_sets.json` / `wandb_utils.py`。[scripts tree](https://github.com/pollen-robotics/microduck_rl/tree/bae39f5900b318f7e87fc485c30a31213cfa14eb/scripts)
- 新的 `pickup_datagen.py` / `pickup_train.py` / `pickup_eval.py` / `pickup_battery.py` / `pickup_demo.py` / `pickup_e2e_robotd.py` 研究的是**人将机器人抱起时暂停/放回后恢复**，不是“机器人拾取电池”；`battery` 在此指测试组。CPU demo 需独立 detector 路径，默认指向本地 logs，不能视为随官方10个策略直接交付的资产。[demo](https://github.com/pollen-robotics/microduck_rl/blob/bae39f5900b318f7e87fc485c30a31213cfa14eb/scripts/pickup_demo.py)；[训练](https://github.com/pollen-robotics/microduck_rl/blob/bae39f5900b318f7e87fc485c30a31213cfa14eb/scripts/pickup_train.py)；[测试组](https://github.com/pollen-robotics/microduck_rl/blob/bae39f5900b318f7e87fc485c30a31213cfa14eb/scripts/pickup_battery.py)
- ONNX 只供推理，不包含训练继续所需 critic/optimizer/curriculum。新训练包文档定义 `pollen-robotics/microduck-training/bundles/...`，默认上传 private；本轮无法确认其公开 repo 的可读完整 bundle 清单。虽然文档给出 `velstand/0045i2si_2749` 示例，不应据此声称所有运动都已有可公开继续训练的 `.pt`。[training bundles](https://github.com/pollen-robotics/microduck_rl/blob/bae39f5900b318f7e87fc485c30a31213cfa14eb/docs/training_checkpoints.md)

#### 头部、脸、待机、情绪、音乐、视觉及社交

| 能力/证据 | 已公开内容 | MuJoCo/硬件与集成边界 |
|---|---|---|
| 头部/身体/嘴控制，A | 4维 head命令＋6维body命令，嘴额外控制，IK/gaze链。[kinematics](https://github.com/pollen-robotics/microduck/tree/da34a2212ae12eddfd73d0dfbf924f291aaf1dc9/kinematics)；[控制](https://github.com/pollen-robotics/microduck/blob/da34a2212ae12eddfd73d0dfbf924f291aaf1dc9/robotd/src/control.rs) | 能在官方 daemon+body 路径表现；某些网络未训练body/head响应，不能把所有policy当同一种动作空间语义。 |
| Idle 待机，A | `idle_head.rs`：四处瞟、微漂、侧头、呼吸式body_z、渐安静和无声哈欠。[source](https://github.com/pollen-robotics/microduck/blob/da34a2212ae12eddfd73d0dfbf924f291aaf1dc9/robotd/src/idle_head.rs) | 是确定机制＋随机参数的程序行为，文件明确“nothing here looks at anything”；不是视觉注意力/云回答。roller 默认禁用idle头部避免网络不兼容。[cheatsheet](https://github.com/pollen-robotics/microduck/blob/da34a2212ae12eddfd73d0dfbf924f291aaf1dc9/docs/robot/cheatsheet.md) |
| 情绪关键帧，A | 官方 emotions 库14项：sad7.5s、devastated8.5s、curious3s、mmh2s、yes1.5s、yes_fast1.5s、no1.8s、defiant2.2s、angry2.6s、mock2.6s、excited3.4s、impatient2.6s、laugh3s、play_dead7.5s；关键帧＋wav＋preview＋旧runtime patch。[catalog](https://github.com/pollen-robotics/microduck_emotions/blob/431c73df8a9d3cb6b6067d09ced6c169fdfa59fd/emotions.json)；[README](https://github.com/pollen-robotics/microduck_emotions/blob/431c73df8a9d3cb6b6067d09ced6c169fdfa59fd/README.md) | 不属新增RL策略；current robotd 随包只有前13项，**不含 play_dead**。devastated可请求sit并维持坐下，play_dead说明需要mat。不能把旧patch直接套在最新runtime。[随包目录](https://github.com/pollen-robotics/microduck/tree/da34a2212ae12eddfd73d0dfbf924f291aaf1dc9/robotd/emotions) |
| 脸部LED/灯，B | beta板12 LED与flashlight命令。[说明](https://github.com/pollen-robotics/microduck/blob/da34a2212ae12eddfd73d0dfbf924f291aaf1dc9/docs/robot/cheatsheet.md)；[实现](https://github.com/pollen-robotics/microduck/blob/da34a2212ae12eddfd73d0dfbf924f291aaf1dc9/robotd/src/leds.rs) | 硬件输出；仿真不模拟GPIO电路，网页表情显示需要另外明确映射。 |
| Quack/抚摸反应，A/B | 程序合成声库、开关机叫声；mic classifier触发coo可选，默认关闭。[说明](https://github.com/pollen-robotics/microduck/blob/da34a2212ae12eddfd73d0dfbf924f291aaf1dc9/docs/robot/cheatsheet.md)；[pet-detect目录](https://github.com/pollen-robotics/microduck/tree/da34a2212ae12eddfd73d0dfbf924f291aaf1dc9/pet-detect) | 声音本地合成不等于LinX云语音；声音可在CPU回放，触摸识别需要音频输入/模型。 |
| “空气键盘”相关：ToF theremin，A | `robotctl theremin`：8×8 ToF最近有效距离→音高，嘴随音符开合。[实现](https://github.com/pollen-robotics/microduck/blob/da34a2212ae12eddfd73d0dfbf924f291aaf1dc9/robotd/src/theremin.rs)；[说明](https://github.com/pollen-robotics/microduck/blob/da34a2212ae12eddfd73d0dfbf924f291aaf1dc9/docs/robot/cheatsheet.md) | 是距离连续控制的乐器，不是已确认的手指/多键识别；对墙也会发声。仿真ToF为raycast，可通过几何遮挡交互；没有本轮证据证明摄像头手部追踪或“空气钢琴”。 |
| 多鸭合唱，A | `chorale.rs`，BLE beacon同步四声部，`duck-ether`可模拟丢包和延迟；wistful、duck-strut乐谱，outer-wilds标为test asset not for release。[chorale](https://github.com/pollen-robotics/microduck/blob/da34a2212ae12eddfd73d0dfbf924f291aaf1dc9/robotd/src/chorale.rs)；[说明](https://github.com/pollen-robotics/microduck/blob/da34a2212ae12eddfd73d0dfbf924f291aaf1dc9/docs/robot/cheatsheet.md)；[仿真设计](https://github.com/pollen-robotics/microduck/blob/da34a2212ae12eddfd73d0dfbf924f291aaf1dc9/docs/design/simulation.md) | 官方文档自报四duck容器仿真，但不是本轮实测；音频资产发布注意排除test曲目。 |
| 头部RGB与ToF，A | body server渲染head camera；ToF64射线15Hz；daemon mediad/tofd模拟入口。[body](https://github.com/pollen-robotics/microduck_rl/blob/bae39f5900b318f7e87fc485c30a31213cfa14eb/src/mjlab_microduck/sim/body_server.py)；[说明](https://github.com/pollen-robotics/microduck/blob/da34a2212ae12eddfd73d0dfbf924f291aaf1dc9/docs/robot/simulation.md) | 可成为视觉能力的数据入口；真实NPU/ISP/VPU/驱动未模拟，不能将仿真延迟当板载延迟。 |
| 识别另一只Microduck，A/B | duck_detector训练 YOLO11n 320×320，导出ONNX/RKNN；HF公开pt/onnx/rknn。[训练repo](https://github.com/pollen-robotics/duck_detector/blob/cc1b52eb3ace9643c8948320e63f46a85cf6fb65/README.md)；[HF files](https://huggingface.co/pollen-robotics/microduck-duck-detector/tree/main) | RKNN INT8面向RK3566 NPU，CPU应用可走ONNX但需写清输入/后处理；只有duck一个类，不是通用物体/充电桩检测器。 |
| 官方远端vision demo，A | `spaces/vision-demo` 从robot接H264/JPEG，CPU OpenCV做Canny/帧差/光流/几何叠加。[README](https://github.com/pollen-robotics/microduck/blob/da34a2212ae12eddfd73d0dfbf924f291aaf1dc9/spaces/vision-demo/README.md)；[filters](https://github.com/pollen-robotics/microduck/blob/da34a2212ae12eddfd73d0dfbf924f291aaf1dc9/spaces/vision-demo/filters.py) | 这是视频数据处理示例，不是多模态大模型理解；`media.stream`只有帧，控制需独立JSON-RPC路径。 |
| 浏览器官方sandbox，A（文件/README级核查） | MuJoCo WASM＋onnxruntime-web，腿/轮双模型，踢球/啄取/坐立/轮滑蹲滑，3×3 arena、彩色皮肤、P2P ghost。[README](https://huggingface.co/spaces/pollen-robotics/microduck-simulator/blob/main/README.md) | 物理在每个tab，ghost是pose广播，不是共享碰撞世界；不是robotd远程连接，也不是LinX cloud。完整app代码本轮未逐行审计。 |


#### “有代码”和“MuJoCo端到端跑过”的证据差别

| 类别 | 能确认的最强证据 | 本报告允许的宣传口径 |
|---|---|---|
| 基础walking/stand、duck-body、RGB、ToF | 官方使用文档有具体启动链路；simulation设计页自述50Hz以及多鸭合唱测试，属于作者报告。[官方文档](https://github.com/pollen-robotics/microduck/blob/da34a2212ae12eddfd73d0dfbf924f291aaf1dc9/docs/design/simulation.md) | “官方实现支持；本轮未复跑”。不能改成“DuckKing已验证50Hz”。 |
| 10个运动ONNX及全套scene | 已核对公开资产与脚本；没有本轮场景×策略全组合轨迹记录。[policy manifest](https://huggingface.co/pollen-robotics/microduck-policies/blob/283771bcb3690a0a94a288c108365d9b630d21e4/manifest.json) | “可复用的官方公开资产；具体组合待测”。 |
| 13个随包情绪、idle、head/body/mouth | runtime代码与资源齐全，情绪文档给出sim目录；没有本轮MuJoCo录屏/完整成功日志。[emotion使用说明](https://github.com/pollen-robotics/microduck/blob/da34a2212ae12eddfd73d0dfbf924f291aaf1dc9/docs/robot/cheatsheet.md) | “官方runtime行为，可接模拟body；尚需本项目端到端验证”。 |
| ToF theremin | runtime合成与距离处理实现、仿真ToF射线输入皆存在；没有本轮用虚拟手/墙控制音高的验证。[theremin](https://github.com/pollen-robotics/microduck/blob/da34a2212ae12eddfd73d0dfbf924f291aaf1dc9/robotd/src/theremin.rs) | “可连接的乐器代码”，暂不称“网页空气键盘已实现”。 |
| detector、pet_detect、face LED | 检测模型/音频分类/硬件输出代码存在；simulation边界明确不模拟NPU、摄像头ISP等驱动。[boundary](https://github.com/pollen-robotics/microduck/blob/da34a2212ae12eddfd73d0dfbf924f291aaf1dc9/docs/robot/simulation.md) | “硬件功能或需要CPU替代实现的能力”；无本轮MuJoCo端到端证明。 |

### Inferences

- 最有价值的现成官方增量不是再包装已有8个运动按钮，而是情绪13项、旧walk/stand比较、官方公寓/RGB/ToF、真实daemon多机合唱，以及v9回归评测；这些可以组成不同证据等级的场景。[资产与路径依据](https://github.com/pollen-robotics/microduck/blob/da34a2212ae12eddfd73d0dfbf924f291aaf1dc9/docs/robot/simulation.md)；[情绪](https://github.com/pollen-robotics/microduck/blob/da34a2212ae12eddfd73d0dfbf924f291aaf1dc9/docs/robot/cheatsheet.md)；[策略diff](https://huggingface.co/pollen-robotics/microduck-policies/commit/283771bcb3690a0a94a288c108365d9b630d21e4)
- Swizzle/Spin/Slope/RollerStandUp是后续训练候选，不能把未核实权重的条目立即做成“官方现成可玩”菜单。[任务注册](https://github.com/pollen-robotics/microduck_rl/blob/bae39f5900b318f7e87fc485c30a31213cfa14eb/src/mjlab_microduck/tasks/__init__.py)

### Gaps

- 未确认所有独立HF模型仓库的穷尽清单、microduck-training全部公开训练bundle；HF API本轮多次网络重置。
- 未对每个motion执行稳定性、取消、互斥、模型切换、场景碰撞和CPU实时率测试；本文不能提供本项目成功率。
- 未穷尽所有未合并PR/个人分支；比如bow/headstand/MicroDuck2.0等PR标题不能列成官方已发布能力。

## 2. Self-charging 到底已公开到哪一层？

### Takeaway

官方公开代码确有“坐下”策略和公寓中的“charging dock”可视几何，但本轮未找到官方完整自主找桩/对接/充电闭环。尤其官方dock四个geom都关闭碰撞，sim body电压与温度为常数，这与“真实充电接触与电量变化”是不同层次。[dock源码](https://github.com/pollen-robotics/microduck_rl/blob/bae39f5900b318f7e87fc485c30a31213cfa14eb/src/mjlab_microduck/robot/microduck/apartment.xml)；[传感器源码](https://github.com/pollen-robotics/microduck_rl/blob/bae39f5900b318f7e87fc485c30a31213cfa14eb/src/mjlab_microduck/sim/body_server.py)

### Cited Findings

| 层级 | 官方已核实证据 | 正确表述/不能声称 |
|---|---|---|
| L1 坐下/休息姿态 | SIT关键帧；sitstand二值命令，座位高度目标约0.060m，站立目标约0.115m。[sit cfg](https://github.com/pollen-robotics/microduck_rl/blob/bae39f5900b318f7e87fc485c30a31213cfa14eb/src/mjlab_microduck/tasks/microduck_sitstand_env_cfg.py) | 可称“坐下等待/休息”；没有充电状态，不能把坐下自动称为已连接充电。 |
| L2 充电桩视觉物体 | apartment的`body name="dock" pos="-3.80 -2.78 0"`，base/panel/s1/s2四geom、`dock_site`。[XML](https://github.com/pollen-robotics/microduck_rl/blob/bae39f5900b318f7e87fc485c30a31213cfa14eb/src/mjlab_microduck/robot/microduck/apartment.xml) | 可称“官方公寓内含充电桩视觉地标”；四geom均`contype=0 conaffinity=0`，不是物理触点/磁吸/USB-C模型。 |
| L3 找到桩 | 有头部摄像头、ToF、公寓、odom/kinematics、duck detector，但未检出dock检测/定位/目标选择控制器。[sim](https://github.com/pollen-robotics/microduck/blob/da34a2212ae12eddfd73d0dfbf924f291aaf1dc9/docs/robot/simulation.md)；[body](https://github.com/pollen-robotics/microduck_rl/blob/bae39f5900b318f7e87fc485c30a31213cfa14eb/src/mjlab_microduck/sim/body_server.py)；[detector](https://github.com/pollen-robotics/duck_detector/blob/cc1b52eb3ace9643c8948320e63f46a85cf6fb65/README.md) | 地标坐标/真值site可供研究，但“读取XML目标坐标”不能描述为视觉自主定位。 |
| L4 接近/停靠 | 本轮检索runtime及RL发布任务中没有官方dock/return-to-charge task/policy。[registry](https://github.com/pollen-robotics/microduck_rl/blob/bae39f5900b318f7e87fc485c30a31213cfa14eb/src/mjlab_microduck/tasks/__init__.py)；[发布策略](https://huggingface.co/pollen-robotics/microduck-policies/blob/283771bcb3690a0a94a288c108365d9b630d21e4/manifest.json) | 可以组合移动＋坐下展示行为流程，须标自写控制逻辑或社区实现，不得冠以“官方自主回充”。 |
| L5 碰撞/接触确认 | 官方dock不碰撞，未见电气触点判定；sim电流字段注释明确“未对真实servo标定”，由力矩取值拼接，仅是形状一致的负载占位。[body](https://github.com/pollen-robotics/microduck_rl/blob/bae39f5900b318f7e87fc485c30a31213cfa14eb/src/mjlab_microduck/sim/body_server.py) | 不能从“进入某半径/坐下”推出触点接通，不能将sim currents_ma当实测功率。 |
| L6 电池充放电/停止/恢复 | `slow_sensors()`返回`NOMINAL_VOLTS`与固定`NOMINAL_TEMP_C`，没有SOC积分/充电器状态；runtime有电压估计与低电处理，但这不是仿真电池模型。[body](https://github.com/pollen-robotics/microduck_rl/blob/bae39f5900b318f7e87fc485c30a31213cfa14eb/src/mjlab_microduck/sim/body_server.py)；[model](https://github.com/pollen-robotics/microduck/blob/da34a2212ae12eddfd73d0dfbf924f291aaf1dc9/duck-control/src/model.rs) | 可测试上层被注入电压后的状态机；不能称真实充电、电池续航结果或能量优化验证。 |
| L7 量产硬件 | #174官方参与者2026-09-06回答量产最终单元会有onboard charging；#470在2026-10-26追问电流、外部充电冲突、断电后加充电电源能否自启，页面只见社区跟问。[#174](https://github.com/pollen-robotics/microduck/issues/174)；[#470](https://github.com/pollen-robotics/microduck/issues/470) | onboard charging不是“已发布自动回桩”；电气/自启具体约束仍未获本轮可引用答案。 |

官方产品页实际销售内容为机器人附电池/USB-C/controller、Charger pack的双槽充电器＋两电池等；本轮页面没有官方自动充电桩商品或自充电策略承诺。搜索出现的 `microducks.org` “$79 dock/Isaac Lab/RTX Spark”文案不在本轮确认的官方Pollen入口，不采用为官方证据；官网明确称MuJoCo。[Pollen产品页](https://pollen-robotics.com/microduck/)

`vetbook`把启动后第一条电压比上次高0.4 V以上推测为“充过电”，这是启发式日志，不能当实时接触充电确认。[vetbook](https://github.com/pollen-robotics/microduck/blob/da34a2212ae12eddfd73d0dfbf924f291aaf1dc9/robotd/src/vetbook.rs)

### Inferences

- 对DuckKing而言，可将“坐下休息”“走到公寓桩标记”“社区接触判定的回桩实验”分成三个条目；前三层的组合不能借名跃迁成全部七层已实现。[官方姿态/地标证据](https://github.com/pollen-robotics/microduck_rl/blob/bae39f5900b318f7e87fc485c30a31213cfa14eb/src/mjlab_microduck/tasks/microduck_sitstand_env_cfg.py)；[dock](https://github.com/pollen-robotics/microduck_rl/blob/bae39f5900b318f7e87fc485c30a31213cfa14eb/src/mjlab_microduck/robot/microduck/apartment.xml)
- 任何新Self-charging展示至少需要同时报告导航依据（真值/视觉）、对接判据（几何距离/物理接触）、电气模型（无/简化/硬件测量）。这是基于源代码缺口的集成建议，不是官方既有功能。[sim boundary](https://github.com/pollen-robotics/microduck/blob/da34a2212ae12eddfd73d0dfbf924f291aaf1dc9/docs/design/simulation.md)
- 社区MicroDock仓库由另一研究分支审计，应独立标注作者、源码/ONNX版本和“仿真验证、未硬件验证”等边界，不宜合并进“官方策略已具备”表。

### Gaps

- 未发现官方发布的dock checkpoint、识别充电桩模型、完整dock几何碰撞/接触电路、电池SOC动态或完整返航→接触确认→充电→恢复工作代码。
- 本轮没有观看/逐帧分析所有官方视频，也不以视频本身证明可下载运行；即使硬件视频存在，仍需对应代码/权重/模型版本。
- 量产板充电管理、电源路径、自启动、外部触点承载等问题未得到可引用的具体官方规范；不补造硬件参数。

## 3. 哪些能在CPU和一站式语音站点整合，风险在哪里？

### Takeaway

CPU上最直接的两条路径是现有本地MuJoCo＋ONNX replay，和官方daemon→duck-body；浏览器WASM是第三种独立架构。训练仍需要CUDA/MuJoCo Warp；“语音理解→动作”属于DuckKing的编排层，官方quack/情绪/合唱不能标为LinX云回答。[CPU replay](https://github.com/pollen-robotics/microduck_rl/blob/bae39f5900b318f7e87fc485c30a31213cfa14eb/scripts/infer_policy.py)；[daemon仿真](https://github.com/pollen-robotics/microduck/blob/da34a2212ae12eddfd73d0dfbf924f291aaf1dc9/docs/robot/simulation.md)；[训练依赖](https://github.com/pollen-robotics/microduck_rl/blob/bae39f5900b318f7e87fc485c30a31213cfa14eb/pyproject.toml)

### Cited Findings

- **训练与推理解耦**：官方训练基于mjlab1.3.0、warp1.12.0、torch2.9.1，Python>=3.12,<3.13；README要求CUDA，示例4096并行环境，Hugging Face Jobs可代训。`infer_policy.py`是CPU MuJoCo且用ONNX Runtime，默认BAM执行器，可用`--no-bam`退到XML PD，但二者物理不同，需披露实际使用项。[pyproject](https://github.com/pollen-robotics/microduck_rl/blob/bae39f5900b318f7e87fc485c30a31213cfa14eb/pyproject.toml)；[README](https://github.com/pollen-robotics/microduck_rl/blob/bae39f5900b318f7e87fc485c30a31213cfa14eb/README.md)；[infer](https://github.com/pollen-robotics/microduck_rl/blob/bae39f5900b318f7e87fc485c30a31213cfa14eb/scripts/infer_policy.py)
- **真实daemon接模拟body**：`robotd --sim host:port`替代servo bus，TCP newline JSON protocol1，50Hz；`scripts/duck-sim`管理daemon/body/可选camera和多duck；`--fake`只回显关节不含物理，与`--sim`互斥。[协议实现](https://github.com/pollen-robotics/microduck/blob/da34a2212ae12eddfd73d0dfbf924f291aaf1dc9/duck-control/src/sim.rs)；[使用说明](https://github.com/pollen-robotics/microduck/blob/da34a2212ae12eddfd73d0dfbf924f291aaf1dc9/docs/robot/simulation.md)
- **实时性**：上层是墙钟50Hz，模拟慢于实时会影响闭环而非仅让画面慢；官方文档有45Hz健康门槛、多camera成本说明，但本项目机器没有本轮benchmark。[说明](https://github.com/pollen-robotics/microduck/blob/da34a2212ae12eddfd73d0dfbf924f291aaf1dc9/docs/robot/simulation.md)
- **兼容性不只obs shape**：61→14只是必要条件；sitstand的binary flag、ground_pick/crouch/spin的phase、gait twist具有不同语义；head/body默认值、action_scale、kp/BAM、XML碰撞、轮滑被动关节排序也需绑定版本。[manifest](https://huggingface.co/pollen-robotics/microduck-policies/blob/283771bcb3690a0a94a288c108365d9b630d21e4/manifest.json)；[infer](https://github.com/pollen-robotics/microduck_rl/blob/bae39f5900b318f7e87fc485c30a31213cfa14eb/scripts/infer_policy.py)；[spin](https://github.com/pollen-robotics/microduck_rl/blob/bae39f5900b318f7e87fc485c30a31213cfa14eb/src/mjlab_microduck/tasks/microduck_spin_env_cfg.py)
- **许可证必须拆开**：microduck/runtime与RL代码Apache-2.0；最新RL `LICENSE-MODELS.md`明确两目录的`.stl`为CC BY-NC-SA4.0（署名、非商业、相同方式共享）；XML/JSON/.part仍Apache。不能把“整个软件栈Apache”的官网口号外推成STL可以任意商业再发布。[RL许可证边界](https://github.com/pollen-robotics/microduck_rl/blob/bae39f5900b318f7e87fc485c30a31213cfa14eb/LICENSE-MODELS.md)；[RL代码许可证](https://github.com/pollen-robotics/microduck_rl/blob/bae39f5900b318f7e87fc485c30a31213cfa14eb/LICENSE)；[runtime许可证](https://github.com/pollen-robotics/microduck/blob/da34a2212ae12eddfd73d0dfbf924f291aaf1dc9/LICENSE)
- **其他许可证**：HF motion模型卡Apache-2.0；emotions库Apache-2.0；browser Space README仅明确app代码Apache，模型/音乐/转制mesh仍需按各上游许可核对；duck_detector训练依赖Ultralytics且模型卡写Apache，不能仅凭一个仓库LICENSE宣布所有依赖/预训练权重许可相同。[motion model card](https://huggingface.co/pollen-robotics/microduck-policies/blob/283771bcb3690a0a94a288c108365d9b630d21e4/README.md)；[emotions许可证](https://github.com/pollen-robotics/microduck_emotions/blob/431c73df8a9d3cb6b6067d09ced6c169fdfa59fd/LICENSE)；[browser README](https://huggingface.co/spaces/pollen-robotics/microduck-simulator/blob/main/README.md)；[detector pyproject](https://github.com/pollen-robotics/duck_detector/blob/cc1b52eb3ace9643c8948320e63f46a85cf6fb65/pyproject.toml)
- **许可时间差**：DuckKing目前RL pin早于本轮最新HEAD；应另外检查该固定revision当时的许可证与文件来源。本文不能替项目断言新许可证对旧版本追溯适用，亦不能用旧pin许可忽略准备引入的新资源。[当前公开许可证](https://github.com/pollen-robotics/microduck_rl/blob/bae39f5900b318f7e87fc485c30a31213cfa14eb/LICENSE-MODELS.md)

### Inferences

推荐整合次序（这是研究判断，不是本轮实现承诺）：

1. **优先A**：官方情绪13项、可取消的点头/摇头/好奇/笑与音频同步；官方RGB/ToF数据可视化；v9 vs当前v8可复现对比。它们具有明确可下载资产/实现。[情绪清单](https://github.com/pollen-robotics/microduck_emotions/blob/431c73df8a9d3cb6b6067d09ced6c169fdfa59fd/emotions.json)；[body](https://github.com/pollen-robotics/microduck_rl/blob/bae39f5900b318f7e87fc485c30a31213cfa14eb/src/mjlab_microduck/sim/body_server.py)；[v9 diff](https://huggingface.co/pollen-robotics/microduck-policies/commit/283771bcb3690a0a94a288c108365d9b630d21e4)
2. **优先A/B**：官方apartment/vslam/ball场景；daemon原生theremin与多duck chorale；针对已有ONNX的alpha_walking/alpha_stand对照模式。物理模型/协议与音频通道必须保持可辨。[场景目录](https://github.com/pollen-robotics/microduck_rl/tree/bae39f5900b318f7e87fc485c30a31213cfa14eb/src/mjlab_microduck/robot/microduck)；[runtime说明](https://github.com/pollen-robotics/microduck/blob/da34a2212ae12eddfd73d0dfbf924f291aaf1dc9/docs/robot/cheatsheet.md)
3. **研究B**：swizzle、roller slope、roller standup、spin和pickup classifier，先补齐权重来源/复现，再给站点可玩入口。[注册](https://github.com/pollen-robotics/microduck_rl/blob/bae39f5900b318f7e87fc485c30a31213cfa14eb/src/mjlab_microduck/tasks/__init__.py)；[pickup demo](https://github.com/pollen-robotics/microduck_rl/blob/bae39f5900b318f7e87fc485c30a31213cfa14eb/scripts/pickup_demo.py)
4. **独立社区实验**：Self-charging应采用已查实的社区实现及作者声明，保持“官方坐立策略复用＋社区dock/控制器”的组合出处，不将其标为官方提供的整套能力。

站点每次实验应保留：后端类型、模型/场景policy hash、simulation time与wall time、动作退出原因、是否使用ground truth、是否存在简化电池/接触判定。这些是依据当前公开协议/模型差异提出的可复核要求，不是官方已经替DuckKing做完的测试。[协议](https://github.com/pollen-robotics/microduck/blob/da34a2212ae12eddfd73d0dfbf924f291aaf1dc9/duck-control/src/sim.rs)；[模型边界](https://github.com/pollen-robotics/microduck/blob/da34a2212ae12eddfd73d0dfbf924f291aaf1dc9/docs/design/simulation.md)

### Gaps

- 没有CPU吞吐、显存需求、训练费用或各动作本项目成功率的本轮数据；README“1–2h usable gait”是官方描述，硬件条件不完整，不能当本项目预算。
- “完整一站式”若包括硬件LED、真实mic抚摸、真实NPU检测、电池充电和远端LinX voice，需要逐个独立后端测试；现有公开仿真不能替它们给出真实性背书。
- 本轮不修改app、不更新pin、不生成演示视频、不运行策略、不部署、不提交云任务；后续实现需要按项目AGENTS分支/PR和取消/有界动作/失败处理规则另行执行。
