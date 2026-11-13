import {test} from 'node:test';
import assert from 'node:assert/strict';
import {createFeatureIntent} from '../src/feature-intent.js';

const deferred=()=>{let resolve,reject;const promise=new Promise((ok,no)=>{resolve=ok;reject=no});return {promise,resolve,reject}};

test('Stop cancels an action still waiting for audio permission or download',async()=>{
 const intent=createFeatureIntent(),audio=deferred(),sent=[];
 const pending=intent.run(()=>audio.promise,()=>sent.push('old action'));
 intent.cancel();audio.resolve();
 assert.equal(await pending,false);assert.deepEqual(sent,[]);
 await intent.run(()=>Promise.resolve(),()=>sent.push('new action'));
 assert.deepEqual(sent,['new action']);
});

test('a newer action wins even if an older sound download finishes later',async()=>{
 const intent=createFeatureIntent(),slow=deferred(),sent=[];
 const old=intent.run(()=>slow.promise,()=>sent.push('sad'));
 await intent.run(()=>Promise.resolve(),()=>sent.push('happy'));
 slow.resolve();await old;assert.deepEqual(sent,['happy']);
});

test('cancelled scene errors stay silent while current preparation errors are reported',async()=>{
 const intent=createFeatureIntent(),audio=deferred();
 const old=intent.run(()=>audio.promise,()=>assert.fail('released scene must not run'));
 intent.cancel();audio.reject(Error('old download failed'));
 assert.equal(await old,false);
 await assert.rejects(intent.run(()=>Promise.reject(Error('current audio failed')),()=>assert.fail()),/current audio failed/);
});
