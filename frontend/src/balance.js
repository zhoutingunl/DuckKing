import {createLoadingState} from './loading-state.js';
import './site-nav.js';
import './style.css';
import './balance.css';
import {physicsView} from './physics-view.js';
import {createPhysicsModelLoader} from './model-loader.js';
import {setupVoice} from './voice.js';
import {setupRoom} from './room.js';
import {appURL,currentRoom} from './urls.js';
import {sceneStateFeed} from './scene-state-feed.js';
import {api} from './demo-runtime.js';
import {rewardTerms,hyperparameters,observationGroups,metricLabels,ppoSymbols,clippedExample,compatibleRuns,balanceFailureReason,balanceOutcome,balanceHoldTime} from './balance-explain.js';
import {drawChart} from './balance-chart.js';
import {measurement,loadMetrics,afterFrame} from './experience.js';

const $=id=>document.getElementById(id),titles=['跟着圆盘站稳','转盘转，我不转','从边缘回到中心'];
let level=1,observedLevel=1,levelChosen=false,viewer,baselineViewer,lastBackend,ready=false,loading=false,selectedRun='',records=[],detail=null,sample=null,sampleStep=null,term='center',stateFeed,timer,closed=false,revision=null;
let lastStateKey='',lastObservation=null,lastObservationAt=0,detailKey=null,optionsKey='';
let settingsKey='',seedEdited=false,durationEdited=false,preparing=false;
let needsSwitch=false,prepareFailed=false;
const lifetime=new AbortController();
window.addEventListener('pagehide',()=>{
 closed=true;lifetime.abort();clearInterval(timer);stateFeed?.close();viewer?.dispose();baselineViewer?.dispose();
},{once:true});
window.addEventListener('pageshow',event=>{if(event.persisted)location.reload()});
const loader=createPhysicsModelLoader();
const loadFeedback=[...document.querySelectorAll('.balance-placeholder')].map(createLoadingState);let prepareAbort;
const notify=text=>{$('notice').hidden=false;$('notice').textContent=text};
function appendLog(text,label='实际执行'){
 const row=document.createElement('div');row.className='log-line';const tag=document.createElement('span');tag.className='log-label';tag.textContent=label;const body=document.createElement('span');body.textContent=text;row.append(tag,body);$('activity-log').append(row);while($('activity-log').children.length>80)$('activity-log').firstChild.remove();
}
await setupRoom();
const voice=setupVoice({appendLog,notify,endpoint:'scene-voice',cloudOnly:true});
function controls(){
 $('start-challenge').disabled=!ready||loading||!stateFeed?.fresh();$('stop-balance').disabled=!ready;
 $('prepare-balance').disabled=loading;$('prepare-balance').textContent=preparing?'正在准备圆盘…':needsSwitch?'切换为圆盘':prepareFailed?'重试准备圆盘':ready?'圆盘已准备 · 重新加载':'准备圆盘';
 document.querySelectorAll('[data-level]').forEach(b=>{b.disabled=loading;b.setAttribute('aria-pressed',String(Number(b.dataset.level)===level))});
 for(const id of ['controller','fixed-seed','challenge-duration'])$(id).disabled=loading;
 $('challenge-seed').disabled=loading||!$('fixed-seed').checked;
 $('connect-voice').disabled=(!ready||loading)&&!['connecting','recovering','interrupting','ready','listening','thinking','speaking'].includes(voice.state)||voice.state==='disconnecting';
}
window.addEventListener('duckking-voice-state',controls,{signal:lifetime.signal});
function validSettings(){return $('challenge-duration').reportValidity()&&(!$('fixed-seed').checked||$('challenge-seed').reportValidity())}
function formSettings(){return {...($('fixed-seed').checked?{seed:Number($('challenge-seed').value)}:{}),duration_seconds:Number($('challenge-duration').value)}}
$('fixed-seed').addEventListener('change',controls);
function durationNote(){
 const input=$('challenge-duration'),seconds=Number(input.value);
 $('duration-note').textContent=input.validity.valid?`${seconds} 秒仿真：${seconds-3} 秒扰动＋3 秒减速；失稳会提前结束。训练曲线使用原13秒严格标准，与演示通关条件不同。`:'请输入 6–33 秒的整数，包含最后 3 秒减速。';
 $('center-deadline').textContent=input.validity.valid?`若本轮运行${seconds}秒，最迟须在${seconds-1}秒进入目标区，并一直保持到结束。`:'';
}
for(const id of ['challenge-seed','challenge-duration'])$(id).addEventListener('input',()=>{
 if(id==='challenge-seed')seedEdited=true;else{durationEdited=true;durationNote()}
});
durationNote();
function renderSide(b,prefix,status){
 const r=b.result,a=b.aftermath,current=a?.measurements??r,terminal=['completed','failed','cancelled'].includes(b.phase),settling=a?.phase==='running';
 $(prefix+'-time-label').textContent=terminal?(b.phase==='failed'?'判定失败时刻':'结束时刻'):'本侧仿真时间';
 $(prefix+'-rpm-label').textContent=terminal&&!settling?'定格时盘速':'实际盘速';
 $(prefix+'-rpm').textContent=current?`${current.rpm.toFixed(2)} RPM`:'—';
 $(prefix+'-radius').textContent=current?`${(current.radius*100).toFixed(1)} cm`:'—';
 $(prefix+'-contact').textContent=current?`${current.contacts} / 2 脚`:'—';
 $(prefix+'-time').textContent=`${b.sim_time.toFixed(1)} s`;
 $(prefix+'-goal-fact').hidden=b.level===1;
 $(prefix+'-goal-label').textContent=b.level===3?'目标区内连续保持（需≥1秒）':'朝向达标率（需≥85%）';
 $(prefix+'-goal-value').textContent=b.level===3?`${balanceHoldTime(r?.center_hold)} s`:Number.isFinite(r?.heading_fraction)?`${(r.heading_fraction*100).toFixed(1)}%`:'—';
 const reason=balanceFailureReason(r,b.level);
 const phases={idle:'等待指令',running:'挑战中',stopping:'正在减速停盘',completed:'挑战成功',failed:'挑战失败',cancelled:'已停止 · 人为干预不计成功'};
 const physical=a?` · ${settling?'后续物理展示中':'画面已定格'} ${a.seconds.toFixed(1)} s（不计成绩）`:(terminal?' · 画面已定格':'');
 $(status).textContent=`${phases[b.phase]??b.phase}${reason?' · '+reason:''}${r?` · ${terminal?'判分时':''}脚边缘余量 ${(r.rim_margin*100).toFixed(1)} cm`:''}${physical}${b.error?' · '+b.error:''}`;
 $(status).dataset.phase=b.phase;
 const outcome=balanceOutcome(b),banner=$(prefix+'-result');banner.hidden=!outcome;
 if(outcome){banner.dataset.state=outcome.state;banner.querySelector('strong').textContent=outcome.title;banner.querySelector('span').textContent=outcome.detail}
}
function updateLabels(controller){
 const text={trained:'训练后',early:'训练前',baseline:'未训练'}[controller];
 $('trained-label').textContent=text;
 $('trained-caption').textContent={trained:'PPO＋官方步态',early:'任务网络 0 步＋官方步态',baseline:'官方步态基线'}[controller];
 viewer?.setLabel(text);
}
function renderState(state){
 const b=state?.balance;if(!b||closed)return;
 const key=state.revision+JSON.stringify(b);if(key===lastStateKey)return;lastStateKey=key;lastBackend=b;
 const nextSettings=JSON.stringify([state.revision,b.command_revision,b.level,b.seed,b.duration_seconds]);
 if(settingsKey!==nextSettings){
  settingsKey=nextSettings;$('challenge-seed').value=b.seed;$('challenge-duration').value=b.duration_seconds??13;
  if(b.phase!=='idle')$('controller').value=b.controller;
  seedEdited=durationEdited=false;durationNote();
 }
 $('seed-summary').textContent=b.seed_info?`本轮种子 ${b.seed} · 俯视${b.seed_info.rotation==='counterclockwise'?'逆时针':'顺时针'}旋转 · 盘面摩擦系数 ${b.seed_info.friction.toFixed(2)}`:'';
 if(b.level!==observedLevel){observedLevel=b.level;level=b.level;selectedRun='';sampleStep=null;controls();void refresh()}
 viewer?.update(state);renderSide(b,'disc','challenge-status');
 const comparison=b.comparison,baseline=state.comparison?.baseline;
 if(baseline){baselineViewer?.update(baseline);renderSide(baseline.balance,'baseline','baseline-status')}
 updateLabels(b.phase==='idle'?$('controller').value:b.controller);
 const phases={idle:'等待同时开始',running:'同步挑战中',stopping:'两侧正在减速',settling:'判分结束 · 正在显示后续物理过程',completed:'对照结束',cancelled:'对照已停止',failed:'对照计算异常，物理已暂停'};
 const frozen=[['左侧',baseline?.balance],['右侧',b]].filter(([,side])=>side?.phase==='failed').map(([name,side])=>`${name} ${side.sim_time.toFixed(1)} s 判定失败${side.aftermath?.phase==='running'?'（物理继续）':'（已定格）'}`);
 $('comparison-status').textContent=(comparison?.enabled?`${phases[comparison.phase]??comparison.phase} · 共同进度 ${comparison.sim_time.toFixed(1)} / ${b.duration_seconds??13} s · 种子 ${b.seed} · 左侧官方基线 / 右侧${$('trained-label').textContent}`:'本轮仅运行右侧策略，左侧未参与')+(frozen.length?' · '+frozen.join('；'):'');
 $('heading-guide-note').textContent=b.level===2?'圆盘外地面的蓝色标记表示目标朝向。拖动视角只改变观看位置，不改变目标方向。':b.level===3?'盘面红色圆区是目标范围：半径8 cm，以躯干投影计；标记随盘面倾斜。进入后须连续保持1秒，离开即重新计时。':'本关允许随盘转动，不要求保持固定朝向。';
 $('challenge-goal').textContent=b.goal?.description??'正在读取本关验收条件…';
 $('center-deadline').hidden=b.level!==3;
 const name={baseline:'官方步态基线',early:'训练步数 0 的任务网络＋官方步态',trained:'已评估反馈力度 PPO＋官方步态'}[b.controller];
 $('controller-source').textContent=`右侧：${b.phase==='idle'?'等待本轮策略加载':name}${b.policy_steps!=null&&b.phase!=='idle'?` · ${b.policy_steps.toLocaleString()} 训练步`:''}。${comparison?.enabled?'同一仿真时钟，独立计算两侧物理。':''}训练过程见下方记录。`;
 $('scene-title').textContent=`第 ${b.level} 关 · ${b.title}`;
 if(state.observation){lastObservation=[state.observation,state.task_action];updateObservation(b.execution!=='running')}
}
async function prepare({replace=false}={}){
 if(loading||closed||!validSettings())return;
 const inputs=formSettings(),requested={...(levelChosen?{level}:{}),...(seedEdited&&inputs.seed!=null?{seed:inputs.seed}:{}),...(durationEdited?{duration_seconds:inputs.duration_seconds}:{})};
 loading=preparing=true;prepareFailed=false;controls();$('notice').hidden=true;
 prepareAbort?.abort();prepareAbort=new AbortController();const signal=AbortSignal.any([lifetime.signal,prepareAbort.signal]);
 const sessions=loadFeedback.map(f=>f.begin({phase:'backend',cancel:()=>prepareAbort.abort(),retry:()=>prepare({replace:needsSwitch}),retryLabel:'重新准备圆盘'}));
 const progress=value=>sessions.forEach(s=>s.progress(value));
 const experience=measurement('load'),metrics={};
 try{
  let state=await api(`api/balance/prepare?replace=${replace}`,currentRoom,{body:{},signal});signal.throwIfAborted();needsSwitch=false;
  if(Object.entries(requested).some(([key,value])=>state.backend.balance[key]!==value)){
   await api('api/balance/command',currentRoom,{body:{operation:'select',...requested},signal});
   state=await api('api/scenes/state',currentRoom,{signal});signal.throwIfAborted();
  }
  if(requested.level!=null)observedLevel=level=requested.level;
  if(!state.backend.comparison?.baseline)throw Error('服务尚未支持左右对照，请更新并重启本地后端。');
  if(revision!==state.backend.revision){
   const data=await loader(appURL('api/scenes/model.dkm.gz'),state.backend.revision,{signal,metrics,progress});signal.throwIfAborted();progress({phase:'assemble'});const started=performance.now();
   if(!viewer)viewer=physicsView($('physics-viewport'),{label:'训练后',onCameraChange:state=>baselineViewer?.syncCamera(state)});
   if(!baselineViewer)baselineViewer=physicsView($('baseline-viewport'),{label:'未训练',onCameraChange:state=>viewer?.syncCamera(state)});
   viewer.load(data);baselineViewer.load(data);viewer.frameScene('balance');baselineViewer.frameScene('balance');
   metrics.assemble_ms=performance.now()-started;revision=state.backend.revision;
  }else metrics.cache='memory';
  lastStateKey='';renderState(state.backend);progress({phase:'draw'});const firstFrame=performance.now();await afterFrame();signal.throwIfAborted();viewer.renderNow();baselineViewer.renderNow();await afterFrame();signal.throwIfAborted();metrics.first_frame_ms=Math.round(performance.now()-firstFrame);sessions.forEach(s=>s.ready());ready=true;
  experience.finish('completed',{...loadMetrics(metrics),scene_ms:Math.round(performance.now()-experience.started)},{cache:metrics.cache,scene:'balance'});
  if(!stateFeed)connect();else void stateFeed.refresh();appendLog('左右圆盘已准备：左侧官方基线，右侧所选策略；按钮或灵矽口令均可同时发起挑战。');
 }catch(e){experience.finish(signal.aborted||e.code==='scene_conflict'?'cancelled':'failed');if(!closed){ready=false;needsSwitch=e.code==='scene_conflict';prepareFailed=!needsSwitch;if(signal.aborted)sessions.forEach(s=>s.cancelled());else{notify(e.message);sessions.forEach(s=>s.fail(e))}}}finally{loading=preparing=false;if(!closed)controls()}
}
function connect(){
 if(closed)return;
 stateFeed=sceneStateFeed({
  readState:signal=>api('api/scenes/state',currentRoom,{signal}),
  onState:state=>{
   // Preparing a new world briefly exposes its default level before the
   // requested settings are restored. Do not let that frame overwrite them.
   if(preparing)return;
   if(state.backend?.scene==='balance')renderState(state.backend);
   else{ready=false;needsSwitch=!!state.backend;notify('本房间已切到其他场景。可切换回圆盘，或新建房间。')}
   controls();
  },
  onStatus:({mode,reason})=>{
   const labels={connecting:'正在连接物理状态…',websocket:'实时连接正常 · 两侧实际物理状态',http:'已通过 HTTP 接续实际物理状态 · 正在恢复实时连接',offline:'实时状态不可用 · 画面保留上次记录，恢复后可开始；仍可尝试停盘'};
   $('scene-connection').textContent=labels[mode]+(mode==='offline'&&reason?' · '+reason:'');
   $('scene-connection').dataset.transport=mode;controls();
  },
 });
}
async function command(body){
 $('command-feedback').textContent='正在提交请求…';
 try{
  const result=await api('api/balance/command',currentRoom,{body,signal:lifetime.signal});
  if(closed)return;
  $('command-feedback').textContent=`${{start:'挑战',stop:'停盘',select:'设置'}[body.operation]??'操作'}请求已受理 · 进度见对照画面`;
  appendLog(`第 ${result.level} 关 · ${result.phase} · ${result.controller}`,'本地排练');void stateFeed?.refresh();return result;
 }catch(e){if(!closed){$('command-feedback').textContent='请求未确认，请查看提示及实际进度。';notify(e.message)}}
}
$('prepare-balance').addEventListener('click',()=>prepare({replace:needsSwitch}));
$('start-challenge').addEventListener('click',async()=>{
 if(loading||!ready||!stateFeed?.fresh()||!validSettings())return;
 loading=true;controls();$('notice').hidden=true;
 try{await command({operation:'start',compare:true,level,controller:$('controller').value,...formSettings(),...(selectedRun?{run:selectedRun}:{})})}finally{loading=false;controls()}
});
$('stop-balance').addEventListener('click',()=>{void voice.interrupt();void command({operation:'stop'})});
window.addEventListener('keydown',e=>{if(e.code==='Escape'&&ready)void command({operation:'stop'})});
$('reset-camera').addEventListener('click',()=>{viewer?.reset();baselineViewer?.reset()});
$('controller').addEventListener('change',()=>{if(!lastBackend||lastBackend.phase==='idle')updateLabels($('controller').value)});
$('clear-log').addEventListener('click',()=>$('activity-log').replaceChildren());
for(const button of document.querySelectorAll('[data-level]'))button.addEventListener('click',async()=>{
 if(loading||!validSettings())return;level=Number(button.dataset.level);levelChosen=true;controls();
 if(ready)await command({operation:'select',level,...formSettings()});
 if(!ready)$('scene-title').textContent=`待挑战第 ${level} 关 · ${titles[level-1]}`;
 selectedRun='';sampleStep=null;await refresh();
});
function options(select,entries){const previous=select.value;select.replaceChildren();for(const[value,label]of entries){const o=document.createElement('option');o.value=value;o.textContent=label;select.append(o)}if(entries.some(([value])=>value===previous))select.value=previous}
options($('optimizer-metric'),Object.entries(metricLabels).filter(([k])=>k.startsWith('train/')||k.startsWith('parameters/')||k.startsWith('hyper/')).map(([k,v])=>[k,v[0]]));
$('optimizer-metric').value='parameters/action_std';
options($('physics-metric'),Object.entries(metricLabels).filter(([k])=>k.startsWith('physics/')||k.startsWith('reward/')).map(([k,v])=>[k,v[0]]));
function termInfo(){
 let [title,equation,description]=rewardTerms[term];
 if(detail?.manifest&&(detail.manifest.reward_version??1)===1){
  if(term==='heading'){equation='1 × cos(ψ)';description='此历史记录使用第一版朝向奖励：朝向误差的余弦。第 1 关为 0。'}
  if(term==='fall')description='此历史记录只惩罚物理失败，不另惩罚终点未达标。';
  if(term==='success'){equation='此轮未启用';description='这份历史记录没有终点成功奖励，不能用当前公式解释其回报。'}
 }
 $('term-title').textContent=title;$('term-equation').textContent=equation;$('term-description').textContent=description;
 const value=sample?.['reward/'+term];$('term-value').textContent=Number.isFinite(value)?`${value.toFixed(4)} 分 / 任务步`:'该采样点没有记录此项';
 document.querySelectorAll('[data-term]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.term===term)));
 $('formula-sample').textContent=sample?`当前查看第 ${sample.steps.toLocaleString()} 步的采样均值。系数固定；奖励分量随经历改变。`:'等待训练采样；系数说明现在即可查看。';
}
for(const[key,[label]]of Object.entries(rewardTerms)){
 if($('reward-equation').children.length)$('reward-equation').append(document.createTextNode(' + '));
 const b=document.createElement('button');b.dataset.term=key;b.textContent=label;b.addEventListener('click',()=>{term=key;termInfo()});$('reward-equation').append(b);
}
function renderParameters(){
 $('parameter-table').replaceChildren();for(const[key,[label,description]]of Object.entries(hyperparameters)){
  const tr=document.createElement('tr');for(const text of [label,description,detail?.manifest?.hyperparameters?.[key]??'尚未选择记录']){const td=document.createElement('td');td.textContent=String(text);tr.append(td)}$('parameter-table').append(tr);
 }
 const manifest=detail?.manifest;
 for(const[label,description,value]of [
  ['训练奖励缩放','仅影响优化器使用的奖励尺度；验证回报与奖励分量曲线仍用原始单位。',manifest?(manifest.optimization_reward_scale??1):'尚无记录'],
  ['初始探索标准差','高斯动作分布的初始标准差；后续数值会学习变化，见优化曲线。',manifest?.policy_kwargs?Math.exp(manifest.policy_kwargs.log_std_init).toFixed(3):'尚无记录'],
  ['并行采样环境','独立 CPU 采样进程数；梯度优化使用 1 个 Torch 线程。',manifest?.envs??'尚无记录'],
 ]){const tr=document.createElement('tr');for(const text of [label,description,value]){const td=document.createElement('td');td.textContent=String(text);tr.append(td)}$('parameter-table').append(tr)}
}
const observationDetails=$('observation-table').closest('details');
const observationCells=observationGroups.map(([, ,title,explanation])=>{const tr=document.createElement('tr');for(const text of [title,explanation,'等待物理场景']){const td=document.createElement('td');td.textContent=text;tr.append(td)}$('observation-table').append(tr);return tr.lastChild});
function updateObservation(force=false){
 if(closed||!lastObservation||!observationDetails.open||document.hidden)return;
 if(!force&&performance.now()-lastObservationAt<200)return;
 lastObservationAt=performance.now();renderObservation(...lastObservation);
}
observationDetails.addEventListener('toggle',()=>updateObservation(true));
document.addEventListener('visibilitychange',()=>{if(!document.hidden){updateObservation(true);void refresh()}});
function renderObservation(values=[],actions=[]){
 observationGroups.forEach(([start,end],i)=>{const text=values.length?values.slice(start,end).map(v=>v.toFixed(3)).join(' / '):'等待物理场景';if(observationCells[i].textContent!==text)observationCells[i].textContent=text});
 $('action-values').textContent=actions.length?`PPO 反馈力度 g：${values.slice(20,23).map(v=>Math.max(0,v).toFixed(3)).join(' / ')}。实际任务指令：前后 ${actions[0].toFixed(3)} m/s；横移 ${actions[1].toFixed(3)} m/s；转向 ${actions[2].toFixed(3)} rad/s。限幅 ±0.18 / ±0.12 / ±1.8，另有每步变化限幅。`:'等待物理场景';
}
function charts(){
 const rows=(detail?.metrics??[]).map(row=>({...row,...Object.fromEntries(Object.entries(detail?.manifest?.hyperparameters??{}).map(([k,v])=>['hyper/'+k,v]))}));const select=row=>{if(row.kind==='update'){sampleStep=row.steps;sample=row;termInfo()}};
 drawChart($('success-chart'),rows,'success_rate',select);drawChart($('return-chart'),rows,'mean_return',select);
 drawChart($('optimizer-chart'),rows,$('optimizer-metric').value,select);drawChart($('physics-chart'),rows,$('physics-metric').value,select);
}
function symbolInfo(name){
 const[title,equation,description,key]=ppoSymbols[name];$('ppo-symbol-title').textContent=title;$('ppo-symbol-equation').textContent=equation;$('ppo-symbol-description').textContent=description;
 $('ppo-symbol-value').textContent=key?`本次配置：${detail?.manifest?.hyperparameters?.[key]??'尚无记录'}`:'此项逐样本值未导出；不伪造实测值。';
 document.querySelectorAll('[data-ppo]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.ppo===name)));
}
for(const button of document.querySelectorAll('[data-ppo]'))button.addEventListener('click',()=>symbolInfo(button.dataset.ppo));
for(const id of ['optimizer-metric','physics-metric'])$(id).addEventListener('change',charts);
function renderRun(){
 const state=detail?.status,rows=detail?.metrics??[];
 const phase={preparing:'准备环境',baseline:'测量官方基线',training:'CPU 训练中',evaluating:'独立验证中',testing:'最终测试中','baseline-testing':'同种子基线对照中',completed:'训练结束',cancelled:'训练已取消',failed:'训练失败'};
 $('training-phase').textContent=state?`${phase[state.phase]??state.phase} · ${(state.steps??0).toLocaleString()} / ${state.budget_steps.toLocaleString()} 环境步`:'本关尚无训练记录';
 $('training-time').textContent=state?`已记录墙钟耗时 ${(state.elapsed_s/60).toFixed(1)} 分钟`:'耗时待测';
 $('training-progress').max=state?.budget_steps??1;$('training-progress').value=state?.steps??0;
 const gate=state?.converged_at,test=detail?.test;
 $('gate-status').textContent=state?`${gate?`达到预定验证门槛：${gate.steps.toLocaleString()} 步，用时 ${(gate.elapsed_s/60).toFixed(1)} 分钟。`:'尚未达到预定验证门槛，不能标为已收敛。'}${state.baseline_success_rate!=null?` 官方基线 ${(state.baseline_success_rate*100).toFixed(0)}%。`:''}${state.baseline_success_rate>=.9?' 基线已经能过关，本关不能据此宣称 PPO 带来提升。':''}${test?` 最终未见测试：${test.successes}/${test.episodes}；95% 区间 ${(test.ci95[0]*100).toFixed(1)}%–${(test.ci95[1]*100).toFixed(1)}%。`:''}${detail?.baseline_test?` 同组未见种子的基线：${detail.baseline_test.successes}/${detail.baseline_test.episodes}。`:''}${state.error?' '+state.error:''}`:'预定门槛：连续两次验证至少 18/20 成功。尚无数据。';
 sample=rows.find(r=>r.kind==='update'&&r.steps===sampleStep)??rows.findLast(r=>r.kind==='update')??null;charts();termInfo();renderParameters();symbolInfo(document.querySelector('[data-ppo][aria-pressed=true]')?.dataset.ppo??'ratio');
 $('run-evidence').textContent=detail?JSON.stringify({id:detail.id,manifest:detail.manifest,status:state,baseline_test:detail.baseline_test?{...detail.baseline_test,results:undefined}:null,test:test?{...test,results:undefined}:null},null,2):'尚无记录';
 $('run-download').hidden=!detail;if(detail)$('run-download').href=appURL(`api/balance/runs/${encodeURIComponent(detail.id)}`);
}
let refreshing=false,refreshAgain=false;
async function refresh(){
 if(closed||document.hidden)return;if(refreshing){refreshAgain=true;return}refreshing=true;
 const requestedLevel=level;
 try{
  const list=await api('api/balance/runs',currentRoom,{signal:lifetime.signal});
  if(closed)return;if(level!==requestedLevel){refreshAgain=true;return}records=compatibleRuns(list,level);
  if(!records.some(r=>r.id===selectedRun))selectedRun=records[0]?.id??'';
  const entries=records.length?records.map(r=>[r.id,`${r.id} · ${r.steps??0} 步`]):[['','本关尚无训练记录']],nextOptions=JSON.stringify(entries);
  if(nextOptions!==optionsKey){options($('run-select'),entries);optionsKey=nextOptions}$('run-select').value=selectedRun;
  const run=selectedRun,nextKey=JSON.stringify(records.find(r=>r.id===run)??null),changed=nextKey!==detailKey;
  if(changed){
   const next=run?await api(`api/balance/runs/${encodeURIComponent(run)}`,currentRoom,{signal:lifetime.signal}):null;
   if(closed)return;if(level!==requestedLevel||selectedRun!==run){refreshAgain=true;return}
   detail=next;detailKey=nextKey;renderRun();
  }
  $('start-training').disabled=!list.training_enabled;$('cancel-training').disabled=!list.training_enabled||list.active_run!==selectedRun||!['preparing','baseline','training','evaluating','testing','baseline-testing'].includes(detail?.status?.phase);
  const capability=list.training_enabled?'一次运行一个 CPU 任务；关卡切换不会伪造或清除训练记录。':'此服务展示训练记录；管理员可按训练文档启用 CPU 任务。';if($('training-capability').textContent!==capability)$('training-capability').textContent=capability;
 }catch(e){if(!closed)notify(e.message)}finally{refreshing=false;if(refreshAgain&&!closed){refreshAgain=false;void refresh()}}
}
$('run-select').addEventListener('change',async()=>{selectedRun=$('run-select').value;sampleStep=null;await refresh()});
$('start-training').addEventListener('click',async()=>{
 $('start-training').disabled=true;try{const job=await api('api/balance/train',currentRoom,{body:{level,steps:Number($('training-steps').value),seed:42}});selectedRun=job.id;appendLog('独立 CPU 训练任务已提交；网页曲线等候实际记录。','训练');await refresh()}catch(e){notify(e.message);await refresh()}
});
$('cancel-training').addEventListener('click',async()=>{try{await api(`api/balance/runs/${encodeURIComponent(selectedRun)}/cancel`,currentRoom,{body:{}});$('cancel-training').disabled=true;appendLog('已请求取消，正在保存最后的训练状态。','训练')}catch(e){notify(e.message)}});
function example(){
 const ratio=Number($('example-ratio').value),advantage=Number($('example-advantage').value),epsilon=Number($('example-epsilon').value);
 $('ratio-value').textContent=ratio.toFixed(2);$('advantage-value').textContent=advantage.toFixed(1);$('epsilon-value').textContent=epsilon.toFixed(2);
 const e=clippedExample(ratio,advantage,epsilon);$('example-result').textContent=`未裁剪项 ${e.raw.toFixed(3)}，裁剪项 ${e.clipped.toFixed(3)}；取较小值 ${e.objective.toFixed(3)}。${advantage>=0?'好动作的概率增大到一定程度后，继续增大不再增加这一项收益。':'对坏动作同样取较小值；不是无论优势正负都把结果夹进同一个区间。'}`;
}
for(const id of ['example-ratio','example-advantage','example-epsilon'])$(id).addEventListener('input',example);
// The initial HTML keeps controls disabled until room setup and all handlers
// are ready. A fast click during the asynchronous room request must not vanish.
controls();example();termInfo();renderParameters();renderObservation();charts();void refresh();void prepare();if(!closed)timer=setInterval(refresh,5000);

window.addEventListener('duckking-room-lost',()=>{closed=true;lifetime.abort();prepareAbort?.abort();clearInterval(timer);stateFeed?.close();loadFeedback.forEach(f=>f.cancel())});
