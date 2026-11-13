import test from 'node:test';
import assert from 'node:assert/strict';
import {sceneVisit} from '../src/scene-visit.js';

test('scene entries count once and exclude loading, hidden and inactive time',async()=>{
 let time=0,ready=false,visible=true,id=0;const events=[];
 const visit=sceneVisit({send:async e=>events.push(e),eligible:()=>ready&&visible,now:()=>time,newId:()=>String(++id)});
 await visit.ensure('ball');await visit.ensure('ball');assert.equal(events.length,1);
 time=5000;await visit.pulse();assert.equal(events.at(-1).active_ms,0);
 ready=true;time=10000;await visit.pulse();assert.equal(events.at(-1).active_ms,5000);
 visible=false;time=15000;await visit.pulse();assert.equal(events.at(-1).active_ms,5000);
 visible=true;time=80000;await visit.pulse();assert.equal(events.at(-1).active_ms,5000);
 visit.interact();time=85000;await visit.pulse();assert.equal(events.at(-1).active_ms,10000);
 await visit.enter('hill');assert.equal(events.at(-2).operation,'end');assert.equal(events.at(-2).capability,'ball');assert.equal(events.at(-1).capability,'hill');
 await visit.end();time=90000;await visit.pulse();assert.equal(events.at(-1).operation,'end');
});

test('a failed analytics request does not prevent later scene tracking',async()=>{
 let calls=0;const events=[];
 const visit=sceneVisit({send:async e=>{if(++calls===1)throw Error('offline');events.push(e)},eligible:()=>true,now:()=>0,newId:()=>String(calls)});
 await visit.enter('a');await visit.enter('b');await visit.end();assert.equal(events.at(-1).capability,'b');
});


test('HTTP contexts without randomUUID can still enter and track a scene',async()=>{
 const descriptor=Object.getOwnPropertyDescriptor(globalThis.crypto,'randomUUID');
 Object.defineProperty(globalThis.crypto,'randomUUID',{configurable:true,value:undefined});
 try{
  const events=[],visit=sceneVisit({send:async event=>events.push(event),eligible:()=>true});
  await visit.enter('movement');
  assert.match(events[0].id,/^[a-f0-9]{8}-[a-f0-9]{4}-4[a-f0-9]{3}-[89ab][a-f0-9]{3}-[a-f0-9]{12}$/);
 }finally{
  if(descriptor)Object.defineProperty(globalThis.crypto,'randomUUID',descriptor);
  else delete globalThis.crypto.randomUUID;
 }
});


test('one visible active scene is capped even with continued input and heartbeat delivery',async()=>{
 let time=0;const events=[];
 const visit=sceneVisit({send:async e=>events.push(e),eligible:()=>true,now:()=>time,newId:()=>"bounded",maxActiveMs:15000});
 await visit.enter('a');
 for(let i=0;i<20;i++){time+=5000;visit.interact();await visit.pulse()}
 await visit.end();assert.equal(events.at(-1).active_ms,15000);
});
