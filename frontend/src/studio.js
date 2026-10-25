import './style.css';
import './scenarios.css';
import './studio.css';
import {StudioChoir} from './studio-choir.js';
import {STUDIO_SCENES} from './studio-catalog.js';
import {api,pause} from './demo-runtime.js';
import {physicsView} from './physics-view.js';
import {createPhysicsModelLoader} from './model-loader.js';
import {setupVoice} from './voice.js';
import {setupRoom} from './room.js';
import {appURL,currentRoom} from './urls.js';
import {createSocket} from './transport.js';

await setupRoom();
const $=id=>document.getElementById(id),loader=createPhysicsModelLoader(),choir=new StudioChoir();
let viewer,selected=null,revision=null,latest=null,loading=false,connected=false,voiceState='disconnected',epoch=0,seen=0;
try{viewer=physicsView($('physics-viewport'))}catch{$('scene-placeholder').textContent='WebGL 无法启动；仍可查看任务结果。'}
const notify=text=>{$('notice').textContent=text;$('notice').hidden=false};
function appendLog(text,label='任务',error=false){const row=document.createElement('div');row.className=`log-line${error?' error':''}`;const tag=document.createElement('span');tag.className='log-label';tag.textContent=label;const body=document.createElement('span');body.textContent=text;row.append(tag,body);$('activity-log').append(row);while($('activity-log').children.length>80)$('activity-log').firstChild.remove()}
const voiceBusy=()=>!['disconnected','error','busy','awaiting_binding'].includes(voiceState);
function controls(){
 document.querySelectorAll('[data-studio]').forEach(b=>b.disabled=loading||voiceBusy()||!STUDIO_SCENES.find(s=>s.id===b.dataset.studio).ready);
 $('stop-studio').disabled=!selected||!connected;
 document.querySelectorAll('[data-studio-command]').forEach(b=>b.disabled=loading||!selected||!connected);
}
for(const [i,scene] of STUDIO_SCENES.entries()){
 const b=document.createElement('button');b.dataset.studio=scene.id;b.textContent=`${String(i+1).padStart(2,'0')} ${scene.title}${scene.ready?'':' · 待接入'}`;b.disabled=!scene.ready;b.addEventListener('click',()=>select(scene));$('studio-list').append(b);
}
async function invoke(name,args,rehearsalText){
 try{
 if(name==='duck_conduct'&&args.operation==='start')await choir.enable();const state=await api('api/studio/action',currentRoom,{body:{name,arguments:args,...(rehearsalText?{rehearsal_text:rehearsalText}:{})}});appendLog(state.task?.message??'请求已受理，等待实际执行结果','本地排练');renderStudio(state);if(state.message)appendLog(state.message,'任务反馈');if(state.observation)appendLog(`球的位置已读取 · 左脚${state.observation.ready.left?'可踢':'未准备好'} · 右脚${state.observation.ready.right?'可踢':'未准备好'}`,'仿真状态')}catch(e){notify(e.message)}
}
async function select(scene){
 if(loading||voiceBusy())return;
 void choir.enable();choir.stop();
 loading=true;selected=null;controls();$('notice').hidden=true;$('scene-placeholder').hidden=false;$('scene-placeholder').textContent='正在准备官方场景…';
 const mine=++epoch;
 try{
  const rec=await api('api/scenes/start',currentRoom,{body:{name:`scene_${scene.scene}`,request_id:crypto.randomUUID()}});
  let result=rec;
  for(let i=0;result.status==='running'&&i<300;i++){await pause(100);result=await api(`api/scenes/actions/${rec.id}`,currentRoom)}
  if(result.status!=='completed')throw Error(result.error??'场景准备超时');
  await api('api/studio/select',currentRoom,{body:{scene:scene.id}});
  const state=await api('api/scenes/state',currentRoom);await model(state.backend);
  if(mine!==epoch)return;
  selected=scene;$('scene-title').textContent=scene.title;$('studio-prompt').textContent=scene.prompt;
  $('studio-controls').replaceChildren();
  for(const [label,name,args,text] of scene.controls??[]){const b=document.createElement('button');b.dataset.studioCommand=name;b.textContent=label;b.addEventListener('click',()=>invoke(name,args,text));$('studio-controls').append(b)}
  document.querySelectorAll('[data-studio]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.studio===scene.id)));
  renderStudio(state.studio);$('scene-placeholder').hidden=true;
  $('voice-lab').hidden=!['voice','persona'].includes(scene.id);
  $('persona-settings').hidden=scene.id!=='persona';
  if(['voice','persona'].includes(scene.id))await loadVoiceProfiles();
 }catch(e){notify(e.message)}finally{loading=false;controls()}
}
async function model(state){
 if(revision===state.revision)return;
 const url=appURL('api/scenes/model.dkm.gz');url.searchParams.set('room',currentRoom);
 const data=await loader(url,state.revision,{signal:AbortSignal.timeout(60000)});
 viewer?.load(data);viewer?.frameScene(state.scene);viewer?.update(state);revision=state.revision;
}
function renderStudio(studio){
 if(!studio)return;
 const task=studio.task??{},labels={idle:'等待指令',running:'正在执行',completed:'已完成',failed:'未完成',cancelled:'已取消',paused:'已暂停'};
 $('task-status').textContent=[task.title,labels[task.status]??task.status,task.step?`第 ${task.step} 步`:''].filter(Boolean).join(' · ');
 const details=[task.message];
 if(studio.singer)details.push(`正在演唱：鸭 ${studio.singer.toUpperCase()}；下一位：${studio.queue.map(s=>s.toUpperCase()).join('、')||'无'}`);
 if(studio.draft)details.push(`待确认暗号：${studio.draft.name}，第 ${studio.draft.version} 版`);
 if(studio.game?.prefix)details.push(`当前口令：${studio.game.prefix}；通过 ${studio.game.accepted}，拒绝 ${studio.game.refused}`);
 if(studio.discussion?.facts?.length)details.push(`已确认：${studio.discussion.facts.join('；')}。下一问：${studio.discussion.question}`);
 if(studio.focus_remaining_s!==null&&studio.focus_remaining_s!==undefined)details.push(`还剩 ${Math.ceil(studio.focus_remaining_s)} 秒`);
 $('studio-detail').textContent=details.filter(Boolean).join(' · ');
}
function connect(){
 const socket=createSocket('scene-ws');
 socket.onmessage=event=>{
  const data=JSON.parse(event.data);connected=true;controls();
  if(data.type==='state'){
   latest=data;viewer?.update(data.backend);choir.update(data.backend.seated_choir);$('physics-viewport').dataset.musicEvidence=JSON.stringify(choir.scheduled);renderStudio(data.studio);
   $('sim-status').textContent=data.backend.error?'物理场景异常':'MuJoCo 物理运行中';
   for(const event of data.events??[]){if(event.id<=seen)continue;seen=event.id;appendLog(event.text,'实际动作',event.status==='failed')}
   if(data.backend.error)notify(data.backend.error);
  }else if(data.type==='scene_error')notify(data.message);
  if(socket.readyState===1)socket.send('next');
 };
 socket.onclose=()=>{choir.stop();connected=false;controls();$('sim-status').textContent='场景连接中断 · 正在重连';setTimeout(connect,1500)};
 window.addEventListener('pagehide',()=>{socket.onclose=null;socket.close()},{once:true});
}
$('reset-camera').addEventListener('click',()=>viewer?.reset());
$('stop-studio').addEventListener('click',()=>{choir.stop();voice.interrupt();void invoke('duck_task',{operation:'cancel'})});
$('enable-sound').addEventListener('click',()=>void choir.enable());
$('clear-log').addEventListener('click',()=>$('activity-log').replaceChildren());
window.addEventListener('keydown',e=>{if(e.code==='Escape'&&selected){choir.stop();voice.interrupt();void invoke('duck_task',{operation:'cancel'})}});
window.addEventListener('duckking-voice-state',e=>{voiceState=e.detail.state;controls()});
const voice=setupVoice({appendLog,notify,endpoint:'scene-voice',cloudOnly:true});connect();

async function loadVoiceProfiles(){
 const data=await api('api/voice/profiles',currentRoom);
 for(const [id,entries] of [['voice-profile',data.voices],['voice-persona',[{key:'default',label:'默认鸭王'},...data.personas]]]){
  const select=$(id);select.replaceChildren();
  for(const entry of entries){const option=document.createElement('option');option.value=entry.key;option.textContent=entry.label;select.append(option)}
  if(!entries.length){const option=document.createElement('option');option.textContent='尚未配置克隆音色';option.value='';select.append(option)}
 }
 $('apply-voice').disabled=!data.voices.length;
}
$('apply-voice').addEventListener('click',()=>{
 if(voice.state!=='ready'){notify('先连接灵矽，等待就绪后再切换声音');return}
 voice.send({type:'voice_style',settings:{profile:$('voice-profile').value,pitch:Number($('voice-pitch').value),speed:1,emotion:'neutral'}});
});
$('apply-persona').addEventListener('click',()=>{
 if(voice.state!=='ready'){notify('先连接灵矽，等待就绪后再切换角色');return}
 voice.clearPlayback();voice.send({type:'persona',settings:{persona:$('voice-persona').value}});
 appendLog('正在重连到所选角色，旧会话将结束','角色切换');
});
for(const audio of document.querySelectorAll('[data-voice-sample]'))audio.src=appURL(`voice-samples/${audio.dataset.voiceSample}.wav`);

window.addEventListener('pagehide',()=>{choir.stop();if(!selected)return;const url=appURL('api/scenes/actions');url.searchParams.set('room',currentRoom);void fetch(url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:'stop'}),keepalive:true}).catch(()=>{});viewer?.dispose()});
