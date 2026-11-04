import {test} from 'node:test';
import assert from 'node:assert/strict';
import {requestId} from '../src/ids.js';

test('request and measurement IDs work without the secure-context randomUUID API',async()=>{
 const descriptor=Object.getOwnPropertyDescriptor(globalThis.crypto,'randomUUID');
 Object.defineProperty(globalThis.crypto,'randomUUID',{configurable:true,value:undefined});
 try{
   const ids=Array.from({length:128},()=>requestId());
   assert.equal(new Set(ids).size,128);
   assert.ok(ids.every(id=>/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/.test(id)));
   globalThis.location=new URL('http://local.test/');
   const {context}=await import('../src/experience.js');
   assert.match(context().id,/^[0-9a-f-]{36}$/);
 }finally{
   if(descriptor)Object.defineProperty(globalThis.crypto,'randomUUID',descriptor);
   else delete globalThis.crypto.randomUUID;
 }
});

test('interruption, recovery, queued start and unavailable telemetry do not fabricate completion',async()=>{
 const window=new EventTarget(),document=new EventTarget();document.hidden=false;
 Object.assign(globalThis,{window,document,location:new URL('https://example.test/duckking/scenarios.html?room=2')});
 Object.defineProperty(globalThis,'navigator',{configurable:true,value:{webdriver:true,userAgent:'TEST',platform:'',maxTouchPoints:0}});
 const reports=[];globalThis.fetch=async(_url,options)=>{reports.push(JSON.parse(options.body));return {ok:true}};
 const {VoiceExperience}=await import('../src/experience.js');
 const recorder=new VoiceExperience({room:'2'});
 const a=recorder.start('local_first','https-poll');recorder.stop();
 // A queued reconnect can say ready before listening starts: it is not completion.
 recorder.receive({type:'voice_status',state:'ready'});assert.ok(recorder.current);
 recorder.receive({type:'voice_status',state:'listening'});
 recorder.receive({type:'transcript',role:'user',source:'local',text:'not stored'});
 recorder.receive({type:'voice_route',route:'cloud_fallback'});
 recorder.receive({type:'transcript',role:'user',text:'not stored either'});
 recorder.receive({type:'playback_end',aborted:true});
 recorder.receive({type:'voice_status',state:'recovering'});
 assert.equal(recorder.current,null);
 const b=recorder.start('cloud','websocket');recorder.stop();recorder.finish('cancelled');
 recorder.receive({type:'voice_status',state:'ready'});recorder.receive({type:'audio'});
 const c=recorder.start('local_first','websocket');recorder.stop();
 recorder.receive({type:'voice_status',state:'listening'});
 recorder.receive({type:'voice_milestone',phase:'turn_end',result:'failed'});
 await new Promise(r=>setTimeout(r,220));
 const events=reports.flatMap(r=>r.events);
 assert.equal(events.find(e=>e.id===a.id).status,'timeout');
 assert.equal(events.find(e=>e.id===a.id).route,'cloud_fallback');
 assert.deepEqual(Object.keys(events.find(e=>e.id===a.id).metrics).sort(),['stt_cloud_ms','stt_local_ms']);
 assert.equal(events.find(e=>e.id===b.id).status,'cancelled');
 assert.equal(events.find(e=>e.id===c.id).status,'failed');
 assert.ok(events.every(e=>e.traffic==='verification'));
 assert.ok(!JSON.stringify(events).includes('not stored'));
 // Exhausted telemetry delivery must not reject into the speech UI.
 globalThis.fetch=async()=>{throw Error('offline')};
 recorder.start('cloud','websocket');window.dispatchEvent(new Event('pagehide'));
 await new Promise(r=>setTimeout(r,220));
});
