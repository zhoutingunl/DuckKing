import { decodePCM } from './audio-codec.js';

// One hardware-rate context for capture and playback. Never keep unbounded
// resume() promises or a backlog of silent, suspended AudioBufferSourceNodes.
export class VoiceAudio {
  constructor(changed=()=>{}) {
    this.changed=changed;this.ctx=null;this.sources=new Map();this.pending=[];
    this.nextTime=0;this.epoch=0;this.capture=false;this.disposed=false;
    this.received=0;this.scheduled=0;this.ended=0;this.dropped=0;this.peak=0;
  }
  mode() {
    try { if(navigator.audioSession)navigator.audioSession.type=this.capture?'play-and-record':'playback'; }
    catch { /* Optional Audio Session API; ordinary Web Audio remains available. */ }
  }
  context() {
    if(this.disposed)throw new Error('声音通道已关闭');
    if(!this.ctx||this.ctx.state==='closed'){
      const Audio=globalThis.AudioContext||globalThis.webkitAudioContext;
      this.ctx=new Audio();this.primed=false;this.workletReady=null;this.resumeBlocked=false;
      const ctx=this.ctx;
      ctx.onstatechange=()=>{if(this.ctx===ctx&&!this.disposed){this.flush();this.report()}};
    }
    return this.ctx;
  }
  captureWorklet(url){
    this.workletReady??=this.context().audioWorklet.addModule(url).catch(error=>{this.workletReady=null;throw error});
    return this.workletReady;
  }
  get busy(){return this.pending.length>0||[...this.sources.values()].some(local=>!local)}
  snapshot() {
    return {output_state:this.ctx?.state??'uninitialized',received_frames:this.received,
      scheduled_frames:this.scheduled,ended_frames:this.ended,dropped_frames:this.dropped,
      queued_ms:Math.round((this.pending.reduce((n,p)=>n+p.pcm.length/p.rate,0)+Math.max(0,this.nextTime-(this.ctx?.currentTime??0)))*1000),
      signal_peak_milli:Math.round(this.peak*1000),output_sample_rate:this.ctx?.sampleRate??0};
  }
  report(){if(!this.disposed)this.changed(this.snapshot())}
  setCapture(value){this.capture=value;this.mode()}
  resume({gesture=false}={}) {
    if(this.disposed)return Promise.resolve(false);
    this.mode();let ctx;
    // Start a silent sample synchronously in the user's gesture, including on
    // iOS where resume alone may not activate a destination that has never run.
    try{
      ctx=this.context();
      if(gesture&&(!this.primed||ctx.state!=='running')){
        const silent=ctx.createBufferSource();silent.buffer=ctx.createBuffer(1,1,ctx.sampleRate);
        silent.connect(ctx.destination);silent.onended=()=>silent.disconnect();silent.start(0);this.primed=true;
      }
    }catch{this.report();return Promise.resolve(false)}
    if(ctx.state==='running'){this.resumeBlocked=false;this.flush();this.report();return Promise.resolve(true)}
    if(this.resuming&&!gesture)return this.resuming;
    if(this.resumeBlocked&&!gesture)return Promise.resolve(false);
    let timer;
    // Invoke resume now, not in a promise callback: retain user activation.
    let resumed;try{resumed=ctx.resume()}catch{resumed=Promise.reject(new Error('audio_resume_failed'))}
    const pending=Promise.race([
      Promise.resolve(resumed).then(()=>ctx.state==='running',()=>false),
      new Promise(resolve=>{timer=setTimeout(()=>resolve(false),1500)}),
    ]).then(ok=>{
      if(!this.disposed&&this.ctx===ctx){this.resumeBlocked=!ok;if(ok)this.flush();this.report()}
      return ok&&!this.disposed&&this.ctx===ctx;
    }).finally(()=>{clearTimeout(timer);if(this.resuming===pending)this.resuming=null});
    this.resuming=pending;return pending;
  }
  enqueue(data) {
    if(!Number.isInteger(data.sample_rate)||data.sample_rate<8000||data.sample_rate>192000||typeof data.pcm!=='string'||data.pcm.length>256*1024)throw new Error('无效的下行音频');
    const pcm=decodePCM(data.pcm);if(!pcm.length)return;
    this.received++;for(const v of pcm)this.peak=Math.max(this.peak,Math.abs(v));
    if(this.snapshot().queued_ms+pcm.length/data.sample_rate*1000>12000||this.pending.length+this.sources.size>=300){
      this.dropped++;this.report();return;
    }
    this.pending.push({pcm,rate:data.sample_rate});this.flush();
    if(this.ctx?.state!=='running')void this.resume();
    this.report();
  }
  schedule(pcm,rate,{local=false}={}) {
    const ctx=this.context(),epoch=this.epoch;
    const buffer=ctx.createBuffer(1,pcm.length,rate);buffer.copyToChannel(pcm,0);
    const source=ctx.createBufferSource();source.buffer=buffer;source.connect(ctx.destination);
    this.nextTime=Math.max(ctx.currentTime,this.nextTime);source.start(this.nextTime);this.nextTime+=buffer.duration;
    this.sources.set(source,local);if(!local)this.scheduled++;
    source.onended=()=>{
      source.disconnect();this.sources.delete(source);
      if(!local&&epoch===this.epoch)this.ended++;
      this.report();
    };
  }
  flush(){
    if(this.disposed||this.capture||this.ctx?.state!=='running')return;
    while(this.pending.length){const p=this.pending.shift();this.schedule(p.pcm,p.rate)}
  }
  clear(){
    this.epoch++;this.pending=[];this.nextTime=0;
    for(const source of this.sources.keys()){source.onended=null;try{source.stop()}catch{}source.disconnect()}
    this.sources.clear();this.report();
  }
  async testTone(){
    this.clear();const epoch=this.epoch;
    if(!await this.resume({gesture:true})||this.epoch!==epoch)return false;
    const rate=this.context().sampleRate,pcm=new Float32Array(Math.round(rate*.25));
    for(let i=0;i<pcm.length;i++)pcm[i]=Math.sin(2*Math.PI*660*i/rate)*.15*Math.sin(Math.PI*i/pcm.length);
    this.schedule(pcm,rate,{local:true});this.report();return true;
  }
  close(){
    this.clear();this.disposed=true;
    if(this.ctx){this.ctx.onstatechange=null;void this.ctx.close().catch(()=>{})}
    try{if(navigator.audioSession)navigator.audioSession.type='auto'}catch{}
  }
}
