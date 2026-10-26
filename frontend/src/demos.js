import {measurement,loadMetrics,afterFrame} from './experience.js';
import './style.css';
import './demos.css';
import { DEMOS, ACTION_NAMES, AUDIO_VERSION } from './demo-catalog.js';
import { DemoRun, DemoVoice, api, action, until, pause, pcmWave, stopped, matchesCloudActions } from './demo-runtime.js';
import { VoiceAudio } from './audio-output.js';
import { physicsView } from './physics-view.js';
import { createPhysicsModelLoader } from './model-loader.js';
import { createChorus } from './chorus.js';
import { playChorale, PART_NAMES } from './chorale-demo.js';
import { playTableChoir, decodeTracks, checkOffset, loadBuiltinSong, TABLE_PARTS, TABLE_SECONDS } from './table-choir.js';
import {playSeatedChoir,SEATED_SECONDS} from './seated-choir.js';
import { TABLE_SCORES } from './table-scores.js';
import { DuckSocket } from './transport.js';
import { appURL, currentRoom } from './urls.js';
import { setupRoom } from './room.js';
import { setupVoice } from './voice.js';

await setupRoom();
const $=id=>document.getElementById(id),output=new VoiceAudio(),clips=new Map(),loadPhysicsModel=createPhysicsModelLoader(),stages=new Map();
const chorus=createChorus(()=>{},{getContext:()=>output.context()});let current=null,selected=-1,serial=Promise.resolve();
const pendingStageMembers=new Map();let selectionState=null;
let stageInteractive=false,selectionQueue=Promise.resolve(),selectionVersion=-1,selectionInstance=null;
let tableTracks=null,trackError=null,trackLoading=false,trackEpoch=0,preview=null;
const controlsBusy=value=>document.querySelectorAll('[data-idle-control]').forEach(el=>{el.disabled=value});
const message=(role,text)=>{$('caption-role').textContent=role;$('caption').textContent=text};
const status=text=>$('show-status').textContent=text;
function entry(text,state='completed'){const item=document.createElement('li');item.textContent=text;item.dataset.status=state;$('demo-timeline').append(item);}
function error(text){$('demo-notice').textContent=text;$('demo-notice').hidden=false;}
function mode(){const live=$('demo-mode').value==='live';$('mode-note').textContent=live?'预录指令发往真实灵矽，现场识别和回答；依赖网络。':'本地编排 + 实时物理仿真；不使用麦克风。';$('voice-source').textContent=live?'预录指令 · 灵矽实时回答':'预录台词 · 本地编排';}
$('demo-mode').addEventListener('change',mode);
const stageVoice=setupVoice({endpoint:'/scene-voice',cloudOnly:true,appendLog:(text,label)=>entry(label+' · '+text),notify:error,beforeListen:async()=>{const stage=stages.get(currentRoom);if(!current||(!stageInteractive&&!current.completed)||DEMOS[selected]?.id!=='stage')throw Error('请先进入第13幕现场互动');await syncStageOrder(stage)}});
const stageVoiceBusy=()=>!['disconnected','error','busy','awaiting_binding'].includes(stageVoice.state);
$('stage-play').addEventListener('change',()=>{stageInteractive=$('stage-play').value==='interactive'});
function renderSelection(state){
  if(state.instance===selectionInstance&&state.selection_version<selectionVersion)return;
  if(selectionInstance!==state.instance)pendingStageMembers.clear();
  selectionInstance=state.instance;selectionVersion=state.selection_version;selectionState=state;
  for(const input of document.querySelectorAll('[data-stage-member]'))input.checked=pendingStageMembers.get(input.value)?.checked??state.selected.includes(input.value);
  $('stage-hint').textContent=state.selected.length?`已选中：${state.selected.map(c=>'鸭 '+c.toUpperCase()).join('、')}。再次点击可取消；翻滚使用当前选中集合。`:'未选中鸭子。点击鸭子或勾选 A—D，再让它们翻跟头。';
}
function stageSelect(change,stage=stages.get(currentRoom)){
  const state=stage.latest.backend,body={...change,order:stage.viewer.screenOrder(),revision:state.revision,instance:state.stage.instance};
  const pending=selectionQueue.catch(()=>{}).then(()=>api('api/scenes/stage/selection',currentRoom,{body}));
  selectionQueue=pending;return pending.then(result=>{renderSelection(result);stage.viewer.selection(result)});
}
async function syncStageOrder(stage){await selectionQueue;await stageSelect({operation:'order'},stage)}
function stageInteraction(){
  const stage=stages.get(currentRoom);if(!stage||stage.latest?.backend.scene!=='stage')return;
  stage.viewer.interaction(async selection=>{
    try{
      if(selection.revision!==stage.latest.backend.revision||selection.instance!==stage.latest.backend.stage.instance)throw Error('舞台已重置，请重新点选');
      if(selection.mode==='poke')await stageAction('stage_poke',{member:selection.target});
      else await stageSelect({operation:'toggle',target:selection.target});
    }catch(e){error(e.message)}
  },$('stage-pointer').value);
}
$('stage-pointer').addEventListener('change',stageInteraction);
for(const input of document.querySelectorAll('[data-stage-member]'))input.addEventListener('change',()=>{
  const pending={checked:input.checked};pendingStageMembers.set(input.value,pending);
  stageSelect({operation:'toggle',target:input.value}).catch(e=>error(e.message)).finally(()=>{
    if(pendingStageMembers.get(input.value)===pending)pendingStageMembers.delete(input.value);
    if(selectionState)renderSelection(selectionState);
  });
});
async function stageAction(name,options={member:'selected'}){
  if(!current||DEMOS[selected]?.id!=='stage'){error('请先选择现场互动并重演第13幕。');return}
  if(current&&!stageInteractive&&!current.completed){error('自动演出中请先停止，再选择现场互动。');return}
  if(stageVoiceBusy()&&!['ready'].includes(stageVoice.state)){error('请等待本轮语音完成，或停止当前演出。');return}
  const run=current,signal=run.signal;
  try{await selectionQueue;$('demo-notice').hidden=true;status('本地操作 · '+ACTION_NAMES[name]);$('theatre-result')?.remove();const result=await action(currentRoom,name,signal,options);if(current!==run||run.signal.aborted)return;entry(`本地点选 · ${ACTION_NAMES[name]} · ${result.status}`,result.status);if(result.status!=='completed')throw Error(result.error??'任务未完成');status('本地操作完成 · 可继续操作')}catch(e){if(e.name!=='AbortError'){error(e.message);status('本地操作未完成 · 可重试')}}
}
for(const name of ['gather','roll','dance'])$('stage-'+name).addEventListener('click',()=>stageAction('stage_'+name));
window.addEventListener('duckking-voice-state',()=>{if(stageVoiceBusy()&&current?.live===false&&!stageInteractive&&!current.completed)void stop('已停止自动演示，请选择现场互动后连接语音')});

$('program-count').textContent=`${DEMOS.length} 幕`;
$('table-tracks').addEventListener('change',async event=>{
  const epoch=++trackEpoch;tableTracks=null;trackError='音源尚未就绪';trackLoading=true;$('track-note').textContent='正在读取本机音频…';
  try{const tracks=await decodeTracks([...event.target.files],output.context());if(epoch!==trackEpoch)return;tableTracks=tracks;trackError=null;$('track-note').textContent=`已选 ${tracks.buffers.length} 轨：${tracks.names.join('、')}。演示使用 ${TABLE_SECONDS} 秒片段。`}
  catch(e){if(epoch===trackEpoch){trackError=e.message;$('track-note').textContent=e.message+'；请重新选择或恢复内置音源。'}}
  finally{if(epoch===trackEpoch)trackLoading=false}
});
function resetTracks(){trackEpoch++;tableTracks=null;trackError=null;trackLoading=false;$('table-tracks').value='';$('table-offset').value='0';const name=$('table-song').value;$('track-note').textContent=TABLE_SCORES[name]?.description??(name==='original'?'独立原创练声曲《桌边的星光》，与《夜空中最亮的星》的旋律无关。':'《夜空中最亮的星》使用你提供的录音。叠唱版由鸭 D 轻声主唱，三层鸭声和声突出；不是独立人声分轨。')}
$('clear-tracks').addEventListener('click',resetTracks);$('table-song').addEventListener('change',resetTracks);
for(const button of document.querySelectorAll('[data-table-song]'))button.addEventListener('click',()=>{$('table-song').value=button.dataset.tableSong;resetTracks();start(DEMOS.findIndex(d=>d.id==='tabletop'))});
for(const [button,id,text,role] of [['preview-human','football-left','请用左脚踢球。','人类指令 · 试听'],['preview-duck','interview-joke','恭喜录用，工资是每天两句夸奖。','小鸭台词 · 试听']]){
  $(button).addEventListener('click',async()=>{
    if(current)return;preview?.abort();preview=new AbortController();const signal=preview.signal,enabled=output.resume({gesture:true});output.clear();
    try{if(!await enabled)throw new Error('请再点击一次以启用声音');await speak(id,text,role,{signal})}catch(e){if(e.name!=='AbortError')error(e.message)}
  });
}
for(const [index,demo] of DEMOS.entries()){
  const button=document.createElement('button');button.className='program-item';button.dataset.demo=demo.id;button.setAttribute('aria-current','false');
  const n=document.createElement('span');n.textContent=String(index+1).padStart(2,'0');const text=document.createElement('div'),title=document.createElement('strong'),detail=document.createElement('small');title.textContent=demo.title;detail.textContent=demo.hook;text.append(title,detail);button.append(n,text);button.addEventListener('click',()=>start(index));$('demo-list').append(button);
}
async function clip(id,signal){
  if(clips.has(id))return clips.get(id);
  const url=appURL(`demo-audio/${id}.wav`);url.searchParams.set('v',AUDIO_VERSION);
  const response=await fetch(url,{signal});if(!response.ok)throw new Error('预录台词加载失败，请刷新后重试');
  const pcm=pcmWave(await response.arrayBuffer());clips.set(id,pcm);return pcm;
}
async function speak(id,text,role,run,{wait=true}={}){
  message(role,text);const pcm=await clip(id,run.signal);run.signal.throwIfAborted();
  if(output.context().state!=='running')throw new Error('浏览器声音已暂停，请重新点击节目以启用声音');
  const samples=Float32Array.from(pcm,v=>v/32768);output.schedule(samples,16000,{local:true});
  if(wait)await pause(pcm.length/16+150,run.signal);
  return pcm;
}
function connectStage(room,container){
  container.querySelectorAll('canvas').forEach(canvas=>canvas.remove());
  const viewer=physicsView(container),socket=new DuckSocket('scene-ws'),stage={room,viewer,socket,latest:null,revision:null,loading:null,error:null};
  socket.onopen=()=>socket.send(JSON.stringify({type:'join_room',room}));
  socket.onmessage=event=>{
    const data=JSON.parse(event.data);if(data.type==='state'){
      stage.latest=data;viewer.update(data.backend);if(data.backend.scene==='stage'){
        $('stage-state').textContent=({scattered:'四鸭散落，等待召集',gather_rising:'集结前起身',gathering:'集结排队中',gather_sitting:'排好队，一起坐下',contact_sit:'碰撞后坐下，再起身',lined_up:'排队完成，已坐稳',roll_rising:'四鸭起身，准备翻滚',roll_recovering:'翻滚后恢复站稳',roll_sitting:'翻滚后就地坐下',dance_rising:'选中鸭起身，准备齐舞',rolling:'点名前滚翻',returning:'正在归位',dancing:'选中鸭同拍齐舞',completed:'表演完成',failed:'任务未完成',stopped:'已停止'}[data.backend.stage.phase]??data.backend.stage.phase);
        renderSelection(data.backend.stage);
      }if(room===currentRoom)chorus.update(data.backend.chorus);
    }else if(data.type==='scene_error')stage.error=data.message||'物理场景异常';
    if(socket.readyState===1)socket.send('next');
  };
  socket.onclose=()=>{stage.error='场景连接中断，请重新点选节目';if(current?.rooms.has(room)&&!current.signal.aborted)void stop('场景连接中断，演示已停止');};
  stages.set(room,stage);return stage;
}
async function prepare(room,scene,run,second=false){
  const experience=measurement('load',{room}),metrics={};
  try{
  run.signal.throwIfAborted();run.rooms.add(room);status('正在准备官方物理场景…');
  let stage=stages.get(room);if(stage?.socket.readyState===3){stage.viewer.dispose();stages.delete(room);stage=null}
  stage??=connectStage(room,$(second?'demo-second':'demo-viewport'));
  if(second)$('demo-second').hidden=false;
  else{$('stage-placeholder').hidden=false;$('stage-placeholder').textContent='正在加载官方场景外观…';}
  const record=await api('api/scenes/start',room,{body:{name:'scene_'+scene,request_id:crypto.randomUUID()},signal:run.signal});
  let state;
  const end=performance.now()+60000;
  do{
    if(performance.now()>end)throw new Error('物理场景准备超时');await pause(100,run.signal);
    state=await api('api/scenes/state',room,{signal:run.signal});
    if(state.error)throw new Error(state.error);
  }while(state.backend.scene!==scene||state.action?.id===record.id);
  const rev=state.backend.revision,url=appURL('api/scenes/model.dkm.gz');url.searchParams.set('room',room);
  const model=await loadPhysicsModel(url,rev,{signal:AbortSignal.any([run.signal,AbortSignal.timeout(60000)]),metrics});
  const assembling=performance.now();
  run.signal.throwIfAborted();if(stage.revision!==rev){stage.viewer.load(model);stage.revision=rev;}
  stage.viewer.frameScene(scene);
  stage.viewer.update(stage.latest?.backend.revision===rev?stage.latest.backend:state.backend);
  if(!second)$('stage-placeholder').hidden=true;
  metrics.assemble_ms=performance.now()-assembling;const drawing=performance.now();stage.viewer.renderNow();await afterFrame();metrics.first_frame_ms=performance.now()-drawing;
  experience.finish('completed',{...loadMetrics(metrics),scene_ms:Math.round(performance.now()-experience.started)},{cache:metrics.cache??'unknown',scene});
  stage.error=null;status('舞台已就绪');if(scene==='stage'){stage.latest=state;stageInteraction();renderSelection(state.backend.stage)}else stage.viewer.interaction(null);return stage;
  }catch(error){experience.finish(run.signal.aborted?'cancelled':'failed');throw error}
}
async function perform(run,room,name,options={},expectFailure=false){
  const result=await action(room,name,run.signal,options);run.results.push({...result,room});
  entry(`房间 ${room} · ${ACTION_NAMES[name]??name} · ${result.status==='completed'?'完成':result.status==='cancelled'?'已取消':'未完成'}`,result.status);
  if(expectFailure){if(result.status!=='failed'||result.outcome?.verified!==false||result.outcome?.peers?.length!==0)throw new Error('本幕预期“背对同伴时检测失败”，实际结果不符，未继续剧情');}
  else if(result.status!=='completed')throw new Error(result.error||'动作没有完成，后续剧情已停止');
  return result;
}
async function inspect(run,room,label){
  const state=(await api('api/scenes/state',room,{signal:run.signal})).backend;
  if(!state.connected||!state.physics)throw new Error('未取得有效物理状态');
  const lines=[`房间 ${room} · ${state.ducks.length} 只鸭 · MuJoCo 实时运行`];
  if(state.ball)lines.push(`球位移 ${state.ball.displacement_m.toFixed(2)} m；触球脚：${state.ball.contact_feet.map(f=>f==='left'?'左':'右').join('、')||'尚无'}`);
  if(state.grasp)lines.push(`夹持阶段 ${({ready:'待夹取',holding:'已夹稳',carried:'已搬到',released:'已放稳',failed:'未通过',dropped:'已滑落'}[state.grasp.phase]??'进行中')}；搬运 ${(state.grasp.carry_distance_m*100).toFixed(1)} cm；离架 ${(state.grasp.max_lift_clearance_m*1000).toFixed(1)} mm`);
  if(state.scene==='duo')lines.push(`发现 ${state.discovered.length} 条同伴记录；双鸭接触采样 ${state.contacts.ducks}`);
  $('result-summary').textContent=lines.join('\n');entry(label+'：'+lines.join('；'));return state;
}
async function voiceFor(run,room){
  if(run.voiceMap?.has(room))return run.voiceMap.get(room);run.voiceMap??=new Map();
  const voice=new DemoVoice(room,output,data=>{
    if(current!==run||run.signal.aborted)return;
    if(data.type==='transcript'){message(data.role==='user'?'灵矽识别到':'灵矽实时回答',data.text);entry((data.role==='user'?'识别：':'灵矽：')+data.text);}
    if(data.type==='voice_status')status('灵矽 · '+({connecting:'正在连接',ready:'已就绪',listening:'收取预录指令',thinking:'正在思考',speaking:'正在回答',interrupting:'切换新指令'}[data.state]??data.state));
  });run.voices.push(voice);await voice.connect(run.signal);run.voiceMap.set(room,voice);return voice;
}
async function cloudResults(run,room,before,expected,scene){
  const state=await api('api/scenes/state',room,{signal:run.signal});
  const ids=state.events.filter(e=>e.id>before&&e.kind==='result').map(e=>e.action_id);
  const records=[];for(const id of ids){const r=await api('api/scenes/actions/'+id,room,{signal:run.signal});records.push(r);run.results.push({...r,room});entry(`灵矽动作 · ${ACTION_NAMES[r.name]??r.name} · ${r.status==='completed'?'完成':r.status}`,r.status);}
  if(records.some(r=>r.status!=='completed'))throw new Error('灵矽调用的动作未全部完成，演示已停止');
  if(state.backend.scene!==scene||!matchesCloudActions(records,expected,scene))throw new Error(`本轮实际动作未符合剧本（期望 ${expected.map(n=>ACTION_NAMES[n]).join('、')}）；已保留真实结果，不补造动作`);
}
async function command(run,room,step){
  if(step.actions.includes('stage_roll')){const stage=stages.get(room);await selectionQueue;if(selectionVersion===0)await stageSelect({targets:['a']},stage);await syncStageOrder(stage)}
  if(run.live){
    const voice=await voiceFor(run,room),state=await api('api/scenes/state',room,{signal:run.signal}),before=state.events.at(-1)?.id??0;
    const pcm=await speak(step.id,step.text,'预录指令 → 灵矽',run,{wait:false});await voice.turn(pcm,run.signal);await cloudResults(run,room,before,step.actions,state.backend.scene);
  }else{
    await speak(step.id,step.text,'预录指令 · 本地剧本',run);
    for(const name of step.actions)await perform(run,room,name,name==='stage_roll'?{member:'selected'}:{});
  }
}
async function interrupt(run,step){
  const room=currentRoom,next=step.next??'nod';let old;
  const initial=await api('api/scenes/state',room,{signal:run.signal}),baseline=initial.events.at(-1)?.id??0;
  if(run.live){
    const voice=await voiceFor(run,room);const pcm=await speak(step.id,step.text,'预录旧指令 → 灵矽',run,{wait:false});await voice.input(pcm,run.signal);
    const deadline=performance.now()+60000;
    while(!old){if(performance.now()>deadline)throw new Error('灵矽未在时限内开始旧动作，无法验证打断');const s=await api('api/scenes/state',room,{signal:run.signal});if(s.action?.name===step.actions[0])old=s.action;else await pause(40,run.signal);}
    await pause(150,run.signal);await voice.interrupt(run.signal);
  }else{
    await speak(step.id,step.text,'预录旧指令',run,{wait:false});
    old=await api('api/scenes/actions',room,{body:{name:step.actions[0],request_id:crypto.randomUUID()},signal:run.signal});await pause(650,run.signal);output.clear();
    await perform(run,room,'stop');
  }
  const cancelled=await api('api/scenes/actions/'+old.id,room,{signal:run.signal});
  if(cancelled.status!=='cancelled')throw new Error('旧动作已结束，未能验证取消；请重演本幕');
  run.results.push({...cancelled,room});entry('旧动作确实已取消；旧剧本剩余动作已撤销','cancelled');
  await command(run,room,{id:step.replacement,text:step.replacementText,actions:[next]});
  const after=await api('api/scenes/state',room,{signal:run.signal});
  const actions=after.events.filter(e=>e.id>baseline&&e.kind==='action');
  const records=await Promise.all(actions.map(e=>api('api/scenes/actions/'+e.action_id,room,{signal:run.signal})));
  const oldIndex=records.findIndex(r=>r.id===old.id);
  if(oldIndex<0||!matchesCloudActions(records.slice(0,oldIndex),[],initial.backend.scene)||!matchesCloudActions(records.slice(oldIndex+1),[next],initial.backend.scene))throw new Error('检测到旧剧本剩余动作，打断验收未通过');
}
async function runStep(run,step){
  run.signal.throwIfAborted();
  if(step.kind==='line')await speak(step.id,step.text,step.role==='旁白'?'预录旁白':'预录角色台词',run);
  if(step.kind==='command')await command(run,currentRoom,step);
  if(step.kind==='action')await perform(run,currentRoom,step.name,{...(step.duration?{duration:step.duration}:{}),...(step.target?{target:step.target}:{})},step.expectFailure);
  if(step.kind==='inspect')await inspect(run,currentRoom,step.label);
  if(step.kind==='interrupt')await interrupt(run,step);
  if(step.kind==='duel'){
    const claimed=await api('api/rooms/claim',currentRoom,{body:{},signal:run.signal}),other=claimed.room;
    if(other===currentRoom)throw new Error('本幕需要两个独立房间，请重新选择空闲房间');
    await prepare(other,'ball',run,true);
    if(run.live)await Promise.all([command(run,currentRoom,{id:step.id,text:step.text,actions:['flash_step']}),command(run,other,{id:step.second,text:step.secondText,actions:['bear_shake']})]);
    else{await speak(step.id,step.text,'预录指令 · 房间 '+currentRoom,run);await speak(step.second,step.secondText,'预录指令 · 房间 '+other,run);await Promise.all([perform(run,currentRoom,'flash_step'),perform(run,other,'bear_shake')]);}
    await inspect(run,currentRoom,'两个独立世界的舞步已完成');
  }
  if(step.kind==='music'){
    $('chorale-panel').hidden=false;message('官方乐谱 · 本地合成','先听低音与高音。第 4 拍加入中音，第 8 拍补齐四声部，第 13 拍中音离席。');
    let musicDone=false;
    const singing=playChorale(output,run.signal,frame=>{
      if(!frame)return;$('chorale-beat').textContent=`第 ${Math.floor(frame.beat)+1} / 16 拍 · ${frame.active} 声部 · 指挥 A`;
      $('chorale-seats').replaceChildren(...frame.seats.map(seat=>{const d=document.createElement('div');d.className='chorale-seat';d.dataset.active=seat.active;const name=document.createElement('strong');name.textContent=PART_NAMES[seat.part];const label=document.createElement('span');label.textContent=seat.label+(seat.active?'':' · 留席');d.append(name,label);return d}));
    }).finally(()=>{musicDone=true});
    const following=(async()=>{for(let i=0;i<16&&!musicDone;i++){
      const result=await action(currentRoom,'nod',run.signal,{target:'both'});
      if(result.status!=='completed')throw new Error('合奏头部动作未完成，已停止音乐');
      run.results.push({...result,room:currentRoom});
    }})();
    const [result]=await Promise.all([singing,following]);
    $('result-summary').textContent='官方乐谱节选已演奏。四个声部先后进入，中音离开后留席；两只物理鸭随有界头部动作表演。';
    run.results.push({name:'chorale',status:'completed',outcome:result});entry('四声部节选完成：加入不重排，中音离开后保留席位；未模拟 BLE 时钟');
  }
  if(step.kind==='seated_music'){
    $('table-panel').hidden=false;$('table-song-title').textContent='欢乐颂 · 坐着合唱，站起独唱';
    $('table-beat').textContent='正在就座';$('table-cue').textContent='四位歌手先坐稳，再开始合唱。';$('table-seats').replaceChildren();
    message('本地合成四声部 · 官方坐站策略','A、B、C、D 轮流起身独唱，唱完坐回原位。');
    const movement=perform(run,currentRoom,'seated_show');
    const music=playSeatedChoir(output,run.signal,()=>stages.get(currentRoom)?.latest?.backend.seated_choir,frame=>{
      $('table-beat').textContent=`${Math.min(SEATED_SECONDS,Math.floor(frame.elapsed))} / ${SEATED_SECONDS} 秒`;
      const who=frame.solo?.toUpperCase();
      $('table-cue').textContent=frame.phase==='solo'?`鸭 ${who} 已站稳，轮到它独唱。`:frame.phase==='rising'?`鸭 ${who} 正在起身，其他成员轻声和声。`:frame.phase==='sitting'?`鸭 ${who} 唱完坐回原位，准备接唱。`:'四位歌手坐着合唱。';
      $('table-seats').replaceChildren(...frame.postures.map((pose,i)=>{const seat=document.createElement('div');seat.className='table-seat';seat.dataset.duck='abcd'[i];seat.dataset.active=String(frame.activeParts[i]);seat.dataset.solo=String(frame.phase==='solo'&&frame.solo==='abcd'[i]);const name=document.createElement('strong');name.textContent='鸭 '+'ABCD'[i];const label=document.createElement('span');label.textContent=frame.phase==='solo'&&frame.solo==='abcd'[i]?'站起独唱':pose.observed==='sit'?'坐姿和声':pose.observed==='stand'?'站稳候唱':'调整姿态';seat.append(name,label);return seat}));
    });
    const [result,audio]=await Promise.all([movement,music]);
    run.results.push({name:'seated_music',status:'completed',outcome:audio});
    $('table-beat').textContent=`${SEATED_SECONDS} / ${SEATED_SECONDS} 秒`;
    $('result-summary').textContent='四只鸭均完成坐姿合唱、站稳独唱、唱完坐回。全程保留桌面接触，没有根坐标传送。';
    entry(`独唱交接完成：${result.outcome.completed_solos.map(d=>d.toUpperCase()).join(' → ')}；四只鸭均已坐稳`);
  }
  if(step.kind==='table_music'){
    if(trackLoading||trackError)throw new Error(trackError||'歌曲音源还在读取，请稍后重演');
    const tracks=tableTracks??await loadBuiltinSong($('table-song').value,output.context(),run.signal),offset=Number($('table-offset').value);checkOffset(tracks,offset);
    $('table-panel').hidden=false;$('table-song-title').textContent=tracks?(tracks.title??'本机音源 · '+tracks.names.join(' / ')):'桌边的星光 · 独立原创练声曲';
    message(tracks?.notes?'熟悉旋律 · 本地合成四声部':tracks?(tracks.title?'预录歌曲 · 四鸭物理编排':'本机歌曲 · 四鸭物理编排'):'独立原创曲 · 本地合成',tracks?.description??'四位歌手，请留意脚下的舞台。');
    const movement=perform(run,currentRoom,'table_show');
    const music=playTableChoir(output,run.signal,()=>stages.get(currentRoom)?.latest?.backend.tabletop,frame=>{
      $('table-beat').textContent=`${Math.min(TABLE_SECONDS,Math.floor(frame.elapsed))} / ${TABLE_SECONDS} 秒`;
      $('table-cue').textContent=frame.returning?(frame.floorDancing?'楼下那位，继续踏步、继续唱。':'楼下那位，站稳后继续踏步。'):frame.landed?'已确认落地，另外三只仍在桌上。':frame.dropped?'等一下，怎么少了一个声部？':tracks?.description??'四只鸭交替踏步、点头、摇摆。';
      $('table-seats').replaceChildren(...(tracks?.parts??TABLE_PARTS).map((part,i)=>{const seat=document.createElement('div');seat.className='table-seat';seat.dataset.duck='abcd'[i];seat.dataset.fallen=String(i===3&&frame.dropped);seat.dataset.active=String(frame.activeParts[i]);const name=document.createElement('strong');name.textContent='鸭 '+'ABCD'[i];const label=document.createElement('span');label.textContent=i===3&&frame.dropped?(frame.returning?(frame.floorDancing?'楼下踏步':'楼下站稳'):'暂离桌面'):!frame.activeParts[i]?'等待入唱':tracks?.buffers?.length===1?'歌曲混音':part;seat.append(name,label);return seat}));
    },{tracks,offset});
    const [result,audio]=await Promise.all([movement,music]);
    run.results.push({name:'table_music',status:'completed',outcome:audio});
    $('table-beat').textContent=`${TABLE_SECONDS} / ${TABLE_SECONDS} 秒`;
    $('result-summary').textContent=`四只鸭参与；鸭 D 在第 ${result.outcome.dropped_at.toFixed(1)} 秒离桌，随后实际接触地面。其余三只仍有桌面支撑。`;
    entry('真实跌落验收通过：桌面支撑 → 离桌 → 地面接触；其余三只留在桌上');
  }
}
function cleanup(run){
  return run.cleanupPromise??=(async()=>{
  run.abort();output.clear();chorus.stop();if(stageVoiceBusy())stageVoice.disconnect();
  await Promise.allSettled([...run.rooms].map(room=>api('api/scenes/actions',room,{body:{name:'stop',request_id:crypto.randomUUID()}})));
  if(run.voices.length){
    const owned=new Set(run.voices.map(v=>v.room));
    for(let i=0;i<50;i++){
      try{const state=await api('api/rooms',currentRoom);if(!state.rooms.some(r=>owned.has(r.id)&&r.voice_busy))break}catch{break}
      await pause(100);
    }
  }
  for(const [room,stage] of stages)if(room!==currentRoom){stages.delete(room);stage.socket.close();stage.viewer.dispose();}
  // A borrowed second world should not keep simulating through the remaining
  // program. Let its viewer disconnect settle; preserve it if someone joined.
  for(const room of run.rooms)if(room!==currentRoom){
    for(let attempt=0;attempt<5;attempt++){
      try{await api('api/scenes/close?if_unused=true',room,{body:{},signal:AbortSignal.timeout(2000)});break}
      catch{await pause(100)}
    }
  }
  })();
}
function stop(reason='演示已停止'){
  const run=current;if(!run)return Promise.resolve();current=null;run.abort();output.clear();chorus.stop();status(reason);$('stop-demo').disabled=true;$('demo-mode').disabled=false;
  serial=Promise.allSettled([serial,cleanup(run),run.promise]).then(()=>{if(!current){controlsBusy(false);$('stage-play').disabled=false}});return serial;
}
function start(index){
  if(stageVoiceBusy()){error('请先断开真人语音再切换或重演节目。');return}
  // Unlock in the original click, before any fetch or room allocation.
  const enabled=output.resume({gesture:true});void chorus.enable().catch(()=>{});
  preview?.abort();output.clear();controlsBusy(true);
  if(current)void stop('正在切换节目…');
  const run=new DemoRun();run.live=$('demo-mode').value==='live';current=run;selected=index;
  status('正在准备节目…');$('theatre-result')?.remove();$('demo-notice').hidden=true;$('stop-demo').disabled=false;$('next-demo').disabled=index>=DEMOS.length-1;$('demo-mode').disabled=true;
  $('demo-timeline').replaceChildren();$('result-summary').textContent='等待本轮动作结果。';$('chorale-panel').hidden=true;$('table-panel').hidden=true;$('stage-panel').hidden=DEMOS[index].id!=='stage';$('demo-second').hidden=true;
  const demo=DEMOS[index];$('stage-play').disabled=true;$('stage-voice').hidden=!stageInteractive;for(const b of document.querySelectorAll('.stage-tools button'))b.disabled=!stageInteractive;mode();if(['chorale','tabletop','seated'].includes(demo.id)){run.live=false;$('voice-source').textContent='本幕：本地音乐 + 物理编排'}$('show-number').textContent=`第 ${String(index+1).padStart(2,'0')} 幕 · ${demo.duration}`;$('show-title').textContent=demo.title;
  for(const b of document.querySelectorAll('.program-item'))b.setAttribute('aria-current',String(b.dataset.demo===demo.id));
  run.promise=(async()=>{
    try{
      await serial;if(!await enabled)throw new Error('浏览器未允许播放，请再点一次节目');run.signal.throwIfAborted();
      const rooms=await api('api/rooms',currentRoom,{signal:run.signal});if(rooms.rooms.find(r=>r.id===currentRoom)?.voice_busy)throw new Error('本房间语音正在其他页面使用，请先断开或选择空闲房间');
      await prepare(currentRoom,demo.scene,run);
      if(demo.id==='stage'&&stageInteractive){
        message('现场互动 · 本地点选 / 灵矽实连','集结后坐下；四鸭起身，选中鸭翻滚后就地坐下；选中鸭起身齐舞。可反复点选操作。');
        $('voice-source').textContent='点选：本地操作 · 真人语音：灵矽实连';
        status('现场互动已就绪 · 可点选、轻戳或连接语音');
        while(!run.signal.aborted)await pause(200,run.signal);
      }
      for(const step of demo.steps){status('正在演出');await runStep(run,step)}
      run.signal.throwIfAborted();if($('result-summary').textContent==='等待本轮动作结果。')$('result-summary').textContent=`本轮 ${run.results.filter(r=>r.status==='completed').length} 个动作完成，${run.results.filter(r=>r.status==='cancelled').length} 个动作已取消。结果来自本次物理执行。`;status('本幕完成 · 可重演或进入下一幕');entry('本幕完成');
      $('theatre-result')?.remove();const proof=document.createElement('script');proof.type='application/json';proof.id='theatre-result';proof.textContent=JSON.stringify({scene:demo.id,mode:run.live?'live_linx':'scripted_rehearsal',status:'completed',results:run.results,cloud_audio_frames:run.voices.reduce((n,v)=>n+v.received,0)});document.body.append(proof);run.completed=true;
    }catch(e){if(e.name!=='AbortError'&&!run.signal.aborted&&current===run){error(e.message);status('本幕未完成 · 点击节目重试');entry(e.message,'failed')}}
    finally{
      if(current===run&&demo.id==='stage'&&run.completed){
        // Preserve the room and command lifetime after the scripted show.
        // Stop, switching scenes and page exit still own the usual cleanup.
        for(const voice of run.voices)voice.close();
        run.voices=[];run.voiceMap?.clear();$('stage-voice').hidden=false;
        for(const b of document.querySelectorAll('.stage-tools button'))b.disabled=false;
        controlsBusy(false);$('demo-mode').disabled=false;
      }else{
        await cleanup(run);
        if(current===run){current=null;$('stop-demo').disabled=true;$('demo-mode').disabled=false;$('stage-play').disabled=false;controlsBusy(false);}
      }
    }
  })();
}
$('stop-demo').addEventListener('click',()=>void stop());$('next-demo').addEventListener('click',()=>start(Math.min(selected+1,DEMOS.length-1)));
$('reset-camera').addEventListener('click',()=>{for(const stage of stages.values())stage.viewer.reset()});
window.addEventListener('keydown',e=>{if(e.key==='Escape')void stop()});
window.addEventListener('pagehide',()=>{const run=current;run?.abort();preview?.abort();output.close();chorus.dispose();for(const stage of stages.values()){stage.socket.close();stage.viewer.dispose()}
  for(const room of run?.rooms??[]){const url=appURL('api/scenes/actions');url.searchParams.set('room',room);void fetch(url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:'stop',request_id:crypto.randomUUID()}),keepalive:true}).catch(()=>{})}
});
mode();
