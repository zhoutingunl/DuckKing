import {test,expect} from '@playwright/test';
import {DEMOS} from '../src/demo-catalog.js';

// Short, explicitly synthetic fixture speech keeps CI focused on real physics
// and orchestration. A separate manual/public acceptance uses the shipped audio.
function silentFixture(){
 const b=Buffer.alloc(44+3200);b.write('RIFF');b.writeUInt32LE(b.length-8,4);b.write('WAVE',8);b.write('fmt ',12);b.writeUInt32LE(16,16);b.writeUInt16LE(1,20);b.writeUInt16LE(1,22);b.writeUInt32LE(16000,24);b.writeUInt32LE(32000,28);b.writeUInt16LE(2,32);b.writeUInt16LE(16,34);b.write('data',36);b.writeUInt32LE(3200,40);return b;
}
for(const demo of DEMOS)test(`automated ${demo.id} validates actual MuJoCo outcomes`,{tag:'@journey'},async({page})=>{
 test.setTimeout(120000);
 await page.route('**/demo-audio/*.wav*',route=>route.fulfill({contentType:'audio/wav',body:silentFixture()}));
 const errors=[];page.on('pageerror',e=>errors.push(e.message));await page.goto('/demos.html?room=1');
 await expect(page.locator('.program-item')).toHaveCount(13);
  await page.locator(`[data-demo="${demo.id}"]`).click();
  await expect.poll(async()=>{const state=await page.locator('#show-status').textContent();if(state.includes('未完成'))throw Error(await page.locator('#demo-notice').textContent());return state},{timeout:90000}).toBe('本幕完成 · 可重演或进入下一幕');
  const proof=await page.locator('#theatre-result').textContent();expect(JSON.parse(proof).scene).toBe(demo.id);
  expect(JSON.parse(proof).mode).toBe('scripted_rehearsal');
  if(demo.id==='seated'){const result=JSON.parse(proof);expect(result.results.find(r=>r.name==='seated_show').outcome.completed_solos).toEqual(['a','b','c','d']);expect(result.results.find(r=>r.name==='seated_music').outcome.solos).toEqual(['a','b','c','d']);}
  if(demo.id==='tabletop')await expect(page.locator('#table-beat')).toHaveText('36 / 36 秒');await expect(page.locator('#demo-notice')).toBeHidden();
  await expect(page.locator('#demo-mode')).toBeEnabled({timeout:10000});
  if(demo.steps.some(step=>step.kind==='duel')){
   const rooms=await (await page.request.get('/api/rooms')).json();
   expect(rooms.rooms.filter(room=>room.physics).map(room=>room.id)).toEqual(['1']);
  }
 expect(errors).toEqual([]);
});
test('stop and rapid replacement cannot continue or report success for the old script',async({page})=>{
 test.setTimeout(60000);await page.goto('/demos.html?room=1');
 await page.locator('[data-demo="delivery"]').click();await page.locator('#stop-demo').click();
 await expect(page.locator('#show-status')).toHaveText('演示已停止');
 await page.locator('[data-demo="identity"]').click();await page.locator('[data-demo="football"]').click();
 await page.locator('#stop-demo').click();await expect(page.locator('#show-status')).toHaveText('演示已停止');
 await page.waitForTimeout(1500);await expect(page.locator('#theatre-result')).toHaveCount(0);
});
test('real cloud mode exposes connection failure and never silently runs local actions',async({page})=>{
 test.setTimeout(60000);
 const previous=await page.request.get('/api/scenes/state?room=1');const before=previous.ok()?(await previous.json()).events.at(-1)?.id??0:0;
 await page.goto('/demos.html?room=1');await page.locator('#demo-mode').selectOption('live');
 await page.locator('[data-demo="identity"]').click();
 await expect(page.locator('#show-status')).toHaveText('本幕未完成 · 点击节目重试',{timeout:45000});
 await expect(page.locator('#demo-notice')).toBeVisible();await expect(page.locator('#theatre-result')).toHaveCount(0);
 const s=await (await page.request.get('/api/scenes/state?room=1')).json();
 expect(s.events.filter(e=>e.id>before&&e.kind==='action'&&e.text.includes('nod'))).toHaveLength(0);
});
test('mobile program and stage stay inside the viewport',async({page})=>{
 await page.setViewportSize({width:390,height:844});await page.goto('/demos.html?room=1');
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
 await expect(page.locator('[data-demo="identity"]')).toBeVisible();
});

for(const song of ['chorale','tabletop'])test(`suspended audio clock stops ${song} instead of hanging the script`,async({page})=>{
 test.setTimeout(60000);
 await page.addInitScript(()=>{const Native=window.AudioContext;window.demoContexts=[];window.AudioContext=class extends Native{constructor(...args){super(...args);window.demoContexts.push(this)}}});
 await page.route('**/demo-audio/*.wav*',route=>route.fulfill({contentType:'audio/wav',body:silentFixture()}));
 await page.goto('/demos.html?room=1');await page.locator(`[data-demo="${song}"]`).click();
 await expect(page.locator(song==='chorale'?'#chorale-panel':'#table-panel')).toBeVisible({timeout:30000});
 await expect(page.locator(song==='chorale'?'#chorale-beat':'#table-beat')).toContainText(song==='chorale'?'第 ':'秒');
 await page.evaluate(()=>Promise.all(window.demoContexts.map(ctx=>ctx.suspend())));
 await expect(page.locator('#show-status')).toHaveText('本幕未完成 · 点击节目重试');
 await expect(page.locator('#demo-notice')).toContainText('音频时钟');
});

test('table music failure is explicit and never substitutes another song or starts the fall',async({page})=>{
 test.setTimeout(60000);
 await page.route('**/demo-audio/*.wav*',route=>route.fulfill({contentType:'audio/wav',body:silentFixture()}));
 await page.route('**/demo-music/*.mp3*',route=>route.fulfill({status:503,body:'unavailable'}));
 await page.goto('/demos.html?room=1');await page.locator('[data-demo="tabletop"]').click();
 await expect(page.locator('#show-status')).toHaveText('本幕未完成 · 点击节目重试',{timeout:45000});
 await expect(page.locator('#demo-notice')).toContainText('音源加载失败');
 const state=await (await page.request.get('/api/scenes/state?room=1')).json();
 expect(state.backend.tabletop.dropped_at).toBeNull();expect(state.backend.tabletop.elapsed).toBe(0);
 await expect(page.locator('#theatre-result')).toHaveCount(0);
});

test('stopping the table song silences every music node and cancels the real choreography',async({page})=>{
 test.setTimeout(90000);
 await page.addInitScript(()=>{
  const native=AudioBufferSourceNode.prototype.start,nativeStop=AudioBufferSourceNode.prototype.stop,stopped=new WeakSet();window.tableMusic={started:0,stopped:0,ended:0,selectorDisabled:false};
  AudioBufferSourceNode.prototype.stop=function(...args){if(this.buffer?.duration>=35&&!stopped.has(this)){stopped.add(this);window.tableMusic.stopped++}return nativeStop.apply(this,args)};
  AudioBufferSourceNode.prototype.start=function(...args){
   const music=this.buffer?.duration>=35;
   if(music){window.tableMusic.started++;this.addEventListener('ended',()=>window.tableMusic.ended++,{once:true})}
   const result=native.apply(this,args);
   // Press the actual stop button as soon as all four real music sources
   // start. This avoids a driver round-trip racing a busy software renderer.
   if(music&&window.tableMusic.started===4)queueMicrotask(()=>{window.tableMusic.selectorDisabled=document.querySelector('#table-song').disabled;document.querySelector('#stop-demo').click()});
   return result;
  };
 });
 await page.route('**/demo-audio/*.wav*',route=>route.fulfill({contentType:'audio/wav',body:silentFixture()}));
 await page.goto('/demos.html?room=1');await page.locator('[data-demo="tabletop"]').click();
 await expect(page.locator('#table-panel')).toBeVisible({timeout:45000});
 await expect(page.locator('#show-status')).toHaveText('演示已停止',{timeout:15000});
 // Audio-thread ended callbacks and driver evaluation can be delayed by the
 // software renderer. Every source must still receive stop and actually end.
 await expect.poll(()=>page.evaluate(()=>window.tableMusic),{timeout:15000}).toEqual({started:4,stopped:4,ended:4,selectorDisabled:true});
 await expect(page.locator('#table-song')).toBeEnabled();
 const state=await (await page.request.get('/api/scenes/state?room=1')).json();
 expect(state.backend.tabletop.running).toBe(false);expect(state.backend.tabletop.dropped_at).toBeNull();
 await expect(page.locator('#theatre-result')).toHaveCount(0);
});

test('source link stays at the right edge with no navigation or viewport overlap',async({page})=>{
 for(const width of [1440,820,390]){
  await page.setViewportSize({width,height:900});await page.goto('/');
  const source=await page.locator('.home-topbar > .repo-link').boundingBox(),header=await page.locator('.home-topbar').boundingBox();
  expect(header.x+header.width-source.x-source.width).toBeLessThan(width*.05+1);
  const nav=await page.locator('.home-nav').boundingBox();
  expect(nav.y>=source.y+source.height||nav.x+nav.width<=source.x).toBe(true);
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
 }
});

for(const song of ['ode','tigers'])test(`stopping synthesized ${song} stops all oscillators and actual stepping`,async({page})=>{
 test.setTimeout(90000);
 await page.addInitScript(()=>{const native=OscillatorNode.prototype.start;window.scorePlaying=0;OscillatorNode.prototype.start=function(...args){window.scorePlaying++;this.addEventListener('ended',()=>window.scorePlaying--,{once:true});return native.apply(this,args)}});
 await page.route('**/demo-audio/*.wav*',route=>route.fulfill({contentType:'audio/wav',body:silentFixture()}));
 await page.goto('/demos.html?room=1');await page.locator(`[data-table-song="${song}"]`).click();
 await expect(page.locator('#table-panel')).toBeVisible({timeout:45000});
 await expect.poll(()=>page.evaluate(()=>window.scorePlaying),{timeout:15000}).toBeGreaterThan(0);
 await expect(page.locator('#caption-role')).toContainText('本地合成');
 if(song==='tigers')await expect(page.locator('.table-seat[data-duck=d]')).toContainText('等待入唱');
 await page.locator('#stop-demo').click();await expect.poll(()=>page.evaluate(()=>window.scorePlaying)).toBe(0);
 await expect(page.locator('#table-song')).toBeEnabled(); // Network stop finishes after local audio stops.
 const state=await (await page.request.get('/api/scenes/state?room=1')).json();expect(state.backend.tabletop.running).toBe(false);
 await expect(page.locator('#theatre-result')).toHaveCount(0);
});


test('seated solos stop sounding and return to seated rest when cancelled',async({page})=>{
 test.setTimeout(75000);
 await page.addInitScript(()=>{
  const start=OscillatorNode.prototype.start;window.seatedSounding=0;
  OscillatorNode.prototype.start=function(...args){window.seatedSounding++;this.addEventListener('ended',()=>window.seatedSounding--,{once:true});return start.apply(this,args)};
 });
 await page.goto('/demos.html?room=1');await page.locator('#demo-mode').selectOption('live');
 // Software GPU tracing can spend several seconds waiting for click stability.
 // Arm the real stop button handler in-page so cancellation occurs during A's
 // four-second solo. Physics, transport and audio still run without interception.
 await page.evaluate(()=>{
  const cue=document.getElementById('table-cue');window.cancelledSolo=null;
  const observer=new MutationObserver(()=>{
   if(cue.textContent==='鸭 A 已站稳，轮到它独唱。'){
    window.cancelledSolo=cue.textContent;observer.disconnect();document.getElementById('stop-demo').click();
   }
  });observer.observe(cue,{childList:true,characterData:true,subtree:true});
 });
 await page.locator('[data-demo="seated"]').click();
 await page.waitForFunction(()=>window.cancelledSolo,null,{timeout:45000});
 expect(await page.evaluate(()=>window.cancelledSolo)).toBe('鸭 A 已站稳，轮到它独唱。');
 await expect(page.locator('#voice-source')).toContainText('本地音乐');
 await expect(page.locator('#show-status')).toHaveText('演示已停止');
 await expect.poll(()=>page.evaluate(()=>window.seatedSounding)).toBe(0);
 await expect(page.locator('#demo-mode')).toBeEnabled();
 await expect.poll(async()=>{const s=await (await page.request.get('/api/scenes/state?room=1')).json();return s.backend.ducks.every(d=>d.posture.observed==='sit')}).toBe(true);
 const state=await (await page.request.get('/api/scenes/state?room=1')).json();
 expect(state.backend.seated_choir.running).toBe(false);
 // A delayed rendered cue can arrive after A's solo has finished. Cancellation
 // must preserve that truthful history, cancel the action, and never add solos.
 const started=state.events.findLast(e=>e.kind==='action'&&e.text==='开始动作 · seated_show');
 expect(started).toBeTruthy();
 const record=await(await page.request.get(`/api/scenes/actions/${started.action_id}?room=1`)).json();
 expect(record.status).toBe('cancelled');
 expect(state.backend.seated_choir.completed_solos.length).toBeLessThan(4);
 await page.waitForTimeout(1500);
 const later=await(await page.request.get('/api/scenes/state?room=1')).json();
 expect(later.backend.seated_choir.completed_solos).toEqual(state.backend.seated_choir.completed_solos);
 expect(later.backend.ducks.every(d=>d.posture.observed==='sit')).toBe(true);
 await expect(page.locator('#theatre-result')).toHaveCount(0);
});

test('physics page can sit, keep the pose and stand again',async({page})=>{
 test.setTimeout(60000);await page.goto('/scenarios.html?room=1');
 await page.locator('[data-scene="ball"]').click();
 await expect(page.locator('#posture-controls')).toBeVisible({timeout:30000});
 await page.locator('[data-sim-action="sit"]').click();
 await expect(page.locator('#posture-status')).toContainText('已坐稳',{timeout:10000});
 await expect(page.locator('#action-result')).toContainText('坐下 · 完成');
 await page.locator('[data-sim-action="stand"]').click();
 await expect(page.locator('#action-result')).toContainText('站起来 · 完成');
 await expect(page.locator('#posture-status')).toContainText('站立');
});
