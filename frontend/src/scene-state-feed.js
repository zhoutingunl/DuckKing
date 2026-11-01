import {createSocket} from './transport.js';

// Both channels read the SAME real room state. Only GET snapshots are retried;
// this feed never submits, retries or replays a motion/voice command.
export function sceneStateFeed({readState,onState,onStatus,
 socketFactory=()=>createSocket('scene-ws'),hidden=()=>document.hidden,
 now=()=>performance.now(),later=(fn,ms)=>setTimeout(fn,ms),cancel=id=>clearTimeout(id),
 staleMs=3000,requestMs=2500,watchMs=500,pollMs=100,idleMs=750,retryMs=2000,maxRetryMs=30000,
}){
 let closed=false,socket=null,read=null,pollTimer,ackTimer,retryTimer,watchTimer;
 let lastState=-Infinity,lastSocket=-Infinity,socketStarted=0,version=0,active=false,mode='connecting',reason='',retry=retryMs;
 const clear=key=>{if(key!==undefined)cancel(key)};
 const socketFresh=()=>socket&&now()-lastSocket<staleMs;
 function status(next,why=''){
  if(closed||next===mode&&why===reason)return;
  mode=next;reason=why;onStatus?.({mode,reason});
 }
 function packet(value){
  if(value?.type==='not_started')return value;
  if(value?.backend&&typeof value.backend.scene==='string')return {...value,type:'state'};
  throw Error('物理状态响应无效');
 }
 function accept(value,channel){
  const data=packet(value);
  lastState=now();
  active=(data.backend?.balance?.comparison?.execution??data.backend?.balance?.execution)==='running'
    ||data.backend?.seesaw?.execution==='running'||data.backend?.seesaw?.comparison?.execution==='running';
  status(channel);onState(data);
 }
 function cancelRead(){
  if(!read)return;
  const old=read;read=null;clear(old.timer);old.controller.abort();
 }
 function schedulePoll(delay){
  clear(pollTimer);pollTimer=undefined;
  if(!closed&&!socketFresh())pollTimer=later(()=>{pollTimer=undefined;void refresh()},delay);
 }
 function refresh(){
  if(closed)return Promise.resolve();
  clear(pollTimer);pollTimer=undefined;
  // A command's confirmation must not use a pre-command in-flight snapshot.
  cancelRead();const current={controller:new AbortController(),version};read=current;
  current.timer=later(()=>{
   if(read!==current||closed)return;
   cancelRead();status('offline','实时状态读取超时');schedulePoll(1000);
  },requestMs);
  const aborted=new Promise((_,reject)=>current.controller.signal.addEventListener('abort',()=>reject(new DOMException('Aborted','AbortError')),{once:true}));
  const response=Promise.resolve().then(()=>{
   current.controller.signal.throwIfAborted();return readState(current.controller.signal);
  });
  return Promise.race([response,aborted]).then(value=>{
   if(closed||read!==current||version!==current.version)return;
   accept(value,socketFresh()?'websocket':'http');
  }).catch(error=>{
   if(!closed&&read===current&&!current.controller.signal.aborted)status('offline',error.message||'无法读取物理状态');
  }).finally(()=>{
   clear(current.timer);
   if(read===current){read=null;schedulePoll(mode==='offline'?1000:hidden()?2000:active?pollMs:idleMs)}
  });
 }
 function closeSocket(){
  if(!socket)return;
  const old=socket;socket=null;lastSocket=-Infinity;clear(ackTimer);ackTimer=undefined;
  old.onmessage=old.onclose=null;old.close();
 }
 function reconnect(){
  if(closed||retryTimer!==undefined)return;
  retryTimer=later(()=>{retryTimer=undefined;connect()},retry);retry=Math.min(maxRetryMs,retry*2);
 }
 function disconnected(){
  closeSocket();reconnect();
  if(mode==='websocket')status('connecting','实时连接中断，正在读取物理状态');
  if(!read)void refresh();
 }
 function connect(){
  if(closed||socket)return;
  let ws;try{ws=socket=socketFactory();socketStarted=now()}catch{reconnect();return}
  ws.onmessage=event=>{
   if(closed||socket!==ws)return;
   try{
    const data=packet(JSON.parse(event.data));
    version++;lastSocket=now();retry=retryMs;
    cancelRead();clear(pollTimer);pollTimer=undefined;
    accept(data,'websocket');
    clear(ackTimer);ackTimer=later(()=>{
     ackTimer=undefined;
     if(closed||ws!==socket||ws.readyState!==1)return;
     try{ws.send('next')}catch{disconnected()}
    },hidden()?1000:active?0:250);
   }catch{disconnected()}
  };
  ws.onclose=()=>{if(!closed&&ws===socket)disconnected()};
 }
 function watch(){
  if(closed)return;
  if(now()-lastState>=staleMs&&mode!=='offline')status('offline','尚未取得最新物理状态');
  // A socket can stay OPEN without delivering data. HTTP takes over as soon
  // as its last snapshot expires; a reconnect may then replace that stalled socket.
  if(socket&&now()-(lastSocket===-Infinity?socketStarted:lastSocket)>=staleMs)disconnected();
  if(!socketFresh()&&!read&&pollTimer===undefined)void refresh();
  watchTimer=later(watch,watchMs);
 }
 onStatus?.({mode:'connecting',reason:''});
 connect();void refresh();watchTimer=later(watch,watchMs);
 return {
  refresh,
  fresh:()=>!closed&&['websocket','http'].includes(mode)&&now()-lastState<staleMs,
  close(){
   if(closed)return;closed=true;
   for(const timer of [pollTimer,ackTimer,retryTimer,watchTimer])clear(timer);
   closeSocket();cancelRead();
  },
 };
}
