import {test,expect} from '@playwright/test';

test.use({isMobile:true,hasTouch:true,viewport:{width:390,height:844}});
const cases=[
 {page:'scenarios',views:['physics-viewport'],choose:'[data-scene=ball]',controls:['[data-sim-action=kick_left]','#connect-voice','#stop-scene']},
 {page:'studio',views:['physics-viewport'],choose:'[data-studio=director]',controls:['#studio-controls button:first-child','#connect-voice','#stop-studio']},
 {page:'demos',views:['demo-viewport'],choose:'[data-demo=stage]',controls:['#stage-gather','#stage-roll','#connect-voice']},
 {page:'balance',views:['baseline-viewport','physics-viewport'],controls:['#start-challenge','#connect-voice','#stop-balance']},
 {page:'seesaw',views:['baseline-viewport','trained-viewport'],controls:['[data-human-direction=forward]','#connect-voice','#start','#stop']},
];
async function checkVisible(page,views,control){
 await expect(page.locator('.mobile-stage-dock')).toBeVisible();
 await page.locator(control).evaluate(el=>el.scrollIntoView({block:'center'}));
 const height=page.viewportSize().height;
 for(const id of views){
  // WebKit rounds the canvas border to fractional pixels; check actual bounds too.
  await expect(page.locator(`#${id}`)).toBeInViewport({ratio:.99});
  const box=await page.locator(`#${id}`).boundingBox();expect(box.y).toBeGreaterThanOrEqual(-1);expect(box.y+box.height).toBeLessThanOrEqual(height+1);expect(box.height).toBeGreaterThan(85);
 }
 const target=page.locator(control);await expect(target).toBeInViewport({ratio:1});
 expect(await target.evaluate(el=>{const r=el.getBoundingClientRect(),hit=document.elementFromPoint(r.x+r.width/2,r.y+r.height/2);return el.contains(hit)?'reachable':`${el.id||el.dataset.simAction}: hit ${hit?.tagName}.${hit?.className} at ${r.x},${r.y}`})).toBe('reachable');
 const dock=await page.locator('.mobile-stage-dock').boundingBox();expect(dock.height).toBeLessThan(height*.45);
 expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBeLessThanOrEqual(page.viewportSize().width);
 expect(await page.evaluate(()=>innerWidth)).toBe(page.viewportSize().width);
}
for(const scene of cases)test(`${scene.page}: mobile scene stays visible beside controls and restores the same canvases on desktop`,async({page,request},info)=>{
 test.setTimeout(90000);const errors=[],loads=[];page.on('pageerror',e=>errors.push(e.message));
 const claim=await request.post('/api/rooms/claim'),{room}=await claim.json();expect(claim.ok()).toBe(true);
 expect((await request.post(`/api/scenes/close?room=${room}&if_unused=true`)).status()).toBe(204);
 page.on('request',r=>{if(/\/api\/scenes\/model\.|\/api\/(?:balance|seesaw)\/prepare/.test(r.url()))loads.push(r.url())});
 try{
  await page.goto(`/${scene.page}.html?room=${room}`);
  if(scene.page==='demos')await page.selectOption('#stage-play','interactive');
  if(scene.choose)await page.locator(scene.choose).click();
  await page.locator('.mobile-stage-dock').scrollIntoViewIfNeeded();
  for(const id of scene.views)await expect(page.locator(`#${id}`)).toHaveAttribute('data-rendered-scene',/\w/,{timeout:45000});
  if(scene.page==='demos')await page.locator('#stage-voice summary').click();
  await page.evaluate(ids=>window.sceneCanvases=ids.map(id=>document.getElementById(id).querySelector('canvas')),scene.views);
  const beforeLoads=loads.length,revision=(await(await request.get(`/api/scenes/state?room=${room}`)).json()).backend.revision;
  for(const viewport of [{width:390,height:844},{width:320,height:568}]){
   await page.setViewportSize(viewport);
   for(const control of scene.controls)await checkVisible(page,scene.views,control);
  }
  for(const language of ['en','fr','zh']){
   await page.locator('#lang-switch-button').click();await page.locator(`[data-lang=${language}]`).click();
   for(const control of scene.controls)await checkVisible(page,scene.views,control);
   const dock=page.locator('.mobile-stage-dock');expect(await dock.evaluate(el=>el.scrollWidth<=el.clientWidth)).toBe(true);
   for(const button of await dock.locator('.subtle-button').all()){
    const rect=await button.boundingBox(),outer=await dock.boundingBox();expect(rect.x).toBeGreaterThanOrEqual(outer.x);expect(rect.x+rect.width).toBeLessThanOrEqual(outer.x+outer.width);
   }
  }
  for(const viewport of [{width:667,height:375},{width:1440,height:1050}]){
   await page.setViewportSize(viewport);await expect(page.locator('.mobile-stage-dock')).toHaveCount(0);
  }
  for(const id of scene.views)expect(await page.locator(`#${id}`).evaluate(el=>!!el.closest('.scene-stage,.theatre-stage,.balance-stage,.seesaw-stage'))).toBe(true);
  await page.setViewportSize({width:390,height:844});await checkVisible(page,scene.views,scene.controls[0]);
  expect(await page.evaluate(ids=>ids.every((id,i)=>document.getElementById(id).querySelector('canvas')===window.sceneCanvases[i]),scene.views)).toBe(true);
  expect(loads.length).toBe(beforeLoads);
  expect((await(await request.get(`/api/scenes/state?room=${room}`)).json()).backend.revision).toBe(revision);
  await page.screenshot({path:info.outputPath(`${scene.page}-mobile-controls.png`)});
  // Verify an actual physical command while the controls and live view are both on screen.
  if(scene.page==='scenarios'){
   await page.locator('[data-sim-action=kick_left]').tap();await expect(page.locator('#action-result')).toContainText('左脚踢球 · 已完成',{timeout:15000});
   await expect(page.locator('#ball-contact')).toHaveText('左脚');
   await checkVisible(page,scene.views,'#stop-scene');await page.locator('#stop-scene').tap();
   await expect(page.locator('#action-result')).toContainText('停止 · 已完成');
  }
  expect(errors).toEqual([]);
 }catch(error){
  await page.screenshot({path:info.outputPath('layout-failure.png')});
  await info.attach('layout.json',{body:JSON.stringify(await page.evaluate(()=>({width:innerWidth,height:innerHeight,scrollY,overflow:[...document.querySelectorAll("body *")].filter(el=>el.getBoundingClientRect().right>document.documentElement.clientWidth+1&&!el.closest(".home-nav")).map(el=>({id:el.id,cls:el.className,text:el.textContent.slice(0,80)})),boxes:[...document.querySelectorAll('.mobile-stage-dock,[data-mobile-stage],#stage-gather,#studio-controls button')].map(el=>({id:el.id,cls:el.className,box:el.getBoundingClientRect().toJSON(),scrollTop:el.scrollTop}))}))),contentType:'application/json'});
  throw error;
 }finally{await page.close();await request.post(`/api/scenes/close?room=${room}`)}
});

test('dual-room demo keeps both live worlds visible at the stop button',async({page,request},info)=>{
 test.setTimeout(60000);
 const claim=await request.post('/api/rooms/claim'),{room}=await claim.json();expect(claim.ok()).toBe(true);
 // Short silent narration is only a playback fixture; both MuJoCo worlds are real.
 const wav=Buffer.alloc(44+3200);wav.write('RIFF');wav.writeUInt32LE(wav.length-8,4);wav.write('WAVE',8);wav.write('fmt ',12);wav.writeUInt32LE(16,16);wav.writeUInt16LE(1,20);wav.writeUInt16LE(1,22);wav.writeUInt32LE(16000,24);wav.writeUInt32LE(32000,28);wav.writeUInt16LE(2,32);wav.writeUInt16LE(16,34);wav.write('data',36);wav.writeUInt32LE(3200,40);
 await page.route('**/demo-audio/*.wav*',route=>route.fulfill({contentType:'audio/wav',body:wav}));
 try{
  await page.goto(`/demos.html?room=${room}`);
  const secondClaim=page.waitForResponse(r=>new URL(r.url()).pathname.endsWith('/api/rooms/claim')&&r.request().method()==='POST');
  await page.locator('[data-demo=duel]').click();const secondRoom=(await(await secondClaim).json()).room;expect(secondRoom).not.toBe(room);
  for(const id of ['demo-viewport','demo-second'])await expect(page.locator(`#${id}`)).toHaveAttribute('data-rendered-scene','ball',{timeout:45000});
  await checkVisible(page,['demo-viewport','demo-second'],'#stop-demo');
  await page.screenshot({path:info.outputPath('dual-room-mobile.png')});
  await page.locator('#stop-demo').tap();await expect(page.locator('#show-status')).toHaveText('演示已停止');
  await expect(page.locator('#demo-mode')).toBeEnabled({timeout:10000});
  // Stop acknowledges cancellation before asynchronous secondary-room release finishes.
  await expect.poll(async()=>((await(await request.get('/api/rooms')).json()).rooms.find(r=>r.id===secondRoom)?.physics??false)).toBe(false);
 }finally{await page.close();await request.post(`/api/scenes/close?room=${room}`)}
});
