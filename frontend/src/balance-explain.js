// Explanations are grouped by their real role: measurements, reward, optimizer.
export const rewardTerms={
 upright:['直立奖励','1 × u','u 是躯干竖直轴与世界竖直轴的点积；1 表示直立；前面的系数 1 是这一项的奖励权重。'],
 center:['中心奖励','2 × exp(−(d / 0.10)²)','d 是鸭子躯干在盘面坐标系里的离心距离，单位米。0.10 m 是奖励衰减尺度，不是成功半径；系数 2 提高靠近中心在总奖励中的比重。'],
 heading:['朝向奖励','1 × exp(−(ψ / 0.35)²)','ψ 是相对世界初始正前方的偏航角（rad）；0.35 rad 是奖励衰减尺度。第 2、3 关启用；第 1 关为 0；前面的系数 1 是朝向奖励权重。'],
 progress:['回中心进展','8 × (dₜ₋₁ − dₜ) / 0.1','每个任务控制步为 0.1 秒。靠近中心为正，远离为负；使用真实位置变化；系数 8 放大回中心速度的奖励。'],
 slip:['相对滑动惩罚','−0.15 × v_slip','接触点处，脚的速度减去盘面的速度，取盘面切向长度，单位 m/s。圆盘运动不等于脚打滑；系数 0.15 决定滑速惩罚力度。'],
 smooth:['动作突变惩罚','−0.025 × mean((aₜ − aₜ₋₁)²)','a 是三个归一化任务动作。抑制突然变化，系数 0.025 是平滑权重，不是关节扭矩上限。'],
 fall:['失败惩罚','−10 × I_failure','I_failure 在物理失败，或正常挑战结束却未达到全部条件时为 1；手动停止不算正常挑战结果；10 为单次失败扣分。'],
 success:['终点成功奖励','20 × I_success','只在完整挑战和减速结束、独立成功判定通过的最后一步给分；不按中途姿态推测成功；20 为完整成功的额外奖励。'],
};
export const hyperparameters={
 learning_rate:['学习率','每次优化更新参数的步长；本轮固定，曲线平坦是正常的。'],
 gamma:['折扣因子 γ','越接近 1，越重视稍后的奖励；不代表成功概率。'],
 gae_lambda:['优势估计 λ','广义优势估计在短期预测与较长轨迹之间的折中。'],
 clip_range:['裁剪范围 ε','限制概率比在目标函数中的收益增长；不是硬性限制所有权重变化。'],
 ent_coef:['探索系数 cₑ','熵奖励的系数，鼓励尝试不同动作。'],
 vf_coef:['价值系数 cᵥ','价值预测误差在总损失中的权重。'],
 n_steps:['每环境采样步数','每轮收集的任务步数；总采样量还要乘并行环境数。'],
 batch_size:['小批量大小','一次梯度更新使用多少条采样。'],
 n_epochs:['重复学习轮数','同一批经验重复学习的轮数；不会增加环境步数。'],
};
export const observationGroups=[
 [0,2,'目标位置','指向世界 XY 盘心，按身体偏航角旋转 / 0.10 m（水平面）'],
 [2,4,'朝向','sin(ψ)、cos(ψ)，避免跨过 ±π 时不连续'],
 [4,7,'重力方向','身体坐标系投影重力，三个无量纲分量'],
 [7,10,'身体角速度','身体坐标系，rad/s；来自 MuJoCo 状态'],
 [10,13,'身体线速度','身体坐标系，m/s'],
 [13,15,'圆盘倾角','滚转、俯仰，rad'],
 [15,18,'圆盘关节速度','滚转、俯仰、自转，rad/s'],
 [18,19,'脚部支撑','接触盘面的脚数 / 2'],
 [19,20,'身体高度','相对盘面法向高度 / 0.15 m'],
 [20,23,'上次动作','PPO 输出的三个反馈力度；负值按 0 执行'],
 [23,24,'已用时间','已知挑战总时长的比例；不是未来扰动信息'],
 [24,25,'停盘状态','当前是否已发出减速指令，0 或 1'],
];
export const metricLabels={
 'success_rate':['验证成功率','%'], 'mean_return':['验证回报','分'],
 'train/approx_kl':['新旧策略差异（近似 KL）',''],
 'train/clip_fraction':['进入裁剪区域的比例',''],
 'train/entropy_loss':['负熵（越低探索越多）',''],
 'train/value_loss':['价值预测损失',''],
 'train/policy_gradient_loss':['策略损失',''],
 'train/explained_variance':['价值解释方差',''],
 'train/learning_rate':['学习率',''], 'train/clip_range':['裁剪范围 ε',''],
 'parameters/action_std':['动作标准差（探索幅度）',''],
 'parameters/actor_l2':['策略隐藏层权重 L2 范数',''],
 'physics/radius':['采样平均离心距离','m'], 'physics/slip':['采样平均相对滑速','m/s'],
 'physics/upright':['采样平均直立度',''], 'physics/rpm':['采样平均盘速（带方向）','RPM'],
 ...Object.fromEntries(Object.entries(rewardTerms).map(([k,v])=>['reward/'+k,[v[0],'分/步']])),
 ...Object.fromEntries(Object.entries(hyperparameters).map(([k,v])=>['hyper/'+k,[v[0]+'（配置常量）','']])),
};
export const ppoSymbols={
 ratio:['概率比 ρₜ','π新(aₜ|sₜ) / π采样时(aₜ|sₜ)','相同观测与动作，新策略相对采样时策略的概率比。逐样本的概率比不在当前训练记录里；右侧教学滑块可计算一个假设样本。',null],
 advantage:['优势 Âₜ','Âₜ = Σₗ (γλ)ˡ δₜ₊ₗ；δₜ = rₜ + γV(sₜ₊₁) − V(sₜ)','优势表示实际经历比价值网络原先预计的好多少。终止边界有掩码；批内优势标准化。逐样本优势未导出，不用平均回报冒充。',null],
 epsilon:['裁剪范围 ε','clip(ρₜ, 1−ε, 1+ε)','PPO 在两个目标项之间取较小值；正负优势的裁剪方向不同。右侧滑块可以观察。','clip_range'],
 value:['价值损失系数 cᵥ','cᵥ × Lvalue','价值网络预测之后能拿到多少回报。该系数决定预测误差对总损失的影响；损失曲线单独展示。','vf_coef'],
 entropy:['探索系数 cₑ 与熵 H','−cₑ × H','优化器最小化总损失，减去熵项会鼓励保留探索。动作标准差也记录在优化曲线中。','ent_coef'],
};
export function clippedExample(ratio,advantage,epsilon){
 const clipped=Math.max(1-epsilon,Math.min(1+epsilon,ratio));
 return {raw:ratio*advantage,clipped:clipped*advantage,objective:Math.min(ratio*advantage,clipped*advantage)};
}
export function series(rows,key){
 return rows.filter(r=>Number.isFinite(r[key])&&Number.isFinite(r.steps)).map(r=>({step:r.steps,value:r[key],row:r}));
}

// A newly launched worker has no manifest while MuJoCo compiles. Keep the owned
// run selected so its preparing/failed state cannot disappear behind an old run.
export function compatibleRuns(list,level){
 return list.runs.filter(r=>r.level===level&&(r.contract==='balance-v4-gain-bodyframe'||(!r.contract&&r.id===list.active_run)));
}
