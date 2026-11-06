export const actionLabels={
  backward:'后退',strafe_left:'左横移',strafe_right:'右横移',shake_head:'摇头',tilt_head:'歪头',nod:'点头',walk:'前进',turn_left:'左转',turn_right:'右转',stop:'停止',reset:'重置场景',flash_step:'闪身步',bear_shake:'狗熊哆嗦毛',
  look_left:'向左看',look_right:'向右看',look_forward:'向前看',look_down:'低头看',sit:'坐下',stand:'站起来',
  scene_skills:'动作练习场',scene_rollers:'轮滑小鸭',scene_ball:'单鸭踢球',scene_duo:'双鸭互动',scene_carry:'嘴部搬运',scene_table:'桌上合唱',scene_seated:'坐姿轮唱',scene_stage:'四鸭舞台',
  roulade:'前滚翻',ground_pick:'低头啄取',skate:'向前滑行',roller_crouch:'轮滑下蹲',yawn:'打个哈欠',idle_on:'开启自然待机',idle_off:'关闭自然待机',
  pick_up:'用嘴夹起',carry:'夹持搬运',put_down:'放下物品',kick_left:'左脚踢球',kick_right:'右脚踢球',ball_prepare_left:'左脚摆球',ball_prepare_right:'右脚摆球',ball_shoot_left:'左脚射门',ball_shoot_right:'右脚射门',
  find_companion:'发现同伴',duo_walk:'双鸭一起走',collide:'相向碰面',chorus:'同步合唱',table_show:'桌上合唱表演',seated_show:'坐姿轮唱表演',seated_ready:'准备坐姿',seated_solo:'单鸭独唱',stage_gather:'集合列队',stage_roll:'四鸭翻滚',stage_dance:'四鸭共舞',stage_poke:'轻推小鸭',
};
export const resultLabels={completed:'已完成',failed:'未完成',cancelled:'已取消',running:'进行中',paused:'已暂停'};
export function actionEventText(event){
  const raw=String(event.text??'');
  const scene=raw.match(/\bscene_[a-z_]+\b/)?.[0];
  if(scene&&actionLabels[scene]){
    const result=event.kind==='result'?(event.status==='completed'?'场景就绪':`场景准备${resultLabels[event.status]??'未完成'}`):'正在准备场景';
    return `${result} · ${actionLabels[scene]}`;
  }
  return raw.replace(/\b[a-z][a-z_]*\b/g,key=>actionLabels[key]??resultLabels[key]??key);
}
export function appendActionDetails(row,raw){
  const details=document.createElement('details');details.className='action-diagnostics';
  const summary=document.createElement('summary');summary.textContent='诊断详情';summary.setAttribute('data-ui-text','');
  const text=document.createElement('code');text.textContent=raw;
  details.append(summary,text);row.append(details);
}
