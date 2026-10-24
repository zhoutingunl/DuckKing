import { test } from 'node:test';
import assert from 'node:assert/strict';
import { VoiceAudio } from '../src/audio-output.js';

function hardware(t) {
  const instances=[];
  class Context {
    constructor(){
      instances.push(this);this.state='suspended';this.sampleRate=48000;this.currentTime=0;
      this.destination={};this.nodes=[];this.resumeCalls=0;this.modules=0;
      this.audioWorklet={addModule:async()=>{this.modules++}};
    }
    resume(){this.resumeCalls++;return new Promise(resolve=>{this.unblock=()=>{this.state='running';resolve()}})}
    close(){this.state='closed';return Promise.resolve()}
    createBuffer(channels,length,rate){return {length,duration:length/rate,copyToChannel(pcm){this.pcm=pcm}}}
    createBufferSource(){
      const node={connect(){},disconnect(){this.detached=true},start(time){this.time=time},stop(){this.stopped=true}};
      this.nodes.push(node);return node;
    }
  }
  const previous=globalThis.AudioContext;globalThis.AudioContext=Context;
  t.after(()=>{globalThis.AudioContext=previous});
  return instances;
}
// Node has no Web Audio. Each test explicitly supplies a controlled fake device.
globalThis.AudioContext=class {};
const frame=(seconds=1,value=.5)=>{
  const pcm=Buffer.alloc(16000*seconds*2);
  for(let i=0;i<pcm.length;i+=2)pcm.writeInt16LE(value*32768,i);
  return {sample_rate:16000,pcm:pcm.toString('base64')};
};

test('suspended output is bounded, resumes in frame order, and interrupt stops all sources',async t=>{
  const instances=hardware(t),audio=new VoiceAudio();
  for(let i=0;i<13;i++)audio.enqueue(frame(1,i/16));
  const ctx=instances[0];
  assert.equal(ctx.resumeCalls,1);assert.equal(ctx.nodes.length,0);
  assert.equal(audio.snapshot().queued_ms,12000);assert.equal(audio.snapshot().dropped_frames,1);
  ctx.unblock();await audio.resuming;
  assert.equal(audio.snapshot().scheduled_frames,12);
  ctx.nodes.forEach((node,i)=>{assert.equal(node.time,i);assert.equal(node.buffer.pcm[0],i/16)});
  audio.clear();assert.equal(audio.busy,false);
  assert.ok(ctx.nodes.every(node=>node.stopped&&node.detached));
  assert.equal(audio.snapshot().ended_frames,0);
  audio.close();
});

test('late resume cannot revive interrupted audio or a cancelled local test tone',async t=>{
  const instances=hardware(t),audio=new VoiceAudio();
  audio.enqueue(frame());const pending=audio.resuming;
  audio.clear();instances[0].unblock();await pending;
  assert.equal(instances[0].nodes.length,0);
  instances[0].state='interrupted';
  const tone=audio.testTone();audio.clear();instances[0].unblock();
  assert.equal(await tone,false);assert.equal(audio.snapshot().scheduled_frames,0);
  audio.close();assert.equal(await audio.resume({gesture:true}),false);
});

test('one hardware-rate context and worklet are reused, capture defers output, local tone is separate',async t=>{
  const instances=hardware(t),audio=new VoiceAudio();
  const ready=audio.resume({gesture:true});
  assert.equal(instances[0].nodes.length,1); // Synchronous silent unlock in the gesture.
  instances[0].unblock();assert.equal(await ready,true);
  await audio.captureWorklet('/capture-worklet.js');await audio.captureWorklet('/capture-worklet.js');
  assert.equal(instances[0].modules,1);
  audio.setCapture(true);audio.enqueue(frame(.06));assert.equal(audio.snapshot().scheduled_frames,0);
  audio.setCapture(false);await audio.resume({gesture:true});
  assert.equal(instances.length,1);assert.equal(audio.snapshot().output_sample_rate,48000);
  assert.equal(audio.snapshot().scheduled_frames,1);
  instances[0].nodes.at(-1).onended();assert.equal(audio.snapshot().ended_frames,1);
  assert.equal(await audio.testTone(),true);assert.equal(audio.busy,false);
  instances[0].nodes.at(-1).onended();assert.equal(audio.snapshot().ended_frames,1);
  assert.equal(audio.snapshot().received_frames,1);
  audio.close();
});

test('rejected or stuck resumes and unavailable hardware cannot hang connection controls',async t=>{
  t.mock.timers.enable({apis:['setTimeout']});
  const instances=hardware(t),audio=new VoiceAudio();
  const pending=audio.resume({gesture:true});
  t.mock.timers.tick(1500);assert.equal(await pending,false);
  for(let i=0;i<10;i++)audio.enqueue(frame(.06));
  assert.equal(instances[0].resumeCalls,1); // Further TTS frames wait for a new gesture.
  instances[0].resume=()=>Promise.reject(new Error('blocked'));
  assert.equal(await audio.resume({gesture:true}),false);
  instances[0].resume=()=>{throw new Error('blocked')};
  assert.equal(await audio.resume({gesture:true}),false);
  audio.close();
  globalThis.AudioContext=class {constructor(){throw new Error('unavailable')}};
  assert.equal(await new VoiceAudio().resume({gesture:true}),false);
});

test('malformed, oversized, and tiny-frame floods cannot create unbounded playback',t=>{
  hardware(t);const audio=new VoiceAudio();audio.setCapture(true);audio.context().state='running';
  for(const sample_rate of [null,0,NaN,8000.5,192001])assert.throws(()=>audio.enqueue({sample_rate,pcm:''}));
  assert.throws(()=>audio.enqueue({sample_rate:16000,pcm:'x'.repeat(256*1024+1)}));
  assert.throws(()=>audio.enqueue({sample_rate:16000,pcm:'eA=='}));
  for(let i=0;i<301;i++)audio.enqueue({sample_rate:16000,pcm:'AAA='});
  assert.equal(audio.pending.length,300);assert.equal(audio.snapshot().dropped_frames,1);
  audio.close();
});
