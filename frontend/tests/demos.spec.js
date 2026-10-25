import {test,expect} from '@playwright/test';
import {DEMOS} from '../src/demo-catalog.js';

// Short, explicitly synthetic fixture speech keeps CI focused on real physics
// and orchestration. A separate manual/public acceptance uses the shipped audio.
function silentFixture(){
 const b=Buffer.alloc(44+3200);b.write('RIFF');b.writeUInt32LE(b.length-8,4);b.write('WAVE',8);b.write('fmt ',12);b.writeUInt32LE(16,16);b.writeUInt16LE(1,20);b.writeUInt16LE(1,22);b.writeUInt32LE(16000,24);b.writeUInt32LE(32000,28);b.writeUInt16LE(2,32);b.writeUInt16LE(16,34);b.write('data',36);b.writeUInt32LE(3200,40);return b;
}
test('all ten automated scripts validate actual MuJoCo outcomes and chorale seats',async({page})=>{
 test.setTimeout(240000);
 await page.route('**/demo-audio/*.wav',route=>route.fulfill({contentType:'audio/wav',body:silentFixture()}));
 const errors=[];page.on('pageerror',e=>errors.push(e.message));await page.goto('/demos.html?room=1');
 await expect(page.locator('.program-item')).toHaveCount(10);
 for(const demo of DEMOS){
  await page.locator(`[data-demo="${demo.id}"]`).click();
  await expect(page.locator('#show-status')).toHaveText('本幕完成 · 可重演或进入下一幕',{timeout:60000});
  const proof=await page.locator('#theatre-result').textContent();expect(JSON.parse(proof).scene).toBe(demo.id);
  expect(JSON.parse(proof).mode).toBe('scripted_rehearsal');await expect(page.locator('#demo-notice')).toBeHidden();
  await expect(page.locator('#demo-mode')).toBeEnabled({timeout:10000});
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

test('suspended audio clock stops the chorale instead of hanging the script',async({page})=>{
 test.setTimeout(60000);
 await page.addInitScript(()=>{const Native=window.AudioContext;window.demoContexts=[];window.AudioContext=class extends Native{constructor(...args){super(...args);window.demoContexts.push(this)}}});
 await page.route('**/demo-audio/*.wav',route=>route.fulfill({contentType:'audio/wav',body:silentFixture()}));
 await page.goto('/demos.html?room=1');await page.locator('[data-demo="chorale"]').click();
 await expect(page.locator('#chorale-panel')).toBeVisible({timeout:30000});
 await expect(page.locator('#chorale-beat')).toContainText('第 ');
 await page.evaluate(()=>Promise.all(window.demoContexts.map(ctx=>ctx.suspend())));
 await expect(page.locator('#show-status')).toHaveText('本幕未完成 · 点击节目重试');
 await expect(page.locator('#demo-notice')).toContainText('音频时钟');
});
