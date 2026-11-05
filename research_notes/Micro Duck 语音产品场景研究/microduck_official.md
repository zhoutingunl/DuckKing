# Micro Duck 官方能力与 DuckKing 可引入增量

## 1. 官方已经提供什么，哪些仍是设想或有硬件条件？

### Takeaway

**用户最新确认：目前只有仿真，暂时没有实体机。** 官方现成价值主要在感知、表达与状态闭环；本轮应优先把注视、声音/嘴部表达、相对运动适配到仿真，把机载相机、麦克风抚摸、BLE、ToF 留作后续硬件路线。以下是源码与文档研究，没有进行实体机器人或云端实验。

### Cited Findings

- 版本口径：Microduck 固定到项目使用的 `942e58e3aa6dbb28e7037203fff11866122c7567`；本次检查上游 `main` 也是该提交。Microduck RL 固定到 `b02fdea4902c2b93b7d34a83a6f05da4ececb7d3`；策略包固定到 `665ae4eb20bfe13bca1ef4ea6d4bb6b4a096e448`。策略清单包含行走/站立、坐站、轮滑、低头啄取、轮滑下蹲、前滚翻、左右踢球；没有一个可直接加载的大型“情绪动作大全”。[Microduck 固定提交](https://github.com/pollen-robotics/microduck/commit/942e58e3aa6dbb28e7037203fff11866122c7567)、[RL 固定提交](https://github.com/pollen-robotics/microduck_rl/tree/b02fdea4902c2b93b7d34a83a6f05da4ececb7d3)、[官方策略 manifest](https://huggingface.co/pollen-robotics/microduck-policies/raw/665ae4eb20bfe13bca1ef4ea6d4bb6b4a096e448/manifest.json)
- `robot.look` 接受躯干坐标系里的三维目标点，官方逆运动学计算头部姿态；它不是“识别人脸”或“定位说话人”。`robot.mouth` 与 `robot.sound` 提供嘴部及表达音，后者包含 greet、inquire、chirp、coo、alarm 等；这些声音是本地合成表达，不是灵矽语音回答。[官方 IPC 定义](https://github.com/pollen-robotics/microduck/blob/942e58e3aa6dbb28e7037203fff11866122c7567/duck-ipc-proto/src/lib.rs#L670)
- 官方 `pet-detect` 是通过头部麦克风听摩擦声的小型模型，发布包已有 ONNX 模型，由 robotd 工作线程触发抚摸开始事件和 coo。它不是皮肤触觉、压力测量或情绪识别。[pet-detect README](https://github.com/pollen-robotics/microduck/blob/942e58e3aa6dbb28e7037203fff11866122c7567/pet-detect/README.md)
- 官方有“被抱起暂停”的检测/控制路径，适用条件与配置由 daemon 管理；文档说明该分类器来自仿真训练，不能把文档中的响应时间当作本项目实测保证。当前 DuckKing robotd 适配器已在就绪检查中拒绝 `picked_up` 状态的新动作，因此缺口是交互闭环，不是完全缺少安全检查。[官方 pickup 实现](https://github.com/pollen-robotics/microduck/blob/942e58e3aa6dbb28e7037203fff11866122c7567/robotd/src/pickup.rs)、[官方运行说明](https://github.com/pollen-robotics/microduck/blob/942e58e3aa6dbb28e7037203fff11866122c7567/docs/robot/cheatsheet.md#picking-the-robot-up)、[DuckKing 适配器](https://github.com/zhoutingunl/DuckKing/blob/477253f/src/duckking/robotd.py#L62)
- 真实摄像头媒体通道已经存在：`media.frame` 提供本机帧，mediad 的 `GET /frame` 提供 PNG；`media.stream` 可向远端推送 H.264/JPEG。固定版本还包含 Microduck 检测器，但“能检测鸭子”不等于通用视觉、识别人脸或识别任意物体。[快照代码](https://github.com/pollen-robotics/microduck/blob/942e58e3aa6dbb28e7037203fff11866122c7567/mediad/src/snapshot.rs)、[视觉示例](https://github.com/pollen-robotics/microduck/blob/942e58e3aa6dbb28e7037203fff11866122c7567/spaces/vision-demo/README.md)、[鸭子检测器](https://github.com/pollen-robotics/microduck/blob/942e58e3aa6dbb28e7037203fff11866122c7567/duck-detect/src/lib.rs)
- ToF 手势乐器已有官方实现，通过头部测距控制音高、响度和嘴部开合；它把有效距离内最近的回波当作手，因此墙等物体也可能触发。它依赖实体 ToF，不能假定所有复刻机已经安装；固定版本文档指出多数 Radxa Zero3 开发机没有该模块。[theremin 实现](https://github.com/pollen-robotics/microduck/blob/942e58e3aa6dbb28e7037203fff11866122c7567/robotd/src/theremin.rs)、[ToF 安装/运行说明](https://github.com/pollen-robotics/microduck/blob/942e58e3aa6dbb28e7037203fff11866122c7567/docs/robot/cheatsheet.md#the-tof-sensor-tofd)
- BLE 合唱是已实现的独立机器人协作协议，包含入团、角色选择、节拍与离团处理，需要至少两台启用该功能的实体设备。它与浏览器里几个模型共享一个音频时钟不是同一项能力。[官方 chorale 实现](https://github.com/pollen-robotics/microduck/blob/942e58e3aa6dbb28e7037203fff11866122c7567/robotd/src/chorale.rs)
- `docs/ideas/autonomous_behavior.md` 列出 Wander、Zoomies、Startle、Preen、Nap、BallPlay 等 16 个状态及能量/心情模型，但文件明确旧 `autonomous.rs` 没有移植到当前 daemon。这是产品灵感与开发计划，不能作为当前已实现功能清单。该文件部分事项还落后于实际代码，具体 pickup、检测器等以当前模块为准。[官方 ideas 文档](https://github.com/pollen-robotics/microduck/blob/942e58e3aa6dbb28e7037203fff11866122c7567/docs/ideas/autonomous_behavior.md)

### Inferences

- 应区分三层：策略提供身体能力；robotd/mediad 提供感知及执行服务；DuckKing 与灵矽负责意图、任务、状态表达。已有官方代码只说明能复用，不能直接宣称本项目已经打通。
- 本次值得扩展的是“输入→理解/澄清→动作→反馈”的闭环。即使新增一个很小的定向注视，也比再做一段长动作脚本更能体现语音智能硬件主题。抱起、摸头如用于本轮，只能由明确标为模拟事件的控件注入，不可称作真实传感器检测。

### Gaps

- 用户没有实体机器，因此机载摄像头、头部麦克风/扬声器、ToF、BLE 与 beta 面部 LED 均不属于本轮可用条件；后续采购/装配必须重新确认版本与驱动。
- 未找到可直接证明标准硬件具有麦克风阵列声源定位、成熟人脸跟随、全屋导航或通用桌面边缘防跌落的官方证据；不能在场景里把这些当成现有能力。
- 未验证官方拾起分类器在用户实体机上的泛化效果，也未进行任何现场噪声、温度、步态或物体抓取测量。

## 2. 当前项目还值得接入哪些能力？

### Takeaway

以下九项区分本轮仿真增量与后续实体路线。P0/P1/P2 是本次研究判断，不是官方级别；“需封装”表示上游组件已存在，但仍需接入 DuckKing 的能力声明、动作取消、结果及错误反馈，不能仅添加一句提示词。对仿真，可复用算法和表达设计，不意味着 robotd 服务已在当前 MuJoCo 连接中可调用。

### Cited Findings

当前 robotd 适配器实际调用 `robot.move`、`robot.head`、`robot.pose`、`robot.stop` 并订阅状态，没有暴露下面的大多数服务。下表的项目缺口以这一实际连接路径为参照；现有仿真或动画相似表现不能替代真实服务。[DuckKing 当前 robotd 适配器](https://github.com/zhoutingunl/DuckKing/blob/477253f/src/duckking/robotd.py)

| 优先级与能力 | 官方已有的部分 | DuckKing 需要补的闭环 / 条件 | 产品价值及工作量判断 |
|---|---|---|---|
| P0 仿真：定向注视 `look_at` | 目标点 IK、可达范围裁剪。[IPC LookParams](https://github.com/pollen-robotics/microduck/blob/942e58e3aa6dbb28e7037203fff11866122c7567/duck-ipc-proto/src/lib.rs#L2293) | 适配有界注视工具；以模拟世界坐标转躯干坐标，区分“左边/桌面目标点”与真正视觉定位到的人；未知目标先澄清。 | 小至中：配合倾听/思考/选择形成注意力感。模拟坐标须标明来源，不称为视觉检测。 |
| P0 仿真：鸭声与嘴部表达 | 独有合成音色、语义音效、嘴部驱动；音频播放统一由官方 sound owner 管理。[声音实现](https://github.com/pollen-robotics/microduck/blob/942e58e3aa6dbb28e7037203fff11866122c7567/robotd/src/sound.rs) | 将表达音与嘴部包络适配到浏览器，与灵矽 TTS 做音频互斥、被打断即停；明确本地表情音来源。官方 daemon 音频输出不等于已接入浏览器。 | 小至中：每轮回答都可强化角色存在感。先做“收到/困惑/成功”三种短反馈；现有本地文字＋提示音不能说成已有自然语言 TTS。 |
| 后续实体：坐姿拍照问答 | 实机帧读取及媒体流。[快照实现](https://github.com/pollen-robotics/microduck/blob/942e58e3aa6dbb28e7037203fff11866122c7567/mediad/src/snapshot.rs) | 连接灵矽官方拍照工具链，图片上传结果、超时及权限反馈；固定坐姿并提示视野范围。通用物体理解来自另外接入的模型。 | 中：可做猜物、看卡片、纠正误认。本轮无实体机，机载视觉不列为交付承诺；若另做浏览器相机，必须说明是电脑摄像头而非鸭子视野。 |
| P1 仿真事件：抱起暂停与放回对话 | 检测及暂停控制；项目已有状态 guard。[官方 pickup](https://github.com/pollen-robotics/microduck/blob/942e58e3aa6dbb28e7037203fff11866122c7567/robotd/src/pickup.rs)、[项目 guard](https://github.com/zhoutingunl/DuckKing/blob/477253f/src/duckking/robotd.py#L62) | 本轮用显式“模拟抱起”事件，终止当前任务并清空续播动作，放回后等待新的“继续”；实体接入后再验证检测误差。 | 小至中：把安全状态变成可感知的宠物互动；模拟事件与真实识别必须一眼能分辨。 |
| P1 仿真事件；后续实体检测：摸头回应 | 麦克风摩擦声分类器、ONNX 与事件管道。[pet-detect](https://github.com/pollen-robotics/microduck/blob/942e58e3aa6dbb28e7037203fff11866122c7567/pet-detect/README.md) | 本轮点击头部/明确的模拟事件触发反馈。未来实际检测需确认麦克风位置、误触发、录音与 ASR 资源冲突。 | 模拟小、实体中：可做“说一句，再摸一下”的互动，但本轮不能宣传为真实抚摸识别，更不是触觉皮肤。 |
| 后续实体：真实电量/健康与休息 | `robot.health` 读健康；`robot.rest` 温和坐下并释放到可重新初始化的休息态。[IPC 生命周期定义](https://github.com/pollen-robotics/microduck/blob/942e58e3aa6dbb28e7037203fff11866122c7567/duck-ipc-proto/src/lib.rs#L435) | 只读问询先落地；电量未知时明确未知。受控休息需完成当前任务、确认姿态与状态，不把 `relax` 直接暴露成随意语音工具。 | 小至中：支撑真实设备陪伴。本轮可做明确命名的“角色精力”游戏状态，但不得冒充真实电量/温度。 |
| P1 仿真：短距离相对移动 | 足底接触、关节 FK、IMU 里程计，坐标以启动方向为基准，没有磁力计。[官方 odometry](https://github.com/pollen-robotics/microduck/blob/942e58e3aa6dbb28e7037203fff11866122c7567/odometry/src/lib.rs) | 仿真先用 MuJoCo 位姿做闭环，标明是真值；设置误差/时间/距离上限、进度和取消。未来接实机里程计另验漂移。 | 中：让“向前一点”有距离含义。仿真位置控制不能证明实体定位精度或全屋导航。 |
| 后续实体：真实 BLE 双鸭合唱 | 自动角色、节拍、成员变化，逐台 opt-in。[官方 chorale](https://github.com/pollen-robotics/microduck/blob/942e58e3aa6dbb28e7037203fff11866122c7567/robotd/src/chorale.rs) | 准备两台真机、蓝牙功能、音频互斥及加入/退出语音反馈；区分于现有四鸭仿真编排。 | 中至大：从“单鸭表演”升级成会加入同伴的装置。本轮不投入实体组网。 |
| 后续实体：手势乐器 | 距离驱动音高、音量及嘴部，失去新鲜测距会静音。[官方 theremin](https://github.com/pollen-robotics/microduck/blob/942e58e3aa6dbb28e7037203fff11866122c7567/robotd/src/theremin.rs) | 检测传感器可用性、明确进入/退出模式、语音与演奏交替，限制动作幅度。 | 中：把“说话→手势→鸭子唱”组合成可参与体验；本轮没有实体 ToF，不进入现场承诺。 |

### Inferences

- 截止前的一轮实质开发建议选择 **定向注意力＋语音/鸭声表达**，并按现有仿真接口情况补 **有界相对位移**。可接灵矽 emotion/action 事件驱动这些表达（协议细节由灵矽研究核验）。抱起/抚摸只能作为显式模拟输入；机载拍照、BLE、ToF、真实电量不作为本轮演示承诺。
- 应避免把表中九项全部承诺在截止前完成。工期是相对估计，尚未根据实体设备与驱动状态测量；优先选择已有硬件可复用、能独立验收的路径。
- 按官方实现，声音服务会排他使用 PCM；Linx TTS 与本地鸭声必须有唯一播放仲裁，否则再好的音色也可能打断语义回答。[声音 owner 实现](https://github.com/pollen-robotics/microduck/blob/942e58e3aa6dbb28e7037203fff11866122c7567/robotd/src/sound.rs)

### Gaps

- 这份清单不证明上述能力已经在 DuckKing 的真实机器人、真实媒体与灵矽云链路联调通过。总报告应采用代码审计研究者提供的各后端能力矩阵，避免把浏览器动画、MuJoCo 与 robotd 混在一起。
- 用户已确认没有实体机，因此相机/ToF/BLE 等条件项只能进入后续路线；不能用尚未购买/组装的传感器支撑本周二演示。

## 3. 对现有演示与场景设计有什么约束，哪些方向不值得本轮投入？

### Takeaway

围绕“会说话的实体鸭子”，比围绕“技能按钮集合”更容易形成记忆点。一个场景最好同时具备用户意图、可见身体反馈、真实结果和可被用户打断/纠正的分支；复杂感知和硬件改装则留给后续。

### Cited Findings

- 项目 `ground_pick` 的成功条件是嘴部高度和下降幅度，不验证物品进入嘴部并被带走。它可以证明低头啄取姿态，不能直接命名成“已经从地上捡回物体”。[DuckKing 动作测量](https://github.com/zhoutingunl/DuckKing/blob/477253f/src/duckking/official_skills.py#L101)
- 官方检测器线程主动限频，以避免持续推理使 Radxa 过热降频。这支持“用户要求时拍照”的节奏，不能据此承诺持续高速视觉跟随。[mediad 检测线程](https://github.com/pollen-robotics/microduck/blob/942e58e3aa6dbb28e7037203fff11866122c7567/mediad/src/detect.rs)
- 官方面部 LED 仅适用特定 beta 硬件，Zero3 和模拟器不具备同样面板；状态灯还由 daemon 根据机器状态管理。它适合已具备对应硬件的后续产品表达，不宜作为本轮默认增量。[LED 实现](https://github.com/pollen-robotics/microduck/blob/942e58e3aa6dbb28e7037203fff11866122c7567/robotd/src/leds.rs)
- NFC 服务当前重点是通过标签配对手柄。可设计故事卡/任务卡，但通用语义卡片交互仍要开发，不能宣传成已有官方技能。[NFC 服务](https://github.com/pollen-robotics/microduck/blob/942e58e3aa6dbb28e7037203fff11866122c7567/nfc/src/main.rs)
- 官方 velstand 策略已有身体倾斜和跌倒恢复描述，但策略能力不等于安全、稳定、可反复故意摔倒的产品演示；当前项目 `fallen` guard 也会阻止新的普通动作。[策略说明](https://huggingface.co/pollen-robotics/microduck-policies/raw/665ae4eb20bfe13bca1ef4ea6d4bb6b4a096e448/manifest.json)、[项目就绪检查](https://github.com/zhoutingunl/DuckKing/blob/477253f/src/duckking/robotd.py#L62)

### Inferences

- 值得迁移进十场景设计的基本结构：①“你说不清→鸭子歪头追问→你纠正→注视并执行”；②“行动被显式模拟抱起或语音打断→停下并解释→用户重新授权继续”；③“同一个语音意图用不同短动作与鸭声表达，但执行结果始终来自仿真状态”。后续有相机可增加“看卡片/物体→判断→换物→承认变化”。这些是设计建议，未实现。
- 适合保留的现有运动戏份：短距离递物、左右脚选择、坐姿问答、动作教学；需要真实执行结果。合唱、轮滑、翻滚宜作为短彩蛋，避免占据主线，把语音主题稀释成动作秀。
- 本轮不建议新训练高难度策略、连续翻滚、通用抓取、自动追球/带球、全屋巡航、人体/声源跟随、从零装 ToF 或 NFC、迁移整套自主状态机。原因分别是训练/硬件/定位/感知/集成链路新增长，且官方现有证据没有提供本项目可直接验收的完整方案。
- 口头“拍一下就懂”“跟着我”“去拿那个”会隐含额外识别和定位能力。设计台词须明确可达目标、观察方式与失败反馈；无真实传感器时只能作为标明来源的预览，不可伪装现场感知。

### Gaps

- 本轮没有获得现场评委流程、空间与噪声、实际台面防护或设备供电条件。最终十场景应由总报告结合代码审计，列出可立即演示、需要一轮开发、依赖新增硬件三种状态。
- 截止采用用户最新明确时间 **2026-10-27 09:00 Asia/Shanghai**；本研究不修改应用、不启动设备或云会话、不更改远端仓库，也不声称已完成工程交付。
