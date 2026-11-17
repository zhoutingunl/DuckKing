import {test,expect} from '@playwright/test';
import {existsSync} from 'node:fs';

test('functional catalogue prepares without starting, cancels, releases and reopens',async({page})=>{
 test.setTimeout(90000);
 const errors=[];page.on('pageerror',error=>errors.push(error.message));
 await page.request.post('/api/scenes/close?room=1');
 await page.goto('/features.html?room=1&lang=en&feature=movement');
 await expect(page.locator('[data-capability]')).toHaveCount(41);
 await expect(page.locator('[data-capability=basketball]')).toContainText('Blind basketball balance');
 await expect(page.locator('#scene-placeholder')).toBeHidden({timeout:45000});
 await expect(page.locator('[data-feature-action=walk]')).toBeEnabled();
 await expect(page.locator('#reset-feature')).toHaveCount(0);
 await expect(page.locator('#prepare-feature')).toBeHidden();
 const state=await (await page.request.get('/api/scenes/state?room=1')).json();
 expect(state.backend.scene).toBe('functional');expect(state.backend.feature.status).toBe('idle');
 // Keep the action alive while software WebGL scrolls the stop button into view.
 // Cancellation is confirmed through the real control and paused state.
 await page.locator('#feature-duration').fill('36');
 await page.locator('[data-feature-action=walk]').click();
 await expect(page.locator('#task-status')).toHaveText(/Executing|Running|In progress|正在执行/,{timeout:5000});
 await page.locator('#stop-feature').click();
 await expect(page.locator('#task-status')).toHaveText('Task cancelled',{timeout:10000});
 await page.locator('#release-feature').click();
 await expect(page.locator('#scene-placeholder')).toBeVisible();
 await expect(page.locator('[data-feature-action=walk]')).toBeDisabled();
 await expect(page.locator('#scene-placeholder')).not.toContainText('first frame');
 await page.locator('#prepare-feature').click();
 await expect(page.locator('#scene-placeholder')).toBeHidden({timeout:45000});
 await page.setViewportSize({width:390,height:844});
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
 await page.locator('#feature-duration').scrollIntoViewIfNeeded();
 expect(await page.locator('#physics-viewport').evaluate(el=>el.getBoundingClientRect().bottom>0)).toBe(true);
 expect(errors).toEqual([]);
 await page.request.post('/api/scenes/close?room=1');
});

test('missing functional policy has a recovery action and no preview fallback',async({page})=>{
 await page.route('**/api/features/prepare?*',route=>route.fulfill({status:503,json:{detail:'Missing functional policy'}}));
 await page.goto('/features.html?room=1&lang=en&feature=movement');
 await expect(page.locator('#notice')).toHaveText('Missing functional policy');
 await expect(page.locator('[data-feature-action=walk]')).toBeDisabled();
 await expect(page.locator('#prepare-feature')).toBeEnabled();
 await expect(page.locator('#scene-placeholder')).toBeVisible();
});

test('readiness fixtures disable unavailable actions and explain the recovery path',async({page})=>{
 test.setTimeout(60000);let mode='blocked';
 // Only the readiness envelope is a fixture; the model/room are real. Use HTTP
 // snapshots so the test does not race a second, unmodified WebSocket channel.
 await page.routeWebSocket(/\/scene-ws(?:\?|$)/,socket=>socket.close({code:1013,reason:'readiness fixture'}));
 await page.route('**/api/scenes/state?*',async route=>{
  const response=await route.fetch(),body=await response.json(),f=body.backend?.feature;
  if(f){
   if(mode==='blocked')f.actions.walk={enabled:false,reason:'请等待场景准备完成。'};
   if(mode==='preparing'){f.status='running';f.phase='preparing';f.message='这个动作从起点开始，正在准备新一轮。'}
   if(mode==='recovery'){f.status='failed';f.phase='failed';f.recovery_required=true;f.recovery_reason='场景恢复失败，请重新准备场景。'}
  }
  await route.fulfill({response,json:body});
 });
 try{
  await page.goto('/features.html?room=1&feature=movement&lang=zh');
  await expect(page.locator('#scene-placeholder')).toBeHidden({timeout:45000});
  await expect(page.locator('[data-feature-action=walk]')).toBeDisabled();
  await expect(page.locator('[data-feature-action=nod]')).toBeEnabled({timeout:45000});
  await expect(page.locator('#feature-action-hint')).toHaveText('请等待场景准备完成。');
  mode='preparing';
  await expect(page.locator('#task-status')).toHaveText('正在准备场景');
  await expect(page.locator('[data-feature-action=nod]')).toBeDisabled();
  await expect(page.locator('#stop-feature')).toBeEnabled();
  await expect(page.locator('#prepare-feature')).toBeHidden();
  mode='recovery';
  await expect(page.locator('#feature-action-hint')).toHaveText('场景恢复失败，请重新准备场景。');
  await expect(page.locator('[data-feature-action=walk]')).toBeDisabled();
  await expect(page.locator('#prepare-feature')).toBeVisible();
  await expect(page.locator('#prepare-feature')).toBeEnabled();
  mode='ready';
  await expect(page.locator('[data-feature-action=walk]')).toBeEnabled();
  await expect(page.locator('#prepare-feature')).toBeHidden();
  await expect(page.locator('#reset-feature')).toHaveCount(0);
 }finally{await page.request.post('/api/scenes/close?room=1')}
});

test.describe('phone action entry',()=>{
test.use({isMobile:true,hasTouch:true,viewport:{width:390,height:844}});
for(const language of ['zh','es'])for(const capability of ['movement','dock'])test(`${language} ${capability}: selecting a scene exposes actions before details and preserves the world across layouts`,async({page},info)=>{
 test.skip(capability==='dock'&&!existsSync(new URL('../../external/features/playground/hardware/microdock-v2/policy/scoot_dock.onnx',import.meta.url)), 'Requires the optional MicroDock policy assets');
 test.setTimeout(90000);
 const action=capability==='dock'?'dock':'walk';
 const prepares=[];page.on('request',request=>{if(new URL(request.url()).pathname==='/api/features/prepare')prepares.push(request.url())});
 await page.request.post('/api/scenes/close?room=1');
 try{
  await page.goto(`/features.html?room=1&lang=${language}`);
  await page.locator('#show-all-scenes').click();
  await page.locator(`[data-capability=${capability}]`).tap();
  await expect(page.locator(`[data-feature-action=${action}]`)).toBeEnabled({timeout:45000});
  await expect(page.locator('#scene-placeholder')).toBeHidden();
  // Do not scroll the controls into view: selecting the scene must reveal them.
  const checkEntry=async()=>{
   await expect.poll(()=>page.evaluate(action=>{
    const button=document.querySelector(`[data-feature-action=${action}]`),stage=document.querySelector('.mobile-stage-dock');
    if(!button||!stage)return false;
    const r=button.getBoundingClientRect(),dock=stage.getBoundingClientRect();
    return r.top>=dock.bottom&&r.bottom<=innerHeight&&button.contains(document.elementFromPoint(r.x+r.width/2,r.y+r.height/2));
   },action)).toBe(true);
  };
  await checkEntry();
  if(capability==='dock'){
   await expect(page.locator('[data-feature-action=undock]')).toBeDisabled();
   await expect(page.locator('#feature-action-hint')).toContainText(language==='es'?'Primero regresa al nido':'先回窝');
  }
  await expect(page.locator('.feature-evidence #feature-introduction')).toHaveCount(1);
  await expect(page.locator('.scene-controls>.feature-details')).toHaveCount(1);
  await expect(page.locator('.physics-caption')).toContainText(language==='es'?'Esperando instrucciones':'等待指令');
  await page.screenshot({path:info.outputPath(`${capability}-phone-actions.png`)});
  await page.locator('#physics-viewport canvas').evaluate(canvas=>window.featureCanvas=canvas);
  const revision=(await(await page.request.get('/api/scenes/state?room=1')).json()).backend.revision;
  if(capability==='movement')await page.locator('#feature-duration').fill('36');
  const accepted=page.waitForResponse(response=>new URL(response.url()).pathname==='/api/features/command'&&response.request().postDataJSON()?.action===action);
  await page.locator(`[data-feature-action=${action}]`).tap();expect((await accepted).ok()).toBe(true);
  await page.locator('#stop-feature').tap();
  await expect(page.locator('#task-status')).toHaveText(language==='es'?'Tarea cancelada':'任务已取消',{timeout:10000});
  for(const viewport of [{width:1440,height:1050},{width:667,height:375}]){
   await page.setViewportSize(viewport);
   await expect(page.locator('.scene-stage>.feature-details')).toHaveCount(1);
   await expect(page.locator('.scene-actions>#feature-introduction')).toHaveCount(1);
   await expect(page.locator('.mobile-stage-dock')).toHaveCount(0);
  }
  for(const viewport of [{width:320,height:568},{width:390,height:844}]){
   await page.setViewportSize(viewport);
   // matchMedia updates on a later render tick after setViewportSize resolves.
   await expect(page.locator('.mobile-stage-dock')).toBeVisible();
   // Only the scene-selection scroll is repeated after resizing, never a control scroll.
   await page.locator('#functional-workspace').evaluate(element=>element.scrollIntoView({block:'start'}));
   await checkEntry();
   expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  }
  expect(await page.locator('#physics-viewport canvas').evaluate(canvas=>canvas===window.featureCanvas)).toBe(true);
  expect((await(await page.request.get('/api/scenes/state?room=1')).json()).backend.revision).toBe(revision);
  expect(prepares).toHaveLength(1);
 }finally{await page.request.post('/api/scenes/close?room=1')}
});
});

test.describe('phone basketball',()=>{
test.use({isMobile:true,hasTouch:true});
test('mobile basketball keeps a large unobscured canvas while trial controls remain tappable',async({page},info)=>{
 test.skip(!existsSync(new URL('../../external/features/policies/basketball/policy.onnx',import.meta.url)), 'Requires the optional community basketball assets');
 test.setTimeout(90000);
 await page.setViewportSize({width:390,height:844});
 await page.request.post('/api/scenes/close?room=1');
 try{
  await page.goto('/features.html?room=1&feature=basketball');
  await expect(page.locator('[data-feature-action=balance_ball]')).toBeEnabled({timeout:45000});
  await expect(page.locator('#scene-placeholder')).toBeHidden({timeout:45000});
  const checkLayout=async()=>{
   await page.locator('[data-feature-action=balance_ball]').evaluate(el=>el.scrollIntoView({block:'start'}));
   await expect.poll(()=>page.evaluate(()=>{
    const dock=document.querySelector('.mobile-stage-dock').getBoundingClientRect();
    const view=document.querySelector('#physics-viewport canvas').getBoundingClientRect();
    const caption=document.querySelector('.physics-caption').getBoundingClientRect();
    const button=document.querySelector('[data-feature-action=balance_ball]'),r=button.getBoundingClientRect();
    const issues=[];
    if(view.height<Math.min(210,innerHeight*.27))issues.push(`canvas too short: ${view.height}`);
    if(view.y<0||view.bottom>caption.top+1||caption.bottom>dock.bottom+1)issues.push(`canvas/caption clipped: ${JSON.stringify({view:view.toJSON(),caption:caption.toJSON(),dock:dock.toJSON()})}`);
    if(innerHeight-dock.height<230)issues.push('controls area too short');
    if(r.top<dock.bottom||r.bottom>innerHeight)issues.push(`button outside available area: ${r.top}..${r.bottom}, dock ${dock.bottom}, screen ${innerHeight}`);
    if(!button.contains(document.elementFromPoint(r.x+r.width/2,r.y+r.height/2)))issues.push('button obscured');
    return issues;
   }),{timeout:15000}).toEqual([]);
  };
  await checkLayout();
  await page.locator('[data-feature-action=balance_ball]').tap();
  await expect(page.locator('#task-status')).toHaveText(/任务完成|本轮未完成/,{timeout:30000});
  const before=(await(await page.request.get('/api/scenes/state?room=1')).json()).backend;
  expect(before.feature.status).toBe('completed');
  await page.locator('[data-feature-action=roll_forward]').tap();
  await expect.poll(async()=>{
   const f=(await(await page.request.get('/api/scenes/state?room=1')).json()).backend.feature;
   return f.results.filter(r=>r.action==='roll_forward'&&r.status==='completed').length;
  },{timeout:30000}).toBe(1);
  const after=(await(await page.request.get('/api/scenes/state?room=1')).json()).backend;
  expect(after.sim_time).toBeGreaterThan(before.sim_time+9.9);
  expect(after.feature.restarted).toBe(false);
  await expect(page.locator('#reset-feature')).toHaveCount(0);
  await checkLayout();
  await page.screenshot({path:info.outputPath('basketball-phone.png')});
  const canvas=page.locator('#physics-viewport canvas');await canvas.evaluate(el=>window.basketballCanvas=el);
  await page.setViewportSize({width:320,height:568});await checkLayout();
  await page.screenshot({path:info.outputPath('basketball-small-phone.png')});
  await page.setViewportSize({width:1440,height:1050});
  expect(await canvas.evaluate(el=>el===window.basketballCanvas)).toBe(true);
 }finally{await page.request.post('/api/scenes/close?room=1')}
});
});
