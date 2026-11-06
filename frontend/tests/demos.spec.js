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
  if(demo.id==='lonely'){
   const discoveries=JSON.parse(proof).results.filter(result=>result.name==='find_companion');
   expect(discoveries).toHaveLength(2);
   expect(discoveries[0]).toMatchObject({status:'failed',outcome:{verified:false,peers:[]}});
   expect(discoveries[1]).toMatchObject({status:'completed',outcome:{verified:true}});
   expect(discoveries[1].outcome.peers.length).toBeGreaterThan(0);
  }
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
for(const demo of ['identity','tabletop'])test(`real cloud ${demo} exposes connection failure and never silently runs local actions`,async({page})=>{
 test.setTimeout(100000);
 const previous=await page.request.get('/api/scenes/state?room=1');const before=previous.ok()?(await previous.json()).events.at(-1)?.id??0:0;
 await page.goto('/demos.html?room=1');await page.locator('#demo-mode').selectOption('live');
 await page.locator(`[data-demo="${demo}"]`).click();
 await expect(page.locator('#stage-placeholder')).toBeHidden({timeout:60000});
 await expect(page.locator('#show-status')).toHaveText('本幕未完成 · 点击节目重试',{timeout:45000});
 await expect(page.locator('#demo-notice')).toBeVisible();await expect(page.locator('#theatre-result')).toHaveCount(0);
 const s=await (await page.request.get('/api/scenes/state?room=1')).json();
 expect(s.events.filter(e=>e.id>before&&e.kind==='action'&&e.text.includes('nod'))).toHaveLength(0);
 if(demo==='tabletop'){
  expect(s.events.filter(e=>e.id>before&&e.kind==='action'&&e.text.includes('table_show'))).toHaveLength(0);
  expect(s.backend.tabletop.dropped_at).toBeNull();
  await expect(page.locator('#voice-source')).toContainText('灵矽开演');
 }
});
test('table live recovery cannot turn a failed round into a completed show',async({page})=>{
 test.setTimeout(90000);
 await page.route('**/demo-audio/*.wav*',route=>route.fulfill({contentType:'audio/wav',body:silentFixture()}));
 await page.routeWebSocket('**/scene-voice',socket=>socket.onMessage(message=>{
  if(typeof message!=='string')return;const type=JSON.parse(message).type;
  const send=data=>socket.send(JSON.stringify(data));
  if(type==='connect')send({type:'voice_status',state:'ready'});
  if(type==='listen_start')send({type:'voice_status',state:'listening'});
  if(type==='listen_stop'){
   send({type:'voice_status',state:'recovering',error:'协议测试：本轮超时'});
   send({type:'voice_status',state:'ready'});
   send({type:'audio',sample_rate:24000,pcm:Buffer.alloc(4800).toString('base64')});
   send({type:'playback_end',aborted:false});
  }
 }));
 await page.goto('/demos.html?room=1');await page.selectOption('#demo-mode','live');await page.locator('[data-table-song="tigers"]').click();
 await expect(page.locator('#show-status')).toHaveText('本幕未完成 · 点击节目重试',{timeout:75000});
 await expect(page.locator('#demo-notice')).toContainText('本轮超时');
 await expect(page.locator('#theatre-result')).toHaveCount(0);
});
test('table live protocol fixture starts real physics without a browser action fallback',async({page,request})=>{
 // Software rendering can delay protocol delivery and the closing line: the
 // CI trace reached that line at 81 s after both real physics and status query
 // completed, and a local replay passed at ~84 s. Budget the whole script;
 // production action/recovery deadlines and every outcome assertion stay intact.
 test.setTimeout(150000);let calls=0;const browserActions=[];
 page.on('request',r=>{if(r.method()==='POST'&&new URL(r.url()).pathname==='/api/scenes/actions')browserActions.push(r.postDataJSON().name)});
 await page.route('**/demo-audio/*.wav*',route=>route.fulfill({contentType:'audio/wav',body:silentFixture()}));
 // Only the cloud protocol is a fixture; the action and contacts use real MuJoCo.
 await page.routeWebSocket('**/scene-voice',socket=>{
  const send=data=>socket.send(JSON.stringify(data));
  socket.onMessage(async message=>{
   if(typeof message!=='string')return;const d=JSON.parse(message);
   if(d.type==='connect')send({type:'voice_status',state:'ready'});
   if(d.type==='listen_start')send({type:'voice_status',state:'listening'});
   if(d.type==='listen_stop'){
    calls++;send({type:'transcript',role:'user',text:'协议测试：开始桌上合唱'});
    send({type:'voice_status',state:'thinking'});
    if(calls===1){
     const rec=await(await request.post('/api/scenes/actions?room=1',{data:{name:'table_show',request_id:'table-cloud-fixture'}})).json();
     expect(rec.status).toBe('running');
    }else{
     const state=await(await request.get('/api/scenes/state?room=1')).json();
     expect(state.backend.tabletop.phase).toBe('completed');
    }
    send({type:'transcript',role:'assistant',text:'协议测试：'+(calls===1?'已受理':'已完成')});
    send({type:'audio',sample_rate:24000,pcm:Buffer.alloc(4800).toString('base64')});
    send({type:'playback_end',aborted:false});send({type:'voice_status',state:'ready'});
   }
  });
 });
 await page.goto('/demos.html?room=1');await page.selectOption('#demo-mode','live');
 await page.locator('[data-table-song="tigers"]').click();
 await expect(page.locator('#show-status')).toHaveText('本幕完成 · 可重演或进入下一幕',{timeout:120000});
 const proof=JSON.parse(await page.locator('#theatre-result').textContent());
 expect(proof.mode).toBe('live_linx');expect(proof.cloud_audio_frames).toBeGreaterThan(0);
 expect(calls).toBe(2);expect(browserActions).not.toContain('table_show');
 expect(proof.results.find(r=>r.name==='table_show').status).toBe('completed');
 await expect(page.locator('#table-song-title')).toContainText('两只老虎');
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
 await page.goto('/demos.html?room=1');
 // CI accepted table_show, but software rendering delayed the first music tick
 // beyond the former 5-second text assertion. Suspend in the browser on the
 // actual tick, not on panel visibility or a driver round trip. Keep all real
 // audio/physics and production watchdog deadlines unchanged.
 await page.evaluate(song=>{
   const counter=document.querySelector(song==='chorale'?'#chorale-beat':'#table-beat');
   const playing=song==='chorale'?/^第 \d+/:/\d+\s*\/\s*\d+\s*秒/;
   window.clockSuspension=null;
   const observer=new MutationObserver(()=>{
     if(!playing.test(counter.textContent))return;
     observer.disconnect();const cue=counter.textContent;
     Promise.all(window.demoContexts.map(ctx=>ctx.suspend())).then(()=>{
       window.clockSuspension={cue,states:window.demoContexts.map(ctx=>ctx.state)};
     }).catch(error=>{window.clockSuspension={cue,error:error.name}});
   });
   observer.observe(counter,{childList:true,characterData:true,subtree:true});
 },song);
 await page.locator(`[data-demo="${song}"]`).click();
 await expect(page.locator(song==='chorale'?'#chorale-panel':'#table-panel')).toBeVisible({timeout:30000});
 await expect.poll(()=>page.evaluate(()=>window.clockSuspension),{timeout:45000}).not.toBeNull();
 const suspended=await page.evaluate(()=>window.clockSuspension);
 expect(suspended.error).toBeUndefined();expect(suspended.states.length).toBeGreaterThan(0);
 expect(suspended.states.every(state=>state==='suspended')).toBe(true);
 await expect(page.locator('#show-status')).toHaveText('本幕未完成 · 点击节目重试',{timeout:10000});
 await expect(page.locator('#demo-notice')).toContainText('音频时钟');
 await expect(page.locator('#theatre-result')).toHaveCount(0);
 if(song==='tabletop')await expect.poll(async()=>{
   const state=await(await page.request.get('/api/scenes/state?room=1')).json();
   return state.backend.tabletop.running;
 }).toBe(false);
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

test('source link stays at the desktop edge and scrolls with mobile navigation',async({page})=>{
 for(const language of ['zh','en','fr'])for(const width of [1440,820,390]){
  await page.setViewportSize({width,height:900});await page.goto(`/?lang=${language}`);
  await expect(page.locator('html')).toHaveAttribute('lang',language==='zh'?'zh-CN':language);
  const source=await page.locator('.home-nav .repo-link').boundingBox();
  const lang=await page.locator('.lang-switch').boundingBox();
  const nav=await page.locator('.home-nav').boundingBox();
  if(width>1150){
   expect(source.x+source.width).toBeLessThanOrEqual(lang.x);
   expect(Math.abs(nav.x+nav.width-lang.x-lang.width)).toBeLessThan(2);
   await expect(page.locator('.home-nav .repo-link')).toBeInViewport({ratio:1});
  }else{
   const brand=await page.locator('.brand').boundingBox();
   expect(Math.abs(lang.y+lang.height/2-brand.y-brand.height/2)).toBeLessThan(5);
   expect(nav.y).toBeGreaterThanOrEqual(lang.y+lang.height);
   await expect(page.locator('.nav-destinations a').last()).toHaveClass('repo-link');
   const overflows=await page.locator('.nav-destinations').evaluate(el=>el.scrollWidth>el.clientWidth+1);
   await page.locator('.repo-link').scrollIntoViewIfNeeded();
   const scrolled=await page.locator('.repo-link').boundingBox();
   if(overflows)expect(scrolled.x).toBeLessThan(source.x-10);
  }
  await expect(page.locator('.home-nav .repo-link')).toBeInViewport({ratio:1});
  await page.locator('#lang-switch-button').click();
  await expect(page.getByRole('menuitem')).toHaveCount(3);
  for(const option of await page.getByRole('menuitem').all())await expect(option).toBeInViewport({ratio:1});
  // Source is reachable at the end of navigation; language never scrolls away.
  await page.locator('.nav-destinations a').last().scrollIntoViewIfNeeded();
  await expect(page.locator('.home-nav .repo-link')).toBeInViewport({ratio:1});
  await expect(page.locator('#lang-switch-button')).toBeInViewport({ratio:1});
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
 await expect(page.locator('#action-result')).toContainText('坐下 · 已完成');
 await page.locator('[data-sim-action="stand"]').click();
 await expect(page.locator('#action-result')).toContainText('站起来 · 已完成');
 await expect(page.locator('#posture-status')).toContainText('站立');
});
