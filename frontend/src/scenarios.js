import './style.css';
import './scenarios.css';
import { physicsView } from './physics-view.js';
import { createChorus } from './chorus.js';
import { setupVoice } from './voice.js';
import { appURL } from './urls.js';
import { createSocket } from './transport.js';

const $=id=>document.getElementById(id);
const names={scene_ball:'单鸭踢球',scene_duo:'双鸭互动',kick_left:'左脚踢球',kick_right:'右脚踢球',find_companion:'发现同伴',duo_walk:'双鸭一起走',collide:'相向碰面',chorus:'同步合唱',walk:'前进',turn_left:'左转',turn_right:'右转',stop:'停止',reset:'重置场景',nod:'点头'};
const statuses={completed:'完成',failed:'未完成',cancelled:'已取消',running:'进行中'};
let viewer,scene=null,revision=null,loadingModel=false,changing=false,seen=0,latest=null,online=false;
try{viewer=physicsView($('physics-viewport'));}catch{$('canvas-fallback').hidden=false;}
function notify(text){$('notice').textContent=text;$('notice').hidden=false;}
function appendLog(text,label='场景',error=false){const row=document.createElement('div');row.className=`log-line${error?' error':''}`;for(const [value,cls] of [[new Date().toLocaleTimeString('zh-CN',{hour12:false}),'log-time'],[label,'log-label'],[text,'']]){const span=document.createElement('span');span.textContent=value;span.className=cls;row.append(span);}$('activity-log').append(row);while($('activity-log').children.length>80)$('activity-log').firstChild.remove();$('activity-log').scrollTop=$('activity-log').scrollHeight;}
const chorus=createChorus(text=>$('chorus-status').textContent=text);
function buttons(){document.querySelectorAll('[data-sim-action]').forEach(b=>b.disabled=!online||!scene||changing);$('stop-scene').disabled=$('reset-scene').disabled=!online||!scene;document.querySelectorAll('[data-scene]').forEach(b=>{b.disabled=changing||!online;b.setAttribute('aria-pressed',String(b.dataset.scene===scene));});}
async function post(url,body){const response=await fetch(appURL(url),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body),signal:AbortSignal.timeout(45000)});const data=await response.json();if(!response.ok)throw new Error(typeof data.detail==='string'?data.detail:'场景指令未被接受');return data;}
const requestId=()=>Array.from(crypto.getRandomValues(new Uint8Array(16)),v=>v.toString(16).padStart(2,'0')).join('');
let requests=Promise.resolve();
function action(name){
  const target=['walk','turn_left','turn_right','nod'].includes(name)?$('duck-target').value:'a';
  if(name==='stop'||name==='reset')chorus.stop();
  requests=requests.then(()=>post('/api/scenes/actions',{name,target,request_id:requestId()})).catch(e=>notify(e.message));return requests;
}
for(const button of document.querySelectorAll('[data-scene]'))button.addEventListener('click',async()=>{
  changing=true;buttons();chorus.stop();$('sim-status').textContent='正在加载官方模型…';$('notice').hidden=true;
  try{await post('/api/scenes/start',{name:`scene_${button.dataset.scene}`,request_id:requestId()});}
  catch(e){notify(e.message);$('sim-status').textContent='物理场景启动失败';}
  finally{changing=false;buttons();}
});
for(const button of document.querySelectorAll('[data-sim-action]'))button.addEventListener('click',async()=>{if(button.dataset.simAction==='chorus')await chorus.enable();await action(button.dataset.simAction);});
$('enable-chorus').addEventListener('click',()=>chorus.enable().catch(e=>notify(e.message)));
$('reset-scene').addEventListener('click',()=>action('reset'));$('stop-scene').addEventListener('click',()=>action('stop'));$('reset-camera').addEventListener('click',()=>viewer?.reset());$('clear-log').addEventListener('click',()=>$('activity-log').replaceChildren());
window.addEventListener('keydown',e=>{if(e.key==='Escape'&&scene)action('stop');});
async function loadModel(state){
  if(loadingModel||revision===state.revision)return;loadingModel=true;
  try{const response=await fetch(appURL('/api/scenes/model'),{cache:'no-store',signal:AbortSignal.timeout(60000)});if(!response.ok)throw new Error('模型加载失败');const model=await response.json();if(latest?.revision!==model.revision)return;viewer?.load(model);revision=model.revision;if(latest?.revision===revision)viewer?.update(latest);$('scene-placeholder').hidden=true;}
  catch(e){notify(e.message);}finally{loadingModel=false;}
}
function update(data){
  const state=data.backend;latest=state;online=true;scene=state.scene;buttons();
  if(data.events.length&&data.events.at(-1).id<seen)seen=0;
  $('sim-status').textContent=state.error?'物理场景异常':'MuJoCo 物理运行中';
  $('scene-title').textContent=scene==='ball'?'单鸭 + 球':'鸭 A + 鸭 B · 共享物理世界';
  $('actions-heading').textContent=scene==='ball'?'练习一次定点踢球':'一起活动';
  $('ball-controls').hidden=scene!=='ball';$('duo-controls').hidden=scene!=='duo';
  $('ball-distance').textContent=state.ball?`${state.ball.displacement_m.toFixed(2)} m`:'—';
  $('ball-contact').textContent=state.ball?(state.ball.contact_feet.map(f=>f==='left'?'左脚':'右脚').join('、')||'尚无'):'—';
  $('duck-contact').textContent=scene==='duo'?state.contacts.ducks:'—';$('sim-speed').textContent=`${state.real_time_factor.toFixed(2)}×`;
  if(state.discovered.length)$('peer-status').textContent=state.discovered.map(p=>`鸭 ${p.observer.toUpperCase()} 发现鸭 ${p.peer.toUpperCase()}，相距 ${p.distance_m.toFixed(2)} m`).join('；');
  else $('peer-status').textContent='未记录发现结果。检测范围 1.2 m / 120°，考虑遮挡。';
  if(state.error)notify(state.error);
  chorus.update(state.chorus);loadModel(state);viewer?.update(state);
  if(data.action)$('action-result').textContent=`${names[data.action.name]??data.action.name} · 进行中`;
  for(const event of data.events){if(event.id<=seen)continue;seen=event.id;const text=event.text.replace(/scene_ball|scene_duo|kick_left|kick_right|find_companion|duo_walk|collide|chorus|turn_left|turn_right|walk|stop|reset|nod/g,k=>names[k]??k).replace(/completed|failed|cancelled/g,k=>statuses[k]);appendLog(text,event.kind==='result'?'执行结果':'物理动作',event.status==='failed');if(event.kind==='result')$('action-result').textContent=text;}
  if(data.error)notify(data.error);
}
let socket,connectionNotice=null,retryDelay=1000;
function notStarted(){
  scene=revision=latest=null;seen=0;viewer?.clear();chorus.stop();buttons();
  $('scene-placeholder').hidden=false;$('sim-status').textContent='选择场景开始';$('scene-title').textContent='等待启动';$('actions-heading').textContent='选择场景后开始';
  $('ball-controls').hidden=$('duo-controls').hidden=true;
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
