import './style.css';
import { createDuckScene } from './duck.js';

const $ = (id) => document.getElementById(id);
const names = {nod:'点头',walk:'前进',turn_left:'左转',turn_right:'右转',stop:'停止',reset:'回到起点'};
let scene;
try { scene = createDuckScene($('viewport')); }
catch { $('canvas-fallback').hidden = false; }
let seen=0, completed=new Set(), reconnectDelay=500;
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
  const response=await fetch(url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  const value=await response.json();if(!response.ok)throw new Error(typeof value.detail==='string'?value.detail:'请求参数或服务状态异常');return value;
}
async function action(name){
  try { await post('/api/actions',{name,request_id:crypto.randomUUID()}); }
  catch(error){notify(error.message);}
}
document.querySelectorAll('[data-action]').forEach(button=>button.addEventListener('click',()=>action(button.dataset.action)));
$('reset-camera').addEventListener('click',()=>scene?.resetCamera());
$('clear-log').addEventListener('click',()=>{$('activity-log').replaceChildren();});
window.addEventListener('keydown',e=>{if(e.key==='Escape')action('stop');});
function connect(){
  const ws=new WebSocket(`${location.protocol==='https:'?'wss':'ws'}://${location.host}/ws`);
  ws.onopen=()=>{reconnectDelay=500;$('connection-label').textContent='本地工作台已连接';$('connection-dot').classList.remove('offline')};
  ws.onmessage=event=>{
    const data=JSON.parse(event.data);if(data.type!=='state')return;
    scene?.update(data.backend);
    $('current-action').textContent=names[data.action?.name]??'待机';
    $('duck-mood').innerHTML=`<i></i>${data.action?'正在'+(names[data.action.name]??'执行动作'):'正在等待你的指令'}`;
    $('velocity').textContent=Number(data.backend.velocity?.forward??0).toFixed(2);
    for(const event of data.events){
      if(event.id<=seen)continue;seen=event.id;
      if(event.status==='completed')completed.add(event.action_id);
      const text=event.text.replace(/nod|walk|turn_left|turn_right|stop|reset/g,key=>names[key]);
      appendLog(text,event.kind==='action'?'动作请求':'执行结果',event.status==='failed');
    }
    $('action-count').textContent=String(completed.size).padStart(2,'0');
    if(data.error)notify(data.error);
  };
  ws.onclose=()=>{$('connection-label').textContent='连接中断 · 正在重连';$('connection-dot').classList.add('offline');setTimeout(connect,reconnectDelay);reconnectDelay=Math.min(reconnectDelay*2,5000)};
}connect();
