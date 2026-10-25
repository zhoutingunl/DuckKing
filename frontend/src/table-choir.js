// User-supplied song mixes, plus a separately selectable original rehearsal score.
import {pause,until} from './demo-runtime.js';
import {appURL} from './urls.js';
import {TABLE_SCORES} from './table-scores.js';
export const TABLE_SECONDS=36, TABLE_TEMPO=72;
export const TABLE_PARTS=['低音','次中音','中音','高音'];
export const BUILTIN_SONGS={
  choir:{title:'夜空中最亮的星 · 鸭声和声版',files:['night-star-a.mp3','night-star-b.mp3','night-star-c.mp3','night-star-d.mp3'],source:'user_provided_octave_chorus_mix',parts:['低八度鸭声','齐唱鸭声','高八度鸭声','轻声人声主唱'],pans:[-.55,-.2,.55,0]},
  vocal:{title:'夜空中最亮的星 · 原人声版',files:['night-star-vocal.mp3'],source:'user_provided_vocal_mix'},
  instrumental:{title:'夜空中最亮的星 · 器乐版',files:['night-star-instrumental.mp3'],source:'user_provided_instrumental_mix'},
};
const musicCache=new Map();
export async function loadBuiltinSong(name,ctx,signal){
  signal.throwIfAborted();
  if(TABLE_SCORES[name])return TABLE_SCORES[name];
  if(name==='original')return null;
  const info=BUILTIN_SONGS[name];if(!info)throw new Error('未知歌曲音源');
  if(musicCache.has(name))return musicCache.get(name);
  const buffers=await Promise.all(info.files.map(async file=>{
    const url=appURL('demo-music/'+file);url.searchParams.set('v','duck-forward-20261025');
    const response=await fetch(url,{signal:AbortSignal.any([signal,AbortSignal.timeout(30000)])});
    if(!response.ok)throw new Error('歌曲音源加载失败，请重演；不会自动替换曲目');
    return ctx.decodeAudioData(await response.arrayBuffer());
  }));
  signal.throwIfAborted();const tracks={...info,buffers,names:[info.title]};checkOffset(tracks,0);
  musicCache.set(name,tracks);if(musicCache.size>2)musicCache.delete(musicCache.keys().next().value);return tracks;
}
export function originalTableScore(){
  const chords=[[48,55,60,64],[45,52,57,60],[41,48,53,57],[43,50,55,59],[48,55,60,64],[45,52,57,60]];
  const notes=[];
  chords.forEach((chord,bar)=>{
    for(let part=0;part<3;part++)for(let beat=0;beat<8;beat+=4)notes.push({part,midi:chord[part],beat:bar*8+beat,duration:4});
    const melody=[chord[3],chord[1]+12,chord[0]+24,chord[1]+12,chord[3],chord[2],chord[3],chord[1]+12];
    melody.forEach((midi,beat)=>notes.push({part:3,midi,beat:bar*8+beat,duration:.92}));
  });
  return notes.filter(n=>n.beat<TABLE_SECONDS*TABLE_TEMPO/60).map(n=>({...n,duration:Math.min(n.duration,TABLE_SECONDS*TABLE_TEMPO/60-n.beat)}));
}
export function checkTrackFiles(files){
  if(![1,4].includes(files.length))throw new Error('请选择一份歌曲混音，或四份按鸭 A—D 排列的分声部音轨');
  if(files.some(f=>!f.size||f.size>25*1024*1024)||files.reduce((n,f)=>n+f.size,0)>40*1024*1024)throw new Error('音源过大，请选择总计 40 MB 以内的演示片段');
}
export async function decodeTracks(files,ctx){
  checkTrackFiles(files);const buffers=[];let samples=0;
  for(const file of files){
    const buffer=await ctx.decodeAudioData(await file.arrayBuffer());
    samples+=buffer.length*buffer.numberOfChannels;
    if(samples>20_000_000||buffer.duration<TABLE_SECONDS)throw new Error('请选择不少于 36 秒的短音频片段；多轨建议每轨 36—60 秒');
    buffers.push(buffer);
  }
  return {buffers,names:files.map(f=>f.name)};
}
export function checkOffset(tracks,offset){
  if(!Number.isFinite(offset)||offset<0||offset>600)throw new Error('起播位置须在 0—600 秒之间');
  if(tracks?.notes&&offset!==0)throw new Error('合成曲目从第 0 秒开始，请将起播位置归零');
  if(tracks?.buffers?.some(b=>b.duration<offset+TABLE_SECONDS))throw new Error('起播位置之后需要至少 36 秒音频');
}
export async function playTableChoir(output,signal,readState,onFrame,{tracks=null,offset=0}={}){
  checkOffset(tracks,offset);
  await until(()=>readState()?.running,{signal,timeout:10000});
  const ctx=output.context();if(ctx.state!=='running')throw new Error('声音未启用，请重新点击节目');
  const first=readState(),start=ctx.currentTime-first.elapsed,seconds=60/(tracks?.bpm??TABLE_TEMPO);
  const master=ctx.createGain();master.gain.value=.7;master.connect(ctx.destination);
  const buses=TABLE_PARTS.map((_,i)=>{const gain=ctx.createGain(),pan=ctx.createStereoPanner();pan.pan.value=tracks?.pans?.[i]??(i-1.5)*.35;gain.connect(pan);pan.connect(master);return {gain,pan}});
  const nodes=new Set(),scheduled=new Set(),score=tracks?.notes??originalTableScore();let reacted=false,lastProgress=performance.now(),lastElapsed=first.elapsed;
  const stop=()=>{for(const source of nodes){try{source.stop()}catch{}}};
  signal.addEventListener('abort',stop,{once:true});
  function hum(note,elapsed){
    const from=Math.max(note.beat*seconds,elapsed),length=(note.beat+note.duration)*seconds-from;
    if(length<.04)return;
    const at=Math.max(ctx.currentTime,start+from),osc=ctx.createOscillator(),gain=ctx.createGain();
    // Keep the fundamental audible: the previous vowel-only filters obscured
    // recognizable melodies. A gentle triangle voice carries the pitch.
    osc.type='triangle';osc.frequency.value=440*2**((note.midi-69)/12);
    const filter=ctx.createBiquadFilter();filter.type='lowpass';filter.frequency.value=2600;osc.connect(filter);filter.connect(gain);
    const volume=tracks?.gains?.[note.part]??.10,attack=Math.min(.025,length/4),release=Math.min(.07,length/3);
    gain.gain.setValueAtTime(0,at);gain.gain.linearRampToValueAtTime(volume,at+attack);gain.gain.setValueAtTime(volume,at+length-release);gain.gain.linearRampToValueAtTime(0,at+length);
    gain.connect(buses[note.part].gain);osc.start(at);osc.stop(at+length+.01);nodes.add(osc);
    osc.onended=()=>{nodes.delete(osc);osc.disconnect();gain.disconnect();filter.disconnect()};
  }
  function stumble(){
    const osc=ctx.createOscillator(),gain=ctx.createGain(),at=ctx.currentTime;
    osc.type='triangle';osc.frequency.setValueAtTime(380,at);osc.frequency.exponentialRampToValueAtTime(90,at+.25);
    gain.gain.setValueAtTime(.07,at);gain.gain.exponentialRampToValueAtTime(.001,at+.3);
    osc.connect(gain);gain.connect(master);osc.start();osc.stop(at+.32);nodes.add(osc);
    osc.onended=()=>{nodes.delete(osc);osc.disconnect();gain.disconnect()};
  }
  try{
    if(tracks?.buffers)tracks.buffers.forEach((buffer,i)=>{
      const source=ctx.createBufferSource();source.buffer=buffer;source.connect(tracks.buffers.length===1?master:buses[i].gain);
      source.start(ctx.currentTime,offset+first.elapsed,TABLE_SECONDS-first.elapsed);nodes.add(source);source.onended=()=>{nodes.delete(source);source.disconnect()};
    });
    const deadline=performance.now()+TABLE_SECONDS*1000+5000;
    while(ctx.currentTime<start+TABLE_SECONDS){
      signal.throwIfAborted();const state=readState(),elapsed=Math.max(0,ctx.currentTime-start);
      if(ctx.state!=='running'||performance.now()>deadline)throw new Error('合唱音频时钟已暂停或超时，请重演');
      if(!state||['failed','stopped'].includes(state.phase))throw new Error('物理表演已停止，音乐同步停止');
      if(state.elapsed>lastElapsed){lastElapsed=state.elapsed;lastProgress=performance.now()}
      if(performance.now()-lastProgress>4000)throw new Error('桌上物理状态长时间未更新，音乐已停止');
      const dropped=state.dropped_at!==null,returning=state.landed_at!==null&&state.elapsed-state.landed_at>1.2;
      master.gain.setTargetAtTime(state.phase==='surprised'?.12:.7,ctx.currentTime,.06);
      buses[3].gain.gain.setTargetAtTime(dropped&&!returning?0:1,ctx.currentTime,.05);
      if(dropped&&!reacted){reacted=true;stumble()}
      if(!tracks?.buffers)for(const [id,note] of score.entries()){
        if(scheduled.has(id)||note.beat*seconds>elapsed+.08||(note.beat+note.duration)*seconds<=elapsed)continue;
        scheduled.add(id);hum(note,elapsed);
      }
      onFrame({elapsed,phase:state.phase,dropped,landed:state.landed_at!==null,returning,floorDancing:state.floor_dance?.started_at!=null,parts:tracks?.buffers?.length??4,activeParts:(tracks?.entries??[0,0,0,0]).map((beat,i)=>elapsed>=beat*seconds&&!(i===3&&dropped&&!returning))});
      await pause(30,signal);
    }
    return {source:tracks?.source??(tracks?'user_selected_audio':'original_synth_harmony'),parts:tracks?.buffers?.length??4,duration:TABLE_SECONDS,physical_ducks:4,fall_cue:reacted,ble:false};
  }finally{signal.removeEventListener('abort',stop);stop();master.disconnect();buses.forEach(b=>{b.gain.disconnect();b.pan.disconnect()});}
}
