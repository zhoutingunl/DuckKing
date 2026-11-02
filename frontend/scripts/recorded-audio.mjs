// Capture actual Web Audio samples; retain the output clock instead of recorder.start().
export function installPageAudioRecorder(){
 window.recordedAudio=[];
 const connect=AudioNode.prototype.connect,taps=new Map();
 const processor=`class Recorder extends AudioWorkletProcessor{
  constructor(){super();this.frame=null;this.used=0;this.data=new Float32Array(4096);this.port.onmessage=e=>{if(e.data==='finish'){this.flush();this.port.postMessage({finished:true})}}}
  flush(){if(this.used){const pcm=this.data.slice(0,this.used*2);this.port.postMessage({frame:this.frame,pcm},[pcm.buffer]);this.used=0;this.frame=null}}
  process(inputs){const input=inputs[0],size=input[0]?.length??128;
   for(let i=0;i<size;i++){if(this.frame===null)this.frame=currentFrame+i;this.data[this.used*2]=input[0]?.[i]??0;this.data[this.used*2+1]=input[1]?.[i]??input[0]?.[i]??0;this.used++;if(this.used===2048)this.flush()}
   return true
  }
 }registerProcessor('duckking-recorder',Recorder)`;
 function tapFor(ctx){
  if(taps.has(ctx))return taps.get(ctx);
  const bus=ctx.createGain();bus.channelCount=2;bus.channelCountMode='explicit';
  const tap={ctx,bus,rate:ctx.sampleRate,chunks:[],anchors:[],events:[],states:[],ids:new WeakMap(),nextId:0};taps.set(ctx,tap);window.recordedAudio.push(tap);
  ctx.addEventListener('statechange',()=>tap.states.push({state:ctx.state,wall_time_ms:Date.now(),context_time:ctx.currentTime}));
  const url=URL.createObjectURL(new Blob([processor],{type:'application/javascript'}));
  tap.ready=ctx.audioWorklet.addModule(url).then(()=>{
   URL.revokeObjectURL(url);const node=new AudioWorkletNode(ctx,'duckking-recorder',{numberOfInputs:1,numberOfOutputs:1,outputChannelCount:[2]}),mute=ctx.createGain();mute.gain.value=0;
   connect.call(bus,node);connect.call(node,mute);connect.call(mute,ctx.destination);tap.node=node;
   node.port.onmessage=({data})=>{
    if(data.finished){tap.finished?.();return}
    tap.chunks.push(data);const ts=ctx.getOutputTimestamp();
    if(ts.contextTime>0&&ts.performanceTime>0)tap.anchors.push({frame:data.frame,wall_time_ms:performance.timeOrigin+ts.performanceTime+(data.frame/ctx.sampleRate-ts.contextTime)*1000});
   };
  });return tap;
 }
 AudioNode.prototype.connect=function(target,...args){
  const result=connect.call(this,target,...args);
  if(target===this.context.destination)connect.call(this,tapFor(this.context).bus);
  return result;
 };
 for(const [Type,kind]of [[AudioBufferSourceNode,'buffer'],[OscillatorNode,'oscillator']]){
  for(const method of ['start','stop']){
   const native=Type.prototype[method];
   Type.prototype[method]=function(...args){
    const tap=tapFor(this.context);let id=tap.ids.get(this);if(!id){id=++tap.nextId;tap.ids.set(this,id)}
    tap.events.push({id,kind,method,context_time:Math.max(this.context.currentTime,args[0]??0)});
    return native.apply(this,args);
   };
  }
 }
 window.finishRecordedAudio=async()=>Promise.all(window.recordedAudio.map(async tap=>{
  await tap.ready;
  await new Promise((resolve,reject)=>{const timer=setTimeout(()=>reject(Error('Audio capture did not flush')),2000);tap.finished=()=>{clearTimeout(timer);resolve()};tap.node.port.postMessage('finish')});
  const chunks=tap.chunks,first=chunks[0]?.frame,last=chunks.at(-1);if(first===undefined)throw Error('No actual audio samples captured');
  const pcm=new Float32Array((last.frame-first+last.pcm.length/2)*2);
  for(const c of chunks)pcm.set(c.pcm,(c.frame-first)*2);
  const bytes=new Uint8Array(pcm.buffer);let text='';for(let i=0;i<bytes.length;i+=8192)text+=String.fromCharCode(...bytes.subarray(i,i+8192));
  return {sampleRate:tap.rate,channels:2,firstFrame:first,anchors:tap.anchors,events:tap.events,states:tap.states,pcm_base64:btoa(text)};
 }));
}

const median=values=>{const sorted=[...values].sort((a,b)=>a-b);return sorted[Math.floor(sorted.length/2)]};
export function alignClockedAudio({pcm,sampleRate,channels,firstFrame,anchors}){
 if(!(pcm instanceof Float32Array)||pcm.length%channels||!anchors.length)throw Error('Missing actual PCM or output-clock anchors');
 const lastFrame=firstFrame+pcm.length/channels,groups=[];
 for(const anchor of anchors){
  if(!Number.isFinite(anchor.frame)||!Number.isFinite(anchor.wall_time_ms))throw Error('Invalid output-clock anchor');
  const offset=anchor.wall_time_ms-anchor.frame/sampleRate*1000;
  let group=groups.at(-1);
  if(!group||Math.abs(offset-median(group.offsets.slice(-8)))>100){
   if(group&&offset<median(group.offsets))throw Error('Output clock moved backwards');
   group={firstFrame:groups.length?Math.max(firstFrame,anchor.frame):firstFrame,offsets:[]};groups.push(group);
  }
  group.offsets.push(offset);
 }
 const segments=groups.map((g,i)=>{
  const offset=median(g.offsets),jitter=Math.max(...g.offsets.map(v=>Math.abs(v-offset)));
  if(jitter>50)throw Error('Output clock is too uncertain for audio/video sync');
  return {first_frame:g.firstFrame,last_frame:groups[i+1]?.firstFrame??lastFrame,offset_ms:offset,max_anchor_jitter_ms:jitter};
 });
 const started=segments[0].offset_ms+firstFrame/sampleRate*1000,last=segments.at(-1);
 const output=new Float32Array(Math.ceil((last.offset_ms+lastFrame/sampleRate*1000-started)*sampleRate/1000)*channels);
 let previousEnd=0;
 for(const s of segments){
  const position=Math.round((s.offset_ms+s.first_frame/sampleRate*1000-started)*sampleRate/1000);
  if(position<previousEnd-2)throw Error('Output-clock segments overlap');
  output.set(pcm.subarray((s.first_frame-firstFrame)*channels,(s.last_frame-firstFrame)*channels),position*channels);previousEnd=position+s.last_frame-s.first_frame;
 }
 return {pcm:output,started_wall_time_ms:started,sampleRate,channels,segments};
}
export function contextTimeToWall(recording,seconds){
 const frame=seconds*recording.sampleRate;
 const segment=recording.segments.find(s=>frame<s.last_frame)??recording.segments.at(-1);
 return segment.offset_ms+seconds*1000;
}
export function floatWav({pcm,sampleRate,channels}){
 const wav=Buffer.alloc(44+pcm.byteLength);wav.write('RIFF');wav.writeUInt32LE(wav.length-8,4);wav.write('WAVEfmt ',8);wav.writeUInt32LE(16,16);wav.writeUInt16LE(3,20);wav.writeUInt16LE(channels,22);wav.writeUInt32LE(sampleRate,24);wav.writeUInt32LE(sampleRate*channels*4,28);wav.writeUInt16LE(channels*4,32);wav.writeUInt16LE(32,34);wav.write('data',36);wav.writeUInt32LE(pcm.byteLength,40);
 for(let i=0;i<pcm.length;i++)wav.writeFloatLE(pcm[i],44+i*4);return wav;
}
