import './style.css';
import './balance.css';
import {physicsView} from './physics-view.js';
import {createPhysicsModelLoader} from './model-loader.js';
import {setupVoice} from './voice.js';
import {setupRoom} from './room.js';
import {appURL,currentRoom} from './urls.js';
import {createSocket} from './transport.js';
import {api} from './demo-runtime.js';
import {rewardTerms,hyperparameters,observationGroups,metricLabels,ppoSymbols,clippedExample,compatibleRuns} from './balance-explain.js';
import {drawChart} from './balance-chart.js';
import {measurement,loadMetrics,afterFrame} from './experience.js';

const $=id=>document.getElementById(id),titles=['跟着圆盘站稳','转盘转，我不转','从边缘回到中心'];
let level=1,observedLevel=1,viewer,ready=false,loading=false,selectedRun='',records=[],detail=null,sample=null,sampleStep=null,term='center',socket,timer,closed=false,revision=null;
const loader=createPhysicsModelLoader();
const notify=text=>{$('notice').hidden=false;$('notice').textContent=text};
function appendLog(text,label='实际执行'){
 const row=document.createElement('div');row.className='log-line';const tag=document.createElement('span');tag.className='log-label';tag.textContent=label;const body=document.createElement('span');body.textContent=text;row.append(tag,body);$('activity-log').append(row);while($('activity-log').children.length>80)$('activity-log').firstChild.remove();
}
await setupRoom();
const voice=setupVoice({appendLog,notify,endpoint:'scene-voice',cloudOnly:true});
function controls(){
 $('start-challenge').disabled=!ready||loading;$('stop-balance').disabled=!ready;
 $('prepare-balance').disabled=loading;$('prepare-balance').textContent=ready?'圆盘已准备 · 重新加载':'准备圆盘';
 document.querySelectorAll('[data-level]').forEach(b=>{b.disabled=loading;b.setAttribute('aria-pressed',String(Number(b.dataset.level)===level))});
}
function renderState(state){
 const b=state?.balance;if(!b)return;
 if(b.level!==observedLevel){observedLevel=b.level;level=b.level;selectedRun='';sampleStep=null;controls();void refresh()}
 viewer?.update(state);const r=b.result;
 $('disc-rpm').textContent=r?`${r.rpm.toFixed(2)} RPM`:'—';
 $('disc-radius').textContent=r?`${(r.radius*100).toFixed(1)} cm`:'—';
 $('disc-contact').textContent=r?`${r.contacts} / 2 脚`:'—';
 $('disc-time').textContent=`${b.sim_time.toFixed(1)} s`;
 const reasons={fell_or_left_disc:'身体失稳、触地或脚部越过盘缘，物理已暂停',criteria_not_met:'挑战结束，但中心位置、朝向或停盘条件未全部达标'};
 const phases={idle:'等待指令',running:'挑战中',stopping:'正在减速停盘',completed:'挑战成功',failed:'本轮未完成',cancelled:'已停止 · 人为干预不计成功'};
 $('challenge-status').textContent=`${phases[b.phase]??b.phase}${r?.reason&&reasons[r.reason]?' · '+reasons[r.reason]:''}${r?` · 朝向达标 ${(r.heading_fraction*100).toFixed(0)}% · 脚边缘余量 ${(r.rim_margin*100).toFixed(1)} cm · ${r.disk_stopped?'圆盘已停稳':'圆盘仍在运动'}`:''}${b.error?' · '+b.error:''}`;
 const name={baseline:'官方步态基线',early:'训练步数 0 的任务网络＋官方步态',trained:'已评估反馈力度 PPO＋官方步态'}[b.controller];
 $('controller-source').textContent=`MuJoCo ${b.execution==='running'?'计算中':'已暂停'} · ${name}${b.policy_steps!=null?` · ${b.policy_steps.toLocaleString()} 训练步`:''}。训练过程见下方独立记录。`;
 $('scene-title').textContent=`第 ${b.level} 关 · ${b.title}`;
 if(state.observation)renderObservation(state.observation,state.task_action);
}
async function prepare(){
 if(loading)return;loading=true;controls();$('notice').hidden=true;
 $('scene-placeholder').hidden=false;$('scene-placeholder').textContent='正在加载官方模型与有惯量的圆盘…';
 const experience=measurement('load'),metrics={};
 try{
  if(!viewer)viewer=physicsView($('physics-viewport'));
  const state=await api('api/balance/prepare',currentRoom,{body:{}});
  if(revision!==state.backend.revision){const data=await loader(appURL('api/scenes/model.dkm.gz'),state.backend.revision,{signal:AbortSignal.timeout(60000),metrics});const started=performance.now();viewer.load(data);viewer.frameScene('balance');metrics.assemble_ms=performance.now()-started;revision=state.backend.revision}else metrics.cache='memory';
  renderState(state.backend);const firstFrame=performance.now();await afterFrame();viewer.renderNow();await afterFrame();metrics.first_frame_ms=Math.round(performance.now()-firstFrame);$('scene-placeholder').hidden=true;ready=true;
  experience.finish('completed',{...loadMetrics(metrics),scene_ms:Math.round(performance.now()-experience.started)},{cache:metrics.cache,scene:'balance'});
  if(!socket)connect();appendLog('圆盘已准备，可连接灵矽；按钮操作标记为本地排练。');
 }catch(e){experience.finish('failed');notify(e.message);$('scene-placeholder').textContent='加载未完成，可重试。'}finally{loading=false;controls()}
}
function connect(){
 if(closed)return;socket=createSocket('scene-ws');
 socket.onmessage=e=>{try{const state=JSON.parse(e.data);if(state.type==='state'){
   if(state.backend.scene==='balance')renderState(state.backend);
   else{ready=false;controls();notify('本房间已切到其他场景，请重新准备圆盘。')}
  }}catch(error){notify(error.message)}finally{if(socket.readyState===1)socket.send('next')}};
 socket.onclose=()=>{socket=null;if(!closed){$('challenge-status').textContent='状态连接中断，正在重新连接';setTimeout(connect,1500)}};
}
async function command(body){
 try{const result=await api('api/balance/command',currentRoom,{body});appendLog(`第 ${result.level} 关 · ${result.phase} · ${result.controller}`,'本地排练');return result}catch(e){notify(e.message)}
}
$('prepare-balance').addEventListener('click',prepare);
$('start-challenge').addEventListener('click',async()=>{
 loading=true;controls();$('notice').hidden=true;
 try{await command({operation:'start',level,controller:$('controller').value,seed:Number($('challenge-seed').value),...(selectedRun?{run:selectedRun}:{})})}finally{loading=false;controls()}
});
$('stop-balance').addEventListener('click',()=>{void voice.interrupt();void command({operation:'stop'})});
window.addEventListener('keydown',e=>{if(e.code==='Escape'&&ready)void command({operation:'stop'})});
$('reset-camera').addEventListener('click',()=>viewer?.reset());
$('clear-log').addEventListener('click',()=>$('activity-log').replaceChildren());
for(const button of document.querySelectorAll('[data-level]'))button.addEventListener('click',async()=>{
 if(loading)return;level=Number(button.dataset.level);controls();
 if(ready)await command({operation:'select',level});
 $('scene-title').textContent=`待挑战第 ${level} 关 · ${titles[level-1]}`;
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
function renderObservation(values=[],actions=[]){
 $('observation-table').replaceChildren();for(const[start,end,title,explanation]of observationGroups){const tr=document.createElement('tr');for(const text of [title,explanation,values.length?values.slice(start,end).map(v=>v.toFixed(3)).join(' / '):'等待物理场景']){const td=document.createElement('td');td.textContent=text;tr.append(td)}$('observation-table').append(tr)}
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
let refreshing=false;
async function refresh(){
 if(refreshing||closed)return;refreshing=true;
 try{
  const list=await api('api/balance/runs',currentRoom);records=compatibleRuns(list,level);
  if(!records.some(r=>r.id===selectedRun))selectedRun=records[0]?.id??'';
  options($('run-select'),records.length?records.map(r=>[r.id,`${r.id} · ${r.steps??0} 步`]):[['','本关尚无训练记录']]);$('run-select').value=selectedRun;
  detail=selectedRun?await api(`api/balance/runs/${encodeURIComponent(selectedRun)}`,currentRoom):null;
  $('start-training').disabled=!list.training_enabled;$('cancel-training').disabled=!list.training_enabled||list.active_run!==selectedRun||!['preparing','baseline','training','evaluating','testing','baseline-testing'].includes(detail?.status?.phase);
  $('training-capability').textContent=list.training_enabled?'一次运行一个 CPU 任务；关卡切换不会伪造或清除训练记录。':'此服务展示训练记录；管理员可按训练文档启用 CPU 任务。';renderRun();
 }catch(e){notify(e.message)}finally{refreshing=false}
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
example();termInfo();renderParameters();renderObservation();charts();await refresh();timer=setInterval(refresh,5000);
window.addEventListener('pagehide',()=>{closed=true;clearInterval(timer);if(socket){socket.onclose=null;socket.close()}viewer?.dispose()},{once:true});
