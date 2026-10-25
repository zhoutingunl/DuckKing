// Public-domain melodies. Source transcriptions and adaptation notes:
// THIRD_PARTY.md. These are local synthesized voices, not Linx singing.
const bars = text => text.split('|').flatMap(bar => bar.trim().split(/\s+/).map(token => {
  const [midi,duration='1']=token.split(':');return {midi:Number(midi),duration:Number(duration)};
}));
function line(part,notes,start=0){let beat=start;return notes.map(note=>{const n={...note,part,beat};beat+=note.duration;return n})}

export function odeToJoyScore(){
  // First eight bars of Peter Chubb's Mutopia SATB engraving, repeated.
  const parts=[
    '55 55 55 55 | 52:1.5 54:.5 55 50 | 59 59 57 55 | 50:1.5 50:.5 50:2 | 55 55 55 55 | 52:1.5 54:.5 55 50 | 59 59 57 55 | 50 50 43:2',
    '62 62 60 59 | 64:1.5 62:.5 62 62 | 59 59 62 62 | 62:1.5 62:.5 62:2 | 62 62 60 59 | 64:1.5 62:.5 62 62 | 59 59 62 62 | 62 62 59:2',
    '67 67 69 67 | 67:1.5 69:.5 67 66 | 62 62 66 67 | 67:1.5 66:.5 66:2 | 67 67 69 67 | 67:1.5 69:.5 67 66 | 62 62 66 67 | 67 66 62:2',
    '71 71 72 74 | 74 72 71 69 | 67 67 69 71 | 71:1.5 69:.5 69:2 | 71 71 72 74 | 74 72 71 69 | 67 67 69 71 | 69:1.5 67:.5 67:2',
  ];
  return parts.flatMap((part,i)=>[...line(i,bars(part)),...line(i,bars(part),32)]);
}
export function tigerCanonScore(){
  // Traditional Frère Jacques, transposed to C, entrances eight beats apart.
  const melody=bars('60 62 64 60 | 60 62 64 60 | 64 65 67:2 | 64 65 67:2 | 67:.5 69:.5 67:.5 65:.5 64 60 | 67:.5 69:.5 67:.5 65:.5 64 60 | 60 55 60:2 | 60 55 60:2');
  return [0,-12,0,12].flatMap((transpose,part)=>{
    const notes=[];
    for(let start=part*8;start<60;start+=32)notes.push(...line(part,melody.map(n=>({...n,midi:n.midi+transpose})),start));
    return [...notes.filter(n=>n.beat<60).map(n=>({...n,duration:Math.min(n.duration,60-n.beat)})),{part,midi:[60,48,64,72][part],beat:60,duration:4}];
  });
}
export const TABLE_SCORES={
  ode:{title:'欢乐颂 · 四声部',source:'public_domain_ode_satb',bpm:108,notes:odeToJoyScore(),gains:[.075,.075,.085,.17],parts:['低音','次中音','中音','主旋律 · 高音'],entries:[0,0,0,0],description:'四个独立声部，高音鸭 D 领唱。它掉下桌时，主旋律会短暂缺席。'},
  tigers:{title:'两只老虎 · 四鸭轮唱',source:'traditional_frere_jacques_canon',bpm:108,notes:tigerCanonScore(),gains:[.14,.10,.11,.10],parts:['第一轮','第二轮 · 低八度','第三轮','第四轮 · 高八度'],entries:[0,8,16,24],description:'鸭 A 先唱，B、C、D 每隔 8 拍加入；同一旋律交错，最后一起收尾。'},
};
