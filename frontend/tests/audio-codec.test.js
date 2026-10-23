import { test } from 'node:test';
import assert from 'node:assert/strict';
import { PCMFramer, decodePCM } from '../src/audio-codec.js';

test('PCM frames have exact duration and clamp signed samples',()=>{
  const framer=new PCMFramer(16000);
  const input=Float32Array.from({length:960},(_,i)=>i%3===0?-2:i%3===1?2:NaN);
  const frames=[...framer.push(input),...framer.flush()];
  assert.equal(frames.length,1);assert.equal(frames[0].byteLength,1920);
  const view=new DataView(frames[0]);
  assert.equal(view.getInt16(0,true),-32768);assert.equal(view.getInt16(2,true),32767);assert.equal(view.getInt16(4,true),0);
  assert.deepEqual(framer.flush(),[]);
});
test('resampling is continuous across arbitrary browser chunk boundaries',()=>{
  for(const rate of [16000,44100,48000]){
    const samples=Float32Array.from({length:rate/10},(_,i)=>Math.sin(i*.12)*.5);
    const full=new PCMFramer(rate),split=new PCMFramer(rate);
    const expected=[...full.push(samples),...full.flush()].map(x=>Buffer.from(x));
    const actual=[];
    for(let i=0;i<samples.length;i+=128)actual.push(...split.push(samples.slice(i,i+128)));
    actual.push(...split.flush());
    assert.deepEqual(actual.map(x=>Buffer.from(x)),expected);
  }
});
test('invalid rates and partial PCM are rejected; PCM can be decoded for Web Audio',()=>{
  for(const rate of [0,NaN,200000])assert.throws(()=>new PCMFramer(rate));
  assert.throws(()=>new PCMFramer(16000,24000));assert.throws(()=>new PCMFramer(16000,16000,320));
  assert.throws(()=>decodePCM(btoa('x')));
  const pcm=Buffer.alloc(4);pcm.writeInt16LE(-32768,0);pcm.writeInt16LE(16384,2);
  assert.deepEqual([...decodePCM(pcm.toString('base64'))],[-1,.5]);
  const partial=new PCMFramer(16000);
  partial.push([.5,.5,.5]);assert.equal(partial.flush()[0].byteLength,1920);
});
