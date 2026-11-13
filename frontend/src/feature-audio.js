import {appURL} from './urls.js';

// Local sound follows confirmed scene time. It never claims to be Linx speech.
export class FeatureAudio {
 constructor(){this.ctx=null;this.buffers=new Map();this.key=null;this.source=null;this.tone=null;this.watch=null}
 async enable(){this.ctx??=new AudioContext();await this.ctx.resume()}
 async load(emotion){
  if(this.buffers.has(emotion))return this.buffers.get(emotion);
  const response=await fetch(appURL(`api/features/emotion-audio/${emotion}.wav`),{signal:AbortSignal.timeout(10000)});
  if(!response.ok)throw Error('情绪声音资源尚未安装');
  const buffer=await this.ctx.decodeAudioData(await response.arrayBuffer());this.buffers.set(emotion,buffer);return buffer;
 }
 stop(){clearTimeout(this.watch);this.key=null;for(const node of [this.source,this.tone]){try{node?.stop()}catch{}node?.disconnect()}this.source=this.tone=null;this.gain?.disconnect();this.gain=null}
 update(feature){
  if(feature?.status!=='running'||!['emotions','theremin'].includes(feature.capability)){this.stop();return}
  clearTimeout(this.watch);this.watch=setTimeout(()=>this.stop(),1000);
  if(this.ctx?.state!=='running')return;
  if(this.key!==feature.id){this.stop();this.key=feature.id;this.watch=setTimeout(()=>this.stop(),1000)}
  if(feature.capability==='emotions'){
   if(this.source)return;
   const buffer=this.buffers.get(feature.action);if(!buffer)return;
   const offset=feature.metrics?.emotion_elapsed_s;if(!Number.isFinite(offset)||offset>=buffer.duration)return;
   this.source=this.ctx.createBufferSource();this.source.buffer=buffer;this.source.connect(this.ctx.destination);this.source.start(0,offset);
  }else{
   const hz=feature.metrics?.frequency_hz;
   if(!this.tone){this.tone=this.ctx.createOscillator();this.gain=this.ctx.createGain();this.gain.gain.value=0;this.tone.type='sine';this.tone.connect(this.gain);this.gain.connect(this.ctx.destination);this.tone.start()}
   this.gain.gain.setTargetAtTime(Number.isFinite(hz) ? .13 : 0,this.ctx.currentTime,.04);
   if(Number.isFinite(hz))this.tone.frequency.setTargetAtTime(Math.max(80,Math.min(1600,hz)),this.ctx.currentTime,.05);
  }
 }
 async close(){this.stop();this.buffers.clear();await this.ctx?.close()}
}
