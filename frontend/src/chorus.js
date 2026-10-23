// Two original synthetic voices share one browser audio clock. No cloud TTS.
export function createChorus(onStatus) {
  let context=null,id=null,lastSeen=0;
  const nodes=new Set();
  async function enable(){context??=new AudioContext();await context.resume();onStatus('合唱声音已启用 · 本地双声部');}
  function stop(){const active=Boolean(id||nodes.size);for(const node of nodes){try{node.stop();}catch{/* already ended */}}nodes.clear();id=null;if(active)onStatus('合唱声音已停止 · 本地双声部');}
  function update(chorus){
    if(!chorus){stop();return;}lastSeen=performance.now();
    if(chorus.id===id)return;stop();id=chorus.id;
    if(context?.state!=='running'){onStatus('合唱动作进行中，声音未启用。点击“启用合唱声音”。');id=null;return;}
    const melody=[0,2,4,2,0,-3],start=context.currentTime+.08-chorus.elapsed;
    for(let beat=0;beat<6;beat++){
      if(beat*.5<chorus.elapsed-.02)continue;
      for(const base of [196,293.665]){
        const at=start+beat*.5,osc=context.createOscillator(),gain=context.createGain(),filter=context.createBiquadFilter();
        osc.type='triangle';const hz=base*2**(melody[beat]/12);osc.frequency.setValueAtTime(hz*1.12,at);osc.frequency.exponentialRampToValueAtTime(hz,at+.12);
        filter.type='bandpass';filter.frequency.value=800;filter.Q.value=1.4;
        gain.gain.setValueAtTime(0,at);gain.gain.linearRampToValueAtTime(.28,at+.025);gain.gain.exponentialRampToValueAtTime(.001,at+.36);
        osc.connect(filter);filter.connect(gain);gain.connect(context.destination);osc.start(at);osc.stop(at+.4);nodes.add(osc);osc.onended=()=>{nodes.delete(osc);osc.disconnect();filter.disconnect();gain.disconnect();};
      }
    }
    onStatus('本地双声部正在合唱 · 同一个音频时钟');
  }
  const timer=setInterval(()=>{if(nodes.size&&performance.now()-lastSeen>750){stop();onStatus('场景状态中断，合唱声音已停止');}},250);
  return {enable,update,stop,dispose(){clearInterval(timer);stop();context?.close();}};
}
