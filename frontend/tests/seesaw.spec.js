import {test,expect} from '@playwright/test';

test.afterEach(async({page,request})=>{
 const room=new URL(page.url()).searchParams.get('room');
 if(room)await request.post(`/api/scenes/close?room=${room}`);
});

test('passive seesaw accepts bounded exploration, displays true motion, resets and preserves orbit',async({page,request})=>{
 test.setTimeout(60000);const errors=[];page.on('pageerror',error=>errors.push(error.message));
 const {room}=await(await request.post('/api/rooms')).json();
 await page.goto(`/seesaw.html?room=${room}`);
 await page.locator('#prepare').click();await expect(page.locator('#start')).toBeEnabled({timeout:45000});
 await expect(page.locator('#trained-viewport')).toHaveAttribute('data-rendered-scene','seesaw');
 const before=(await(await request.get(`/api/scenes/state?room=${room}`)).json()).backend;
 await page.locator('[data-direction=backward]').click();
 await expect(page.locator('#trained-status')).toContainText('这一小步结束',{timeout:10000});
 const after=(await(await request.get(`/api/scenes/state?room=${room}`)).json()).backend;
 expect(after.seesaw.mode).toBe('explore');expect(after.sim_time).toBeCloseTo(2);
 expect(after.comparison.baseline.sim_time).toBeCloseTo(2);
 expect(after.seesaw.measurement.position_m).toBeLessThan(before.seesaw.measurement.position_m-.05);
 expect(after.seesaw.measurement.angle_deg).not.toBe(0);
 expect(after.seesaw.trace.length).toBe(20);
 await expect(page.locator('#causal-chart path')).toHaveCount(4);
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
 test.setTimeout(60000);const {room}=await(await request.post('/api/rooms')).json();
 await page.goto(`/seesaw.html?room=${room}`);await page.locator('#prepare').click();
 await expect(page.locator('#start')).toBeEnabled({timeout:45000});
 await page.selectOption('#controller','baseline');await page.locator('#start').click();
 await expect(page.locator('#trained-result')).toContainText('失败',{timeout:20000});
 await expect(page.locator('#baseline-result')).toContainText('失败');
 const state=(await(await request.get(`/api/scenes/state?room=${room}`)).json()).backend;
 expect(state.seesaw.result.success).toBe(false);expect(state.seesaw.result.reason).toBe('not_balanced');
 expect(state.sim_time).toBeCloseTo(12);expect(state.comparison.baseline.sim_time).toBeCloseTo(12);
 expect(Math.abs(state.seesaw.measurement.angle_deg)).toBeGreaterThan(5);
 await page.locator('#reset').click();await expect(page.locator('#trained-result')).toBeHidden();
 await expect(page.locator('#baseline-result')).toBeHidden();
});

test('bundled PPO balances the passive board while the same-start baseline fails',async({page,request})=>{
 test.setTimeout(60000);const {room}=await(await request.post('/api/rooms')).json();
 await page.goto(`/seesaw.html?room=${room}`);await page.locator('#prepare').click();
 await expect(page.locator('#start')).toBeEnabled({timeout:45000});
 await page.locator('#start').click();
 await expect(page.locator('#trained-result')).toHaveText('成功 · 稳住了',{timeout:25000});
 await expect(page.locator('#baseline-result')).toContainText('失败');
 const state=(await(await request.get(`/api/scenes/state?room=${room}`)).json()).backend;
 expect(state.seesaw.controller).toBe('trained');expect(state.seesaw.result.success).toBe(true);
 expect(state.seesaw.policy_steps).toBeGreaterThan(0);
 expect(Math.abs(state.seesaw.measurement.angle_deg)).toBeLessThan(1.5);
 expect(state.seesaw.result.hold_seconds).toBeGreaterThanOrEqual(2);
 expect(state.seesaw.measurement.position_m).not.toBe(state.comparison.baseline.seesaw.measurement.position_m);
 await expect(page.locator('#test-results')).toContainText('PPO：88 / 100');
 await page.locator('#reset').click();await expect(page.locator('#trained-result')).toBeHidden();
 await page.selectOption('#controller','early');await page.locator('#start').click();
 await expect(page.locator('#trained-label')).toHaveText('本轮训练前');
 await page.locator('#stop').click();await expect(page.locator('#trained-result')).toHaveText('已暂停');
});
