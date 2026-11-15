import {test} from 'node:test';
import assert from 'node:assert/strict';
import {createLocalAudioContext,resumeLocalAudio} from '../src/local-audio.js';
import {StudioChoir} from '../src/studio-choir.js';
import {FeatureAudio} from '../src/feature-audio.js';
import {createChorus} from '../src/chorus.js';
import {createFeatureIntent} from '../src/feature-intent.js';

function hardware(t,{session={type:'auto'},blocked=false}={}){
 const originals=['AudioContext','webkitAudioContext'].map(key=>[key,Object.getOwnPropertyDescriptor(globalThis,key)]);
 const previous=Object.getOwnPropertyDescriptor(navigator,'audioSession'),contexts=[],events=[];
 Object.defineProperty(navigator,'audioSession',{configurable:true,value:session});
 class Context{
  constructor(){this.state='suspended';this.sampleRate=48000;this.currentTime=0;this.destination={};this.nodes=[];contexts.push(this);events.push(['context',session?.type])}
  createBuffer(channels,length,rate){return {length,sampleRate:rate}}
  createBufferSource(){const node={connect(){},disconnect(){this.detached=true},start:()=>{events.push(['prime',session?.type]);this.unlocked=true}};this.nodes.push(node);return node}
  resume(){events.push(['resume',session?.type]);if(blocked)return new Promise(resolve=>{this.unblock=()=>{this.state='running';resolve()}});assert.ok(this.unlocked);this.state='running';return Promise.resolve()}
  close(){this.state='closed';return Promise.resolve()}
 }
 Object.defineProperty(globalThis,'AudioContext',{configurable:true,writable:true,value:Context});
 t.after(()=>{
  for(const [key,descriptor] of originals){if(descriptor)Object.defineProperty(globalThis,key,descriptor);else delete globalThis[key]}
  if(previous)Object.defineProperty(navigator,'audioSession',previous);else delete navigator.audioSession;
 });
 return {session,contexts,events,Context};
}

for(const Player of [StudioChoir,FeatureAudio])test(`${Player.name} unlocks mobile playback synchronously without a voice connection`,async t=>{
 const {contexts,events,session}=hardware(t),player=new Player();
 const ready=player.enable();
 // Assert before yielding: a download/await must not consume the user's gesture.
 assert.deepEqual(events,[['context','playback'],['prime','playback'],['resume','playback']]);
 assert.equal(await ready,true);assert.equal(session.type,'playback');
 await player.enable();assert.equal(contexts.length,1);assert.equal(contexts[0].nodes.length,1);
});

test('local sounds preserve an active microphone session and borrowed context ownership',async t=>{
 const {session,contexts}=hardware(t,{session:{type:'play-and-record'}}),ctx=createLocalAudioContext();
 const chorus=createChorus(()=>{},{getContext:()=>ctx});
 try{await chorus.enable();assert.equal(session.type,'play-and-record');assert.equal(contexts.length,1)}
 finally{chorus.dispose()}
 assert.equal(ctx.state,'running');
});

test('unsupported Audio Session API and prefixed Web Audio still use gesture unlock',async t=>{
 const {Context,events}=hardware(t,{session:null});delete navigator.audioSession;
 delete globalThis.AudioContext;globalThis.webkitAudioContext=Context;
 const ctx=createLocalAudioContext();assert.equal(await resumeLocalAudio(ctx),true);
 assert.deepEqual(events.map(event=>event[0]),['context','prime','resume']);
});

test('blocked resume is bounded, does not start motion and can retry',async t=>{
 t.mock.timers.enable({apis:['setTimeout']});
 const {contexts}=hardware(t,{blocked:true}),player=new StudioChoir(),intent=createFeatureIntent();let starts=0;
 const pending=intent.run(()=>player.enable(),()=>{starts++});const failed=assert.rejects(pending,/音频通道未就绪/);
 t.mock.timers.tick(1500);await failed;assert.equal(starts,0);
 contexts[0].unblock();await Promise.resolve();assert.equal(starts,0);
 assert.equal(await player.enable(),true);assert.equal(contexts.length,1);
});

test('stop cancels pending audio activation without replaying the old action later',async t=>{
 const {contexts}=hardware(t,{blocked:true}),player=new FeatureAudio(),intent=createFeatureIntent();let starts=0;
 const pending=intent.run(()=>player.enable(),()=>{starts++});intent.cancel();contexts[0].unblock();
 assert.equal(await pending,false);assert.equal(starts,0);
});

test('unavailable audio hardware fails explicitly before submitting a sound-dependent task',async t=>{
 hardware(t);globalThis.AudioContext=class{constructor(){throw Error('hardware unavailable')}};
 const player=new StudioChoir(),intent=createFeatureIntent();let starts=0;
 await assert.rejects(intent.run(()=>player.enable(),()=>{starts++}),/音频通道未就绪/);
 assert.equal(starts,0);
});
