import './style.css';
import { createDuckScene } from './duck.js';
import { setupVoice } from './voice.js';
import { appURL } from './urls.js';
import { createSocket } from './transport.js';

import { setupRoom } from './room.js';
await setupRoom();

const $ = (id) => document.getElementById(id);
const names = {nod:'点头',walk:'前进',turn_left:'左转',turn_right:'右转',stop:'停止',reset:'回到起点',flash_step:'闪身步',bear_shake:'狗熊哆嗦毛'};
const actionNames = new RegExp(Object.keys(names).join('|'),'g');
let scene;
try { scene = createDuckScene($('viewport')); }
catch { $('canvas-fallback').hidden = false; }
let seen=0, completed=new Set(), reconnectDelay=500;
let backendKind='preview',voiceState='disconnected';
function scope(){
  $('scope-note').textContent=(backendKind==='preview'?'动画预览为原创示意形象，不进行物理计算。':'正在连接官方 robotd；本页鸭子仅为示意，物理画面请查看 MuJoCo 窗口。')+
    (['ready','listening','thinking','speaking'].includes(voiceState)?'灵矽语音已连接。':'灵矽语音尚未连接。');
}
window.addEventListener('duckking-voice-state',event=>{voiceState=event.detail;scope()});
export function notify(message) { $('notice').textContent=message;$('notice').hidden=false; }
export function appendLog(text, label='系统', error=false) {
  const log=$('activity-log');log.querySelector('.empty-log')?.remove();
  const row=document.createElement('div');row.className=`log-line${error?' error':''}`;
  const time=document.createElement('span');time.className='log-time';time.textContent=new Date().toLocaleTimeString('zh-CN',{hour12:false});
  const tag=document.createElement('span');tag.className='log-label';tag.textContent=label;
  const body=document.createElement('span');body.textContent=text;
  row.append(time,tag,body);log.append(row);
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
  // Serialize request acceptance, not motion duration, so a rapid Stop cannot
  // arrive before the preceding Walk request on another HTTP connection.
  actionRequests=actionRequests.then(()=>post('/api/actions',{name,request_id:crypto.randomUUID()}))
    .catch(error=>notify(error.message));
  return actionRequests;
}
document.querySelectorAll('[data-action]').forEach(button=>button.addEventListener('click',()=>action(button.dataset.action)));
$('reset-camera').addEventListener('click',()=>scene?.resetCamera());
$('clear-log').addEventListener('click',()=>{$('activity-log').replaceChildren();});
window.addEventListener('keydown',e=>{if(e.key==='Escape')action('stop');});
function connect(){
  const ws=createSocket('ws');
  ws.onopen=()=>{reconnectDelay=500;$('connection-label').textContent='本地工作台已连接';$('connection-dot').classList.remove('offline')};
  ws.onmessage=event=>{
    const data=JSON.parse(event.data);if(data.type!=='state')return;
    backendKind=data.backend.kind;scope();
    $('backend-badge').textContent=backendKind==='preview'?'动画预览':'robotd 适配';
    $('data-source').textContent=backendKind==='preview'?'本地预览':data.backend.connected?'官方 robotd':'未连接';
    $('reset-position').disabled=backendKind!=='preview';
    if(data.backend.error&&backendKind!=='preview')notify(data.backend.error);
    scene?.update(data.backend);
    $('current-action').textContent=names[data.action?.name]??'待机';
    const mood=data.action?'正在'+(names[data.action.name]??'执行动作')+(data.action.phase?' · '+data.action.phase:''):'正在等待你的指令';
    $('duck-mood').replaceChildren(document.createElement('i'),document.createTextNode(mood));
    $('velocity').textContent=Number(data.backend.velocity?.forward??0).toFixed(2);
    for(const event of data.events){
      if(event.id<=seen)continue;seen=event.id;
      if(event.status==='completed')completed.add(event.action_id);
      const text=event.text.replace(actionNames,key=>names[key]);
      appendLog(text,({action:'动作请求',phase:'动作节拍',result:'执行结果'})[event.kind]??'系统',event.status==='failed');
    }
    $('action-count').textContent=String(completed.size).padStart(2,'0');
    if(data.error)notify(data.error);
  };
  ws.onclose=()=>{$('connection-label').textContent='连接中断 · 正在重连';$('connection-dot').classList.add('offline');setTimeout(connect,reconnectDelay);reconnectDelay=Math.min(reconnectDelay*2,5000)};
}connect();
setupVoice({appendLog,notify});
