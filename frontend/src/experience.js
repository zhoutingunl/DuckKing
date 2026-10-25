// Ephemeral measurement IDs only. No transcript, audio, URL, UA or persistent user ID.
import {appURL,currentRoom} from './urls.js';

export function context({traffic}={}){
  const file=location.pathname.split('/').at(-1),page=({
    'scenarios.html':'scenarios','demos.html':'demos','studio.html':'studio',
  })[file]??'home';
  return {id:crypto.randomUUID(),page,
    traffic:navigator.webdriver||new URL(location.href).searchParams.get('measurement')==='verification'
      ?'verification':traffic??'interactive',
    device:/Mobi|Android|iPad/.test(navigator.userAgent)||(navigator.platform==='MacIntel'&&navigator.maxTouchPoints>1)?'mobile':'desktop',
    transport:'unknown'};
}

const pending=new Map();let timer=null,sending=false;
export function report(event,room=currentRoom??'1'){
  pending.set(`${room}:${event.id}`,{room,event:structuredClone(event)});
  while(pending.size>100)pending.delete(pending.keys().next().value);
  if(!timer)timer=setTimeout(flush,150);
}
async function flush(){
  clearTimeout(timer);timer=null;if(sending)return;
  sending=true;
  try{
    while(pending.size){
      const room=pending.values().next().value.room;
      const items=[...pending.entries()].filter(([,v])=>v.room===room).slice(0,20);
      items.forEach(([key])=>pending.delete(key));
      const url=appURL('api/experience');url.searchParams.set('room',room);
      const body=JSON.stringify({events:items.map(([,v])=>v.event)});
      // Small keepalive bodies survive normal navigation. Delivery is still best effort.
      for(let attempt=0;attempt<2;attempt++){
        try{const r=await fetch(url,{method:'POST',headers:{'Content-Type':'application/json'},body,
          keepalive:true,signal:AbortSignal.timeout(5000)});if(r.ok||r.status<500)break;}catch{}
      }
    }
  }finally{sending=false;if(pending.size&&!timer)timer=setTimeout(flush,150)}
}
if(typeof window!=='undefined')window.addEventListener('pagehide',()=>void flush());

export function measurement(kind,{room=currentRoom??'1',traffic,backend,started=performance.now()}={}){
  const event={...context({traffic}),kind,sequence:0,status:'started',route:'pending',cache:'unknown',
    backend:backend??(location.pathname.endsWith('scenarios.html')||location.pathname.endsWith('studio.html')||location.pathname.endsWith('demos.html')?'mujoco':'unknown'),metrics:{},hidden:document.hidden};
  let done=false;
  const emit=()=>{event.sequence++;event.hidden||=document.hidden;report(event,room)};
  const visibility=()=>{event.hidden||=document.hidden};
  const abandon=()=>{finish('abandoned');void flush()};
  const deadline=setTimeout(()=>finish('timeout'),180000);
  document.addEventListener('visibilitychange',visibility);
  window.addEventListener('pagehide',abandon);
  function finish(status='completed',metrics={},extra={}){
    if(done)return;done=true;clearTimeout(deadline);Object.assign(event,{status,...extra});
    Object.assign(event.metrics,metrics);emit();
    document.removeEventListener('visibilitychange',visibility);window.removeEventListener('pagehide',abandon);
  }
  emit();
  return {event,started,finish,
    update(extra){if(!done){Object.assign(event,extra);emit()}},
    mark(key,ms){if(!done&&event.metrics[key]===undefined&&Number.isFinite(ms)&&ms>=0){event.metrics[key]=Math.round(ms);emit()}},
  };
}

export class VoiceExperience {
  constructor(options={}){this.options=options;this.current=null;this.stopped=null}
  start(mode,transport){
    if(typeof document==='undefined')return; // Non-browser protocol tooling has no user clock.
    this.accepted=false;this.aborted=false;
    this.finish('cancelled');this.stopped=null;this.current=measurement('voice',this.options);
    this.current.update({route:mode==='local_first'?'pending':'cloud',transport:transport??'unknown'});
    const {id,page,traffic,device}=this.current.event;
    return {id,page,traffic,device,transport:transport??'unknown'};
  }
  stop(){if(this.current&&this.stopped===null){this.stopped=performance.now();this.current.update({status:'waiting'})}}
  receive(data){
    if(!this.current)return;
    const ms=this.stopped===null?null:performance.now()-this.stopped;
    if(data.type==='voice_route')this.current.update({route:data.route});
    if(ms!==null){
      if(data.type==='transcript'&&data.role==='user'&&data.text?.trim())this.current.mark(data.source==='local'?'stt_local_ms':'stt_cloud_ms',ms);
      if(data.type==='audio')this.current.mark('audio_ms',ms);
      if(data.type==='voice_milestone'&&data.phase==='action_start')this.current.mark('action_ms',ms);
      if(data.type==='playback_end'&&!data.aborted)this.current.mark('reply_ms',ms);
    }
    if(data.type==='voice_milestone'&&data.phase==='turn_end'){this.finish(data.result==='failed'?'failed':'completed');return}
    if(data.type==='voice_status'){
      if(data.backend)this.current.update({backend:data.backend,scene:data.scene??'unknown'});
      if(data.state==='listening')this.accepted=true;
      if(data.state==='ready'&&this.accepted&&this.stopped!==null)this.finish(this.aborted?'cancelled':'completed');
      else if(['error','busy','recovering'].includes(data.state))this.finish(data.state==='recovering'?'timeout':'failed');
      else if(data.state==='disconnected')this.finish('cancelled');
    }
    if(data.type==='error')this.finish('failed');
    if(data.type==='playback_end'&&data.aborted)this.aborted=true;
  }
  finish(status){this.current?.finish(status);this.current=null}
}

export function loadMetrics(metrics){
  const keys=['manifest_ms','asset_ms','parse_ms','assemble_ms','first_frame_ms'];
  return Object.fromEntries(keys.filter(k=>Number.isFinite(metrics[k])).map(k=>[k,Math.round(metrics[k])]));
}

// A rendered frame plus a following animation frame, not just a finished download.
export const afterFrame=()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));
