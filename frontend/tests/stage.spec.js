import {test,expect} from '@playwright/test';
import * as THREE from 'three';
test('thirteenth show completes measured gathering, roll and shared-clock dance',async({page})=>{
 test.setTimeout(180000);const errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto('/demos.html?room=1');await expect(page.locator('.program-item')).toHaveCount(13);
 await page.locator('[data-demo=stage]').click();
 await expect(page.locator('#show-status')).toHaveText('本幕完成 · 可重演或进入下一幕',{timeout:150000});
 const result=JSON.parse(await page.locator('#theatre-result').textContent());
 expect(result.scene).toBe('stage');expect(result.results.map(r=>r.name)).toEqual(['stage_gather','stage_roll','stage_dance']);
 expect(result.results[0].outcome.arrived).toEqual([true,true,true,true]);expect(result.results[1].outcome.rotation_rad).toBeGreaterThan(5);
 expect(result.results[2].outcome.clock).toBe('shared_mujoco_sim_time');expect(errors).toEqual([]);
});
test('interactive stage selects ducks and stops without future actions',async({page})=>{
 test.setTimeout(90000);await page.goto('/demos.html?room=1');
 await page.selectOption('#stage-play','interactive');await page.locator('[data-demo=stage]').click();
 await expect(page.locator('#show-status')).toContainText('现场互动已就绪',{timeout:30000});
 await page.locator('[data-stage-member][value=c]').check();await expect(page.locator('#stage-hint')).toContainText('鸭 C');
 const state=await(await page.request.get('/api/scenes/state?room=1')).json();expect(state.backend.stage.selected).toEqual(['c']);
 const canvas=page.locator('#demo-viewport canvas'),rect=await canvas.boundingBox();
 const camera=new THREE.PerspectiveCamera(38,rect.width/rect.height,.01,30);camera.position.set(2.7,2.1,0);camera.lookAt(0,.13,0);camera.updateMatrixWorld();
 const duck=state.backend.ducks.find(d=>d.id==='d'),[x,y,z]=duck.position;
 const point=new THREE.Vector3(x,z+.045,-y).project(camera),px=rect.x+(point.x+1)*rect.width/2,py=rect.y+(1-point.y)*rect.height/2;
 await page.selectOption('#stage-pointer','stick');await page.mouse.click(px,py);
 await expect(page.locator('#stage-hint')).toContainText('鸭 D');
 await page.selectOption('#stage-pointer','poke');await page.mouse.click(px,py);
 await expect.poll(async()=>{const s=await(await page.request.get('/api/scenes/state?room=1')).json();return s.backend.stage.pokes}).toBe(1);

 await page.locator('#stage-gather').click();await expect(page.locator('#stage-state')).toHaveText('集结排队中');
 await page.locator('#stop-demo').click();await expect(page.locator('#show-status')).toHaveText('演示已停止');
 await expect.poll(async()=>{const s=await(await page.request.get('/api/scenes/state?room=1')).json();return s.backend.stage.running}).toBe(false);
 await expect(page.locator('#theatre-result')).toHaveCount(0);
});

test('mobile thirteenth stage keeps touch controls within the viewport',async({page})=>{
 test.setTimeout(45000);await page.setViewportSize({width:390,height:844});await page.goto('/demos.html?room=1');
 await page.selectOption('#stage-play','interactive');await page.locator('[data-demo=stage]').click();
 await expect(page.locator('#show-status')).toContainText('现场互动已就绪',{timeout:30000});
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
 await page.locator('#stop-demo').click();await expect(page.locator('#show-status')).toHaveText('演示已停止');
});

test('automatic roll honors middle ducks selected by stick and repeated clicks cancel',async({page})=>{
 test.setTimeout(180000);const errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto('/demos.html?room=1');await page.locator('[data-demo=stage]').click();
 await expect(page.locator('#stage-state')).toHaveText('集结排队中',{timeout:30000});
 await expect(page.locator('[data-stage-member][value=a]')).not.toBeChecked();
 await page.selectOption('#stage-pointer','stick');
 async function tap(member){
  const state=await(await page.request.get('/api/scenes/state?room=1')).json();
  const rect=await page.locator('#demo-viewport canvas').boundingBox();
  const camera=new THREE.PerspectiveCamera(38,rect.width/rect.height,.01,30);camera.position.set(2.7,2.1,0);camera.lookAt(0,.13,0);camera.updateMatrixWorld();
  const [x,y,z]=state.backend.ducks.find(d=>d.id===member).position;
  const p=new THREE.Vector3(x,z+.045,-y).project(camera);
  await page.mouse.click(rect.x+(p.x+1)*rect.width/2,rect.y+(1-p.y)*rect.height/2);
 }
 await tap('b');await expect(page.locator('[data-stage-member][value=b]')).toBeChecked();
 await tap('b');await expect(page.locator('[data-stage-member][value=b]')).not.toBeChecked();
 await expect(page.locator('#stage-hint')).toContainText('未选中');
 await tap('b');await expect(page.locator('[data-stage-member][value=b]')).toBeChecked();
 await tap('c');await expect(page.locator('[data-stage-member][value=c]')).toBeChecked();
 await expect(page.locator('#show-status')).toHaveText('本幕完成 · 可重演或进入下一幕',{timeout:140000});
 const proof=JSON.parse(await page.locator('#theatre-result').textContent());
 const roll=proof.results.find(r=>r.name==='stage_roll');
 expect(roll.outcome.members).toEqual(['b','c']);
 expect(roll.outcome.results.map(r=>r.member)).toEqual(['b','c']);
 expect(roll.outcome.results.every(r=>r.rotation_rad>5&&r.returned)).toBe(true);
 expect(errors).toEqual([]);
});
