# 场景短片验证工具（Scene Shows）

以"真物理 + 实测验收 + 可放映成片"的方式，为演示剧场孵化新场景。本目录的四个脚本
基于 #30 的四鸭舞台基建（`duckking.stage`）产出一部带旁白、字幕、演员表与配乐的
MP4，以及逐拍测量的 JSON 报告，供评审选片后再产品化。

## 运行

需要 `uv sync --extra simulation`、`ffmpeg`（PATH 可见）与 macOS `say`（Tingting
中文语音）。可选背景音乐放到 `.duckking/teletubbies/music.mp3`（缺省自动跳过配乐）：

```bash
curl -L -o .duckking/teletubbies/music.mp3 \
  "https://incompetech.com/music/royalty-free/mp3-royaltyfree/Fluffing%20a%20Duck.mp3"
uv run --frozen --no-sync python scripts/validate_turntable.py   # 转盘大逃鸭
uv run --frozen --no-sync python scripts/validate_marathon.py    # 鸭界马拉松（计时排位）
uv run --frozen --no-sync python scripts/validate_teletubbies.py # 鸭鸭宝宝（天线宝宝模仿秀）
```

产物写入 `.duckking/teletubbies/`（不入库）：`*-show-music.mp4`、`*-report.json`。
视频按**仿真时间轴**逐帧渲染（20 fps = 每 0.05 s 仿真时间一帧），播放节奏与物理
节奏一致；`--no-video` 只跑测量。

## 已验证场景与结果

| 场景 | 节拍验收 | 代表结果 |
| --- | --- | --- |
| 鸭鸭宝宝 | 集结/出场/摔倒自爬起/拥抱/转圈/again-again | 两轮 18/18；摔倒自爬起四轮累计 27/28（0.8–2.4 s，无外力辅助） |
| 转盘大逃鸭 | 电动转盘（真实速度执行器）携带、离心出局、出局自爬起、冠军 | 多轮 pass=True 出冠军；出局半径实测 >1.02 m 越界判定 |
| 鸭界马拉松 | 单鸭计时排位（两圈 8 航点）、逐圈计时、电视号码标注 | 4/4 完赛，真实用时 172–233 s（含摔倒自爬起） |
| 鸭嘴接力（草稿） | 真实接触交棒 | 未通过：贴近段停滞在 ~0.95 m，暂不入库，排障后另行提交 |

## 诚实性契约

- 布景（天空/云/树/羊/河/滑板车/轮盘辐条与涂鸦贴片）全部为 `contype=conaffinity=0`
  的静态视觉几何，不参与碰撞，物理零影响；草地摩擦不改。
- 完成判定只来自实测（位置/转角/接触/姿态），出局、夺冠、爬起均逐项记录在
  report JSON；未发生的事件不配音（如未爬起不会说"站起来了"）。
- 旁白为 macOS Tingting 合成并逐条披露；字幕与语音共用同一 cue（时长取自语音
  真实长度）；台词串行队列避免多行同读。转盘盘面速度 HUD 为 ω×半径的实时换算。
- 配乐为 Kevin MacLeod《Fluffing a Duck》（CC-BY 4.0，incompetech），由运行者
  自行下载，本仓库不分发音频与视频产物。

## 工程备注

- `validate_teletubbies.py` 同时是共享"节目套件"（录制器、字幕/演员表叠加、旁白
  合成、`walk_to` 之外的手动节拍助手）；`racekit.walk_to` 提供带近邻斥力的有界
  转向行走，供竞速类场景替代 `stage.navigate`（其 A* 会把静止队友视作障碍导致
  目标点落在障碍圈内时死锁）。
- 转盘要点：MuJoCo 接触摩擦取两几何体的最大值，盘面需 `priority="1"` 才能覆盖
  鸭脚摩擦；盘体需显式小质量 + `gravcomp="1"`（轴承悬浮）避免自重压地摩擦吃掉
  电机扭矩；velstand 的零指令是世界系定点，"随盘共转"由摩擦携带（雕像模式），
  逆向行走指令超过其 ~0.9 rad/s 原地转向上限时表现为边被带转边倒走。
