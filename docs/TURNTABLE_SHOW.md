# 转盘大逃鸭（互动场景 + 短片验证）

物理实验室新增**互动场景**：场景页签「转盘大逃鸭」，按钮控制慢速/中速/全速/停盘与坐站，实时状态行显示转速（弧度/秒与盘沿线速度）和台上剩余；语音（本地优先或灵矽）支持"转起来/加速/停下转盘/坐下"。转盘旋转由后端实时位姿驱动前端渲染自动呈现。

另有单文件短片验证脚本 `scripts/validate_turntable.py`（可放映成片）。四鸭登上电机
驱动的木转盘，被盘面摩擦带着旋转并尝试逆向倒走保持平衡；离心力把鸭鸭依次甩出
边缘出局，出局者在地面自爬起，最后留在盘上者夺冠（头顶奖杯、盘沿线速度 HUD、
轮盘辐条/箭头与盘面涂鸦贴片示速）。单文件 `scripts/validate_turntable.py`
自包含节目套件（仿真时间轴录像、串行 Tingting 旁白与字幕、演员表叠加）。

## 运行

```bash
uv sync --frozen --extra simulation   # MuJoCo 与官方策略
# 可选配乐（CC-BY 4.0，运行者自行下载，仓库不分发）：
curl -L -o .duckking/teletubbies/music.mp3 \
  "https://incompetech.com/music/royalty-free/mp3-royaltyfree/Fluffing%20a%20Duck.mp3"
uv run --frozen --no-sync --extra simulation python scripts/validate_turntable.py
# --no-video 只跑测量与 JSON 报告
```

需要 `ffmpeg`（PATH 可见）与 macOS `say`（Tingting）。产物在
`.duckking/teletubbies/`（不入库）：`turntable-show-music.mp4`、
`turntable-report.json`。视频按仿真时间轴逐帧渲染（20 fps = 每 0.05 s 仿真时间
一帧），播放节奏与物理一致。

## 验收与结果

- 出局判定：躯干位置实测越过盘缘（>1.02 m）；每轮回合记录转速与幸存者。
- 出局后自爬起：velstand 无外力辅助恢复（倒地→upright>0.94 持续 0.5 s），
  未爬起时旁白如实说"躺平"。
- 多轮运行 pass=True 并产生冠军（如 1 号鸭站位策略撑到最后）。

## 诚实性契约

布景（辐条/箭头/圆点/涂鸦贴片/天空/云/太阳）全部为 `contype=conaffinity=0` 的
静态视觉几何或盘体子几何，不参与碰撞；盘面摩擦用 `priority="1"` 覆盖鸭脚摩擦；
盘体显式 12 kg 并 `gravcomp="1"`（轴承悬浮），避免自重压地摩擦吃掉电机扭矩——
这些都是让"电机转盘"物理成立的最小建模。完成判定只来自实测；旁白为 Tingting
合成且串行（字幕时长=语音时长，未发生的事件不配音）；速度 HUD 为 ω×半径换算。

## 工程要点（踩坑记录）

MuJoCo 接触摩擦取两几何体最大值，盘面需 priority 才能生效；velstand 零指令是
世界系定点，"随盘共转"由摩擦携带（sitstand 雕像模式），显式逆向行走指令超过
其 ~0.9 rad/s 原地转向上限时表现为边被带转边倒走（正是本剧的平衡挣扎桥段）。
