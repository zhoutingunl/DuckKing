import { PCMFramer } from './audio-codec.js';
import { appURL } from './urls.js';
import { createSocket } from './transport.js';
import { VoiceAudio } from './audio-output.js';

export function setupVoice({appendLog,notify,endpoint='/voice'}){
  const $=id=>document.getElementById(id),talk=$('talk-button'),connect=$('connect-voice');
  let ws=null,state='disconnected',pressed=false,recording=null,timeout=null,heartbeat=null,closingTimer=null,voiceNotice=null;
  function voiceError(text){voiceNotice=text;notify(text)}
  let generation=0,minGeneration=0,captureId=0,audioReportTimer=null;
  let mode='cloud',route='cloud',modesReady=false;
  const modeSelect=$('voice-mode');
  const reasons={unmatched:'整句未完整匹配动作',unsupported_context:'当前场景不支持整句动作',plan_limit:'指令超出本地动作范围',empty_or_long:'识别内容不足或过长',asr_timeout:'本地识别超时',asr_unavailable:'本地识别暂不可用'};
  const stateLabel=(value=state)=>mode!=='local_first'?labels[value]??value:
    value==='ready'?'本地优先 · 已就绪':value==='disconnected'?'语音未启用':
    value==='thinking'?(route==='local'?'正在执行本地动作':route==='cloud_fallback'?'灵矽处理中':'正在本地识别'):labels[value]??value;
  const output=new VoiceAudio(snapshot=>{
    $('audio-status').textContent=snapshot.output_state!=='running'
      ? (snapshot.received_frames?'已收到回复音频，播放尚未就绪。请点“启用 / 测试声音”。':'点“启用 / 测试声音”可检查手机声音。')
      : snapshot.dropped_frames?'部分回复因播放受限已丢弃；请测试声音后重新说话。'
      : '声音通道已就绪；若仍听不到，请检查媒体音量、静音开关和蓝牙输出。';
    $('audio-diagnostics').textContent=`播放状态：${snapshot.output_state}\n收到 / 提交播放 / 播放结束：${snapshot.received_frames} / ${snapshot.scheduled_frames} / ${snapshot.ended_frames} 帧\n待播：${snapshot.queued_ms} ms；丢弃：${snapshot.dropped_frames} 帧\n音频峰值：${snapshot.signal_peak_milli} / 1000\n浏览器播放状态不等于手机扬声器实际出声。`;
    if(!audioReportTimer)audioReportTimer=setTimeout(()=>{audioReportTimer=null;send({type:'playback_status',...output.snapshot()})},1000);
    update();
  });
  const labels={disconnected:'未连接灵矽',disconnecting:'正在断开连接',connecting:'正在连接',recovering:'正在恢复连接',interrupting:'正在切换新指令',awaiting_binding:'等待设备绑定',ready:'灵矽已连接',listening:'正在聆听',thinking:'正在思考',speaking:'正在回答',error:'连接异常',busy:'本房间语音正在使用'};
  function update(){
    $('voice-badge').textContent=stateLabel();
    $('voice-intro').textContent=mode==='local_first'?'启用语音后，按住说话；常用动作本地执行，未匹配时交给灵矽。':'连接灵矽后，按住说话，松开等待回答。';
    if(modeSelect)modeSelect.disabled=!modesReady||!['disconnected','error','busy','awaiting_binding'].includes(state);
    const canInterrupt=['thinking','speaking'].includes(state)||output.busy;
    talk.disabled=!['ready','listening','thinking','speaking'].includes(state)&&!pressed;
    talk.querySelector('span:not(.key-hint)').textContent=canInterrupt?'打断并说话':'按住说话';
    talk.setAttribute('aria-label',canInterrupt?'打断并说话':'按住说话');
    talk.classList.toggle('recording',state==='listening');
    $('enable-sound').disabled=pressed;
    connect.disabled=state==='disconnecting';
    connect.textContent=state==='disconnecting'?'正在释放语音…':['connecting','recovering','interrupting','ready','listening','thinking','speaking'].includes(state)?'断开连接 ↗':state==='awaiting_binding'?'我已绑定，重新连接 ↗':state==='busy'?'本房间释放后重试 ↗':'连接灵矽 ↗';
    if(mode==='local_first'&&['disconnected','error'].includes(state))connect.textContent='启用语音 ↗';
    $('reset-voice').disabled=!['ready','listening','thinking','speaking','error'].includes(state);
    $('voice-connection-hint').textContent=state==='disconnected'?'使用灵矽智能体':'设备端语音连接';
    if(mode==='local_first')$('voice-connection-hint').textContent='服务器离线识别 · 未匹配时交灵矽';
    $('voice-caption').textContent=state==='ready'?'按住按钮或空格说话，最长 15 秒。':state==='listening'?'正在录音，松开后发送。':state==='thinking'?'按住按钮可打断并说新命令；20 秒无响应会自动重连。':state==='recovering'?'上一轮已结束，正在重连。请连接成功后重新说话。':state==='speaking'?'按住按钮或空格，立即打断并说新命令。':'连接后可进行真实语音对话。';
    if(mode==='local_first'&&state==='disconnected')$('voice-caption').textContent='常用动作在本地执行，聊天和未匹配的整句指令交给灵矽。';
    if(mode==='local_first'&&state==='thinking')$('voice-caption').textContent='按住按钮可打断并说新命令。本地动作一旦开始，不再转交云端重复执行。';
    if(state==='busy')$('voice-caption').textContent='每个房间一次只供一个页面使用语音。可在顶部选择另一个房间，或在本房间的原页面断开后重试。';
    if(state==='interrupting')$('voice-caption').textContent=pressed?'旧回复已停止，正在接收新命令；松开后发送。':'旧回复已停止，正在建立新一轮语音。';
    if(state==='disconnecting')$('voice-caption').textContent='正在关闭语音会话并释放占用，完成后可切换到其他设备。';
    window.dispatchEvent(new CustomEvent('duckking-voice-state',{detail:{state,mode,route}}));
  }
  modeSelect?.addEventListener('change',()=>{
    mode=modeSelect.value;route=mode==='cloud'?'cloud':'local_ready';
    try{sessionStorage.setItem('duckking.voice-mode',mode)}catch{}
    $('voice-route').textContent=mode==='cloud'?'灵矽负责识别和回复。':'整句动作匹配后本地执行；本地反馈为提示音和文字。';update();
  });
  if(modeSelect)fetch(appURL('api/voice/modes')).then(r=>{if(!r.ok)throw Error();return r.json()}).then(cap=>{
    modeSelect.querySelector('[value=local_first]').disabled=!cap.local_first;
    let saved;try{saved=sessionStorage.getItem('duckking.voice-mode')}catch{}
    if(state==='disconnected')mode=cap.local_first&&(saved==='local_first'||(!saved&&cap.available))?'local_first':'cloud';
    modeSelect.value=mode;modesReady=true;
    if(state==='disconnected')modeSelect.dispatchEvent(new Event('change'));else update();
    if(cap.local_first&&!cap.available)$('voice-route').textContent='本地识别暂未就绪；本地优先模式会明确转交灵矽。';
  }).catch(()=>{modesReady=true;modeSelect.querySelector('[value=local_first]').disabled=true;update()});
  function send(data){if(ws?.readyState===WebSocket.OPEN)ws.send(typeof data==='object'&&!(data instanceof ArrayBuffer)?JSON.stringify(data):data)}
  function playback(data){output.enqueue(data)}
  function clearPlayback(){output.clear()}
  async function release(sendStop=true){
    pressed=false;captureId++;clearTimeout(timeout);
    if(recording){
      const {stream,node,source,framer}=recording;recording=null;
      node.port.onmessage=null;source.disconnect();node.disconnect();
      stream.getTracks().forEach(track=>track.stop());
      if(sendStop){framer.flush().forEach(frame=>send(frame));send({type:'listen_stop'})}
    }
    output.setCapture(false);
    if(output.ctx)void output.resume({gesture:true});
    update();
  }
  async function press(){
    if(talk.disabled||pressed)return;pressed=true;
    const channel=ws,attempt=++captureId;
    if(['thinking','speaking'].includes(state)||output.busy){
      minGeneration=generation+1;state='interrupting';send({type:'interrupt'});
    }
    clearPlayback();
    let stream,context;
    try{
      output.setCapture(true);void output.resume({gesture:true});
      stream=await navigator.mediaDevices.getUserMedia({audio:{channelCount:1,echoCancellation:true,noiseSuppression:true}});
      if(!pressed||ws!==channel||attempt!==captureId){stream.getTracks().forEach(track=>track.stop());return}
      context=output.context();if(!await output.resume())throw new Error('音频通道未就绪，请先点启用 / 测试声音');
      await output.captureWorklet(appURL('capture-worklet.js'));
      if(!pressed||ws!==channel||attempt!==captureId){stream.getTracks().forEach(track=>track.stop());return}
      const source=context.createMediaStreamSource(stream),node=new AudioWorkletNode(context,'duck-capture');
      const framer=new PCMFramer(context.sampleRate);
      recording={stream,node,source,context,framer};
      send({type:'listen_start'});
      node.port.onmessage=event=>{if(pressed)framer.push(event.data).forEach(frame=>send(frame))};
      source.connect(node);node.connect(context.destination);
      timeout=setTimeout(()=>release(),15000);
    }catch(error){if(attempt===captureId)await release(false);stream?.getTracks().forEach(track=>track.stop());notify(`无法开始录音：${error.message}`)}
  }
  $('enable-sound').addEventListener('click',async()=>{
    if(pressed)return;
    const ok=await output.testTone();
    appendLog(ok?'已提交本地测试提示音；若听不到，请检查手机媒体音量、静音开关和蓝牙输出。':'浏览器仍未允许声音播放，请留在前台再点一次。','声音测试',!ok);
  });
  connect.disabled=false;update();
  connect.addEventListener('click',async()=>{
    if(state==='disconnecting')return;
    void output.resume({gesture:true});
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
    if(ws?.readyState===WebSocket.OPEN){send({type:'connect',mode});return}
    let receivedStatus=false;
    let owner=true;
    const channel=createSocket(endpoint);ws=channel;
    channel.onopen=()=>{
      if(ws!==channel)return;
      send({type:'connect',mode});send({type:'playback_status',...output.snapshot()});
      heartbeat=setInterval(()=>{if(ws===channel&&channel.readyState===WebSocket.OPEN)send({type:'ping'})},10000);
    };
    channel.onmessage=async(event)=>{
      if(ws!==channel)return;
      const data=JSON.parse(event.data);
      if(['voice_status','voice_route','audio','transcript','playback_end'].includes(data.type)){
        const incoming=data.generation??0;if(incoming<minGeneration)return;generation=incoming;
      }
      if(data.type==='voice_status'){
        receivedStatus=true;
        if(data.mode)mode=data.mode;if(data.route)route=data.route;
        if(state!==data.state)appendLog(stateLabel(data.state),'语音状态',data.state==='error');
        state=data.state;if(state==='busy')owner=false;
        $('activation').hidden=!data.activation_code;
        $('activation').textContent=data.activation_code?`激活码：${data.activation_code}。请在灵矽控制台添加设备，再点击重新连接。`:'';
        if(data.error)voiceError(data.error);
        if(!['listening','ready','interrupting'].includes(state)&&recording)await release(false);
        update();
      }else if(data.type==='voice_route'){
        route=data.route;
        const text=route==='local'?`本地识别 · 动作完整匹配${Number.isFinite(data.asr_ms)?` · ${data.asr_ms} ms`:''}`:route==='cloud_fallback'?`${reasons[data.reason]??'本地未匹配'}，正在连接灵矽并转交原录音。`:'未收到清晰语音，请重试。';
        if($('voice-route'))$('voice-route').textContent=text;
        appendLog(text,'处理路径');if(route==='local')void output.testTone();update();
      }else if(data.type==='transcript'){appendLog(data.text,data.source==='local'?(data.role==='user'?'本地识别':'本地反馈'):data.role==='user'?'你说':'灵矽')}
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
  document.addEventListener('visibilitychange',()=>{if(!document.hidden&&output.ctx)void output.resume()});
  // A history-cache restore reuses a document whose microphone and audio were closed.
  window.addEventListener('pageshow',event=>{if(event.persisted)window.location.reload()});
  window.addEventListener('pagehide',()=>{clearInterval(heartbeat);clearTimeout(closingTimer);release(false);ws?.close();output.close();clearTimeout(audioReportTimer)});
}
