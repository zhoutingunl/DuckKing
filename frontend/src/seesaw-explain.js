export const rewards={
 level:['2 × exp(−(倾角 / 3°)²)','板面越接近水平，得分越高。系数 2；倾角正值代表绿色前端下沉。'],
 balance:['1 × exp(−(重力合力矩 / 0.35 N·m)²)','用鸭子和配重的真实质心计算绕支点的重力合力矩。系数 1；奖励配平，不奖励固定站在中心。这是物理先验，不是电机力矩测量。'],
 upright:['0.25 × 直立度','直立度是身体向上轴与世界向上轴的点积，直立时接近 1。'],
 turning:['−0.1 × min(|角速度| / 12°/s, 2)','惩罚板面快速摆动。只回到零倾角但仍快速摇摆，不代表稳定。'],
 effort:['−0.06 × 是否走动','鼓励不需要调整时站定。这里惩罚的是走动指令，不是测量电机耗电。'],
 settle:['+0.25 × 是否站定且稳定','在水平、低角速度且有脚部支撑时，选择站定获得奖励。'],
 switch:['−0.03 × 是否切换动作','减少不必要的前后反复切换。它并不禁止必要的纠正动作。'],
 fall:['−15 × 是否失败','摔倒、身体触板、触地、脚部越界或长时间无支撑会终止本轮；到时未达标也扣分。'],
 success:['+25 × 是否完成','18 秒完整结束，前 2 秒后稳定时间占比至少 70%，末尾连续 0.5 秒稳定，才发放终局奖励。'],
};
export const controllers={trained:'训练后 · PPO',early:'本轮训练前',rule:'人工规则',baseline:'官方站定',center:'回中站定规则',manual:'你来控制'};
export function outcome(side){
 const p=side?.measurement??{},phase=side?.phase;
 if(phase==='failed'){
  const cause=side.result?.reason==='not_balanced'?
   side.result.balance_fraction>=.7?'最后 0.5 秒未连续稳定':'水平时间不足 70%':
   p.ground_contact?'已触地':p.upright<.65?'身体失稳':p.body_contact?'身体触板':
   p.edge_margin_m<0?'脚部越过板边缘':'失去支撑或物理异常';
  const detail=side.result?.reason==='not_balanced'&&Number.isFinite(side.result.balance_fraction)?
   `水平时间 ${(side.result.balance_fraction*100).toFixed(1)}% · 末尾稳定 ${(side.result.hold_seconds??0).toFixed(1)} s；`:'';
  return {badge:'失败 · '+cause,text:side.error??`${cause}。${detail}本侧物理已暂停。`};
 }
 if(phase==='success')return {badge:'成功 · 稳住了',text:'完整经历 18 秒，水平保持占比和末尾稳定条件均达标。'};
 if(phase==='cancelled')return {badge:'已暂停',text:'人为停止，仿真暂停；不代表板面已经自然停稳，不计成功。'};
 if(phase==='explored')return {badge:'',text:side.result?.reason==='exploration_limit'?'18 秒探索结束，请重置后再试；本轮不计成绩。':'这一小步结束，物理已暂停。可以继续探索或重置。'};
 if(phase==='running')return {badge:'',text:`${side.controller==='manual'?'手动探索':'平衡挑战'}进行中 · 水平时间 ${Math.round((p.balance_fraction??0)*100)}% · 连续 ${(side.result?.hold_seconds??0).toFixed(1)} s`};
 return {badge:'',text:'等待开始 · 板面将由鸭子的接触力带动。'};
}
