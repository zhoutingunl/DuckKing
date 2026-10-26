import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {DEMOS,AUDIO_LINES} from '../src/demo-catalog.js';
import {pcmWave,pause,DemoVoice,matchesCloudActions} from '../src/demo-runtime.js';
import {ChoraleRoster,openingScore} from '../src/chorale-demo.js';
import {checkTrackFiles,checkOffset,decodeTracks,originalTableScore,TABLE_SECONDS,TABLE_TEMPO,playTableChoir} from '../src/table-choir.js';
import {seatedScore} from '../src/seated-choir.js';
import {TABLE_SCORES,odeToJoyScore,tigerCanonScore} from '../src/table-scores.js';

test('recognizable scores preserve melody, independent SATB and eight-beat canon entrances',()=>{
  const ode=odeToJoyScore(),tigers=tigerCanonScore();
  assert.deepEqual(ode.filter(n=>n.part===3).slice(0,8).map(n=>n.midi),[71,71,72,74,74,72,71,69]);
  assert.equal(new Set([0,1,2,3].map(part=>JSON.stringify(ode.filter(n=>n.part===part).map(n=>n.midi)))).size,4);
  for(const [part,transpose] of [0,-12,0,12].entries()){
    const phrase=tigers.filter(n=>n.part===part);
    assert.equal(phrase[0].beat,part*8);
    assert.deepEqual(phrase.slice(0,4).map(n=>n.midi-transpose),[60,62,64,60]);
  }
  for(const score of Object.values(TABLE_SCORES)){
    assert.throws(()=>checkOffset(score,1));checkOffset(score,0);
    assert.ok(score.notes.every(n=>n.beat>=0&&n.duration>0&&n.midi>=36&&n.midi<=84&&(n.beat+n.duration)*60/score.bpm<=TABLE_SECONDS));
    assert.ok(score.gains.reduce((a,b)=>a+b,0)<.6);
    for(let part=0;part<4;part++){
      const line=score.notes.filter(n=>n.part===part);assert.equal(line.at(-1).beat+line.at(-1).duration,64);
      assert.ok(line.every((n,i)=>!i||line[i-1].beat+line[i-1].duration===n.beat));
    }
  }
});

test('all thirteen scripts have real bounded PCM audio, with no microphone requirement',()=>{
  assert.equal(DEMOS.length,13);assert.equal(new Set(DEMOS.map(d=>d.id)).size,13);
  assert.equal(new Set(AUDIO_LINES.map(d=>d.id)).size,AUDIO_LINES.length);
  for(const line of AUDIO_LINES){
    const bytes=readFileSync(new URL('../public/demo-audio/'+line.id+'.wav',import.meta.url));
    const pcm=pcmWave(bytes.buffer.slice(bytes.byteOffset,bytes.byteOffset+bytes.byteLength));
    assert.ok(pcm.some(v=>Math.abs(v)>100));assert.ok(pcm.length<=15*16000);
  }
  assert.throws(()=>pcmWave(new ArrayBuffer(50)));
});
test('cancel stops a waiting timeline and prevents subsequent steps',async()=>{
  const controller=new AbortController();let progressed=false;
  const pending=pause(200,controller.signal).then(()=>{progressed=true});controller.abort();
  await assert.rejects(pending,{name:'AbortError'});assert.equal(progressed,false);
  await assert.rejects(pause(1,controller.signal),{name:'AbortError'});
});
test('cloud may prepare the current scene before its required actions, but cannot replace or reset them',()=>{
  const completed=(...names)=>names.map(name=>({name,status:'completed'}));
  assert.equal(matchesCloudActions(completed('scene_ball','kick_left'),['kick_left'],'ball'),true);
  assert.equal(matchesCloudActions(completed('kick_left'),['kick_left'],'ball'),true);
  assert.equal(matchesCloudActions(completed('scene_ball'),[],'ball'),true);
  assert.equal(matchesCloudActions(completed('stop','scene_ball','nod'),['nod'],'ball'),true);
  assert.equal(matchesCloudActions(completed('stop','scene_carry','pick_up','carry','put_down'),['pick_up','carry','put_down'],'carry'),true);
  for(const names of [['scene_duo','kick_left'],['scene_ball'],['scene_ball','kick_right'],['kick_left','scene_ball'],['scene_ball','scene_ball','kick_left'],['kick_left','nod']]){
    assert.equal(matchesCloudActions(completed(...names),['kick_left'],'ball'),false,names.join(','));
  }
  assert.equal(matchesCloudActions(completed('pick_up','scene_carry','carry','put_down'),['pick_up','carry','put_down'],'carry'),false);
  assert.equal(matchesCloudActions([{name:'scene_ball',status:'failed'},...completed('kick_left')],['kick_left'],'ball'),false);
  assert.equal(matchesCloudActions([{name:'kick_left',status:'cancelled'}],['kick_left'],'ball'),false);
});
test('recorded commands use 1920 byte frames, pad the tail, and abort bounds uplink',async()=>{
  const voice=new DemoVoice('1',{},()=>{});voice.state='ready';const frames=[];
  voice.send=value=>{if(value.type==='listen_start')voice.state='listening';frames.push(value)};
  await voice.input(new Int16Array(1000).fill(123),new AbortController().signal);
  const pcm=frames.filter(x=>x instanceof ArrayBuffer);
  assert.equal(pcm.length,2);assert.ok(pcm.every(x=>x.byteLength===1920));
  assert.equal(new Int16Array(pcm[1])[39],123);assert.equal(new Int16Array(pcm[1])[40],0);
  assert.equal(frames.at(-1).type,'listen_stop');
  const controller=new AbortController();voice.state='ready';frames.length=0;
  const pending=voice.input(new Int16Array(16000),controller.signal);setTimeout(()=>controller.abort(),80);
  await assert.rejects(pending,{name:'AbortError'});assert.ok(frames.filter(x=>x instanceof ArrayBuffer).length<=2);
});
test('chorale preserves seats on late join, departure and return',()=>{
  const choir=new ChoraleRoster([{id:42,pitch:330},{id:7,pitch:160}]);
  assert.equal(choir.conductor,7);assert.deepEqual(choir.seats.map(s=>s.part),['bass','soprano']);
  assert.equal(choir.join({id:64,pitch:100}).part,'alto');
  assert.equal(choir.join({id:100,pitch:440}).part,'tenor');
  choir.leave(64);assert.equal(choir.seats[2].part,'alto');assert.equal(choir.seats[2].active,false);
  assert.throws(()=>choir.join({id:200,pitch:500}));
  assert.equal(choir.join({id:64,pitch:100}).part,'alto');assert.equal(choir.seats.length,4);
});
test('official score opening is sixteen beats with four different harmonic lines',()=>{
  const text=readFileSync(new URL('../public/scores/wistful.duckscore',import.meta.url),'utf8');
  const score=openingScore(text);assert.equal(score.bpm,58);assert.equal(score.beats,16);
  assert.deepEqual(score.notes.slice(0,4).map(n=>n.midi),[48,55,60,64]);
  assert.deepEqual(score.notes.slice(0,4).map(n=>n.beat),[0,.75,1.5,2.25]);
  assert.throws(()=>openingScore('bpm: 120'));
});

test('human instructions and duck dialogue ship distinct synthetic voices and processing',()=>{
  const manifest=JSON.parse(readFileSync(new URL('../public/demo-audio/manifest.json',import.meta.url)));
  const lines=manifest.lines;
  const human=lines.find(line=>line.id==='football-left'),duck=lines.find(line=>line.id==='interview-joke');
  assert.notEqual(human.voice,duck.voice);assert.notEqual(human.processing,duck.processing);
  assert.equal(lines.length,AUDIO_LINES.length);
});


test('table song input and original notes are bounded, invalid files cannot fall back',async()=>{
  for(const files of [[],[{size:1},{size:1}],[{size:0}],[{size:26*1024*1024}],Array(4).fill({size:11*1024*1024})])assert.throws(()=>checkTrackFiles(files));
  checkTrackFiles([{size:1}]);checkTrackFiles(Array(4).fill({size:1}));
  for(const offset of [-1,Infinity,NaN,601])assert.throws(()=>checkOffset(null,offset));
  assert.throws(()=>checkOffset({buffers:[{duration:40}]},5));checkOffset({buffers:[{duration:40}]},4);
  await assert.rejects(decodeTracks([{size:100,arrayBuffer:async()=>new ArrayBuffer(100)}],{decodeAudioData:async()=>({duration:10,length:160000,numberOfChannels:1})}));
  const notes=originalTableScore();assert.equal(new Set(notes.map(n=>n.part)).size,4);
  assert.ok(notes.every(n=>n.beat>=0&&n.duration>0&&(n.beat+n.duration)*60/TABLE_TEMPO<=TABLE_SECONDS+.001));
  const controller=new AbortController(),pending=playTableChoir({context(){throw new Error('audio must not start')}},controller.signal,()=>null,()=>{});
  controller.abort();await assert.rejects(pending,{name:'AbortError'});
});

test('seated solo score gives each standing singer a complete phrase without other voices',()=>{
 const notes=seatedScore();
 assert.ok(notes.every(n=>n.beat>=0&&n.duration>0&&(n.beat+n.duration)/2<=40));
 for(let part=0;part<4;part++){
  const first=12+part*16,last=first+8;
  const audible=notes.filter(n=>n.beat<last&&n.beat+n.duration>first);
  assert.ok(audible.length>0&&audible.every(n=>n.solo&&n.part===part));
  assert.equal(audible.reduce((n,note)=>n+note.duration,0),8);
 }
 for(const beat of [0,72])assert.equal(new Set(notes.filter(n=>n.beat===beat).map(n=>n.part)).size,4);
});
