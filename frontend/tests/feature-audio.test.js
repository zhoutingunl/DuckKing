import {test} from 'node:test';
import assert from 'node:assert/strict';
import {FeatureAudio} from '../src/feature-audio.js';

function audioFixture(t){
 t.mock.timers.enable({apis:['setTimeout']});
 const nodes=[];
 const node=()=>{const n={start:t.mock.fn(),stop:t.mock.fn(),disconnect:t.mock.fn(),connect:t.mock.fn(),frequency:{setTargetAtTime:t.mock.fn()},gain:{setTargetAtTime:t.mock.fn()}};nodes.push(n);return n};
 const sound=new FeatureAudio();
 sound.ctx={state:'running',currentTime:2,destination:{},createBufferSource:node,createOscillator:node,createGain:node,close:t.mock.fn()};
 return {sound,nodes};
}

test('emotion audio waits for the confirmed emotion phase and starts at its actual offset',async t=>{
 const {sound,nodes}=audioFixture(t);sound.buffers.set('curious',{duration:4});
 const state={id:'a',status:'running',capability:'emotions',action:'curious',metrics:{}};
 sound.update(state);assert.equal(nodes.length,0);
 sound.update({...state,metrics:{emotion_elapsed_s:1.4}});
 assert.deepEqual(nodes[0].start.mock.calls[0].arguments,[0,1.4]);
 sound.update({...state,metrics:{emotion_elapsed_s:2}});assert.equal(nodes.length,1);
 sound.update({...state,status:'cancelled'});assert.equal(nodes[0].stop.mock.callCount(),1);
 assert.equal(nodes[0].disconnect.mock.callCount(),1);await sound.close();
});

test('lost state stream stops local tones within one second',t=>{
 const {sound,nodes}=audioFixture(t);
 const state={id:'tone',status:'running',capability:'theremin',metrics:{frequency_hz:440}};
 sound.update(state);assert.equal(nodes[0].start.mock.callCount(),1);
 t.mock.timers.tick(800);sound.update(state);t.mock.timers.tick(800);
 assert.equal(nodes[0].stop.mock.callCount(),0);
 t.mock.timers.tick(200);assert.equal(nodes[0].stop.mock.callCount(),1);
 assert.equal(sound.tone,null);assert.equal(sound.gain,null);
});

test('missing distance mutes a tone and scene changes release all audio nodes',t=>{
 const {sound,nodes}=audioFixture(t);
 sound.update({id:'a',status:'running',capability:'theremin',metrics:{frequency_hz:440}});
 sound.update({id:'a',status:'running',capability:'theremin',metrics:{}});
 assert.equal(nodes[1].gain.setTargetAtTime.mock.calls.at(-1).arguments[0],0);
 sound.update({id:'b',status:'running',capability:'hop'});
 assert.equal(nodes[0].stop.mock.callCount(),1);assert.equal(nodes[1].disconnect.mock.callCount(),1);
});
