import './site-nav.js';
import './style.css';
import './scenarios.css';
import './features.css';
import {setupRoom,rememberChoice,savedChoice} from './room.js';
import {appURL} from './urls.js';
import {requestId} from './ids.js';
import {physicsView} from './physics-view.js';
import {createPhysicsModelLoader} from './model-loader.js';
import {createLoadingState} from './loading-state.js';
import {sceneStateFeed} from './scene-state-feed.js';
import {setupVoice} from './voice.js';
import {StudioChoir} from './studio-choir.js';
import {afterFrame,measurement,loadMetrics} from './experience.js';
import {translate} from './ui-language.js';
import {FeatureAudio} from './feature-audio.js';
import {createFeatureIntent} from './feature-intent.js';

await setupRoom();
const $=id=>document.getElementById(id),loader=createPhysicsModelLoader();
const feedback=createLoadingState($('scene-placeholder')),choir=new StudioChoir(),sound=new FeatureAudio();
const intent=createFeatureIntent();
const labels={walk:'向前走',backward:'向后退',turn_left:'向左转',turn_right:'向右转',sit:'坐下',stand:'站起来',nod:'点点头',curious:'好奇',sad:'难过',devastated:'委屈坐下',mmh:'嗯？',yes:'点头答应',yes_fast:'连连点头',no:'摇头拒绝',defiant:'不服气',angry:'生气',mock:'调皮',excited:'兴奋',impatient:'等不及了',laugh:'笑起来',conduct:'按顺序轮唱',dock:'回窝坐好',undock:'离窝站起来',hop:'跳一下',lift_left:'抬左脚',lift_right:'抬右脚',lower:'放下脚',observe:'看看前方',look_left:'向左看',look_right:'向右看',look_forward:'看前方',play:'演奏距离琴',near:'物体靠近',far:'物体远离',cross:'跨过门槛',find_red:'找红色',find_blue:'找蓝色',find_green:'找绿色',kick_left:'找到球用左脚踢',kick_right:'找到球用右脚踢',go_door:'去门口',go_home:'回窝旁',go_table:'去桌旁',steps:'踩着标记走',swing:'荡起来',jump_rope:'一起跳绳'};
const sources={
 movement:'官方步态与有界动作控制。',
 emotions:'官方 13 种情绪时间线；声音在浏览器本地播放。',
 director:'四只物理鸭，坐姿与独唱状态确认后才播放本地合唱。',
 dock:'MicroDock v2 策略；使用仿真标签位姿与接触代理，电量是虚拟值。',
 senses:'真实 RGB 相机与光轴射线测距；不调用云端视觉。',
 theremin:'移动的是虚拟物体；射线实测距离控制浏览器合成音高。',
 search:'只从 RGB 颜色区域估计目标位置；物体真实位置仅用于结果验收。',
 soccer:'只从 RGB 颜色区域估计目标位置；物体真实位置仅用于结果验收。',
 navigation:'已知地图与仿真自身位姿，A* 绕障；这不是视觉 SLAM。',
 footsteps:'FootstepNet 规划与落足策略；蓝色为计划，红色为实际落点。',
 swing:'实验：固定座椅、两根弹性绳与自驱策略；摆起来不等于通过绳长检查。',
 circus:'实验：三只自由鸭与有接触的绳；嘴柄为理想连接，策略可读取绳相位。完整跳绳验收尚未通过。',
};
const statusLabels={idle:'等待指令',running:'正在执行',completed:'任务完成',failed:'本轮未完成',cancelled:'任务已取消'};
let catalog=[],selected=null,latest=null,revision=null,expectedRevision=null,busy=false,online=false,epoch=0,modelPromise=null,modelAbort=null,session=null,voice;
let viewer;try{viewer=physicsView($('physics-viewport'))}catch{notify('浏览器无法绘制模型，请使用支持 WebGL 的浏览器。')}
function notify(text){$('notice').textContent=text;$('notice').hidden=false}
function appendLog(text,label='任务'){
 const row=document.createElement('p'),tag=document.createElement('strong');tag.textContent=translate(label)+' ';row.append(tag,document.createTextNode(text));$('activity-log').append(row);
 while($('activity-log').children.length>60)$('activity-log').firstChild.remove();
}
function unavailable(){return busy||!online||!latest||latest.feature?.capability!==selected?.id||revision!==latest.revision?'请等小鸭显示后再开始。':''}
function controls(){
 for(const b of document.querySelectorAll('[data-feature-action]'))b.disabled=!!unavailable();
 $('stop-feature').disabled=$('reset-feature').disabled=$('release-feature').disabled=!latest||busy;
 $('prepare-feature').disabled=busy;
 for(const b of document.querySelectorAll('[data-capability]'))b.disabled=busy;
 window.dispatchEvent(new Event('duckking-voice-readiness'));
}
async function api(path,body,signal){
 const response=await fetch(appURL(path),{...(body?{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}:{}),signal:signal??AbortSignal.timeout(100000)});
 if(response.status===204)return {};
 const data=await response.json();if(!response.ok)throw Error(typeof data.detail==='string'?data.detail:data.detail?.message??'场景请求未完成');return data;
}
function describe(entry){
 $('scene-title').textContent=entry.title;$('feature-description').textContent=entry.description;
 $('feature-voice-example').textContent=entry.commands.map(k=>translate(labels[k])).join(' / ');
 $('feature-source').textContent=sources[entry.id]??'社区 ONNX 策略，CPU 推理与 BAM 电机模型；未训练新策略。';
 $('feature-limits').textContent=entry.category==='实验'||entry.id==='dock'?sources[entry.id]:'';
 $('feature-limits').hidden=!$('feature-limits').textContent;
 $('feature-parameters').hidden=entry.id!=='movement';$('feature-order-wrap').hidden=entry.id!=='director';
 $('feature-commands').replaceChildren();
 for(const name of entry.commands){const b=document.createElement('button');b.dataset.featureAction=name;b.textContent=labels[name]??name;b.addEventListener('click',()=>command(name));$('feature-commands').append(b)}
 for(const b of document.querySelectorAll('[data-capability]'))b.setAttribute('aria-pressed',String(b.dataset.capability===entry.id));
}
async function disconnect(){
 if(!voice||['disconnected','error','busy','awaiting_binding'].includes(voice.state))return;
 voice.disconnect();
 for(let i=0;i<100;i++){if(['disconnected','error','busy','awaiting_binding'].includes(voice.state))return;await new Promise(r=>setTimeout(r,100))}
 throw Error('语音尚未释放，请稍后重试');
}
async function select(entry,replace=true){
 if(busy)return;intent.cancel();busy=true;const mine=++epoch;expectedRevision=null;selected=entry;describe(entry);controls();choir.stop();sound.stop();$('notice').hidden=true;
 modelAbort?.abort();modelAbort=new AbortController();const signal=modelAbort.signal;
 session=feedback.begin({phase:'backend',cancel:()=>{modelAbort.abort();session.cancelled()},retry:()=>select(entry,true)});
 const experience=measurement('load'),started=performance.now();
 try{
  await disconnect();const data=await api('api/features/prepare',{capability:entry.id,replace},signal);signal.throwIfAborted();
  if(mine!==epoch)return;latest=data.backend;expectedRevision=latest.revision;revision=null;online=true;await loadModel(latest,signal,mine);
  rememberChoice('feature',entry.id);experience.finish('completed',{scene_ms:Math.round(performance.now()-started)},{scene:'functional'});
  $('sim-status').textContent='场景已准备，等待指令';
 }catch(error){if(mine!==epoch)return;experience.finish(signal.aborted?'cancelled':'failed');signal.aborted?session.cancelled():session.fail(error);notify(error.message)}
 finally{if(mine===epoch){busy=false;controls();feed.refresh()}}
}
async function loadModel(state,signal,mine=epoch){
 if(modelPromise){try{await modelPromise}catch{}signal?.throwIfAborted();if(mine!==epoch)return;}
 const metrics={};
 modelPromise=(async()=>{
  session??=feedback.begin({phase:'download',retry:()=>select(selected,true)});
  const model=await loader(appURL('api/scenes/model.dkm.gz'),state.revision,{signal,metrics,progress:session.progress});
  signal?.throwIfAborted();if(mine!==epoch||latest?.revision!==model.revision)return;
  if(!viewer)throw Error('浏览器无法绘制模型，请使用支持 WebGL 的浏览器。');
  viewer.load(model);viewer.frameScene(state.view_scene??(selected.id==='director'?'seated':'ball'));viewer.update(latest);viewer.renderNow();await afterFrame();
  signal?.throwIfAborted();if(mine!==epoch)return;revision=model.revision;session.ready();
  measurement('load').finish('completed',loadMetrics(metrics),{scene:'functional'});
 })();
 try{await modelPromise}finally{modelPromise=null}
}
const seen=new Set();
function update(packet){
 const state=packet.backend;if(!state||state.scene!=='functional'){
  if(!busy){latest=null;online=false;revision=null;viewer?.clear();feedback.reset('选择一个功能场景开始。');controls()}return;
 }
 if(state.feature.capability!==selected?.id||state.revision!==expectedRevision)return;latest=state;online=!state.error;
 viewer?.update(state);choir.update(state.seated_choir);sound.update(state.feature);
 const f=state.feature;$('task-status').textContent=statusLabels[f.status]??f.status;$('result-message').textContent=f.message??'';
 $('task-status').dataset.outcome=f.status;
 $('feature-metrics').replaceChildren();
 const values={distance_m:['实际位移',100,'cm'],sim_time:['仿真时间',1,'s'],max_clearance_m:['最高离地',100,'cm'],support_feet:['支撑脚',1,''],distance_m_to_target:['距目标',100,'cm'],frequency_hz:['音高',1,'Hz'],ray_distance_m:['前方距离',100,'cm'],virtual_battery_percent:['虚拟电量',1,'%'],steps_completed:['已落足',1,''],swing_span_deg:['摆幅',1,'°'],minimum_string_m:['最短绳长',100,'cm'],maximum_string_m:['最长绳长',100,'cm'],clean_skips:['有效跳绳',1,''],full_revolutions:['绳圈数',1,''],real_time_factor:['仿真 / 墙钟',1,'×'],foot_ball_contacts:['脚球接触采样',1,'']};
 for(const [key,[label,scale,unit]] of Object.entries(values)){const v=f.metrics?.[key];if(!Number.isFinite(v)||(key==='support_feet'&&selected?.id==='swing'))continue;const box=document.createElement('div'),dt=document.createElement('dt'),dd=document.createElement('dd');dt.textContent=label;dd.textContent=`${(v*scale).toFixed(1)} ${unit}`;box.append(dt,dd);$('feature-metrics').append(box)}
 for(const result of f.results??[]){if(seen.has(result.id))continue;seen.add(result.id);appendLog(`${translate(labels[result.action]??result.action)} · ${translate(statusLabels[result.status])} · ${translate(result.message??'')}`,'执行结果')}
 if(seen.size>120)seen.delete(seen.values().next().value);
 $('sensor-panel').hidden=!state.sensors;
 if(state.sensors?.image){const image=`data:${state.sensors.mime??'image/png'};base64,`+state.sensors.image;if($('sensor-image').src!==image)$('sensor-image').src=image;}
 if(state.sensors){const distance=state.sensors.distance_m;$('sensor-status').textContent=distance==null?translate('光轴方向未检测到四米内物体'):`${translate('前方距离')} ${(distance*100).toFixed(1)} cm`;drawDistance(distance)}
 if(state.error)notify(state.error);controls();
}
async function command(action){
 if(unavailable())return;try{
  const entry=selected;
  const body={operation:'start',action,request_id:requestId()};
  if(entry.id==='movement'){body.duration=Number($('feature-duration').value);body.speed=Number($('feature-speed').value)}
  if(entry.id==='director')body.order=$('feature-order').value.toLowerCase().split(/[\s,，]+/).filter(Boolean);
  await intent.run(async()=>{
   await enableSceneSound();
   if(entry.id==='emotions')await sound.load(action);
  },async()=>{
   if(unavailable())return;
   await api('api/features/command',body);appendLog(translate(labels[action]),'本地演示');await feed.refresh();
  });
 }catch(error){notify(error.message)}
}
async function control(operation){intent.cancel();try{choir.stop();sound.stop();await api('api/features/command',{operation,request_id:requestId()});await feed.refresh()}catch(error){notify(error.message)}}
$('stop-feature').addEventListener('click',()=>control('stop'));$('reset-feature').addEventListener('click',()=>control('reset'));
$('prepare-feature').addEventListener('click',()=>select(selected,true));$('reset-camera').addEventListener('click',()=>viewer?.reset());$('clear-log').addEventListener('click',()=>$('activity-log').replaceChildren());
$('release-feature').addEventListener('click',async()=>{if(busy)return;intent.cancel();busy=true;controls();try{await disconnect();await api('api/scenes/close',{});epoch++;modelAbort?.abort();latest=null;revision=expectedRevision=null;choir.stop();sound.stop();viewer?.clear();feedback.reset('场景已释放，点击重新准备即可继续。')}catch(error){notify(error.message)}finally{busy=false;controls()}});
window.addEventListener('keydown',event=>{if(event.key==='Escape'&&latest)void control('stop')});
const feed=sceneStateFeed({readState:signal=>api('api/scenes/state',null,signal),onState:update,onStatus:({mode})=>{online=mode==='websocket'||mode==='http';controls()}});
async function enableSceneSound(){
 if(selected?.id==='director')await choir.enable();
 if(['emotions','theremin'].includes(selected?.id))await sound.enable();
}
for(const id of ['connect-voice','enable-sound'])$(id).addEventListener('click',()=>{void enableSceneSound().then(()=>selected?.id==='emotions'?Promise.all(selected.commands.map(name=>sound.load(name))):null).catch(error=>notify(error.message))});
voice=setupVoice({appendLog,notify,endpoint:'/scene-voice',cloudOnly:true,listenUnavailable:unavailable});
try{
 catalog=(await api('api/features/catalog')).capabilities;
 for(const category of ['全部',...new Set(catalog.map(c=>c.category))]){const b=document.createElement('button');b.textContent=category;b.setAttribute('aria-pressed',String(category==='全部'));b.onclick=()=>{for(const c of $('feature-categories').children)c.setAttribute('aria-pressed',String(c===b));for(const c of $('feature-catalog').children)c.hidden=category!=='全部'&&c.dataset.category!==category};$('feature-categories').append(b)}
 for(const entry of catalog){const b=document.createElement('button');b.dataset.capability=entry.id;b.dataset.category=entry.category;const title=document.createElement('strong'),detail=document.createElement('span');title.textContent=entry.title;detail.textContent=entry.description;b.append(title,detail);b.onclick=()=>select(entry);$('feature-catalog').append(b)}
 const choice=new URL(location.href).searchParams.get('feature')??savedChoice('feature');selected=catalog.find(c=>c.id===choice)??catalog[0];await select(selected,false);
}catch(error){notify(error.message)}
window.addEventListener('pagehide',()=>{intent.cancel();epoch++;modelAbort?.abort();feed.close();choir.stop();sound.stop();viewer?.dispose();void sound.close();void choir.ctx?.close()});

function drawDistance(distance){
 const canvas=$('distance-map'),ctx=canvas.getContext('2d');ctx.clearRect(0,0,320,320);ctx.fillStyle='#edf3e4';ctx.fillRect(0,0,320,320);ctx.strokeStyle='#81995d';ctx.lineWidth=2;ctx.beginPath();ctx.moveTo(160,285);ctx.lineTo(160,30);ctx.stroke();ctx.fillStyle='#405b2c';ctx.beginPath();ctx.arc(160,285,10,0,Math.PI*2);ctx.fill();
 if(Number.isFinite(distance)){const y=285-Math.min(4,distance)/4*250;ctx.fillStyle='#bf603d';ctx.beginPath();ctx.arc(160,y,9,0,Math.PI*2);ctx.fill();ctx.font='16px sans-serif';ctx.fillText(`${distance.toFixed(2)} m`,180,y+5)}
}
