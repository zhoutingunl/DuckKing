import {test,expect} from '@playwright/test';

async function claimRoom(request){
 const response=await request.post('/api/rooms/claim');expect(response.ok()).toBe(true);
 const room=(await response.json()).room;
 // Claim may reuse an idle room containing another test's scene. Entry
 // preparation deliberately preserves that scene, so start this fixture empty.
 expect((await request.post(`/api/scenes/close?room=${room}&if_unused=true`)).status()).toBe(204);
 return room;
}

async function fixedRound(page){
 await page.selectOption('#match-mode','compare');
 await page.locator('.replay-settings summary').click();
 await page.locator('#fixed-seed').check();await page.locator('#seed').fill('0');
 await page.locator('.replay-settings summary').click();
}

test.afterEach(async({page,request})=>{
 const room=new URL(page.url()).searchParams.get('room');
 if(room)await request.post(`/api/scenes/close?room=${room}`);
});

test('arrow keys give bounded left-duck commands without stealing form keys or restarting a paused round',async({page,request})=>{
 test.setTimeout(60000);const room=await claimRoom(request),commands=[];
 page.on('request',r=>{if(r.method()==='POST'&&new URL(r.url()).pathname==='/api/seesaw/command')commands.push(r.postDataJSON())});
 await page.goto(`/seesaw.html?room=${room}`);await expect(page.locator('#start')).toBeEnabled({timeout:45000});
 await expect(page.locator('[data-human-direction=forward]')).toBeEnabled({timeout:45000});
 await page.locator('.replay-settings summary').click();await page.locator('#fixed-seed').check();
 await page.locator('#seed').fill('8852');
 for(const key of ['ArrowLeft','ArrowRight','ArrowDown'])await page.keyboard.press(key);
 expect(commands).toEqual([]);await page.locator('#seed').fill('8852');
 await page.locator('.replay-settings summary').click();
 const state=async()=> (await(await request.get(`/api/scenes/state?room=${room}`)).json()).backend.seesaw;
 await page.keyboard.down('ArrowLeft');
 await expect.poll(async()=> (await state()).human_command?.direction).toBe('forward');
 await expect(page.locator('[data-human-direction=forward]')).toBeEnabled();
 // OS key repeat must not extend the deadline or queue up another movement.
 await page.keyboard.down('ArrowLeft');await page.keyboard.up('ArrowLeft');
 await expect.poll(async()=> (await state()).human_command.remaining_seconds,{timeout:6000}).toBe(0);
 expect(commands).toEqual([expect.objectContaining({operation:'nudge',direction:'forward',seconds:2,seed:8852})]);
 const first=await state();expect(first.controller).toBe('trained');expect(first.comparison.controller).toBe('human');
 // Keep the bounded backward/hold sequence inside the browser: several
 // automation round trips on a software GPU can outlast the real duck's balance.
 await page.evaluate(()=>{
  const hold=document.querySelector('[data-human-direction=hold]');let waiting=false;
  const observer=new MutationObserver(()=>{
   if(hold.disabled){waiting=true;return}
   if(!waiting)return;
   observer.disconnect();document.activeElement.dispatchEvent(new KeyboardEvent('keydown',{key:'ArrowDown',bubbles:true}));
  });
  observer.observe(hold,{attributes:true,attributeFilter:['disabled']});
 });
 await page.keyboard.press('ArrowRight');
 await expect.poll(async()=> (await state()).human_command.direction).toBe('hold');
 expect(commands.map(c=>c.direction)).toEqual(['forward','backward','hold']);
 expect((await state()).seed).toBe(first.seed);expect((await state()).controller).toBe('trained');
 await expect(page.locator('#activity-log')).toContainText('方向键');
 await page.locator('#stop').click();await expect(page.locator('#baseline-result')).toHaveText('已暂停');
 const count=commands.length;
 for(const key of ['ArrowLeft','ArrowRight','ArrowDown'])await page.keyboard.press(key);
 expect(commands.length).toBe(count);expect((await state()).comparison.execution).toBe('paused');
});

test('first left command starts a random PK; mic and both worlds stay in view',async({page,request})=>{
 test.setTimeout(90000);const room=await claimRoom(request);
 await page.setViewportSize({width:1440,height:900});
 await page.goto(`/seesaw.html?room=${room}`);await expect(page.locator('#start')).toBeEnabled({timeout:45000});
 await expect(page.locator('[data-human-direction=backward]')).toBeEnabled({timeout:45000});
 await expect(page.locator('#match-mode')).toHaveValue('duel');
 await expect(page.locator('#seed')).not.toBeVisible();
 await page.locator('.seesaw-arena').scrollIntoViewIfNeeded();
 const boxes=await page.evaluate(()=>Object.fromEntries(['talk-button','baseline-viewport','trained-viewport'].map(id=>{
  const r=document.getElementById(id).getBoundingClientRect();return [id,{top:r.top,bottom:r.bottom}];
 })));
 expect(boxes['talk-button'].top).toBeGreaterThanOrEqual(0);
 expect(boxes['baseline-viewport'].top).toBe(boxes['trained-viewport'].top);
 for(const id of ['baseline-viewport','trained-viewport']){
  expect(boxes[id].top).toBeGreaterThan(boxes['talk-button'].bottom);
  expect(boxes[id].bottom).toBeLessThanOrEqual(900);
 }
 const get=async()=> (await(await request.get(`/api/scenes/state?room=${room}`)).json()).backend.seesaw;
 await page.locator('[data-human-direction=backward]').click();
 await expect.poll(async()=> (await get()).human_command.direction).toBe('backward');
 const first=await get();expect(first.mode).toBe('duel');expect(first.controller).toBe('trained');
 expect(first.comparison.controller).toBe('human');expect(first.seed).not.toBe(0);expect(first.comparison.seed).toBe(first.seed);
 await page.locator('#stop').click();await expect(page.locator('#baseline-result')).toHaveText('已暂停');
 await page.locator('#start').click();
 await expect.poll(async()=> (await get()).seed).not.toBe(first.seed);
 await page.locator('#stop').click();
 const stop=await page.locator('#stop').boundingBox(),reset=await page.locator('#reset').boundingBox();
 expect(stop.height).toBe(reset.height);expect(stop.y).toBe(reset.y);
 await page.setViewportSize({width:390,height:844});
 await page.locator('#baseline-viewport').scrollIntoViewIfNeeded();
 const mic=await page.locator('#talk-button').boundingBox();expect(mic.y).toBeGreaterThanOrEqual(0);expect(mic.y+mic.height).toBeLessThan(844);
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
});

test('training selection preserves room and human PK controls only the left duck',async({page,request})=>{
 test.setTimeout(90000);const errors=[];page.on('pageerror',e=>errors.push(e.message));
 const room=await claimRoom(request);
 await page.goto(`/training.html?room=${room}`);
 await expect(page.locator('.turntable-choice')).toHaveAttribute('href',new RegExp(`balance\\.html\\?room=${room}$`));
 await page.locator('.seesaw-choice').click();await expect(page.locator('#start')).toBeEnabled({timeout:45000});
 await expect(page.locator('#start')).toBeEnabled({timeout:45000});await fixedRound(page);
 await page.selectOption('#match-mode','duel');await page.locator('#start').click();
 await expect(page.locator('#baseline-label')).toHaveText('你来控制 · 真人');
 await page.locator('[data-human-direction=backward]').click();
 await expect(page.locator('#human-status')).toContainText('后退');
 await expect(page.locator('#human-status')).toContainText('站定',{timeout:8000});
 const state=(await(await request.get(`/api/scenes/state?room=${room}`)).json()).backend;
 expect(state.seesaw.mode).toBe('duel');expect(state.seesaw.controller).toBe('trained');
 expect(state.seesaw.comparison.controller).toBe('human');
 expect(state.sim_time).toBeCloseTo(state.comparison.baseline.sim_time);
 expect(state.sim_time).toBeGreaterThan(2);expect(state.seesaw.execution).toBe('running');
 expect(state.seesaw.human_command.remaining_seconds).toBe(0);
 await page.locator('[data-human-direction=forward]').click();
 await expect(page.locator('#human-status')).toContainText('前进');
 // A real two-second human step can leave the board while the PPO continues.
 // Start a fresh round for hold/cancellation; a late hold must not undo a fall.
 await page.locator('#reset').click();await expect(page.locator('#baseline-result')).toBeHidden();
 await page.selectOption('#match-mode','duel');await page.locator('#start').click();
 await expect(page.locator('[data-human-direction=forward]')).toBeEnabled();
 await page.locator('[data-human-direction=hold]').click();
 await expect(page.locator('#human-status')).toContainText('站定');
 await page.locator('#stop').click();await expect(page.locator('[data-human-direction=forward]')).toBeDisabled();
 await expect(page.locator('#baseline-result')).toHaveText('已暂停');
 await expect(page.locator('#human-status')).toContainText('左鸭已暂停');
 await page.setViewportSize({width:390,height:844});expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
 expect(errors).toEqual([]);
});

test('passive seesaw accepts bounded exploration, displays true motion, resets and preserves orbit',async({page,request})=>{
 test.setTimeout(90000);const errors=[];page.on('pageerror',error=>errors.push(error.message));
 const room=await claimRoom(request);
 await page.goto(`/seesaw.html?room=${room}`);
 await expect(page.locator('#start')).toBeEnabled({timeout:45000});await page.selectOption('#controller','rule');await expect(page.locator('#start')).toBeEnabled({timeout:45000});await fixedRound(page);
 await expect(page.locator('#trained-viewport')).toHaveAttribute('data-rendered-scene','seesaw');
 const before=(await(await request.get(`/api/scenes/state?room=${room}`)).json()).backend;
 await page.locator('.explore-controls summary').click();await page.locator('[data-direction=backward]').click();
 await expect(page.locator('#trained-status')).toContainText('这一小步结束',{timeout:10000});
 const after=(await(await request.get(`/api/scenes/state?room=${room}`)).json()).backend;
 expect(after.seesaw.mode).toBe('explore');expect(after.sim_time).toBeCloseTo(2);
 expect(after.comparison.baseline.sim_time).toBeCloseTo(2);
 expect(after.seesaw.comparison.measurement.position_m).toBeLessThan(before.seesaw.comparison.measurement.position_m-.05);
 expect(after.seesaw.controller).toBe('baseline');expect(after.seesaw.comparison.controller).toBe('manual');
 expect(after.seesaw.measurement.angle_deg).not.toBe(0);
 expect(after.seesaw.trace.length).toBe(20);
 await expect(page.locator('#causal-chart path')).toHaveCount(6);
 await page.locator('#reset').click();await expect(page.locator('#trained-time')).toHaveText('0.0 s');
 await expect(page.locator('#trained-result')).toBeHidden();
 await page.selectOption('#controller','baseline');await page.locator('#start').click();
 await expect(page.locator('#trained-status')).toContainText('进行中');
 await page.locator('#stop').click();await expect(page.locator('#trained-result')).toHaveText('已暂停');
 const canvas=page.locator('#trained-viewport canvas').first();
 const pixels=await canvas.screenshot();
 const box=await canvas.boundingBox();await page.mouse.move(box.x+box.width/2,box.y+box.height/2);
 await page.mouse.down();await page.mouse.move(box.x+box.width/2+60,box.y+box.height/2+25,{steps:8});await page.mouse.up();
 await page.waitForTimeout(300);expect(Buffer.compare(pixels,await canvas.screenshot())).not.toBe(0);
 await page.setViewportSize({width:390,height:844});
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
 const overlay=page.locator('#trained-result');expect(await overlay.evaluate(e=>getComputedStyle(e).pointerEvents)).toBe('none');
 expect(errors).toEqual([]);
});

test('official baseline visibly fails at the angle limit and replay clears old result',async({page,request})=>{
 test.setTimeout(90000);const room=await claimRoom(request);
 await page.goto(`/seesaw.html?room=${room}`);await expect(page.locator('#start')).toBeEnabled({timeout:45000});
 await page.selectOption('#controller','rule');await expect(page.locator('#start')).toBeEnabled({timeout:45000});await fixedRound(page);
 await page.selectOption('#controller','baseline');await page.locator('#start').click();
 await expect(page.locator('#trained-result')).toContainText('失败',{timeout:30000});
 await expect(page.locator('#baseline-result')).toContainText('失败');
 const state=(await(await request.get(`/api/scenes/state?room=${room}`)).json()).backend;
 expect(state.seesaw.result.success).toBe(false);expect(state.seesaw.result.reason).toBe('not_docked');
 expect(state.sim_time).toBeCloseTo(18);expect(state.comparison.baseline.sim_time).toBeCloseTo(18);
 expect(Math.abs(state.seesaw.measurement.angle_deg)).toBeGreaterThan(5);
 await page.locator('#reset').click();await expect(page.locator('#trained-result')).toBeHidden();
 await expect(page.locator('#baseline-result')).toBeHidden();
});

test('different actions produce different free-load trajectories',async({page,request})=>{
 test.setTimeout(90000);const room=await claimRoom(request);
 await page.goto(`/seesaw.html?room=${room}`);await expect(page.locator('#start')).toBeEnabled({timeout:45000});
 await page.selectOption('#controller','rule');await expect(page.locator('#start')).toBeEnabled({timeout:45000});await fixedRound(page);
 await page.locator('#start').click();
 await expect(page.locator('#trained-result')).toContainText('失败',{timeout:35000});
 const state=(await(await request.get(`/api/scenes/state?room=${room}`)).json()).backend;
 expect(state.seesaw.load.actuators).toBe(0);
 expect(state.seesaw.comparison.controller).toBe('center');
 const divergence=state.seesaw.trace.map(r=>Math.abs(r.weight_position_cm-r.baseline_weight_position_cm));
 expect(Math.max(...divergence)).toBeGreaterThan(10);
 expect(state.seesaw.comparison.result.success).toBe(false);
 await expect(page.locator('#load-description')).toContainText('无电机');
 await expect(page.locator('#causal-chart path')).toHaveCount(6);
 await page.setViewportSize({width:390,height:844});
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
});

test('bundled PPO docks the free load while the same-start center baseline fails',async({page,request})=>{
 test.setTimeout(90000);const room=await claimRoom(request);
 await page.goto(`/seesaw.html?room=${room}`);await expect(page.locator('#start')).toBeEnabled({timeout:45000});
 await page.selectOption('#controller','rule');await expect(page.locator('#start')).toBeEnabled({timeout:45000});await fixedRound(page);
 await page.selectOption('#controller','trained');await page.locator('#start').click();
 await expect(page.locator('#trained-result')).toHaveText('成功 · 配重已停靠',{timeout:30000});
 await expect(page.locator('#baseline-result')).toContainText('失败');
 const state=(await(await request.get(`/api/scenes/state?room=${room}`)).json()).backend;
 expect(state.seesaw.controller).toBe('trained');expect(state.seesaw.result.success).toBe(true);
 expect(state.seesaw.policy_steps).toBeGreaterThan(0);
 expect(Math.abs(state.seesaw.measurement.angle_deg)).toBeLessThan(2);
 expect(Math.abs(state.seesaw.measurement.weight_position_m)).toBeLessThan(.04);
 expect(Math.abs(state.seesaw.measurement.weight_velocity_m_s)).toBeLessThan(.025);
 expect(state.seesaw.result.hold_seconds).toBeGreaterThanOrEqual(1 - 1e-6);
 expect(state.seesaw.measurement.position_m).not.toBe(state.comparison.baseline.seesaw.measurement.position_m);
 const {report}=await(await request.get('/api/seesaw/training')).json();
 await expect(page.locator('#test-results')).toContainText(`PPO：${report.test.successes} / ${report.test.episodes}`);
 await page.locator('#reset').click();await expect(page.locator('#trained-result')).toBeHidden();
 await page.selectOption('#controller','early');await page.locator('#start').click();
 await expect(page.locator('#trained-label')).toHaveText('本轮训练前');
 await page.locator('#stop').click();await expect(page.locator('#trained-result')).toHaveText('已暂停');
});
