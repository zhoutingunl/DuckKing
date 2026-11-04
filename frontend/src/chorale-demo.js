// Score and seating conventions: Pollen Robotics, pinned 942e58e (Apache-2.0).
// This is an application-level listening demo, not a BLE/duckether implementation.
import { appURL } from './urls.js';
import { pause } from './demo-runtime.js';
const PARTS=['bass','tenor','alto','soprano'];
export const PART_NAMES={bass:'低音',tenor:'次中音',alto:'中音',soprano:'高音'};
const ensemble=n=>n===1?['soprano']:n===2?['bass','soprano']:n===3?['bass','alto','soprano']:PARTS;
export class ChoraleRoster {
  constructor(ducks){
    if(!ducks.length||ducks.length>4||new Set(ducks.map(d=>d.id)).size!==ducks.length)throw new Error('声部名单无效');
    this.seats=ducks.slice().sort((a,b)=>a.pitch-b.pitch||a.id-b.id).map((duck,i)=>({...duck,part:ensemble(ducks.length)[i],active:true}));
    this.conductor=Math.min(...ducks.map(d=>d.id));
  }
  join(duck){
    const old=this.seats.find(s=>s.id===duck.id);if(old){old.active=true;return old}
    if(this.seats.length===4)throw new Error('四个席位已满，本轮不重排声部');
    const part=ensemble(this.seats.length+1).find(p=>!this.seats.some(s=>s.part===p));
    const seat={...duck,part,active:true};this.seats.push(seat);return seat;
  }
  leave(id){const seat=this.seats.find(s=>s.id===id);if(seat)seat.active=false;}
}
function midi(note){const match=/^([A-G])([#b]?)(\d)$/.exec(note);if(!match)throw new Error('不支持的谱面音符');return 12*(Number(match[3])+1)+({C:0,D:2,E:4,F:5,G:7,A:9,B:11}[match[1]])+({b:-1,'#':1,'':0}[match[2]])}
export function openingScore(text){
  const notes=[];let beat=0,bpm=0;
  for(const raw of text.split('\n')){
    const line=raw.split('# ')[0].trim();if(line.startsWith('bpm:'))bpm=Number(line.slice(4));
    if(line.startsWith('solo '))break; // Exact opening excerpt: 16 beats, no invented continuation.
    const m=/^(chord|build)\s+([\d.]+)(?:\s+stagger\s+([\d.]+))?\s+([A-G][^\s]*\s+[A-G][^\s]*\s+[A-G][^\s]*\s+[A-G][^\s]*)$/.exec(line);
    if(!m)continue;const duration=Number(m[2]),stagger=Number(m[3]??0);
    m[4].split(/\s+/).forEach((note,i)=>{const offset=stagger*i;notes.push({part:PARTS[i],midi:midi(note),beat:beat+offset,duration:duration-offset})});beat+=duration;
  }
  if(bpm!==58||beat!==16||notes.length!==20)throw new Error('官方乐谱与固定节选不一致');
  return {bpm,beats:beat,notes};
}
export async function playChorale(output,signal,onFrame){
  const response=await fetch(appURL('scores/wistful.duckscore'),{signal});if(!response.ok)throw new Error('官方乐谱读取失败');
  const score=openingScore(await response.text());
  const ctx=output.context();if(ctx.state!=='running')throw new Error('声音尚未启用，请重新点击开始');
  const roster=new ChoraleRoster([{id:7,pitch:165,label:'鸭 A'},{id:42,pitch:330,label:'鸭 B'}]);
  const start=ctx.currentTime+.15,seconds=60/score.bpm,nodes=new Set(),scheduled=new Set();let joined3=false,joined4=false,left=false;
  function tone(note,seat,beat){
    const at=start+Math.max(beat,note.beat)*seconds,duration=(note.beat+note.duration-Math.max(beat,note.beat))*seconds;
    if(duration<=.03)return;
    const osc=ctx.createOscillator(),gain=ctx.createGain(),filter=ctx.createBiquadFilter();
    osc.type='sawtooth';osc.frequency.value=440*2**((note.midi-69)/12);osc.detune.value=seat.id%7-3;
    filter.type='lowpass';filter.frequency.value=950;filter.Q.value=.7;
    gain.gain.setValueAtTime(0,at);gain.gain.linearRampToValueAtTime(.045,at+.08);gain.gain.setValueAtTime(.045,at+Math.max(.08,duration-.12));gain.gain.linearRampToValueAtTime(0,at+duration);
    osc.connect(filter);filter.connect(gain);gain.connect(ctx.destination);osc.start(at);osc.stop(at+duration+.02);
    const node={osc,gain,part:note.part};nodes.add(node);osc.onended=()=>{nodes.delete(node);osc.disconnect();gain.disconnect();filter.disconnect()};
  }
  const deadline=performance.now()+score.beats*seconds*1000+5000;
  try{
    while(ctx.currentTime<start+score.beats*seconds){
      signal.throwIfAborted();if(ctx.state!=='running'||performance.now()>deadline)throw new Error('合奏音频时钟已暂停或超时，请重新点击节目');const beat=Math.max(0,(ctx.currentTime-start)/seconds);
      if(beat>=3&&!joined3){roster.join({id:64,pitch:260,label:'虚拟鸭 C'});joined3=true}
      if(beat>=7&&!joined4){roster.join({id:100,pitch:220,label:'虚拟鸭 D'});joined4=true}
      if(beat>=12&&!left){roster.leave(64);left=true;for(const node of nodes)if(node.part==='alto'){node.gain.gain.cancelScheduledValues(ctx.currentTime);node.gain.gain.setTargetAtTime(0,ctx.currentTime,.04)}}
      for(const seat of roster.seats.filter(s=>s.active))for(const [index,note] of score.notes.entries()){
        const key=seat.id+':'+index;if(note.part!==seat.part||scheduled.has(key)||note.beat+note.duration<=beat||note.beat>beat+.12)continue;
        scheduled.add(key);tone(note,seat,beat);
      }
      onFrame({beat,conductor:roster.conductor,seats:roster.seats.map(s=>({...s})),active:roster.seats.filter(s=>s.active).length});
      await pause(30,signal);
    }
    return {source:'official_score_local_synth',score:'wistful opening 16 beats',parts:4,ble:false,seats:roster.seats};
  }finally{for(const node of nodes){try{node.osc.stop()}catch{}}onFrame(null);}
}
