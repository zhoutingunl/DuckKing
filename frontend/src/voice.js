import { PCMFramer, decodePCM } from './audio-codec.js';
import { appURL } from './urls.js';
import { createSocket } from './transport.js';

export function setupVoice({appendLog,notify,endpoint='/voice'}){
  const $=id=>document.getElementById(id),talk=$('talk-button'),connect=$('connect-voice');
  let ws=null,state='disconnected',pressed=false,recording=null,playContext=null,nextTime=0,timeout=null,heartbeat=null,closingTimer=null,voiceNotice=null;
  function voiceError(text){voiceNotice=text;notify(text)}
  let generation=0,minGeneration=0,playbackEpoch=0;
  const sources=new Set();
  const labels={disconnected:'未连接灵矽',disconnecting:'正在断开连接',connecting:'正在连接',recovering:'正在恢复连接',interrupting:'正在切换新指令',awaiting_binding:'等待设备绑定',ready:'灵矽已连接',listening:'正在聆听',thinking:'正在思考',speaking:'正在回答',error:'连接异常',busy:'本房间语音正在使用'};
  function update(){
    $('voice-badge').textContent=labels[state]??state;
    const canInterrupt=['thinking','speaking'].includes(state)||sources.size>0;
    talk.disabled=!['ready','listening','thinking','speaking'].includes(state)&&!pressed;
    talk.querySelector('span:not(.key-hint)').textContent=canInterrupt?'打断并说话':'按住说话';
    talk.setAttribute('aria-label',canInterrupt?'打断并说话':'按住说话');
    talk.classList.toggle('recording',state==='listening');
    connect.disabled=state==='disconnecting';
    connect.textContent=state==='disconnecting'?'正在释放语音…':['connecting','recovering','interrupting','ready','listening','thinking','speaking'].includes(state)?'断开连接 ↗':state==='awaiting_binding'?'我已绑定，重新连接 ↗':state==='busy'?'本房间释放后重试 ↗':'连接灵矽 ↗';
    $('reset-voice').disabled=!['ready','listening','thinking','speaking','error'].includes(state);
    $('voice-connection-hint').textContent=state==='disconnected'?'使用灵矽智能体':'设备端语音连接';
    $('voice-caption').textContent=state==='ready'?'按住按钮或空格说话，最长 15 秒。':state==='listening'?'正在录音，松开后发送。':state==='thinking'?'按住按钮可打断并说新命令；20 秒无响应会自动重连。':state==='recovering'?'上一轮已结束，正在重连。请连接成功后重新说话。':state==='speaking'?'按住按钮或空格，立即打断并说新命令。':'连接后可进行真实语音对话。';
    if(state==='busy')$('voice-caption').textContent='每个房间一次只供一个页面使用语音。可在顶部选择另一个房间，或在本房间的原页面断开后重试。';
    if(state==='interrupting')$('voice-caption').textContent=pressed?'旧回复已停止，正在接收新命令；松开后发送。':'旧回复已停止，正在建立新一轮语音。';
    if(state==='disconnecting')$('voice-caption').textContent='正在关闭语音会话并释放占用，完成后可切换到其他设备。';
    window.dispatchEvent(new CustomEvent('duckking-voice-state',{detail:state}));
  }
  function send(data){if(ws?.readyState===WebSocket.OPEN)ws.send(typeof data==='object'&&!(data instanceof ArrayBuffer)?JSON.stringify(data):data)}
  async function playback(data){
    const epoch=playbackEpoch;
    playContext??=new AudioContext();await playContext.resume();
    if(epoch!==playbackEpoch)return;
    const pcm=decodePCM(data.pcm),buffer=playContext.createBuffer(1,pcm.length,data.sample_rate);buffer.copyToChannel(pcm,0);
    const source=playContext.createBufferSource();source.buffer=buffer;source.connect(playContext.destination);
    nextTime=Math.max(playContext.currentTime,nextTime);source.start(nextTime);nextTime+=buffer.duration;
    sources.add(source);source.onended=()=>{sources.delete(source);update()};update();
  }
  function clearPlayback(){playbackEpoch++;for(const source of sources){source.onended=null;source.stop()}sources.clear();nextTime=0;update()}
  async function release(sendStop=true){
    pressed=false;clearTimeout(timeout);
    if(recording){
      const {stream,node,source,context,framer}=recording;recording=null;
      node.port.onmessage=null;source.disconnect();node.disconnect();
      stream.getTracks().forEach(track=>track.stop());
      if(sendStop){framer.flush().forEach(frame=>send(frame));send({type:'listen_stop'})}
      await context.close();
    }
  }
  async function press(){
    if(talk.disabled||pressed)return;pressed=true;
    const channel=ws;
    if(['thinking','speaking'].includes(state)||sources.size){
      minGeneration=generation+1;state='interrupting';clearPlayback();send({type:'interrupt'});
    }
    let stream,context;
    try{
      stream=await navigator.mediaDevices.getUserMedia({audio:{channelCount:1,echoCancellation:true,noiseSuppression:true}});
      if(!pressed||ws!==channel){stream.getTracks().forEach(track=>track.stop());return}
      context=new AudioContext({sampleRate:16000});await context.resume();
      await context.audioWorklet.addModule(appURL('capture-worklet.js'));
      const source=context.createMediaStreamSource(stream),node=new AudioWorkletNode(context,'duck-capture');
      const framer=new PCMFramer(context.sampleRate);
      recording={stream,node,source,context,framer};
      if(!pressed||ws!==channel){await release(false);return}
      send({type:'listen_start'});
      node.port.onmessage=event=>{if(pressed)framer.push(event.data).forEach(frame=>send(frame))};
      source.connect(node);node.connect(context.destination);
      timeout=setTimeout(()=>release(),15000);
    }catch(error){await release(false);stream?.getTracks().forEach(track=>track.stop());if(context&&context.state!=='closed')await context.close();notify(`无法开始录音：${error.message}`)}
  }
  connect.disabled=false;update();
  connect.addEventListener('click',async()=>{
    if(state==='disconnecting')return;
    playContext??=new AudioContext();await playContext.resume();
    if(['connecting','recovering','interrupting','ready','listening','thinking','speaking'].includes(state)){
      if(ws?.readyState===WebSocket.CONNECTING){ws.close();return}
      state='disconnecting';update();
      const closing=ws;
      await release(false);if(ws!==closing)return;
      send({type:'disconnect'});clearPlayback();
      closingTimer=setTimeout(()=>closing?.close(),7000);return;
    }
    if(ws?.readyState===WebSocket.CONNECTING)return;
    if(voiceNotice&&$('notice').textContent===voiceNotice)$('notice').hidden=true;
    voiceNotice=null;
    generation=minGeneration=0;
    state='connecting';update();
    if(ws?.readyState===WebSocket.OPEN){send({type:'connect'});return}
    let receivedStatus=false;
    let owner=true;
    const channel=createSocket(endpoint);ws=channel;
    channel.onopen=()=>{
      if(ws!==channel)return;
      send({type:'connect'});
      heartbeat=setInterval(()=>{if(ws===channel&&channel.readyState===WebSocket.OPEN)send({type:'ping'})},10000);
    };
    channel.onmessage=async(event)=>{
      if(ws!==channel)return;
      const data=JSON.parse(event.data);
      if(['voice_status','audio','transcript','playback_end'].includes(data.type)){
        const incoming=data.generation??0;if(incoming<minGeneration)return;generation=incoming;
      }
      if(data.type==='voice_status'){
        receivedStatus=true;
        if(state!==data.state)appendLog(labels[data.state]??'语音状态更新','语音状态',data.state==='error');
        state=data.state;if(state==='busy')owner=false;
        $('activation').hidden=!data.activation_code;
        $('activation').textContent=data.activation_code?`激活码：${data.activation_code}。请在灵矽控制台添加设备，再点击重新连接。`:'';
        if(data.error)voiceError(data.error);
        if(!['listening','ready','interrupting'].includes(state)&&recording)await release(false);
        update();
      }else if(data.type==='transcript'){appendLog(data.text,data.role==='user'?'你说':'灵矽')}
      else if(data.type==='audio'){try{await playback(data)}catch(error){notify(error.message)}}
      else if(data.type==='playback_end'&&data.aborted){clearPlayback()}
      else if(data.type==='error'){notify(data.message);await release(false)}
    };
    channel.onclose=async()=>{
      if(ws!==channel)return;
      ws=null;clearInterval(heartbeat);clearTimeout(closingTimer);
      await release(false);if(ws!==null)return;clearPlayback();
      state=owner?(['error','awaiting_binding'].includes(state)?state:receivedStatus?'disconnected':'error'):'busy';
      if(owner&&!receivedStatus)voiceError('本地语音通道连接失败，请检查页面地址、代理或修改请求头的浏览器扩展。');
      update();
    };
  });
  $('reset-voice').addEventListener('click',async()=>{
    await release(false);clearPlayback();
    if(ws?.readyState===WebSocket.OPEN){send({type:'reset'})}
    else{connect.click()}
  });
  talk.addEventListener('pointerdown',event=>{event.preventDefault();talk.setPointerCapture(event.pointerId);press()});
  talk.addEventListener('pointerup',()=>release());talk.addEventListener('pointercancel',()=>release());
  window.addEventListener('blur',()=>release());
  window.addEventListener('keydown',event=>{if(event.code==='Space'&&!event.repeat&&!['INPUT','TEXTAREA'].includes(document.activeElement.tagName)){event.preventDefault();press()}});
  window.addEventListener('keyup',event=>{if(event.code==='Space'){event.preventDefault();release()}});
  window.addEventListener('pagehide',()=>{clearInterval(heartbeat);clearTimeout(closingTimer);release(false);ws?.close();clearPlayback()});
}
