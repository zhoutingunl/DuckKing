import {test} from 'node:test';
import assert from 'node:assert/strict';
import {stopRoomScene,newerSceneActivity} from '../src/scene-stop.js';

test('a stop waits for the backend terminal result and never retries the command',async()=>{
 const calls=[],results=[{id:'stop-1',status:'running'},{id:'stop-1',status:'running'},{id:'stop-1',status:'completed',finished_at:20}];
 const record=await stopRoomScene(async(...args)=>{calls.push(args);return results.shift()},{revision:'world-2',id:'stop-1',signal:new AbortController().signal,pause:async()=>{}});
 assert.equal(record.status,'completed');assert.equal(calls.filter(([,body])=>body).length,1);
 assert.match(calls[0][0],/expected_revision=world-2/);assert.deepEqual(calls[0][1],{name:'stop',request_id:'stop-1'});
 assert.deepEqual(calls.slice(1).map(([path])=>path),['api/scenes/actions/stop-1','api/scenes/actions/stop-1']);
});

test('failed and cancelled stop results cannot become a success confirmation',async()=>{
 for(const status of ['failed','cancelled'])await assert.rejects(stopRoomScene(async()=>({status,error:'stop not confirmed'}),{revision:'r',id:'s',signal:new AbortController().signal}),/stop not confirmed/);
});

test('a deadline cancels polling without a second stop or an implicit preparation',async()=>{
 const controller=new AbortController(),calls=[];
 await assert.rejects(stopRoomScene(async path=>{calls.push(path);return {id:'s',status:'running'}},{revision:'r',id:'s',signal:controller.signal,pause:async()=>controller.abort()}),{name:'AbortError'});
 assert.equal(calls.length,1);
});

test('a changed world or rejected request is reported without replaying the POST',async()=>{
 let calls=0;await assert.rejects(stopRoomScene(async()=>{calls++;throw Error('scene changed')},{revision:'old',id:'s',signal:new AbortController().signal}),/scene changed/);assert.equal(calls,1);
});

test('delayed pre-stop packets retain confirmation; later activity and another revision clear it',()=>{
 const ack={revision:'r',id:'stop',finished_at:20};
 assert.equal(newerSceneActivity({backend:{revision:'r'},action:{started_at:10},events:[{kind:'action',time:18,action_id:'stop'}]},ack),false);
 assert.equal(newerSceneActivity({backend:{revision:'r'},action:{started_at:21}},ack),true);
 assert.equal(newerSceneActivity({backend:{revision:'next'}},ack),true);
 assert.equal(newerSceneActivity({backend:{revision:'r',feature:{started_at:22}}},ack),true);
 assert.equal(newerSceneActivity({backend:{revision:'r'},events:[{kind:'action',time:23,action_id:'new'}]},ack),true);
});
