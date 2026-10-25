import {odeToJoyScore} from './table-scores.js';

// A short phrase begins only after the selected physical singer is confirmed standing.
export class StudioChoir {
 constructor(){this.ctx=null;this.nodes=new Set();this.key=null;this.played=new Set();this.watch=null}
 async enable(){this.ctx??=new AudioContext();await this.ctx.resume();return this.ctx.state==='running'}
 stop(){for(const node of this.nodes){try{node.stop()}catch{}}this.nodes.clear();clearTimeout(this.watch);this.played.clear();this.key=null}
 update(state){
  if(!state?.live||!state.running||state.phase!=='solo'||!state.music_started){this.stop();return}
  const part='abcd'.indexOf(state.solo);
  if(part<0||state.postures[part]?.observed!=='stand'){this.stop();return}
  const key=`${state.performance_id}:${state.solo}`;
  if(key!==this.key){this.stop();this.key=key}
  clearTimeout(this.watch);this.watch=setTimeout(()=>this.stop(),1200);
  if(this.ctx?.state!=='running')return;
  const phrase=odeToJoyScore().filter(n=>n.part===3&&n.beat<8);
  for(const [i,n] of phrase.entries()){
   const from=n.beat/2,end=(n.beat+n.duration)/2;
   if(this.played.has(i)||from>state.elapsed+.12||end<=state.elapsed)continue;
   this.played.add(i);const duration=Math.min(4,end)-Math.max(state.elapsed,from);
   if(duration<.04)continue;
   const ctx=this.ctx,osc=ctx.createOscillator(),gain=ctx.createGain(),pan=ctx.createStereoPanner();
   osc.type='triangle';osc.frequency.value=440*2**((n.midi+[-12,0,0,12][part]-69)/12);pan.pan.value=[-.65,-.2,.2,.65][part];
   osc.connect(gain);gain.connect(pan);pan.connect(ctx.destination);
   const at=ctx.currentTime+Math.max(0,from-state.elapsed);
   gain.gain.setValueAtTime(0,at);gain.gain.linearRampToValueAtTime(.18,at+.02);gain.gain.linearRampToValueAtTime(0,at+duration);
   osc.start(at);osc.stop(at+duration);this.nodes.add(osc);osc.onended=()=>{this.nodes.delete(osc);osc.disconnect();gain.disconnect();pan.disconnect()};
  }
 }
}
