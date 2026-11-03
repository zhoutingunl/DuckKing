import test from 'node:test';
import assert from 'node:assert/strict';
import {acquireMicrophone,microphoneError} from '../src/microphone.js';

function fixture(){
 const track={enabled:true,stopped:false,stop(){this.stopped=true}};
 return {track,stream:{getTracks:()=>[track],getAudioTracks:()=>[track]}};
}
const tick=()=>new Promise(resolve=>setTimeout(resolve,0));

test('an incompatible audio session is explained separately from permission denial',()=>{
 assert.match(microphoneError(new DOMException('AudioSession category is not compatible with audio capture','InvalidStateError')),/播放模式与麦克风冲突/);
 assert.match(microphoneError(new DOMException('denied','NotAllowedError')),/网站使用麦克风/);
});

test('permission starts in the initiating call, before the worklet, and capture stays muted',async()=>{
 const {stream,track}=fixture(),calls=[];
 const pending=acquireMicrophone({mediaDevices:{getUserMedia(){calls.push('permission');return Promise.resolve(stream)}},
   prepareWorklet:async()=>{calls.push('worklet');assert.equal(track.enabled,false)}});
 assert.deepEqual(calls,['permission']);assert.equal(await pending,stream);
 assert.deepEqual(calls,['permission','worklet']);assert.equal(track.enabled,false);assert.equal(track.stopped,false);
});

test('unanswered permission times out; a late grant is stopped and a retry can succeed',async()=>{
 const first=fixture(),second=fixture();let grant;
 await assert.rejects(acquireMicrophone({timeoutMs:15,mediaDevices:{getUserMedia:()=>new Promise(r=>{grant=r})},
   prepareWorklet:()=>assert.fail('permission was never granted')}),/未完成麦克风授权/);
 const retry=await acquireMicrophone({mediaDevices:{getUserMedia:async()=>second.stream},prepareWorklet:async()=>{}});
 grant(first.stream);await tick();assert.equal(first.track.stopped,true);
 assert.equal(retry,second.stream);assert.equal(second.track.stopped,false);
});

test('disconnect while awaiting permission stops the late stream without loading a worklet',async()=>{
 const {stream,track}=fixture(),controller=new AbortController();let grant;
 const pending=acquireMicrophone({signal:controller.signal,mediaDevices:{getUserMedia:()=>new Promise(r=>{grant=r})},
   prepareWorklet:()=>assert.fail('disconnected')});
 controller.abort();await assert.rejects(pending,{name:'AbortError'});
 grant(stream);await tick();assert.equal(track.stopped,true);
});

test('disconnect during worklet loading releases the already granted microphone',async()=>{
 const {stream,track}=fixture(),controller=new AbortController();let finish;
 const pending=acquireMicrophone({signal:controller.signal,mediaDevices:{getUserMedia:async()=>stream},
   prepareWorklet:()=>new Promise(r=>{finish=r})});
 await tick();controller.abort();await assert.rejects(pending,{name:'AbortError'});
 assert.equal(track.stopped,true);finish();await tick();
});

test('worklet failure and timeout release capture instead of leaving the device occupied',async()=>{
 for(const fails of [true,false]){
   const {stream,track}=fixture();
   await assert.rejects(acquireMicrophone({timeoutMs:15,mediaDevices:{getUserMedia:async()=>stream},
     prepareWorklet:()=>fails?Promise.reject(new Error('worklet unavailable')):new Promise(()=>{})}),/worklet unavailable|录音组件加载超时/);
   assert.equal(track.stopped,true);
 }
});
