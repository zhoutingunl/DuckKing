import {setLogText} from './ui-language.js';
import {requestId} from './ids.js';
import {actionLabels,actionEventText,appendActionDetails} from './action-labels.js';
import './site-nav.js';
import './style.css';
import { createDuckScene } from './duck.js';
import { setupVoice } from './voice.js';
import { appURL } from './urls.js';
import { createSocket } from './transport.js';
import { initUILanguage } from './ui-language.js';
import {setupGroundPreference} from './ground-preference.js';
import {setupWorkbenchPhysics} from './workbench-physics.js';

import { setupRoom } from './room.js';
await setupRoom();
await initUILanguage();

const $ = (id) => document.getElementById(id);
const names = {...actionLabels,reset:'回到起点'};
const modeURL = new URL(location.href);
const health = await fetch(appURL('api/health'), {signal: AbortSignal.timeout(3000)})
  .then(response => response.ok ? response.json() : null).catch(() => null);
let backendKind = health?.backend ?? 'preview';
const usesPhysics = backendKind !== 'robotd' && modeURL.searchParams.get('view') !== 'preview';
const modeLink = $('workbench-mode-link');
if (usesPhysics) modeURL.searchParams.set('view', 'preview');
else modeURL.searchParams.delete('view');
modeLink.href = modeURL.href;
modeLink.textContent = usesPhysics ? '打开动画预览' : '打开 MuJoCo 平地动作';
modeLink.hidden = backendKind === 'robotd';
$('viewport').hidden = usesPhysics;
$('workbench-physics').hidden = !usesPhysics;
$('workbench-stage').setAttribute('aria-label', usesPhysics ? 'MuJoCo 仿真' : '鸭子预览');
if (!usesPhysics) $('action-heading').textContent = '先动起来';
let scene;
if (!usesPhysics) {
  try { scene = createDuckScene($('viewport'),{onLoad:timing=>appendLog(
    `官方外观${timing.result==='ready'?'已显示':'加载失败'} · ${(timing.elapsed_ms/1000).toFixed(1)} 秒${['persistent','http'].includes(timing.cache)?' · 使用缓存':''}`,
    '模型加载',timing.result!=='ready')}); }
  catch { $('canvas-fallback').hidden = false; }
}
let seen=0, completed=new Set(), physicsCompleted=0, reconnectDelay=500, physics, preview;
let voiceState='disconnected',voiceMode='cloud',voiceRoute='cloud';
function scope(){
  $('scope-note').textContent=(usesPhysics?'平地动作使用 MuJoCo 物理仿真。':backendKind==='preview'?'使用官方 MicroDuck 外观的动画预览，不进行物理计算。':'正在连接官方 robotd；本页为官方外观动画示意，物理画面请查看 MuJoCo 窗口。')+
    (voiceMode==='local_first'?(voiceRoute==='cloud_fallback'?'当前指令已选择灵矽处理。':['ready','listening','thinking'].includes(voiceState)?'本地优先语音已启用，未匹配时转交灵矽。':'本地优先语音尚未启用。'):['ready','listening','thinking','speaking'].includes(voiceState)?'灵矽语音已连接。':'灵矽语音尚未连接。');
}
window.addEventListener('duckking-voice-state',event=>{
  if(typeof event.detail==='string')voiceState=event.detail;
  else{voiceState=event.detail.state;voiceMode=event.detail.mode;voiceRoute=event.detail.route}
  scope();
});
export function notify(message) { $('notice').textContent=message;$('notice').hidden=false; }
export function appendLog(text, label='系统', error=false, raw=null) {
  const log=$('activity-log');log.querySelector('.empty-log')?.remove();
  const row=document.createElement('div');row.className=`log-line${error?' error':''}`;
  const time=document.createElement('span');time.className='log-time';time.textContent=new Date().toLocaleTimeString('zh-CN',{hour12:false});
  const tag=document.createElement('span');tag.className='log-label';tag.textContent=label;
  const body=document.createElement('span');setLogText(body,text,label);
  row.append(time,tag,body);if(raw&&raw!==text)appendActionDetails(row,raw);log.append(row);
  while(log.children.length>80)log.firstChild.remove();log.scrollTop=log.scrollHeight;
}
export async function post(url,body={}) {
  const response=await fetch(appURL(url),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  let value;
  try{value=await response.json()}
  catch{throw new Error(response.ok?'本地服务返回了无效响应。':`本地后端请求失败（HTTP ${response.status}），请检查服务与端口。`)}
  if(!response.ok)throw new Error(typeof value?.detail==='string'?value.detail:'请求参数或服务状态异常');return value;
}
let actionRequests=Promise.resolve();
function action(name){
  if(usesPhysics){
    $('flat-action-notice').hidden=true;
    return physics.action(name);
  }
  // Serialize request acceptance, not motion duration, so a rapid Stop cannot
  // arrive before the preceding Walk request on another HTTP connection.
  actionRequests=actionRequests.then(()=>post('/api/actions',{name,request_id:requestId()}))
    .catch(error=>notify(error.message));
  return actionRequests;
}
document.querySelectorAll('[data-action]').forEach(button=>button.addEventListener('click',()=>action(button.dataset.action)));
$('reset-camera').addEventListener('click',()=>usesPhysics?physics.resetCamera():scene?.resetCamera());
$('scene-settings-toggle').addEventListener('click',()=>{const shown=$('scene-settings').hidden;$('scene-settings').hidden=!shown;$('scene-settings-toggle').setAttribute('aria-expanded',String(shown))});
$('clear-log').addEventListener('click',()=>{$('activity-log').replaceChildren();});
window.addEventListener('keydown',e=>{if(e.key==='Escape')action('stop');});
function renderAction(label, status, velocity){
  $('current-action').textContent=label;
  if($('duck-mood').textContent!==status)$('duck-mood').replaceChildren(document.createElement('i'),document.createTextNode(status));
  $('velocity').textContent=Number(velocity??0).toFixed(2);
}
function renderPreview(){
  $('backend-badge').textContent=backendKind==='preview'?'动画预览':'robotd 适配';
  $('data-source').textContent=backendKind==='preview'?'本地预览':preview?.backend.connected?'官方 robotd':'未连接';
  $('reset-position').disabled=backendKind!=='preview';
  const action=preview?.action;
  const mood=action?'正在'+(names[action.name]??'执行动作')+(action.phase?' · '+action.phase:''):'正在等待你的指令';
  renderAction(names[action?.name]??'待机',mood,preview?.backend.velocity?.forward);
  $('action-count').textContent=String(completed.size).padStart(2,'0');
}
if (!usesPhysics) renderPreview();
scope();
if (usesPhysics) physics=setupWorkbenchPhysics({
  appendLog,
  notify(message){
    $('flat-action-notice').textContent=message;$('flat-action-notice').hidden=!message;
  },
  onState(state,label,status){
    $('data-source').textContent=state?.connected?'MuJoCo 仿真':'未连接';
    renderAction(label??'待机',status??label??'正在等待你的指令',state?.velocity?.forward);
  },
  onBusy(busy){
    for(const button of document.querySelectorAll('[data-action]:not([data-action=stop]),#prepare-physics')){
      button.disabled=busy;
    }
  },
  onCompleted(){$('action-count').textContent=String(++physicsCompleted).padStart(2,'0')},
});
setupVoice({appendLog,notify,endpoint:usesPhysics?'/scene-voice':'/voice',
  listenUnavailable:()=>physics?.voiceUnavailable()??'',requireReady:true});
setupGroundPreference($('ground-style'),style=>{
  $('viewport').dataset.groundStyle=style;
  scene?.setGround(style);physics?.setGround(style);
},{randomDefault:true});
function connect(){
  const ws=createSocket('ws');
  ws.onopen=()=>{reconnectDelay=500;$('connection-label').textContent='本地工作台已连接';$('connection-dot').classList.remove('offline')};
  ws.onmessage=event=>{
    const data=JSON.parse(event.data);if(data.type!=='state')return;
    if(usesPhysics)return;
    preview=data;backendKind=data.backend.kind;scope();
    renderPreview();
    if(data.backend.error&&backendKind!=='preview')notify(data.backend.error);
    scene?.update(data.backend);
    for(const event of data.events){
      if(event.id<=seen)continue;seen=event.id;
      if(event.status==='completed')completed.add(event.action_id);
      const text=actionEventText(event);
      appendLog(text,({action:'动作请求',phase:'动作节拍',result:'执行结果'})[event.kind]??'系统',event.status==='failed',event.text);
    }
    $('action-count').textContent=String(completed.size).padStart(2,'0');
    if(data.error)notify(data.error);
  };
  ws.onclose=()=>{$('connection-label').textContent='连接中断 · 正在重连';$('connection-dot').classList.add('offline');setTimeout(connect,reconnectDelay);reconnectDelay=Math.min(reconnectDelay*2,5000)};
}connect();
