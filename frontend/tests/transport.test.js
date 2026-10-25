import test from 'node:test';
import assert from 'node:assert/strict';
import { DuckSocket } from '../src/transport.js';

const tick=()=>new Promise(resolve=>setTimeout(resolve,25));
const until=async predicate=>{for(let i=0;i<100;i++){if(predicate())return;await tick()}assert.fail('timed out')};
const json=value=>({ok:true,status:200,json:async()=>value});
const identifier='a'.repeat(32);

function fixture({openGate,sendGate,failSend=false,endpoint="voice"}={}){
  const calls=[],batches=[],polls=[];
  const fetch=async(url,options={})=>{
    const path=new URL(url).pathname,method=options.method??'GET';calls.push({path,method});
    if(path.endsWith('capabilities'))return json({protocol:1,transport:'https-poll'});
    if(path.endsWith('/channels')){assert.equal(JSON.parse(options.body).endpoint,endpoint);await openGate;return json({id:identifier})}
    if(method==='DELETE')return {ok:true,status:204};
    if(method==='POST'){
      const body=JSON.parse(options.body);batches.push(body);
      await Promise.race([sendGate,new Promise((_,reject)=>options.signal.addEventListener('abort',()=>reject(new Error('abort')),{once:true}))]);
      if(failSend)throw new Error('offline');
      return json({sequence:body.sequence+1});
    }
    return new Promise((resolve,reject)=>{
      polls.push(packet=>resolve(json(packet)));
      options.signal.addEventListener('abort',()=>reject(new Error('abort')),{once:true});
    });
  };
  const socket=new DuckSocket(endpoint,{url:'https://test.local/duckking/'+endpoint,fetch,WebSocket:class{constructor(){assert.fail('unexpected native socket')}}});
  return {socket,calls,batches,polls};
}

test('ordered text, exact 1920-byte PCM and stop; receive text and binary',async()=>{
  const {socket,batches,polls}=fixture();
  try{
    await until(()=>socket.readyState===1);
    const pcm=Uint8Array.from({length:1920},(_,i)=>i%256);
    socket.send('start');socket.send(pcm.buffer);socket.send('stop');
    await until(()=>batches.length===1&&socket.bufferedAmount===0);
    assert.equal(batches[0].sequence,0);
    assert.deepEqual(batches[0].frames.map(f=>f.binary),[false,true,false]);
    assert.deepEqual(Buffer.from(batches[0].frames[1].data,'base64'),Buffer.from(pcm));
    const messages=[];socket.onmessage=e=>messages.push(e.data);
    polls.shift()({frames:batches[0].frames,closed:false});
    await until(()=>messages.length===3);
    assert.equal(messages[0],'start');assert.deepEqual(new Uint8Array(messages[1]),pcm);assert.equal(messages[2],'stop');
  }finally{socket.close()}
});

test('cancel during channel creation deletes late ID and never opens',async()=>{
  let release;const openGate=new Promise(resolve=>release=resolve);
  const {socket,calls}=fixture({openGate});let opens=0,closes=0;
  socket.onopen=()=>opens++;socket.onclose=()=>closes++;
  await until(()=>calls.some(c=>c.method==='POST'));
  socket.close();release();await until(()=>calls.some(c=>c.method==='DELETE'));
  assert.equal(opens,0);assert.equal(closes,1);assert.equal(socket.readyState,3);
});

test('send failures close and release without retrying speech or commands',async()=>{
  const {socket,calls,batches}=fixture({failSend:true});
  await until(()=>socket.readyState===1);socket.send('action');
  await until(()=>socket.readyState===3);
  assert.equal(batches.length,1);assert(calls.some(c=>c.method==='DELETE'));
});

test('bounded send queue closes slow transport and stops accepting audio',async()=>{
  let release;const sendGate=new Promise(resolve=>release=resolve);
  const {socket,calls}=fixture({sendGate});
  await until(()=>socket.readyState===1);
  for(let i=0;i<5;i++)socket.send(new ArrayBuffer(256*1024));
  assert.equal(socket.readyState,3);assert.equal(socket.bufferedAmount,0);
  assert.throws(()=>socket.send('late'),{name:'InvalidStateError'});
  assert(calls.some(c=>c.method==='DELETE'));release();
});

test('invalid incoming frames fail closed',async()=>{
  const {socket,polls}=fixture();await until(()=>polls.length);
  polls.shift()({frames:[{binary:true,data:'!'}],closed:false});
  await until(()=>socket.readyState===3);
});

test('local pages use native WebSocket; cancelling before setup opens nothing',async()=>{
  const native=[];
  class Native{constructor(url){this.url=String(url);native.push(this)}close(){this.closed=true}send(data){this.data=data}}
  const options={url:'http://127.0.0.1:8765/voice',WebSocket:Native,fetch:()=>assert.fail('unexpected fetch')};
  const cancelled=new DuckSocket('voice',options);cancelled.close();await tick();assert.equal(native.length,0);
  const socket=new DuckSocket('voice',options);await tick();
  assert.equal(native[0].url,'ws://127.0.0.1:8765/voice');native[0].onopen();socket.send('hi');assert.equal(native[0].data,'hi');
  socket.close();assert(native[0].closed);
});


test('a scene ACK can survive model-download contention while voice still fails promptly',async()=>{
  const nativeTimeout=globalThis.setTimeout;let scene,voice,releaseScene,releaseVoice;
  // Compress only transport deadlines; retain the relative 7s / 20s boundary.
  globalThis.setTimeout=(callback,ms,...args)=>nativeTimeout(callback,ms>=1000?ms/100:ms,...args);
  try{
    const first=fixture({endpoint:'scene-ws',sendGate:new Promise(r=>releaseScene=r)});scene=first.socket;
    await until(()=>scene.readyState===1);scene.send('next');await until(()=>first.batches.length===1);
    await new Promise(r=>nativeTimeout(r,90));assert.equal(scene.readyState,1);
    releaseScene();await until(()=>scene.bufferedAmount===0);assert.equal(first.batches.length,1);scene.close();
    const second=fixture({sendGate:new Promise(r=>releaseVoice=r)});voice=second.socket;
    await until(()=>voice.readyState===1);voice.send('listen_stop');
    await until(()=>voice.readyState===3);assert.equal(second.batches.length,1);
  }finally{scene?.close();voice?.close();releaseScene?.();releaseVoice?.();globalThis.setTimeout=nativeTimeout;}
});
