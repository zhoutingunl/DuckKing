import {test,expect} from '@playwright/test';

test.use({isMobile:true,hasTouch:true,viewport:{width:390,height:844},trace:{mode:'retain-on-failure',snapshots:false,screenshots:false}});

// Synthetic short narration; backend state, music, cancellation and MuJoCo remain real.
function narration(){
 const b=Buffer.alloc(44+3200);b.write('RIFF');b.writeUInt32LE(b.length-8,4);b.write('WAVE',8);b.write('fmt ',12);b.writeUInt32LE(16,16);b.writeUInt16LE(1,20);b.writeUInt16LE(1,22);b.writeUInt32LE(16000,24);b.writeUInt32LE(32000,28);b.writeUInt16LE(2,32);b.writeUInt16LE(16,34);b.write('data',36);b.writeUInt32LE(3200,40);return b;
}

for(const prior of ['running','failed-then-stopped'])test(`director to demos: ${prior} world is replaced and subsequent shows can play`,async({page,request})=>{
 test.setTimeout(120000);
 const errors=[];page.on('pageerror',error=>errors.push(error.message));
 await page.route('**/demo-audio/*.wav*',route=>route.fulfill({contentType:'audio/wav',body:narration()}));
 await request.post('/api/scenes/close?room=1');
 try{
  await page.goto('/features.html?room=1&feature=director&lang=zh');
  const conduct=page.locator('[data-feature-action=conduct]');await expect(conduct).toBeEnabled({timeout:45000});
  await page.locator('#feature-order').fill('A B C D');await conduct.tap();
  // Observe an actual solo, rather than navigating during request acceptance/preparation.
  await expect.poll(async()=>{
   const {backend}=await(await request.get('/api/scenes/state?room=1')).json();
   return backend.feature.status==='running'&&backend.seated_choir?.phase==='solo'&&backend.seated_choir.music_started;
  },{timeout:25000}).toBe(true);
  const previous=(await(await request.get('/api/scenes/state?room=1')).json()).backend.revision;
  if(prior==='failed-then-stopped'){
   // Recreate the old failed generic-command state without weakening the feature tool guard.
   const wrong=await request.post('/api/scenes/actions?room=1',{data:{name:'scene_ball'}});
   expect(wrong.status()).toBe(202);const {id}=await wrong.json();
   await expect.poll(async()=>await(await request.get(`/api/scenes/actions/${id}?room=1`)).json()).toMatchObject({status:'failed',error:'请使用当前功能场景工具'});
   await page.locator('#stop-feature').tap();
   await expect(page.locator('#task-status')).toHaveText('任务已取消');
  }
  await page.getByRole('link',{name:'演示场景',exact:true}).click();
  await expect(page).toHaveURL(/demos\.html\?room=1/);
  for(const demo of ['identity','football']){
   await page.locator(`[data-demo=${demo}]`).tap();
   await expect.poll(async()=>{
    if(await page.locator('#demo-notice').isVisible())throw Error(await page.locator('#demo-notice').textContent());
    return page.locator('#show-status').textContent();
   },{timeout:45000}).toBe('本幕完成 · 可重演或进入下一幕');
   const proof=JSON.parse(await page.locator('#theatre-result').textContent());
   expect(proof.scene).toBe(demo);expect(proof.results.some(r=>r.status==='completed')).toBe(true);
   const state=await(await request.get('/api/scenes/state?room=1')).json();
   expect(state.backend.scene).toBe('ball');expect(state.backend.revision).not.toBe(previous);
   expect(state.backend.feature).toBeUndefined();expect(state.error).toBeNull();
  }
  expect(errors).toEqual([]);
 }finally{await page.close();await request.post('/api/scenes/close?room=1')}
});
