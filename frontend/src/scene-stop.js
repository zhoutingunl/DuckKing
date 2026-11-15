// Stop is confirmed only by a terminal backend result. Never prepare a world
// or replay a POST while polling; a revision guard protects a changed room.
export async function stopRoomScene(api,{revision,id,signal,pause=()=>new Promise(resolve=>setTimeout(resolve,100))}){
 let record=await api(`api/scenes/actions?expected_revision=${encodeURIComponent(revision)}`,{name:'stop',request_id:id},signal);
 while(record.status==='running'){
  signal.throwIfAborted();await pause();signal.throwIfAborted();
  record=await api(`api/scenes/actions/${encodeURIComponent(record.id)}`,null,signal);
 }
 if(record.status!=='completed')throw Error(record.error||'停止尚未确认，请重试或释放场景。');
 return record;
}

// Ignore a delayed pre-stop packet, but clear the confirmation when another
// page starts a newer task. All timestamps here originate on the same server.
export function newerSceneActivity(packet,ack){
 const b=packet.backend;
 if(!ack||b?.revision!==ack.revision)return true;
 return (packet.action?.started_at??0)>ack.finished_at
  ||(b.feature?.started_at??0)>ack.finished_at
  ||(packet.studio?.task?.started_at??0)>ack.finished_at
  ||(packet.events??[]).some(e=>e.kind==='action'&&e.time>ack.finished_at&&e.action_id!==ack.id)
  ||(b.balance?.command_revision??b.seesaw?.command_revision??0)>(ack.commandRevision??Infinity);
}
