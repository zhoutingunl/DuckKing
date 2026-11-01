import {test} from 'node:test';
import assert from 'node:assert/strict';
import {sceneStateFeed} from '../src/scene-state-feed.js';

const flush=async()=>{for(let i=0;i<12;i++)await Promise.resolve()};
const snapshot=(time=0,execution='paused')=>({backend:{scene:'balance',balance:{sim_time:time,comparison:{execution}}}});
function harness(reader=async()=>snapshot(),extra={}){
 let time=0,id=0,isHidden=false;
 const timers=new Map(),sockets=[],states=[],statuses=[],requests=[];
 const feed=sceneStateFeed({
  readState:signal=>{requests.push(signal);return reader(signal,requests.length)},
  onState:data=>states.push(data),onStatus:data=>statuses.push(data),
  socketFactory:()=>{const ws={readyState:1,sent:[],send(value){this.sent.push(value)},close(){this.readyState=3;this.onclose?.()},message(value){this.onmessage?.({data:JSON.stringify(value)})}};sockets.push(ws);return ws},
  hidden:()=>isHidden,now:()=>time,later:(fn,ms)=>{timers.set(++id,{fn,at:time+ms});return id},cancel:id=>timers.delete(id),...extra,
 });
 return {feed,timers,sockets,states,statuses,requests,hide:()=>{isHidden=true},
  async advance(ms){const end=time+ms;await flush();while(true){
   const next=[...timers].filter(([,v])=>v.at<=end).sort((a,b)=>a[1].at-b[1].at)[0];if(!next)break;
   time=next[1].at;timers.delete(next[0]);next[1].fn();await flush();
  }time=end;await flush()},
 };
}

test('rejected socket keeps real snapshots flowing, bounded retries, no command replay',async()=>{
 const h=harness(async(_,n)=>snapshot(n,'running'));await flush();h.sockets[0].close();await flush();
 assert.equal(h.statuses.at(-1).mode,'http');assert.equal(h.feed.fresh(),true);
 const before=h.requests.length;await h.advance(500);assert.equal(h.requests.length-before,5);
 await h.advance(1500);assert.equal(h.sockets.length,2);h.sockets[1].close();await flush();
 await h.advance(3999);assert.equal(h.sockets.length,2);await h.advance(1);assert.equal(h.sockets.length,3);
 assert.ok(h.states.at(-1).backend.balance.sim_time>5);
 assert.ok(h.sockets.every(ws=>ws.sent.length===0));h.feed.close();assert.equal(h.timers.size,0);
});

test('socket recovery cancels pending reads, rejects old snapshots and confirms identical state',async()=>{
 let resolve;const h=harness(()=>new Promise(r=>resolve=r));await flush();
 const ws=h.sockets[0];ws.message(snapshot(4,'running'));
 assert.equal(h.requests[0].aborted,true);assert.equal(h.statuses.at(-1).mode,'websocket');
 resolve(snapshot(0));await flush();assert.equal(h.states.length,1);
 await h.advance(1000);assert.deepEqual(ws.sent,['next']);assert.equal(h.requests.length,1);
 ws.close();await flush();resolve(snapshot(4));await flush();
 assert.equal(h.statuses.at(-1).mode,'http');await h.advance(2000);
 h.sockets.at(-1).message(snapshot(4));assert.equal(h.statuses.at(-1).mode,'websocket');
 assert.equal(h.states.at(-1).backend.balance.sim_time,4);h.feed.close();
});

test('silent open sockets expire and HTTP state resumes without waiting for a close event',async()=>{
 const h=harness(async()=>snapshot(2));await flush();
 h.sockets[0].message(snapshot(1));await h.advance(3000);
 assert.equal(h.sockets[0].readyState,3);assert.equal(h.statuses.at(-1).mode,'http');
 assert.equal(h.states.at(-1).backend.balance.sim_time,2);h.feed.close();
 const first=harness();await first.advance(3000);assert.equal(first.sockets[0].readyState,3);first.feed.close();
});

test('failed and malformed reads disable freshness; subsequent successful reads self-heal',async()=>{
 let result='failed';const h=harness(async()=>{
  if(result==='failed')throw Error('Service unavailable');return result==='invalid'?{}:snapshot(7);
 });await flush();assert.equal(h.feed.fresh(),false);assert.equal(h.statuses.at(-1).mode,'offline');
 result='invalid';await h.advance(1000);assert.equal(h.statuses.at(-1).reason,'物理状态响应无效');
 result='ok';await h.advance(1000);assert.equal(h.feed.fresh(),true);assert.equal(h.statuses.at(-1).mode,'http');h.feed.close();
});

test('state reads time out, settle and abort; a new command refresh supersedes an older request',async()=>{
 const replies=[];const h=harness(()=>new Promise(resolve=>replies.push(resolve)));await flush();
 const refresh=h.feed.refresh();await flush();assert.equal(h.requests[0].aborted,true);
 replies[0](snapshot(1));await flush();assert.equal(h.states.length,0);
 replies[1](snapshot(2));await refresh;assert.equal(h.states.at(-1).backend.balance.sim_time,2);
 const pending=h.feed.refresh();await h.advance(2500);await pending;
 assert.equal(h.requests[2].aborted,true);assert.equal(h.feed.fresh(),false);
 assert.equal(h.statuses.at(-1).reason,'实时状态读取超时');
 replies[2](snapshot(99));await flush();assert.equal(h.states.at(-1).backend.balance.sim_time,2);
 h.feed.close();assert.equal(h.timers.size,0);
});

test('leaving aborts reads and timers; late responses cannot render, poll or reopen sockets',async()=>{
 let resolve;const h=harness(()=>new Promise(r=>resolve=r));await flush();
 const message=h.sockets[0].onmessage;h.feed.close();h.feed.close();resolve(snapshot(5));
 message({data:JSON.stringify(snapshot(7))});await h.advance(60000);await h.feed.refresh();
 assert.equal(h.requests[0].aborted,true);assert.equal(h.requests.length,1);assert.equal(h.sockets.length,1);
 assert.equal(h.states.length,0);assert.equal(h.feed.fresh(),false);assert.equal(h.timers.size,0);
 const immediate=harness();immediate.feed.close();await flush();assert.equal(immediate.requests.length,0);
});

test('idle and hidden snapshots use slower polling; socket construction failure still permits HTTP',async()=>{
 const h=harness(undefined,{socketFactory:()=>{throw Error('blocked')}});await flush();await h.advance(1500);assert.equal(h.requests.length,3);
 h.hide();await h.advance(750);const n=h.requests.length;await h.advance(1999);assert.equal(h.requests.length,n);
 await h.advance(1);assert.equal(h.requests.length,n+1);h.feed.close();
 const rejected=harness(undefined,{socketFactory:()=>{throw Error('blocked')}});await flush();
 assert.equal(rejected.feed.fresh(),true);assert.equal(rejected.statuses.at(-1).mode,'http');rejected.feed.close();
});
