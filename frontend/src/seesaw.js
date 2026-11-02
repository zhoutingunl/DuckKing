import './site-nav.js';
import './style.css';
import './seesaw.css';
import {physicsView} from './physics-view.js';
import {createPhysicsModelLoader} from './model-loader.js';
import {setupRoom} from './room.js';
import {setupVoice} from './voice.js';
import {appURL,currentRoom} from './urls.js';
import {api} from './demo-runtime.js';
import {sceneStateFeed} from './scene-state-feed.js';
import {measurement,loadMetrics,afterFrame} from './experience.js';
import {drawChart} from './balance-chart.js';
import {controllers,outcome,humanStatus,humanMotion,rewards,trainingMatches} from './seesaw-explain.js';

const $=id=>document.getElementById(id),lifetime=new AbortController(),loader=createPhysicsModelLoader();
let ready=false,pending=false,initialized=false,closed=false,revision,viewer,baselineViewer,feed,voice,timer;
let lastState,settingRevision,traceKey='',trainingKey='',term='dock',lastPaint=0,refreshing=false,policyReady=false;
const notify=message=>{$('notice').textContent=message;$('notice').hidden=false};
function appendLog(text,label='实际执行'){
 const row=document.createElement('div');row.className='log-line';
 const tag=document.createElement('span');tag.className='log-label';tag.textContent=label;
 const body=document.createElement('span');body.textContent=text;row.append(tag,body);$('activity-log').append(row);
 while($('activity-log').children.length>80)$('activity-log').firstChild.remove();
}
function controls(){
 const active=lastState?.seesaw?.execution==='running'||lastState?.seesaw?.comparison?.execution==='running';
 $('prepare').disabled=!initialized||pending;$('prepare').textContent=!initialized?'正在准备页面…':ready?'跷跷板已准备 · 重新读取':'准备跷跷板';
 for(const id of ['start','reset'])$(id).disabled=!ready||pending||!feed?.fresh();
 $('start').disabled||=['trained','early'].includes($('controller').value)&&!policyReady;
 for(const id of ['controller','fixed-seed','match-mode','human-assist'])$(id).disabled=!initialized||pending||active;
 $('seed').disabled=!initialized||pending||active||!$('fixed-seed').checked;
 $('start').textContent=$('match-mode').value==='duel'?'开始 18 秒人机 PK':'开始 18 秒规则对照';
 $('seed-summary').textContent=$('fixed-seed').checked?'固定本轮初态 · 左右相同':'每轮自动随机 · 左右使用相同初态';
 const ended=['success','failed'].includes(lastState?.seesaw?.phase)||['success','failed'].includes(lastState?.seesaw?.comparison?.phase);
 for(const button of document.querySelectorAll('[data-direction]'))button.disabled=!ready||pending||active||ended||!feed?.fresh();
 const s=lastState?.seesaw,canStart=s?.phase==='idle'&&s?.comparison.phase==='idle'&&s.sim_time===0&&(!['trained','early'].includes($('controller').value)||policyReady)&&$('match-mode').value==='duel';
 for(const button of document.querySelectorAll('[data-human-direction]'))button.disabled=!ready||pending||!feed?.fresh()||!(s?.mode==='duel'&&s.comparison.execution==='running'||canStart&&button.dataset.humanDirection!=='hold');
 $('stop').disabled=!ready;
 $('connect-voice').disabled=!ready||pending||voice?.state==='disconnecting';
}
function showSide(side,prefix){
 const m=side.measurement,result=outcome(side);
 $(prefix+'-angle').textContent=m.angle_deg.toFixed(1)+'°';
 $(prefix+'-time').textContent=side.sim_time.toFixed(1)+' s';
 $(prefix+'-feet').textContent=m.contacts+' / 2';
 $(prefix+'-weight').textContent=(m.weight_position_m*100).toFixed(1)+' cm';
 $(prefix+'-status').textContent=result.text;
 const badge=$(prefix+'-result');badge.hidden=!result.badge;badge.textContent=result.badge;badge.dataset.phase=side.phase;
}
function rewardDetail(){
 const [formula,description]=rewards[term],value=lastState?.seesaw?.result?.reward_terms?.[term];
 $('reward-detail').textContent=`${formula}。${description} ${value==null?'等候实际采样。':`最新贡献：${value.toFixed(3)}`}`;
 for(const button of $('reward-equation').children)button.setAttribute('aria-pressed',String(button.dataset.term===term));
}
const observationNames=['前后位置 / 10 cm','横向位置 / 10 cm','前后实际速度 / 0.25 m/s','横向实际速度 / 0.15 m/s','朝向 / 0.4 rad','直立度','板面倾角 / 6°','板面角速度 / 12°/s','支撑脚数 / 2','上一动作：站定','上一动作：前进','上一动作：后退','区内停稳 / 1 s（上限 1）','已用仿真时间 / 18 s','配重实际位置 / 32 cm','配重实际速度 / 0.25 m/s','重力合力矩 / 1 N·m'];
const observationCells=observationNames.map(name=>{
 const row=document.createElement('tr'),label=document.createElement('td'),value=document.createElement('td');label.textContent=name;value.textContent='—';row.append(label,value);$('observations').append(row);return value;
});
function render(state){
 if(closed||!state?.seesaw)return;
 lastState=state;const s=state.seesaw,m=s.measurement,duel=s.mode==='duel'||s.phase==='idle'&&$('match-mode').value==='duel';
 viewer?.update(state);baselineViewer?.update(state.comparison.baseline);
 showSide(s,'trained');showSide(s.comparison,'baseline');
 const leftLabel=s.phase==='idle'&&$('match-mode').value==='duel'?'你来控制 · 左鸭':controllers[s.comparison.controller];$('baseline-label').textContent=leftLabel;baselineViewer?.setLabel(leftLabel);
 $('baseline-caption').textContent=duel?'语音 / 方向键 / 按钮':s.mode==='explore'?'单独练习 · 不计分':'忽略配重，只回中心';
 $('human-status').textContent=humanStatus(s);
 $('human-motion').textContent=humanMotion(s);
 $('policy-motion').textContent=s.execution==='running'?`${s.mode==='explore'?'官方零速步态':'右侧控制器'}：${['零速','前进','后退'][s.action]}指令 ${(s.command_m_s*100).toFixed(0)} cm/s`:'右侧等待开始或已结束 · 以实际物理状态判定成绩。';
 if(s.phase==='idle'&&$('match-mode').value==='duel')$('human-status').textContent='直接说“向前走”，或点击前进／后退开始 PK。';
 $('pair-explanation').textContent=duel?'左侧听你指挥，右侧自主行动。两侧同一初态、同一时钟，用相同停靠条件判定；语音识别期间仿真继续。方向不随视角改变。':s.mode==='explore'?'左侧单独练习，右侧保持站定；两侧物理同步推进，不计挑战成绩。方向不随视角改变。':'同一初态，不同脚步 → 不同板角 → 不同配重轨迹。规则对照时左侧只回中心站定。两侧均使用官方已训练步态，方向不随视角改变。';
 $('load-position').textContent=(m.weight_position_m*100).toFixed(1)+' cm';
 $('load-speed').textContent=(m.weight_velocity_m_s*100).toFixed(1)+' cm/s';
 $('load-torque').textContent=m.net_gravity_torque_nm.toFixed(2)+' N·m';
 $('load-description').textContent=`自由配重 ${Math.round(s.load.mass_kg*1000)} g · 初始 ${(s.load.start_position_m*100).toFixed(1)} cm · 无电机，轨迹由脚步改变`;
 $('load-progress').value=m.weight_position_m*100;
 $('dock-hold').textContent=(m.dock_hold_seconds??0).toFixed(1)+' / 1.0 s';
 $('weight-value').textContent=(m.weight_position_m*100).toFixed(1)+' cm';
 const travel=Math.abs(m.weight_velocity_m_s)<.005?'滑动缓慢':Math.abs(m.weight_position_m)<.04?'已入区，检查是否刹住':m.weight_position_m*m.weight_velocity_m_s<0?'正在靠近红色区':'正在远离红色区';
 $('weight-effect').textContent=`${travel} · ${Math.abs(m.weight_velocity_m_s*100).toFixed(1)} cm/s`;
 const label=s.phase==='idle'?'待开始':controllers[s.controller]??s.controller;
 $('trained-label').textContent=label;viewer?.setLabel(label);
 $('trained-caption').textContent=s.mode==='explore'?'右侧站定 · 观察左鸭练习':s.policy_steps!=null?`${s.policy_steps.toLocaleString()} 训练步`:'官方步态 + 任务指令';
 if(settingRevision!==s.command_revision){settingRevision=s.command_revision;$('seed').value=s.seed;if(s.phase!=='idle')$('human-assist').checked=!!s.human_command.assist_enabled;if(s.mode!=='explore'&&s.phase!=='idle'){$('match-mode').value=s.mode;$('controller').value=s.controller;}traceKey=''}
 $('action-value').textContent=s.execution==='running'?['站定','向绿色端前进','向赭色端后退'][s.action]:'暂停';
 $('speed-value').textContent=`${(s.command_m_s*100).toFixed(0)} cm/s 指令`;
 $('position-value').textContent=(m.position_m*100).toFixed(1)+' cm';
 $('angle-value').textContent=m.angle_deg.toFixed(1)+'°';
 $('torque-value').textContent=`接触力矩 ${m.contact_torque_nm.toFixed(2)} N·m`;
 const key=s.command_revision+':'+s.sim_time+':'+s.trace.length;
 if(key!==traceKey&&!document.hidden){traceKey=key;causalChart(s.trace);rewardDetail()}
 if(performance.now()-lastPaint>250){lastPaint=performance.now();state.observation.forEach((v,i)=>observationCells[i].textContent=v.toFixed(3))}
 $('trace-caption').textContent=s.mode==='duel'?'左侧真人 · 右侧自主 · 相同停靠标准':s.mode==='explore'?'左侧听你指挥 · 右侧站定，物理同步运行':'同一初态 · 不同动作改变配重轨迹';
 controls();
}
const svgNode=(name,attrs={})=>{const node=document.createElementNS('http://www.w3.org/2000/svg',name);for(const[k,v]of Object.entries(attrs))node.setAttribute(k,v);return node};
function causalChart(rows){
 const host=$('causal-chart');host.replaceChildren();
 if(!rows.length){const p=document.createElement('p');p.className='seesaw-note';p.textContent='开始后显示真实指令、位置和倾角。';host.append(p);return}
 const svg=svgNode('svg',{viewBox:'0 0 760 320',role:'img','aria-label':'同一仿真时间轴：指令 cm/s，位置 cm，配重 cm，倾角度'});
 const x=t=>110+t/18*630,lanes=[['velocity_cm_s','步速指令 cm/s',40,'#8c693f'],['position_cm','实际位置 cm',12,'#477d79'],['weight_position_cm','配重位置 cm',35,'#c35c36'],['angle_deg','实际倾角 °',7,'#243c36']];
 lanes.forEach(([key,label,max,colour],i)=>{
  max=Math.max(max,...rows.map(r=>Math.ceil(Math.abs(r[key]))),...(key==='angle_deg'?rows.map(r=>Math.ceil(Math.abs(r.baseline_angle_deg))):[]));
  const center=40+i*70,y=v=>center-v/max*25;
  const title=svgNode('text',{x:0,y:center-13});title.textContent=label;svg.append(title);
  const value=svgNode('text',{x:0,y:center+8});value.textContent=rows.at(-1)[key].toFixed(1);svg.append(value);
  svg.append(svgNode('line',{x1:110,x2:740,y1:center,y2:center,stroke:'#c9d6c5','stroke-dasharray':'3 4'}));
  if(key==='weight_position_cm')svg.append(svgNode('rect',{x:110,y:y(4),width:630,height:y(-4)-y(4),fill:'#dc343d',opacity:.2}));
  svg.append(svgNode('path',{d:rows.map((r,j)=>`${j?'L':'M'}${x(r.seconds)},${y(r[key])}`).join(' '),fill:'none',stroke:colour,'stroke-width':2}));
  if(['angle_deg','weight_position_cm'].includes(key))svg.append(svgNode('path',{d:rows.map((r,j)=>`${j?'L':'M'}${x(r.seconds)},${y(r['baseline_'+key])}`).join(' '),fill:'none',stroke:'#bd8748','stroke-width':1.5,'stroke-dasharray':'4 4'}));
  const plus=svgNode('text',{x:740,y:center-27,'text-anchor':'end'});plus.textContent=`±${max}`;svg.append(plus);
 });
 for(const t of [0,3,6,9,12,15,18]){const label=svgNode('text',{x:x(t),y:310,'text-anchor':'middle'});label.textContent=t+' s';svg.append(label)}
 host.append(svg);
}
function connectFeed(){
 feed=sceneStateFeed({readState:signal=>api('api/scenes/state',currentRoom,{signal}),
  onState:state=>{if(pending)return;if(state.backend?.scene==='seesaw')render(state.backend);else{ready=false;notify('本房间已切换场景，请重新准备跷跷板。');controls()}},
  onStatus:({mode,reason})=>{$('scene-connection').textContent=({connecting:'正在连接实际物理状态…',websocket:'实时连接 · MuJoCo 实际物理',http:'HTTP 接续实际状态 · 正在恢复实时连接',offline:'状态连接中断 · 画面保留上次记录'}[mode])+(mode==='offline'&&reason?' · '+reason:'');controls()},
 });
}
async function prepare(){
 if(pending||closed)return;pending=true;controls();$('notice').hidden=true;
 const experience=measurement('load'),metrics={};
 for(const p of document.querySelectorAll('.scene-placeholder')){p.hidden=false;p.textContent='正在加载官方 MicroDuck 与被动跷跷板…'}
 try{
  const signal=lifetime.signal,state=await api('api/seesaw/prepare',currentRoom,{body:{},signal});signal.throwIfAborted();
  if(revision!==state.backend.revision){
   const model=await loader(appURL('api/scenes/model.dkm.gz'),state.backend.revision,{signal,metrics});signal.throwIfAborted();
   viewer??=physicsView($('trained-viewport'),{label:'所选策略',onCameraChange:camera=>baselineViewer?.syncCamera(camera)});
   baselineViewer??=physicsView($('baseline-viewport'),{label:'未训练',onCameraChange:camera=>viewer?.syncCamera(camera)});
   viewer.load(model);baselineViewer.load(model);viewer.frameScene('seesaw');baselineViewer.frameScene('seesaw');revision=state.backend.revision;
  }else metrics.cache='memory';
  trainingKey='';void refreshTraining();
  render(state.backend);await afterFrame();signal.throwIfAborted();viewer.renderNow();baselineViewer.renderNow();ready=true;
  for(const p of document.querySelectorAll('.scene-placeholder'))p.hidden=true;
  experience.finish('completed',{...loadMetrics(metrics),scene_ms:Math.round(performance.now()-experience.started)},{cache:metrics.cache,scene:'seesaw'});
  if(!feed)connectFeed();else void feed.refresh();
  appendLog('跷跷板已准备。说“向前走”或点击前进／后退，开始真人与 PPO 对照。');
  document.querySelector('.seesaw-arena').scrollIntoView({block:'start'});
 }catch(error){experience.finish('failed');if(!closed){notify(error.message);for(const p of document.querySelectorAll('.scene-placeholder'))p.textContent='加载未完成，可重试。'}}
 finally{pending=false;if(!closed)controls()}
}
async function command(body,source='本地按钮'){
 if(closed||pending&&body.operation!=='stop')return;
 pending=true;controls();$('notice').hidden=true;$('command-feedback').textContent='正在提交请求…';
 try{
  const result=await api('api/seesaw/command',currentRoom,{body,signal:lifetime.signal});
  if(closed)return;
  $('command-feedback').textContent=body.operation==='stop'?'已停止；仿真暂停，板面自然速度不作归零。':body.operation==='reset'?'已重置两侧，可以重新探索。':'请求已受理，实际过程见两侧画面。';
  appendLog(`${['nudge','explore'].includes(body.operation)?{hold:'站定',forward:'前进',backward:'后退'}[body.direction]:{start:'开始对照',stop:'停止',reset:'重置'}[body.operation]} · ${result.mode==='duel'?'真人控制左鸭':result.mode==='explore'?'左侧单独练习':'本地物理'}，种子 ${result.seed}`,source);
 }catch(error){if(!closed)notify(error.message)}finally{pending=false;if(!closed){await feed?.refresh();controls()}}
}
function seed(){return !$('fixed-seed').checked?{}:$('seed').reportValidity()?{seed:Number($('seed').value)}:null}
$('prepare').addEventListener('click',prepare);
$('start').addEventListener('click',()=>{const value=seed();if(value!==null)void command({operation:'start',mode:$('match-mode').value,controller:$('controller').value,assist:$('human-assist').checked,...value})});
$('reset').addEventListener('click',()=>{const value=seed();if(value!==null)void command({operation:'reset',...value})});
$('stop').addEventListener('click',()=>{voice?.interrupt();void command({operation:'stop'})});
for(const button of document.querySelectorAll('[data-direction]'))button.addEventListener('click',()=>void command({operation:'explore',direction:button.dataset.direction,seconds:2,assist:$('human-assist').checked}));
function humanCommand(direction,source='本地按钮'){
 const button=document.querySelector(`[data-human-direction="${direction}"]`);
 if(!button||button.disabled||closed)return;
 const first=lastState?.seesaw?.phase==='idle',value=first?seed():{};if(value===null)return;
 void command({operation:'nudge',direction,seconds:2,...(first?{controller:$('controller').value,assist:$('human-assist').checked,...value}:{})},source);
}
for(const button of document.querySelectorAll('[data-human-direction]'))button.addEventListener('click',()=>humanCommand(button.dataset.humanDirection));
window.addEventListener('keydown',event=>{
 const direction={ArrowLeft:'forward',ArrowRight:'backward',ArrowDown:'hold'}[event.key];
 const target=event.target;
 if(!direction||closed||event.defaultPrevented||event.isComposing||event.altKey||event.ctrlKey||event.metaKey||event.shiftKey||target?.isContentEditable||target?.closest?.('input,textarea,select,[role="textbox"]'))return;
 const button=document.querySelector(`[data-human-direction="${direction}"]`);
 if(!button||button.disabled)return;
 event.preventDefault();
 if(!event.repeat)humanCommand(direction,'方向键');
},{signal:lifetime.signal});
$('controller').addEventListener('change',controls);
 $('fixed-seed').addEventListener('change',controls);
 $('match-mode').addEventListener('change',()=>{if(lastState)render(lastState);else controls()});
$('reset-camera').addEventListener('click',()=>{viewer?.reset();baselineViewer?.reset()});
$('clear-log').addEventListener('click',()=>$('activity-log').replaceChildren());
for(const [key,[formula]] of Object.entries(rewards)){const b=document.createElement('button');b.textContent=formula;b.dataset.term=key;b.addEventListener('click',()=>{term=key;rewardDetail()});$('reward-equation').append(b)}
async function refreshTraining(){
 if(closed||document.hidden||refreshing)return;refreshing=true;
 try{
  const {report}=await api('api/seesaw/training',currentRoom,{signal:lifetime.signal});
  if(closed)return;const key=JSON.stringify(report);if(key===trainingKey)return;trainingKey=key;
  const compatible=trainingMatches(report,revision);
  policyReady=report?.phase==='completed'&&compatible;controls();
  if(!compatible){
   $('training-status').textContent=report?'这份训练记录属于其他物理任务，不能作为当前停靠成绩；可手动探索。':'自由配重停靠策略尚未完成评估；可选人工规则或手动探索。';
   for(const id of ['training-gate','policy-selection','training-evidence','success-chart','return-chart','optimizer-chart','test-results'])$(id).replaceChildren();
   return;
  }
  const phases={training:'CPU 训练中',testing:'独立测试中',completed:'训练完成',cancelled:'训练已取消',failed:'训练失败'};
  $('training-status').textContent=`${phases[report.phase]??report.phase} · 本轮 ${report.steps.toLocaleString()} 步 · 墙钟 ${(report.elapsed_s/60).toFixed(1)} 分钟 · 单线程 CPU · ${String(report.platform??'环境未记录').startsWith('macOS')?'macOS 实测；跨平台回放可能不同':String(report.platform??'环境未记录')}`;
  const gate=report.converged_at,init=report.initialization;
  const origin=init?.kind==='passive_docking_transfer'?` 本轮继承上一阶段 ${init.source_steps.toLocaleString()} 步的任务 PPO，在无配重电机的新任务中学习引导滑动和制动；不是从随机策略开始。`:'';
  $('training-gate').textContent=gate?`连续两次验证 ≥18/20：${gate.steps.toLocaleString()} 步，${(gate.elapsed_s/60).toFixed(1)} 分钟。最终测试另用 100 个未见种子。${origin}`:'尚未达到连续两次验证 ≥18/20 的预设收敛门槛。曲线显示实际成绩，不把回报上涨当作成功。'+origin;
  $('policy-selection').textContent=report.selected_steps==null?'尚未选择可用 checkpoint。':`“训练后 PPO”选项使用验证最优 checkpoint：${init?.source_steps?`继承 ${init.source_steps.toLocaleString()} ＋ 本轮 ${(report.selected_phase_steps??0).toLocaleString()}`:report.selected_steps.toLocaleString()} 环境步。训练越久不一定更好，不直接使用最后一次更新。`;
  drawChart($('success-chart'),report.metrics,'success_rate');drawChart($('return-chart'),report.metrics,'mean_return');
  drawChart($('optimizer-chart'),report.metrics.map(r=>({...r,approx_kl:r.optimizer?.approx_kl})),'approx_kl');
  $('test-results').replaceChildren();
  for(const [key,label] of [['test','PPO'],['center_test','回中站定规则'],['baseline_test','官方站立基线'],['rule_test','仅配平板面规则']]){
   const r=report[key];if(!r)continue;const p=document.createElement('p');p.textContent=`${label}：${r.successes} / ${r.episodes} 成功 · 平均绝对倾角 ${r.mean_abs_angle_deg.toFixed(2)}° · 末尾距停靠中心 ${(100*r.mean_final_dock_error_m).toFixed(1)} cm`;p.title=`Wilson 95% 区间：${r.ci95.map(v=>(v*100).toFixed(1)+'%').join('–')}`;$('test-results').append(p);
  }
  const {metrics,test,baseline_test,center_test,rule_test,...identity}=report;$('training-evidence').textContent=JSON.stringify(identity,null,2);
 }catch(error){if(!closed)$('training-status').textContent='读取训练记录失败：'+error.message}finally{refreshing=false}
}
window.addEventListener('pagehide',()=>{closed=true;lifetime.abort();clearInterval(timer);feed?.close();viewer?.dispose();baselineViewer?.dispose()},{once:true});
window.addEventListener('pageshow',event=>{if(event.persisted)location.reload()});
document.addEventListener('visibilitychange',()=>{if(!document.hidden){traceKey='';if(lastState)render(lastState)}});
window.addEventListener('duckking-voice-state',controls);
controls();rewardDetail();causalChart([]);
try{await setupRoom();if(!closed){voice=setupVoice({appendLog,notify,endpoint:'scene-voice',cloudOnly:true});initialized=true;controls();await refreshTraining();if(!closed)timer=setInterval(refreshTraining,5000)}}catch(error){notify(error.message)}
