import {test,expect} from '@playwright/test';

test.use({trace:{mode:'retain-on-failure',snapshots:false,screenshots:false}});
function narration(){
 const b=Buffer.alloc(44+3200);b.write('RIFF');b.writeUInt32LE(b.length-8,4);b.write('WAVE',8);b.write('fmt ',12);b.writeUInt32LE(16,16);b.writeUInt16LE(1,20);b.writeUInt16LE(1,22);b.writeUInt32LE(16000,24);b.writeUInt32LE(32000,28);b.writeUInt16LE(2,32);b.writeUInt16LE(16,34);b.write('data',36);b.writeUInt32LE(3200,40);return b;
}
async function playIdentity(page){
 await page.locator('[data-demo=identity]').click();
 await expect.poll(async()=>{
  if(await page.locator('#demo-notice').isVisible())throw Error(await page.locator('#demo-notice').textContent());
  return page.locator('#show-status').textContent();
 },{timeout:45000}).toBe('本幕完成 · 可重演或进入下一幕');
 const proof=JSON.parse(await page.locator('#theatre-result').textContent());
 const nod=proof.results.find(r=>r.name==='nod');expect(nod.status).toBe('completed');return nod.id;
}
for(const device of [
 {name:'desktop',viewport:{width:1440,height:1050},isMobile:false,hasTouch:false},
 {name:'phone',viewport:{width:412,height:839},isMobile:true,hasTouch:true},
])test.describe(device.name,()=>{
 test.use({viewport:device.viewport,isMobile:device.isMobile,hasTouch:device.hasTouch});
 test('director → real show → return and confirm stop → replay in the same room',{tag:'@journey'},async({page,request})=>{
  test.setTimeout(180000);const errors=[],prepares=[];page.on('pageerror',e=>errors.push(e.message));
  page.on('request',r=>{if(new URL(r.url()).pathname==='/api/features/prepare')prepares.push(r.url())});
  await page.route('**/demo-audio/*.wav*',route=>route.fulfill({contentType:'audio/wav',body:narration()}));
  await request.post('/api/scenes/close?room=1');
  try{
   await page.goto('/features.html?room=1&feature=director&lang=zh');
   await expect(page.locator('[data-feature-action=conduct]')).toBeEnabled({timeout:45000});
   await page.locator('#feature-order').fill('A B C D');await page.locator('[data-feature-action=conduct]').click();
   await expect.poll(async()=>{
    const b=(await(await request.get('/api/scenes/state?room=1')).json()).backend;
    return b.feature.status==='running'&&b.seated_choir?.music_started;
   },{timeout:25000}).toBe(true);
   await page.getByRole('link',{name:'演示场景',exact:true}).click();const firstNod=await playIdentity(page);
   const before=(await(await request.get('/api/scenes/state?room=1')).json()).backend;
   const beforePrepare=prepares.length;
   await page.getByRole('link',{name:'首页',exact:true}).click();
   await expect(page.locator('#task-status')).toHaveText('场景已切换');
   await expect(page.locator('#scene-placeholder')).toContainText('可停止房间任务');
   await expect(page.locator('#scene-placeholder')).not.toHaveClass(/loading-feedback/);
   await expect(page.locator('#sim-status')).toHaveText('所选功能未准备');
   await expect(page.locator('#stop-feature')).toBeEnabled();
   await expect(page.locator('[data-feature-action=conduct]')).toBeDisabled();
   const accepted=page.waitForResponse(r=>r.request().method()==='POST'&&new URL(r.url()).pathname==='/api/scenes/actions'&&r.request().postDataJSON()?.name==='stop');
   await page.locator('#stop-feature').click();const response=await accepted;
   expect(response.status()).toBe(202);expect(new URL(response.url()).searchParams.get('expected_revision')).toBe(before.revision);
   const {id}=await response.json();
   await expect(page.locator('#task-status')).toHaveText('任务已停止');
   expect((await(await request.get(`/api/scenes/actions/${id}?room=1`)).json()).status).toBe('completed');
   await expect(page.locator('#scene-placeholder')).toContainText('当前房间任务已停止');
   await expect(page.locator('#notice')).toBeHidden();expect(prepares.length).toBe(beforePrepare);
   const stopped=await(await request.get('/api/scenes/state?room=1')).json();
   expect(stopped.backend.revision).toBe(before.revision);expect(stopped.backend.scene).toBe('ball');expect(stopped.action).toBeNull();
   await page.getByRole('link',{name:'演示场景',exact:true}).click();
   const secondNod=await playIdentity(page);expect(secondNod).not.toBe(firstNod);
   expect(new URL(page.url()).searchParams.get('room')).toBe('1');expect(errors).toEqual([]);
  }finally{await page.close();await request.post('/api/scenes/close?room=1')}
 });
});

test('return-page stop failure remains actionable and only a real retry confirms success',async({page,request})=>{
 test.setTimeout(45000);await request.post('/api/scenes/close?room=1');
 const start=await request.post('/api/scenes/start?room=1',{data:{name:'scene_ball'}});expect(start.status()).toBe(202);
 const preparations=[];page.on('request',r=>{if(new URL(r.url()).pathname==='/api/features/prepare')preparations.push(r.url())});
 try{
  await page.goto('/features.html?room=1&feature=director&lang=zh');
  await expect(page.locator('#stop-feature')).toBeEnabled();
  await page.route('**/api/scenes/actions?*',route=>route.fulfill({status:503,json:{detail:'Controlled stop failure'}}));
  await page.locator('#stop-feature').click();
  await expect(page.locator('#task-status')).toHaveText('停止未确认');
  await expect(page.locator('#notice')).toContainText('请重试停止任务');
  await expect(page.locator('#stop-feature')).toBeEnabled();
  await expect(page.locator('#scene-placeholder')).not.toHaveClass(/loading-feedback/);
  await page.unroute('**/api/scenes/actions?*');await page.locator('#stop-feature').click();
  await expect(page.locator('#task-status')).toHaveText('任务已停止');
  expect(preparations).toEqual([]);
  // A newer task in another page clears the confirmation; stopping cancels it.
  const walk=await request.post('/api/scenes/actions?room=1',{data:{name:'walk',duration:3}});const {id}=await walk.json();
  await expect(page.locator('#task-status')).toHaveText('当前房间任务执行中');
  await page.locator('#stop-feature').click();await expect(page.locator('#task-status')).toHaveText('任务已停止');
  expect((await(await request.get(`/api/scenes/actions/${id}?room=1`)).json()).status).toBe('cancelled');
 }finally{await page.close();await request.post('/api/scenes/close?room=1')}
});
