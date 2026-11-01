import {test,expect} from '@playwright/test';

test('duration and seed settings have stacked labels, bound the real run and follow server voice settings',async({page,request})=>{
 test.setTimeout(90000);
 const created=await request.post('/api/rooms');expect(created.ok()).toBe(true);
 const {room}=await created.json(),commands=[],errors=[];
 page.on('pageerror',error=>errors.push(error.message));
 page.on('request',req=>{if(req.method()==='POST'&&new URL(req.url()).pathname==='/api/balance/command')commands.push(req.postDataJSON())});
 await page.goto(`/balance.html?room=${room}`);
 const seed=page.getByLabel('对照种子',{exact:true}),duration=page.getByLabel('运行时长（秒）',{exact:true});
 await seed.fill('1');await duration.fill('6');
 await expect(page.locator('#duration-note')).toContainText('3 秒扰动＋3 秒减速');
 await expect(page.locator('#duration-note')).toContainText('训练成功率仍仅对应 13 秒');
 await page.locator('#prepare-balance').click();
 await expect(page.locator('#start-challenge')).toBeEnabled({timeout:45000});
 await expect(seed).toHaveValue('1');await expect(duration).toHaveValue('6');
 await expect(page.locator('#seed-summary')).toContainText('逆时针');
 await page.selectOption('#controller','baseline');await page.locator('#start-challenge').click();
 await expect(page.locator('#comparison-status')).toContainText('/ 6 s');
 await expect(page.locator('#comparison-status')).toContainText('对照结束',{timeout:15000});
 const finished=(await(await request.get(`/api/scenes/state?room=${room}`)).json()).backend;
 expect(finished.sim_time).toBeCloseTo(6);expect(finished.comparison.baseline.sim_time).toBeCloseTo(6);
 expect(commands.filter(c=>c.operation==='start')).toEqual([expect.objectContaining({duration_seconds:6,seed:1})]);
 const before=commands.length;
 for(const value of ['100','5','6.5','']){
  await duration.fill(value);await page.locator('#start-challenge').click();
  expect(await duration.evaluate(input=>input.validity.valid)).toBe(false);
 }
 expect(commands.length).toBe(before);
 await duration.fill('20');await page.waitForTimeout(800);await expect(duration).toHaveValue('20');
 await page.locator('[data-level="2"]').click();
 await expect(page.locator('#scene-title')).toContainText('第 2 关');await expect(duration).toHaveValue('20');
 // The voice tool reaches this same backend operation; no cloud ASR is mocked as real.
 const selected=await request.post(`/api/balance/command?room=${room}`,{data:{operation:'select',duration_seconds:8,seed:0}});
 expect(selected.ok()).toBe(true);expect((await selected.json()).phase).toBe('idle');
 await expect(duration).toHaveValue('8');await expect(seed).toHaveValue('0');
 await expect(page.locator('#seed-summary')).toContainText('顺时针');
 await expect(page.locator('#disc-time')).toHaveText('0.0 s');
 // Desktop and phone retain labels above the fields, duration to seed's right.
 for(const width of [1440,390]){
  await page.setViewportSize({width,height:1050});
  const s=await seed.boundingBox(),d=await duration.boundingBox();
  const label=await page.locator('label[for="challenge-seed"]').boundingBox();
  expect(s.y).toBeGreaterThan(label.y+10);expect(d.y).toBeCloseTo(s.y);expect(d.x).toBeGreaterThan(s.x+s.width);
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
 }
 expect(errors).toEqual([]);
});

test('rejected scene socket falls back to real HTTP physics; start, offline stop and reconnection recover',async({page,request})=>{
 test.setTimeout(120000);
 const errors=[],commands=[];page.on('pageerror',e=>errors.push(e.message));
 page.on('request',req=>{if(req.method()==='POST'&&new URL(req.url()).pathname==='/api/balance/command')commands.push(req.postDataJSON())});
 // Exercise the server's actual Origin rejection, without changing its policy.
 await page.addInitScript(()=>{
  window.sceneNativeWebSocket=window.WebSocket;
  window.WebSocket=new Proxy(window.WebSocket,{construct(Target,args){
   const url=new URL(args[0]);if(url.pathname==='/scene-ws'){url.hostname='localhost';args[0]=url.href}
   return new Target(...args);
  }});
 });
 const created=await request.post('/api/rooms');expect(created.ok()).toBe(true);
 const {room}=await created.json();
 await page.goto(`/balance.html?room=${room}`);
 await page.locator('#prepare-balance').click();
 const connection=page.locator('#scene-connection'),start=page.locator('#start-challenge');
 await expect(start).toBeEnabled({timeout:45000});
 await expect(connection).toHaveAttribute('data-transport','http');
 await page.selectOption('#controller','baseline');await start.click();
 await expect(page.locator('#command-feedback')).toContainText('挑战请求已受理');
 await expect(page.locator('#comparison-status')).toContainText('同步挑战中');
 await expect(page.locator('#disc-time')).not.toHaveText('0.0 s');
 await expect(page.locator('#baseline-time')).not.toHaveText('0.0 s');
 const state=(await(await request.get(`/api/scenes/state?room=${room}`)).json()).backend;
 expect(state.balance.comparison.sim_time).toBeGreaterThan(0);
 expect(state.comparison.baseline.sim_time).toBe(state.sim_time);
 expect(state.comparison.baseline.disc_target).toEqual(state.disc_target);
 // A total read outage must never leave a stale scene looking ready to start.
 await page.route('**/api/scenes/state?*',route=>route.fulfill({status:503,json:{detail:'test state outage'}}));
 await expect(connection).toHaveAttribute('data-transport','offline');
 await expect(start).toBeDisabled();await expect(page.locator('#stop-balance')).toBeEnabled();
 await page.locator('#stop-balance').click();
 await expect(page.locator('#command-feedback')).toContainText('停盘请求已受理');
 await expect.poll(async()=>((await(await request.get(`/api/scenes/state?room=${room}`)).json()).backend.balance.comparison.phase),{timeout:10000}).toBe('cancelled');
 await page.unroute('**/api/scenes/state?*');
 await expect(connection).toHaveAttribute('data-transport','http');await expect(start).toBeEnabled();
 await expect(page.locator('#comparison-status')).toContainText('对照已停止');
 await expect(page.locator('#baseline-status')).toContainText('人为干预不计成功');
 const outcome=await page.locator('#challenge-status').textContent();
 await page.evaluate(()=>{window.WebSocket=window.sceneNativeWebSocket});
 await expect(connection).toHaveAttribute('data-transport','websocket',{timeout:40000});
 await expect(page.locator('#challenge-status')).toHaveText(outcome);
 expect(commands.filter(c=>c.operation==='start')).toHaveLength(1);
 expect(commands.filter(c=>c.operation==='stop')).toHaveLength(1);
 expect(errors).toEqual([]);
});

test('balance classroom explains signs, displays real record boundaries and fits a phone',async({page})=>{
 const errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto('/balance.html?room=1');
 await expect(page.locator('#training-phase')).toHaveText('本关尚无训练记录',{timeout:15000});
 await page.locator('[data-term=slip]').click();
 await expect(page.locator('#term-description')).toContainText('脚的速度减去盘面的速度');
 await page.locator('#example-advantage').fill('-1');
 await expect(page.locator('#example-result')).toContainText('对坏动作');
 await page.locator('[data-level="3"]').click();
 await expect(page.locator('[data-level="3"]')).toHaveAttribute('aria-pressed','true');
 await expect(page.locator('#start-training')).toBeDisabled();
 await page.setViewportSize({width:390,height:844});
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
 expect(errors).toEqual([]);
});

test('real disk renders, a missing policy stays explicit, stop and scene switching recover',async({page,request})=>{
 test.setTimeout(120000);
 const errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto('/balance.html?room=2');
 await page.locator('#prepare-balance').click();
 await expect(page.locator('#start-challenge')).toBeEnabled({timeout:45000});
 await expect(page.locator('#physics-viewport')).toHaveAttribute('data-rendered-scene','balance',{timeout:20000});
 await expect(page.locator('#baseline-viewport')).toHaveAttribute('data-rendered-scene','balance',{timeout:20000});
 await expect(page.locator('#baseline-viewport')).toHaveAttribute('data-duck-label','未训练');
 await expect(page.locator('#physics-viewport')).toHaveAttribute('data-duck-label','训练后');
 await page.locator('#start-challenge').click();
 await expect(page.locator('#notice')).toContainText('尚无');
 await page.selectOption('#controller','baseline');
 await page.locator('#start-challenge').click();
 await expect(page.locator('#challenge-status')).toContainText('挑战中');
 await expect(page.locator('#disc-time')).not.toHaveText('0.0 s');
 await expect(page.locator('#baseline-status')).toContainText('挑战中');
 const running=(await(await request.get('/api/scenes/state?room=2')).json()).backend;
 expect(running.balance.comparison.clock).toBe('shared_task_ticks');
 expect(running.comparison.baseline.sim_time).toBe(running.sim_time);
 expect(running.comparison.baseline.disc_target).toEqual(running.disc_target);
 await page.locator('#stop-balance').click();
 await expect(page.locator('#challenge-status')).toContainText('人为干预不计成功',{timeout:10000});
 await expect(page.locator('#baseline-status')).toContainText('人为干预不计成功');
 await expect(page.locator('#comparison-status')).toContainText('对照已停止');
 const response=await request.post('/api/scenes/start?room=2',{data:{name:'scene_ball',request_id:crypto.randomUUID()}});
 expect(response.ok()).toBe(true);
 await page.locator('#prepare-balance').click();
 await expect(page.locator('#start-challenge')).toBeEnabled({timeout:45000});
 await expect(page.locator('#challenge-status')).toContainText('等待指令');
 expect(errors).toEqual([]);
});

test('balance stays sharp and sleeps when static; orbit, colour and repeated scene replacement release GPU buffers',async({page,request})=>{
 test.setTimeout(180000);
 const errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.addInitScript(()=>{
  window.renderProbe={draws:0,buffers:0,textures:0,observations:0};
  for(const Type of [WebGLRenderingContext,WebGL2RenderingContext]){
   for(const method of ['drawElements','drawArrays','drawElementsInstanced','drawArraysInstanced']){
    const fn=Type.prototype[method];if(fn)Type.prototype[method]=function(...args){window.renderProbe.draws++;return fn.apply(this,args)};
   }
   for(const [kind,key] of [['Buffer','buffers'],['Texture','textures']]){
    const created=Type.prototype['create'+kind],deleted=Type.prototype['delete'+kind];
    Type.prototype['create'+kind]=function(...args){const resource=created.apply(this,args);if(resource)window.renderProbe[key]++;return resource};
    Type.prototype['delete'+kind]=function(resource){if(resource)window.renderProbe[key]--;return deleted.call(this,resource)};
   }
  }
 });
 await page.goto('/balance.html?room=2');
 const view=page.locator('#physics-viewport'),canvas=view.locator('canvas'),left=page.locator('#baseline-viewport canvas');
 await page.locator('[data-level="3"]').click();
 await page.locator('#prepare-balance').click();
 await expect(view).toHaveAttribute('data-rendered-scene','balance',{timeout:45000});
 await expect(page.locator('#start-challenge')).toBeEnabled();
 await expect(page.locator('#scene-title')).toContainText('第 3 关');
 const prepared=(await(await request.get('/api/scenes/state?room=2')).json()).backend;
 expect(prepared.balance.level).toBe(3);expect(prepared.comparison.baseline.balance.level).toBe(3);
 expect(prepared.ducks).toEqual(prepared.comparison.baseline.ducks);
 expect(Math.hypot(...prepared.ducks[0].position.slice(0,2))).toBeGreaterThan(.1);
 await page.evaluate(()=>new MutationObserver(m=>window.renderProbe.observations+=m.length).observe(document.querySelector('#observation-table'),{childList:true,subtree:true}));
 // Wait for the initial OrbitControls damping to settle, then observe a quiet window.
 await page.waitForTimeout(1500);
 const first=await page.evaluate(()=>({...window.renderProbe}));
 await page.waitForTimeout(1500);
 expect(await page.evaluate(()=>({...window.renderProbe}))).toEqual(first);
 expect(await canvas.evaluate(c=>c.width>=Math.floor(c.clientWidth)&&c.height>=Math.floor(c.clientHeight))).toBe(true);
 const before=await canvas.screenshot(),leftBefore=await left.screenshot(),rect=await canvas.boundingBox(),leftRect=await left.boundingBox();
 expect(leftRect.x+leftRect.width).toBeLessThan(rect.x);
 expect(Math.abs(leftRect.width-rect.width)).toBeLessThan(1);
 await page.mouse.move(rect.x+rect.width*.5,rect.y+rect.height*.4);await page.mouse.down();
 await page.mouse.move(rect.x+rect.width*.7,rect.y+rect.height*.55,{steps:6});await page.mouse.up();
 await expect.poll(async()=>!before.equals(await canvas.screenshot())).toBe(true);
 await expect.poll(async()=>!leftBefore.equals(await left.screenshot())).toBe(true);
 await page.waitForTimeout(1500);
 await page.locator('#reset-camera').click();
 await expect.poll(async()=>before.equals(await canvas.screenshot()),{timeout:10000}).toBe(true);
 await expect.poll(async()=>leftBefore.equals(await left.screenshot()),{timeout:10000}).toBe(true);
 await view.getByRole('button',{name:'天空蓝 · Sky',exact:true}).click();
 await expect.poll(async()=>!before.equals(await canvas.screenshot())).toBe(true);
 await page.mouse.move(rect.x+rect.width*.5,rect.y+rect.height*.4);const coloured=await canvas.screenshot();
 await page.mouse.wheel(0,-180);await expect.poll(async()=>!coloured.equals(await canvas.screenshot())).toBe(true);
 for(let i=0;i<3;i++){
  expect((await request.post('/api/scenes/start?room=2',{data:{name:'scene_ball',request_id:crypto.randomUUID()}})).ok()).toBe(true);
  await expect(page.locator('#notice')).toContainText('本房间已切到其他场景');
  await page.locator('#prepare-balance').click();
  await expect(view).toHaveAttribute('data-rendered-scene','balance',{timeout:45000});
  await expect(page.locator('#start-challenge')).toBeEnabled({timeout:45000});
  await expect(page.locator('#scene-title')).toContainText('第 3 关');
  const resources=await page.evaluate(()=>({buffers:window.renderProbe.buffers,textures:window.renderProbe.textures}));
  expect(resources).toEqual({buffers:first.buffers,textures:first.textures});
 }
 await page.evaluate(()=>dispatchEvent(new PageTransitionEvent('pagehide')));
 await expect(canvas).toHaveCount(0);await expect(view.locator('.duck-appearance')).toHaveCount(0);
 await expect(left).toHaveCount(0);await expect(page.locator('#baseline-viewport .duck-appearance')).toHaveCount(0);
 const disposed=await page.evaluate(()=>({...window.renderProbe}));await page.waitForTimeout(1000);
 expect(await page.evaluate(()=>({...window.renderProbe}))).toEqual(disposed);
 expect(errors).toEqual([]);
});

test('unchanged training records keep charts and focused samples instead of refetching and rebuilding',async({page})=>{
 let detailRequests=0,steps=512;
 const status=()=>({phase:'training',steps,budget_steps:1024,elapsed_s:steps/10,level:1});
 await page.route('**/api/balance/runs?*',route=>route.fulfill({json:{training_enabled:false,active_run:null,runs:[{id:'cache-test',contract:'balance-v4-gain-bodyframe',...status()}]}}));
 await page.route('**/api/balance/runs/cache-test?*',route=>{detailRequests++;return route.fulfill({json:{id:'cache-test',status:status(),manifest:{hyperparameters:{}},metrics:[{kind:'update',steps,elapsed_s:steps/10,'parameters/action_std':.2}]}})});
 await page.goto('/balance.html?room=1');
 const chart=page.locator('#optimizer-chart circle');await expect(chart).toHaveCount(1);
 await chart.focus();const handle=await chart.elementHandle();
 await page.waitForTimeout(5500);expect(detailRequests).toBe(1);
 expect(await handle.evaluate(e=>e.isConnected&&document.activeElement===e)).toBe(true);
 steps=1024;
 await expect(page.locator('#training-phase')).toContainText('1,024 / 1,024',{timeout:10000});
 expect(detailRequests).toBe(2);await expect(chart).toHaveAttribute('aria-label',/1024步/);
});

test('leaving during model download cannot create a renderer or reconnect later',async({page})=>{
 test.setTimeout(60000);let release,entered;
 const pending=new Promise(resolve=>entered=resolve),hold=new Promise(resolve=>release=resolve);
 await page.route('**/api/scenes/model.dkm.gz*',async route=>{entered();await hold;await route.abort()});
 await page.goto('/balance.html?room=2');await page.locator('#prepare-balance').click();await pending;
 await page.evaluate(()=>dispatchEvent(new PageTransitionEvent('pagehide')));release();
 await expect(page.locator('#physics-viewport canvas')).toHaveCount(0);
 await page.waitForTimeout(1600);await expect(page.locator('#physics-viewport canvas')).toHaveCount(0);
});
