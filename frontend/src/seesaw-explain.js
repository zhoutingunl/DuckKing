export const rewards={
 dock:['4 × exp(−(距停靠中心 / 12 cm)²)','配重越靠近红色区中心，得分越高；奖励的是配重的位置，不是鸭子回中。'],
 brake:['1 × exp(−(距中心 / 6 cm)² − (配重速度 / 5 cm/s)²)','鼓励到站时减速。高速经过红色区不能获得完整得分。'],
 level:['0.5 × exp(−(倾角 / 3°)²)','保持板面温和；可以为了引导配重暂时倾斜，最终还要停稳。正倾角表示绿色前端下沉。'],
 balance:['1 × exp(−(重力合力矩 / 0.35 N·m)²)','用鸭子和配重的真实质心计算绕支点的重力合力矩。系数 1；奖励配平，不奖励固定站在中心。这是物理先验，不是电机力矩测量。'],
 upright:['0.25 × 直立度','直立度是身体向上轴与世界向上轴的点积，直立时接近 1。'],
 turning:['−0.1 × min(|角速度| / 12°/s, 2)','惩罚板面快速摆动。只回到零倾角但仍快速摇摆，不代表稳定。'],
 effort:['−0.06 × 是否走动','鼓励不需要调整时站定。这里惩罚的是走动指令，不是测量电机耗电。'],
 settle:['+0.25 × 是否站定且稳定','配重在区内低速、板面水平且有支撑时，选择站定获得奖励。'],
 switch:['−0.03 × 是否切换动作','减少不必要的前后反复切换。它并不禁止必要的纠正动作。'],
 fall:['−15 × 是否失败','摔倒、身体触板、触地、脚部越界或长时间无支撑会终止本轮；到时未达标也扣分。'],
 success:['+25 × 是否完成','18 秒无跌倒结束，最后连续 1 秒配重在 ±4 cm 内、速度低于 2.5 cm/s，板角和支撑均达标，才发放终局奖励。'],
};
export const controllers={trained:'训练后 · PPO',early:'本轮训练前',rule:'仅配平板面规则',baseline:'官方站定',center:'回中站定规则',manual:'你来控制',human:'你来控制 · 真人'};
export function humanStatus(s){
 if(s.mode==='explore')return `左鸭单独练习 · ${outcome(s.comparison).text}右侧保持站定。`;
 if(s.mode!=='duel')return '选择“真人 vs AI”开始；语音或按钮只控制左鸭。';
 const right=s.execution==='running'?'右侧继续自主控制':'右侧本轮已结束';
 if(s.comparison.execution!=='running')return `左鸭${outcome(s.comparison).badge||'本轮已结束'} · ${right}。重开挑战后可继续控制左鸭。`;
 const human=s.human_command;
 return `左鸭：${{hold:'站定',forward:'前进',backward:'后退'}[human.direction]}${human.remaining_seconds>0?`，剩余 ${human.remaining_seconds.toFixed(1)} 秒`:''} · ${right}`;
}
export function outcome(side){
 const p=side?.measurement??{},phase=side?.phase;
 if(phase==='failed'){
  const docking=side.result?.reason==='not_docked';
  const cause=docking?
   Math.abs(p.weight_position_m??side.result.weight_position_m)>=.04?'配重未进入红色区':
   Math.abs(p.weight_velocity_m_s??side.result.weight_velocity_m_s)>=.025?'配重经过但未刹住':'末尾未连续停稳 1 秒':
   p.ground_contact?'已触地':p.upright<.65?'身体失稳':p.body_contact?'身体触板':
   p.edge_margin_m<0?'脚部越过板边缘':'失去支撑或物理异常';
  const detail=docking?`末尾区内停稳 ${(side.result.hold_seconds??0).toFixed(1)} s；`:'';
  return {badge:'失败 · '+cause,text:side.error??`${cause}。${detail}本侧物理已暂停。`};
 }
 if(phase==='success')return {badge:'成功 · 配重已停靠',text:'完整经历 18 秒；最后 1 秒配重在红色区内低速，板面与支撑均达标。'};
 if(phase==='cancelled')return {badge:'已暂停',text:'人为停止，仿真暂停；不代表板面已经自然停稳，不计成功。'};
 if(phase==='explored')return {badge:'',text:side.result?.reason==='exploration_limit'?'18 秒探索结束，请重置后再试；本轮不计成绩。':'这一小步结束，物理已暂停。可以继续探索或重置。'};
 if(phase==='running')return {badge:'',text:`${side.controller==='manual'?'手动探索':'停靠挑战'}进行中 · 配重距中心 ${(Math.abs(p.weight_position_m??0)*100).toFixed(1)} cm · 区内停稳 ${(side.result?.hold_seconds??0).toFixed(1)} s`};
 return {badge:'',text:'等待开始 · 用脚步倾斜板面，引导自由配重滑动。'};
}

export function trainingMatches(report,revision){
 return report?.manifest?.contract==='seesaw-v4-passive-docking'
  &&typeof report.manifest.model_sha256==='string'
  &&(!revision||['','-red1'].some(paint=>revision==='seesaw-'+report.manifest.model_sha256.slice(0,24)+paint));
}
