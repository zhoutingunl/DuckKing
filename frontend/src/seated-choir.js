import {pause,until} from './demo-runtime.js';
import {odeToJoyScore} from './table-scores.js';

export const SEATED_SECONDS=40;
export function seatedScore(){
  const original=odeToJoyScore().filter(n=>n.beat<32),notes=[];
  for(const n of original){
    if(n.beat<8)notes.push({...n,solo:false});
    if(n.beat>=24)notes.push({...n,beat:72+n.beat-24,solo:false});
  }
  for(let part=0;part<4;part++){
    const phrase=original.filter(n=>n.part===3&&n.beat>=part*8&&n.beat<(part+1)*8);
    for(const n of phrase)notes.push({...n,part,midi:n.midi+[-12,0,0,12][part],beat:12+part*16+n.beat-part*8,solo:true});
    // Quiet ensemble chords cover the actual rise and return transitions.
    for(const beat of [8+part*16,20+part*16])for(let voice=0;voice<4;voice++){
      notes.push({part:voice,midi:(part%2?[50,62,66,69]:[55,62,67,71])[voice],beat,duration:4,bridge:true,solo:false});
    }
  }
  return notes.sort((a,b)=>a.beat-b.beat);
}

export async function playSeatedChoir(output,signal,readState,onFrame){
  await until(()=>readState()?.music_started&&readState()?.running,{signal,timeout:12000});
  const ctx=output.context();
  if(ctx.state!=='running')throw new Error('声音未启用，请重新点击节目');
  const master=ctx.createGain();master.gain.value=.7;master.connect(ctx.destination);
  const pans=[-.65,-.2,.2,.65].map(value=>{const node=ctx.createStereoPanner();node.pan.value=value;node.connect(master);return node});
  const nodes=new Set(),scheduled=new Set(),solos=new Set(),score=seatedScore();
  const first=readState(),deadline=performance.now()+45000;
  let lastElapsed=first.elapsed,lastProgress=performance.now(),frameKey=null;
  const stop=()=>{for(const node of nodes){try{node.stop()}catch{}}};
  signal.addEventListener('abort',stop,{once:true});
  try{
    while(true){
      signal.throwIfAborted();
      if(ctx.state!=='running'||performance.now()>deadline)throw new Error('合唱音频时钟已暂停或超时，请重演');
      const state=readState();
      if(!state||['stopped','failed'].includes(state.phase))throw new Error(state?.error??'坐姿合唱物理编排已停止');
      if(state.phase==='completed'&&state.elapsed>=SEATED_SECONDS)break;
      if(state.elapsed>lastElapsed){lastElapsed=state.elapsed;lastProgress=performance.now()}
      if(performance.now()-lastProgress>4000)throw new Error('坐姿合唱状态长时间未更新，音乐已停止');
      // Follow the confirmed physical phase. The browser audio clock can run
      // ahead while rendering delays state handling; it must not skip a singer.
      const elapsed=state.elapsed;
      for(const [id,note] of score.entries()){
        const from=note.beat/2,end=(note.beat+note.duration)/2;
        if(scheduled.has(id)||(!note.solo&&from>elapsed+.06)||end<=elapsed)continue;
        if(note.solo){
          if(state.phase!=='solo'||state.solo!=='abcd'[note.part])continue;
          if(state.postures[note.part]?.observed!=='stand')throw new Error('未确认独唱者站稳，声音已停止');
        }
        const at=ctx.currentTime+Math.max(0,from-elapsed),duration=end-Math.max(elapsed,from);
        if(duration<.04)continue;
        scheduled.add(id);
        const osc=ctx.createOscillator(),gain=ctx.createGain(),filter=ctx.createBiquadFilter();
        osc.type='triangle';osc.frequency.value=440*2**((note.midi-69)/12);
        filter.type='lowpass';filter.frequency.value=2600;
        osc.connect(filter);filter.connect(gain);gain.connect(pans[note.part]);
        const volume=note.solo?.18:note.bridge?.025:[.065,.065,.075,.13][note.part];
        gain.gain.setValueAtTime(0,at);gain.gain.linearRampToValueAtTime(volume,at+.02);
        gain.gain.setValueAtTime(volume,at+Math.max(.02,duration-.07));gain.gain.linearRampToValueAtTime(0,at+duration);
        osc.start(at);osc.stop(at+duration+.01);nodes.add(osc);
        if(note.solo)solos.add(state.solo);
        osc.onended=()=>{nodes.delete(osc);osc.disconnect();gain.disconnect();filter.disconnect()};
      }
      const key=[state.phase,state.solo,Math.floor(elapsed),...state.postures.map(p=>p.observed)].join(':');
      if(key!==frameKey){frameKey=key;onFrame({...state,elapsed,activeParts:[0,1,2,3].map(i=>state.phase!=='solo'||state.solo==='abcd'[i])})}
      await pause(30,signal);
    }
    if([...solos].join('')!=='abcd')throw new Error('未实际播放四位歌手的独唱，请重演');
    return {source:'public_domain_ode_seated_solos',parts:4,solos:[...solos],duration:SEATED_SECONDS,physical_ducks:4,ble:false};
  }finally{signal.removeEventListener('abort',stop);stop();master.disconnect();pans.forEach(p=>p.disconnect())}
}
