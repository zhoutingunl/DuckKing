import test from 'node:test';
import assert from 'node:assert/strict';
import {readResource,resourceBytes} from '../src/resource-loader.js';

function streamed(chunks,headers={}){
  return new Response(new ReadableStream({start(controller){for(const c of chunks)controller.enqueue(new Uint8Array(c));controller.close()}}),{headers});
}
test('decoded gzip progress uses decoded metadata, never compressed Content-Length',async()=>{
  const progress=[];
  const response=streamed([[1,2],[3,4,5,6]],{'content-encoding':'gzip','content-length':'2','x-model-decoded-bytes':'6'});
  assert.deepEqual([...new Uint8Array(await readResource(response,{progress:p=>progress.push(p)}))],[1,2,3,4,5,6]);
  assert.equal(progress.at(-1).totalBytes,6);assert.equal(progress.at(-1).loaded,6);
  const unknown=[];await readResource(streamed([[1,2,3]],{'content-encoding':'gzip','content-length':'1'}),{progress:p=>unknown.push(p)});
  assert.equal(unknown.at(-1).totalBytes,0);
});
test('a transient GET failure retries once with fresh response; persistent failure stays explicit',async()=>{
  let calls=0;const stages=[];
  const buffer=await resourceBytes(async()=>{if(++calls===1)throw new TypeError('network');return new Response(new Uint8Array([4,5]));},{retryDelayMs:0,progress:p=>stages.push(p)});
  assert.equal(calls,2);assert.deepEqual([...new Uint8Array(buffer)],[4,5]);assert.equal(stages.filter(p=>p.phase==='retry').length,1);
  calls=0;await assert.rejects(resourceBytes(async()=>{calls++;return new Response('',{status:503})},{retryDelayMs:0}));assert.equal(calls,2);
  calls=0;await assert.rejects(resourceBytes(async()=>{calls++;return new Response('',{status:404})},{retryDelayMs:0}));assert.equal(calls,1);
});
test('timeout aborts a blocked body and retries only once; cancellation does not retry',async()=>{
  let calls=0,cancelled=0;
  const create=async()=>{calls++;return new Response(new ReadableStream({cancel(){cancelled++}}))};
  // Keep a real referenced timer while AbortSignal.timeout uses an unref timer in Node.
  const alive=setTimeout(()=>{},1000);
  try{await assert.rejects(resourceBytes(create,{timeoutMs:10,retryDelayMs:0}),e=>e.name==='TimeoutError');}
  finally{clearTimeout(alive)}
  assert.equal(calls,2);assert.equal(cancelled,2);
  calls=0;const controller=new AbortController();
  const loading=resourceBytes(create,{signal:controller.signal,retryDelayMs:0});
  setTimeout(()=>controller.abort(),5);
  await assert.rejects(loading,e=>e.name==='AbortError');assert.equal(calls,1);
});
test('oversized bodies fail without retry or pretending complete progress',async()=>{
  let calls=0;
  await assert.rejects(resourceBytes(async()=>{calls++;return streamed([[1,2],[3,4]])},{maxBytes:3,retryDelayMs:0}),/大小上限/);
  assert.equal(calls,1);
});
