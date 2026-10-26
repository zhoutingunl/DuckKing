import {measurement,loadMetrics,afterFrame} from './experience.js';
import './style.css';
import './scenarios.css';
import { createPhysicsModelLoader } from './model-loader.js';
import { physicsView } from './physics-view.js';
import { createChorus } from './chorus.js';
import { setupVoice } from './voice.js';
import { appURL } from './urls.js';
import { createSocket } from './transport.js';

import { setupRoom } from './room.js';
await setupRoom();

const $=id=>document.getElementById(id);
const names={scene_skills:'动作练习场',scene_rollers:'轮滑小鸭',roulade:'前滚翻',ground_pick:'低头啄取',skate:'向前滑行',roller_crouch:'轮滑下蹲',yawn:'打个哈欠',idle_on:'开启自然待机',idle_off:'关闭自然待机',backward:'后退',strafe_left:'左横移',strafe_right:'右横移',shake_head:'摇头',tilt_head:'歪头',sit:'坐下',stand:'站起来',scene_ball:'单鸭踢球',scene_duo:'双鸭互动',scene_carry:'嘴部搬运',pick_up:'用嘴夹起',carry:'夹持搬运',put_down:'放下物品',kick_left:'左脚踢球',kick_right:'右脚踢球',find_companion:'发现同伴',duo_walk:'双鸭一起走',collide:'相向碰面',chorus:'同步合唱',walk:'前进',turn_left:'左转',turn_right:'右转',stop:'停止',reset:'重置场景',nod:'点头'};
const graspPhases={ready:'待夹取',closing:'正在合嘴',lifting:'正在抬起',holding:'夹持中',carrying:'正在搬运',carried:'已到接物台',lowering:'正在低头',opening:'正在张嘴',retreating:'正在退开',released:'已放稳',interrupted:'已停止',dropped:'夹持丢失',failed:'未通过验证'};
const statuses={completed:'完成',failed:'未完成',cancelled:'已取消',running:'进行中'};
const loadPhysicsModel=createPhysicsModelLoader();
let failedRevision=null,sceneRequestedAt=null,sceneExperience=null,sceneRequestPending=false,sceneRequestId=null,sceneTarget=null;
let viewer,scene=null,revision=null,loadingModel=false,changing=false,seen=0,latest=null,online=false;
try{viewer=physicsView($('physics-viewport'));}catch{$('canvas-fallback').hidden=false;}
let noticeOwner=null;
function notify(text,owner='other'){noticeOwner=owner;$('notice').textContent=text;$('notice').hidden=false;}
function syncSceneError(error){
  if(error)notify(error,'scene');
  else if(noticeOwner==='scene'){$('notice').hidden=true;noticeOwner=null;}
}
function appendLog(text,label='场景',error=false){const row=document.createElement('div');row.className=`log-line${error?' error':''}`;for(const [value,cls] of [[new Date().toLocaleTimeString('zh-CN',{hour12:false}),'log-time'],[label,'log-label'],[text,'']]){const span=document.createElement('span');span.textContent=value;span.className=cls;row.append(span);}$('activity-log').append(row);while($('activity-log').children.length>80)$('activity-log').firstChild.remove();$('activity-log').scrollTop=$('activity-log').scrollHeight;}
const chorus=createChorus(text=>$('chorus-status').textContent=text);
function buttons(){document.querySelectorAll('[data-sim-action]').forEach(b=>b.disabled=!online||!scene||changing||(['pick_up','carry','put_down'].includes(b.dataset.simAction)&&latest?.grasp?.phase!==({pick_up:'ready',carry:'holding',put_down:'carried'}[b.dataset.simAction])));$('release-scene').disabled=$('stop-scene').disabled=$('reset-scene').disabled=!online||!scene;document.querySelectorAll('[data-scene]').forEach(b=>{b.disabled=changing||!online;b.setAttribute('aria-pressed',String(b.dataset.scene===scene));});}
async function post(url,body){const response=await fetch(appURL(url),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body),signal:AbortSignal.timeout(45000)});const data=await response.json();if(!response.ok)throw new Error(typeof data.detail==='string'?data.detail:'场景指令未被接受');return data;}
const requestId=()=>Array.from(crypto.getRandomValues(new Uint8Array(16)),v=>v.toString(16).padStart(2,'0')).join('');
let requests=Promise.resolve();
function action(name){
  const target=['duo','turntable'].includes(scene)&&['sit','stand','walk','backward','strafe_left','strafe_right','turn_left','turn_right','nod','shake_head','tilt_head'].includes(name)?$(scene==='duo'?'duck-target':'turntable-target').value:'a';
  if(name==='stop'||name==='reset')chorus.stop();
  requests=requests.then(()=>post('/api/scenes/actions',{name,target,request_id:requestId()})).catch(e=>notify(e.message));return requests;
}
for(const button of document.querySelectorAll('[data-scene]'))button.addEventListener('click',async()=>{
  sceneExperience?.finish('cancelled');sceneExperience=measurement('load');
  sceneRequestedAt=performance.now();sceneRequestPending=true;sceneRequestId=requestId();sceneTarget=button.dataset.scene;changing=true;buttons();chorus.stop();$('sim-status').textContent='正在加载官方模型…';$('notice').hidden=true;
  try{const record=await post('/api/scenes/start',{name:`scene_${button.dataset.scene}`,request_id:sceneRequestId});if(record.status==='failed')throw Error(record.error??'场景准备失败');}
  catch(e){sceneExperience?.finish('failed');sceneExperience=null;sceneRequestedAt=null;notify(e.message);$('sim-status').textContent='物理场景启动失败';}
  finally{sceneRequestPending=false;changing=false;buttons();}
});
for(const button of document.querySelectorAll('[data-sim-action]'))button.addEventListener('click',async()=>{if(button.dataset.simAction==='chorus')await chorus.enable();await action(button.dataset.simAction);});
$('enable-chorus').addEventListener('click',()=>chorus.enable().catch(e=>notify(e.message)));
$('release-scene').addEventListener('click',async()=>{
  try{const response=await fetch(appURL('api/scenes/close'),{method:'POST',signal:AbortSignal.timeout(15000)});
    if(!response.ok){const data=await response.json();throw new Error(data.detail||'场景释放失败');}
    chorus.stop();appendLog('物理场景已释放，其他房间可以使用空出的名额。','场景');
  }catch(e){notify(e.message);}
});
$('reset-scene').addEventListener('click',()=>action('reset'));$('stop-scene').addEventListener('click',()=>action('stop'));$('reset-camera').addEventListener('click',()=>viewer?.reset());$('clear-log').addEventListener('click',()=>$('activity-log').replaceChildren());
window.addEventListener('keydown',e=>{if(e.key==='Escape'&&scene)action('stop');});
async function loadModel(state,currentAction){
  if(sceneExperience&&(sceneRequestPending||state.scene!==sceneTarget||currentAction?.id===sceneRequestId))return;
  if(loadingModel||((revision===state.revision||failedRevision===state.revision)&&!sceneExperience))return;loadingModel=true;
  const experience=sceneExperience??measurement('load');sceneExperience=null;const requested=sceneRequestedAt!==null;const modelStarted=performance.now();
  const started=sceneRequestedAt??performance.now();sceneRequestedAt=null;
  const metrics={view:'scenario',scene:state.scene,cache:'unknown',manifest_ms:0,asset_ms:0,parse_ms:0,assemble_ms:0,first_frame_ms:0};
  let result='failed';
  try{
    const model=await loadPhysicsModel(appURL('/api/scenes/model.dkm.gz'),state.revision,{signal:AbortSignal.timeout(60000),metrics});
    if(latest?.revision!==model.revision)return;
    if(!viewer)throw new Error('浏览器无法绘制官方模型，请检查 WebGL 支持');
    const assembling=performance.now();viewer.load(model);viewer.frameScene(latest.scene);revision=model.revision;viewer.update(latest);
    metrics.assemble_ms=performance.now()-assembling;
    const drawing=performance.now();viewer.renderNow();await afterFrame();metrics.first_frame_ms=performance.now()-drawing;
    $('scene-placeholder').hidden=true;failedRevision=null;result='ready';
    appendLog(`场景外观已显示 · ${((performance.now()-started)/1000).toFixed(2)} 秒 · ${metrics.cache==='memory'?'复用模型':metrics.cache==='persistent'?'读取缓存':'压缩下载'}`,'加载');
  }catch(e){failedRevision=state.revision;notify(e.message);}
  finally{
    loadingModel=false;
    const timing={...metrics,result,elapsed_ms:performance.now()-started,navigation_ms:performance.now()};
    for(const key of Object.keys(timing))if(typeof timing[key]==='number')timing[key]=Math.round(timing[key]);
    $('physics-viewport').dataset.modelTiming=JSON.stringify(timing);
    experience.finish(result==='ready'?'completed':'failed',{...loadMetrics(timing),model_ms:Math.round(performance.now()-modelStarted),...(requested?{scene_ms:Math.round(performance.now()-started)}:{})},{cache:metrics.cache,scene:state.scene});
    console.info('[DuckKing:scene-load]',timing);
    fetch(appURL('api/models/load-metrics'),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(timing),keepalive:true}).catch(()=>{});
  }
}
function update(data){
  const state=data.backend;latest=state;online=true;scene=state.scene;buttons();
  if(data.events.length&&data.events.at(-1).id<seen)seen=0;
  $('sim-status').textContent=state.error?'物理场景异常':'MuJoCo 物理运行中';
  $('scene-title').textContent=scene==='skills'?'单鸭 · 动作与表情':scene==='rollers'?'单鸭 · 官方轮滑模型':scene==='seated'?'四鸭坐姿合唱 · 轮流独唱':scene==='table'?'四鸭桌上合唱':scene==='carry'?'单鸭 + 轻质小棒 · 接触夹持':scene==='ball'?'单鸭 + 球':'鸭 A + 鸭 B · 共享物理世界';
  $('actions-heading').textContent=scene==='skills'?'练一项新本领':scene==='rollers'?'让小鸭滑起来':scene==='carry'?'用嘴完成一次搬运':scene==='ball'?'练习一次定点踢球':'一起活动';
  $('ball-controls').hidden=scene!=='ball';$('duo-controls').hidden=scene!=='duo';$('carry-controls').hidden=$('grasp-readouts').hidden=scene!=='carry';
  $('posture-controls').hidden=!['ball','duo','skills'].includes(scene);
  $('skills-controls').hidden=scene!=='skills';$('rollers-controls').hidden=scene!=='rollers';
  $('turntable-controls').hidden=scene!=='turntable';
  if(scene==='turntable'&&state.turntable){const t=state.turntable,out=t.ducks.filter(d=>d.out).map(d=>'鸭 '+d.member.toUpperCase());
    $('turntable-status').textContent=`转速 ${t.omega.toFixed(1)} 弧度/秒（盘沿 ${t.rim_speed_mps.toFixed(1)} 米/秒）· 台上 ${t.remaining} 只${out.length?' · 已出局：'+out.join('、'):''}`;}
  $('basic-controls').hidden=!['ball','duo','skills','rollers'].includes(scene);$('floor-moves').hidden=scene==='rollers';
  $('skill-readouts').hidden=!['skills','rollers'].includes(scene)||!state.skill;
  if(state.idle)$('idle-status').textContent=state.idle.enabled?`自然待机已开启 · ${{off:'等待',waiting:'等待安静下来',paused:'当前动作优先',look_around:'看看四周',yawn:'打哈欠'}[state.idle.phase]??'等待'}`:'自然待机已关闭';
  if(state.skill){const k=state.skill;$('skill-readouts').textContent=`${names[k.name]??k.name} · ${statuses[k.status]??'已中断'} · `+(k.name==='ground_pick'?`嘴尖最低 ${(k.min_mouth_height_m*100).toFixed(1)} cm`:k.name==='roulade'?`实测翻转 ${(k.rotation_rad*180/Math.PI).toFixed(0)}°`:k.name==='yawn'?`嘴巴最大张开 ${(k.max_mouth_open_rad*180/Math.PI).toFixed(0)}°`:k.name==='skate'?`实测位移 ${(k.displacement_m*100).toFixed(1)} cm`:`身体最低 ${(k.min_body_height_m*100).toFixed(1)} cm`);}

  $('posture-status').textContent=state.ducks.map(d=>`鸭 ${d.id.toUpperCase()} · ${{sit:'已坐稳',stand:'站立',transition:'调整姿态'}[d.posture?.observed]??'等待姿态数据'}`).join('；');
  if(state.grasp){const g=state.grasp;$('grasp-phase').textContent=graspPhases[g.phase]??g.phase;$('grasp-force').textContent=`${g.normal_force_n.upper.toFixed(2)} / ${g.normal_force_n.lower.toFixed(2)} N`;$('grasp-lift').textContent=`${(Math.max(0,g.max_lift_clearance_m)*1000).toFixed(1)} mm`;$('grasp-distance').textContent=`${(g.carry_distance_m*100).toFixed(1)} cm`;$('grasp-detail').textContent=g.error??`双侧连续接触 ${g.bilateral_s.toFixed(1)} 秒 · 放下稳定 ${g.released_stable_s.toFixed(1)} 秒`;}
  $('ball-distance').textContent=state.ball?`${state.ball.displacement_m.toFixed(2)} m`:'—';
  $('ball-contact').textContent=state.ball?(state.ball.contact_feet.map(f=>f==='left'?'左脚':'右脚').join('、')||'尚无'):'—';
  $('duck-contact').textContent=scene==='duo'?state.contacts.ducks:'—';$('sim-speed').textContent=`${state.real_time_factor.toFixed(2)}×`;
  if(state.discovered.length)$('peer-status').textContent=state.discovered.map(p=>`鸭 ${p.observer.toUpperCase()} 发现鸭 ${p.peer.toUpperCase()}，相距 ${p.distance_m.toFixed(2)} m`).join('；');
  else $('peer-status').textContent='未记录发现结果。检测范围 1.2 m / 120°，考虑遮挡。';
  chorus.update(state.chorus);loadModel(state,data.action);viewer?.update(state);
  if(data.action)$('action-result').textContent=`${names[data.action.name]??data.action.name} · 进行中`;
  for(const event of data.events){if(event.id<=seen)continue;seen=event.id;const text=event.text.replace(new RegExp(Object.keys(names).sort((a,b)=>b.length-a.length).join('|'),'g'),k=>names[k]??k).replace(/completed|failed|cancelled/g,k=>statuses[k]);appendLog(text,event.kind==='result'?'执行结果':'物理动作',event.status==='failed');if(event.kind==='result')$('action-result').textContent=text;}
  syncSceneError(state.error||data.error);
}
let socket,connectionNotice=null,retryDelay=1000;
function notStarted(){
  syncSceneError(null);
  scene=revision=latest=null;seen=0;viewer?.clear();chorus.stop();buttons();
  $('scene-placeholder').hidden=false;$('sim-status').textContent='选择场景开始';$('scene-title').textContent='等待启动';$('actions-heading').textContent='选择场景后开始';
  for(const id of ['posture-controls','skills-controls','rollers-controls','turntable-controls','skill-readouts','basic-controls'])$(id).hidden=true;
  $('ball-controls').hidden=$('duo-controls').hidden=$('carry-controls').hidden=$('grasp-readouts').hidden=true;
  for(const id of ['ball-distance','ball-contact','duck-contact','sim-speed'])$(id).textContent='—';
}
function connect(){
  const channel=createSocket('scene-ws');socket=channel;let received=false;
  channel.onmessage=event=>{
    if(socket!==channel)return;
    const data=JSON.parse(event.data);received=true;online=true;retryDelay=1000;
    if(connectionNotice&&$('notice').textContent===connectionNotice)$('notice').hidden=true;connectionNotice=null;
    if(data.type==='state')update(data);else if(data.type==='not_started')notStarted();
    channel.send('next');
  };
  channel.onclose=event=>{
    if(socket!==channel)return;
    online=false;buttons();chorus.stop();
    $('sim-status').textContent=received?'场景连接中断 · 正在重连':'场景连接未建立 · 正在重试';
    connectionNotice=received
      ?'本地场景连接已断开，正在重连。此连接与灵矽独立；恢复后才能继续操作场景。'
      :`场景实时连接未建立，无需先连接灵矽。请确认后端正在运行，并用 Chrome 无痕窗口直接打开 ${appURL('scenarios.html')}；检查浏览器扩展或代理是否改写 Origin 请求头。`;
    notify(connectionNotice);appendLog(`场景${received?'连接中断':'握手未完成'}（关闭码 ${event.code}）`,'连接',true);
    setTimeout(connect,retryDelay);retryDelay=Math.min(retryDelay*2,10000);
  };
}
connect();buttons();setupVoice({appendLog,notify,endpoint:'/scene-voice'});
window.addEventListener('pagehide',()=>{chorus.dispose();viewer?.dispose();});
