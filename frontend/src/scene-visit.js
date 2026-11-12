import {requestId} from './ids.js';

// Count a deliberate entry once; accrue only visible, ready, active experience.
// The caller owns network delivery. Captured payloads survive scene changes.
export function sceneVisit({send,eligible,now=()=>performance.now(),newId=requestId}){
 let current=null,last=now(),activeAt=now(),queue=Promise.resolve();
 function tick(){const t=now();if(current&&eligible()&&t-activeAt<60000)current.active_ms+=Math.max(0,Math.min(5000,t-last));last=t}
 function emit(operation){
  if(!current)return;tick();const payload={...current,operation,sequence:++current.sequence,active_ms:Math.floor(current.active_ms)};
  queue=queue.catch(()=>{}).then(()=>send(payload)).catch(()=>{});return queue;
 }
 return {
  enter(capability){emit('end');current={id:newId(),capability,sequence:0,active_ms:0};last=activeAt=now();return emit('start')},
  ensure(capability){if(current?.capability!==capability)return this.enter(capability)},
  interact(){activeAt=now()},
  pulse(){return emit('pulse')},
  end(){const result=emit('end');current=null;return result},
  tick,
 };
}
