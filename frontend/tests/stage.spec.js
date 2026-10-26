import {test,expect} from '@playwright/test';
import * as THREE from 'three';
async function clickDuck(page,member){
 const canvas=page.locator('#demo-viewport canvas');
 // Selecting the tool or checkbox can scroll the page. Measure only after
 // revealing the canvas; pointer coordinates are viewport-relative.
 await canvas.scrollIntoViewIfNeeded();
 const state=await(await page.request.get('/api/scenes/state?room=1')).json();
 const rect=await canvas.boundingBox(),camera=new THREE.PerspectiveCamera(38,rect.width/rect.height,.01,30);
 camera.position.set(2.7,2.1,0);camera.lookAt(0,.13,0);camera.updateMatrixWorld();
 const [x,y,z]=state.backend.ducks.find(d=>d.id===member).position;
 const point=new THREE.Vector3(x,z+.03,-y).project(camera);
 await page.mouse.click(rect.x+(point.x+1)*rect.width/2,rect.y+(1-point.y)*rect.height/2);
}
test('thirteenth show completes measured gathering, roll and shared-clock dance',{tag:'@stage'},async({page})=>{
 test.setTimeout(180000);const errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto('/demos.html?room=1');await expect(page.locator('.program-item')).toHaveCount(13);
 await page.locator('[data-demo=stage]').click();
 await expect(page.locator('#show-status')).toHaveText('本幕完成 · 可重演或进入下一幕',{timeout:150000});
 const result=JSON.parse(await page.locator('#theatre-result').textContent());
 expect(result.scene).toBe('stage');expect(result.results.map(r=>r.name)).toEqual(['stage_gather','stage_roll','stage_dance']);
 expect(result.results[0].outcome.arrived).toEqual([true,true,true,true]);expect(result.results[1].outcome.rotation_rad).toBeGreaterThan(5);
 expect(result.results[2].outcome.clock).toBe('shared_mujoco_sim_time');expect(errors).toEqual([]);
});
test('interactive stage selects ducks and stops without future actions',{tag:'@stage'},async({page})=>{
 test.setTimeout(90000);await page.goto('/demos.html?room=1');
 await page.selectOption('#stage-play','interactive');await page.locator('[data-demo=stage]').click();
 await expect(page.locator('#show-status')).toContainText('现场互动已就绪',{timeout:30000});
 await page.locator('[data-stage-member][value=c]').check();await expect(page.locator('#stage-hint')).toContainText('鸭 C');
 const state=await(await page.request.get('/api/scenes/state?room=1')).json();expect(state.backend.stage.selected).toEqual(['c']);
 await page.selectOption('#stage-pointer','stick');await clickDuck(page,'d');
 await expect(page.locator('#stage-hint')).toContainText('鸭 D');
 await page.selectOption('#stage-pointer','poke');await clickDuck(page,'d');
 await expect.poll(async()=>{const s=await(await page.request.get('/api/scenes/state?room=1')).json();return s.backend.stage.pokes}).toBe(1);

 await page.locator('#stage-gather').click();await expect(page.locator('#stage-state')).toHaveText('集结排队中');
 await page.locator('#stop-demo').click();await expect(page.locator('#show-status')).toHaveText('演示已停止');
 await expect.poll(async()=>{const s=await(await page.request.get('/api/scenes/state?room=1')).json();return s.backend.stage.running}).toBe(false);
 await expect(page.locator('#theatre-result')).toHaveCount(0);
});

test('mobile thirteenth stage keeps touch controls within the viewport',{tag:'@stage'},async({page})=>{
 test.setTimeout(45000);await page.setViewportSize({width:390,height:844});await page.goto('/demos.html?room=1');
 await page.selectOption('#stage-play','interactive');await page.locator('[data-demo=stage]').click();
 await expect(page.locator('#show-status')).toContainText('现场互动已就绪',{timeout:30000});
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
 await page.locator('#stop-demo').click();await expect(page.locator('#show-status')).toHaveText('演示已停止');
});

test('automatic roll honors middle ducks selected by stick and repeated clicks cancel',{tag:'@stage'},async({page})=>{
 test.setTimeout(180000);const errors=[];page.on('pageerror',e=>errors.push(e.message));
 let resumeRoll;const gate=new Promise(resolve=>{resumeRoll=resolve});
 await page.route('**/demo-audio/stage-roll.wav*',async route=>{await gate;await route.continue()});
 await page.goto('/demos.html?room=1');await page.locator('[data-demo=stage]').click();
 await expect(page.locator('#stage-state')).toHaveText('排队完成，已坐稳',{timeout:60000});
 await expect(page.locator('#caption')).toHaveText('选中的小鸭们，能一起翻个跟头吗？',{timeout:15000});
 await page.locator('[data-stage-member][value=a]').uncheck();
 await page.selectOption('#stage-pointer','stick');
 await clickDuck(page,'b');await expect(page.locator('[data-stage-member][value=b]')).toBeChecked();
 await clickDuck(page,'b');await expect(page.locator('[data-stage-member][value=b]')).not.toBeChecked();
 await expect(page.locator('#stage-hint')).toContainText('未选中');
 await clickDuck(page,'b');await expect(page.locator('[data-stage-member][value=b]')).toBeChecked();
 await clickDuck(page,'c');await expect(page.locator('[data-stage-member][value=c]')).toBeChecked();
 resumeRoll();
 await expect(page.locator('#show-status')).toHaveText('本幕完成 · 可重演或进入下一幕',{timeout:140000});
 const proof=JSON.parse(await page.locator('#theatre-result').textContent());
 const roll=proof.results.find(r=>r.name==='stage_roll');
 expect(roll.outcome.members).toEqual(['b','c']);
 expect(roll.outcome.results.map(r=>r.member)).toEqual(['b','c']);
 expect(roll.outcome.results.every(r=>r.rotation_rad>5&&!r.returned)).toBe(true);
 expect(errors).toEqual([]);
});

test('finished show accepts repeated selected gathering, seated roll and selected dance',{tag:'@stage'},async({page})=>{
 test.setTimeout(240000);await page.goto('/demos.html?room=1');
 await page.locator('[data-demo=stage]').click();
 await expect(page.locator('#show-status')).toHaveText('本幕完成 · 可重演或进入下一幕',{timeout:120000});
 for(const id of ['stage-gather','stage-roll','stage-dance'])await expect(page.locator('#'+id)).toBeEnabled();
 const state=async()=>(await(await page.request.get('/api/scenes/state?room=1')).json());
 for(const member of 'abcd'){
  const checkbox=page.locator(`[data-stage-member][value=${member}]`);
  if(member==='b'||member==='c')await checkbox.check();else await checkbox.uncheck();
 }
 await expect.poll(async()=> (await state()).backend.stage.selected).toEqual(['b','c']);
 async function perform(id,name){
  const before=(await state()).events.at(-1)?.id??0;
  await page.locator('#'+id).click();
  await expect(page.locator('#show-status')).toHaveText('本地操作完成 · 可继续操作',{timeout:90000});
  const now=await state(),event=now.events.findLast(e=>e.id>before&&e.kind==='result'&&e.text.startsWith(name+' ·'));
  expect(event).toBeTruthy();const result=await(await page.request.get(`/api/scenes/actions/${event.action_id}?room=1`)).json();
  expect(result.status).toBe('completed');expect(result.outcome.members).toEqual(['b','c']);return now;
 }
 const initial=await perform('stage-gather','stage_gather');
 expect(initial.backend.ducks.slice(1,3).map(d=>d.posture.observed)).toEqual(['sit','sit']);
 const rolled=await perform('stage-roll','stage_roll');
 expect(rolled.backend.ducks.map(d=>d.posture.observed)).toEqual(['stand','sit','sit','stand']);
 expect(rolled.backend.stage.roll.returned).toBe(false);
 const dancing=await perform('stage-dance','stage_dance');
 expect(dancing.backend.ducks.slice(1,3).map(d=>d.posture.observed)).toEqual(['stand','stand']);
 await perform('stage-dance','stage_dance');await perform('stage-gather','stage_gather');
 await page.locator('#stop-demo').click();await expect(page.locator('#show-status')).toHaveText('演示已停止');
});
