import {test} from 'node:test';
import assert from 'node:assert/strict';
import {alignClockedAudio,contextTimeToWall} from '../scripts/recorded-audio.mjs';

test('a delayed audio context starts at the actual output clock, not recorder creation',()=>{
 const aligned=alignClockedAudio({pcm:new Float32Array([.1,.2,.3,.4]),sampleRate:1000,channels:1,firstFrame:2000,anchors:[{frame:2000,wall_time_ms:108000},{frame:2002,wall_time_ms:108002}]});
 assert.equal(aligned.started_wall_time_ms,108000);
 assert.equal(contextTimeToWall(aligned,2.003),108003);
 assert.deepEqual([...aligned.pcm],[...new Float32Array([.1,.2,.3,.4])]);
});

test('suspended audio time becomes silence on the video wall clock',()=>{
 const pcm=new Float32Array(2000).fill(.5);
 const aligned=alignClockedAudio({pcm,sampleRate:1000,channels:1,firstFrame:0,anchors:[{frame:0,wall_time_ms:100000},{frame:900,wall_time_ms:100900},{frame:1000,wall_time_ms:105000},{frame:1900,wall_time_ms:105900}]});
 assert.equal(aligned.pcm.length,6000);
 assert.ok(aligned.pcm.subarray(0,1000).every(v=>v===.5));
 assert.ok(aligned.pcm.subarray(1000,5000).every(v=>v===0));
 assert.ok(aligned.pcm.subarray(5000).every(v=>v===.5));
 assert.equal(contextTimeToWall(aligned,1.2),105200);
});

test('uncalibrated or backwards output clocks fail instead of guessing a sync offset',()=>{
 const base={pcm:new Float32Array(2000),sampleRate:1000,channels:1,firstFrame:0};
 assert.throws(()=>alignClockedAudio({...base,anchors:[]}),/anchors/);
 assert.throws(()=>alignClockedAudio({...base,anchors:[{frame:0,wall_time_ms:100000},{frame:1000,wall_time_ms:99000}]}),/backwards/);
});
