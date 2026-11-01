import {test} from 'node:test';
import assert from 'node:assert/strict';
import {renderScheduler} from '../src/render-scheduler.js';

function harness(draw){
 let time=0,id=0;const frames=new Map(),timers=new Map();
 const scheduler=renderScheduler(draw,{
  now:()=>time,interval:()=>50,
  requestFrame:fn=>{frames.set(++id,fn);return id},cancelFrame:id=>frames.delete(id),
  later:(fn,ms)=>{timers.set(++id,{fn,at:time+ms});return id},cancelLater:id=>timers.delete(id),
 });
 return {scheduler,frames,timers,frame(){const callbacks=[...frames.values()];frames.clear();callbacks.forEach(fn=>fn())},
  advance(ms){time+=ms;for(const [id,{fn,at}] of [...timers])if(at<=time){timers.delete(id);fn()}}};
}

test('a static view sleeps; duplicate state invalidations coalesce',()=>{
 let draws=0;const h=harness(()=>{draws++;return false});
 assert.equal(h.frames.size,0);
 for(let i=0;i<100;i++)h.scheduler.invalidate();
 assert.equal(h.frames.size,1);h.frame();assert.equal(draws,1);
 h.advance(10000);assert.equal(h.frames.size+h.timers.size,0);
});
test('continuous updates are bounded; the latest dirty state is not lost',()=>{
 let draws=0;const h=harness(()=>{draws++;return false});
 h.scheduler.invalidate();h.frame();
 for(let i=0;i<100;i++)h.scheduler.invalidate();
 assert.equal(h.frames.size,0);assert.equal(h.timers.size,1);
 h.advance(49);assert.equal(draws,1);h.advance(1);h.frame();assert.equal(draws,2);
 assert.equal(h.frames.size+h.timers.size,0);
});
test('orbit damping renders until settled without leaving an idle loop',()=>{
 let draws=0;const h=harness(()=>++draws<3);
 h.scheduler.invalidate();h.frame();h.advance(50);h.frame();h.advance(50);h.frame();
 assert.equal(draws,3);assert.equal(h.frames.size+h.timers.size,0);
});
test('hidden views cancel queued work, retain the latest update and resume once',()=>{
 let draws=0;const h=harness(()=>{draws++;return false});
 h.scheduler.invalidate();h.scheduler.visible(false);assert.equal(h.frames.size,0);
 h.scheduler.invalidate();h.advance(10000);assert.equal(draws,0);
 h.scheduler.visible(true);h.frame();assert.equal(draws,1);
 h.scheduler.invalidate();assert.equal(h.timers.size,1);
 h.scheduler.visible(false);assert.equal(h.timers.size,0);
});
test('flush cannot create a second loop and disposal rejects late callbacks',()=>{
 let draws=0;const h=harness(()=>{draws++;return false});
 h.scheduler.invalidate();const late=[...h.frames.values()][0];h.scheduler.flush();
 assert.equal(draws,1);assert.equal(h.frames.size,0);
 h.scheduler.invalidate();h.scheduler.dispose();h.scheduler.dispose();
 h.advance(1000);late();h.scheduler.flush();h.scheduler.invalidate();h.scheduler.visible(true);
 assert.equal(draws,1);assert.equal(h.frames.size+h.timers.size,0);
});
test('changes raised inside a draw are scheduled once without re-entrance',()=>{
 let draws=0;const h=harness(()=>{if(++draws===1)h.scheduler.invalidate();return false});
 h.scheduler.invalidate();h.frame();assert.equal(h.timers.size,1);
 h.advance(50);h.frame();assert.equal(draws,2);assert.equal(h.frames.size+h.timers.size,0);
});
