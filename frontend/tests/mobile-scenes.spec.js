import {test,expect} from '@playwright/test';

// Keep API/network traces and explicit layout screenshots. Snapshotting the
// live WebGL DOM on every geometry read overwhelms CI's software renderer.
test.use({isMobile:true,hasTouch:true,viewport:{width:390,height:844},trace:{mode:'retain-on-failure',snapshots:false,screenshots:false}});
const cases=[
 {page:'scenarios',views:['physics-viewport'],choose:'[data-scene=ball]',controls:['[data-sim-action=kick_left]','#connect-voice','#stop-scene']},
 {page:'studio',views:['physics-viewport'],choose:'[data-studio=director]',controls:['#studio-controls button:first-child','#connect-voice','#stop-studio']},
 {page:'demos',views:['demo-viewport'],choose:'[data-demo=stage]',controls:['#stage-gather','#stage-roll','#connect-voice']},
 {page:'balance',views:['baseline-viewport','physics-viewport'],controls:['#start-challenge','#connect-voice','#stop-balance']},
 {page:'seesaw',views:['baseline-viewport','trained-viewport'],controls:['[data-human-direction=forward]','#connect-voice','#start','#stop']},
];
async function checkVisible(page,views,control){
 const viewport=page.viewportSize();
 // One atomic DOM sample avoids many automation/trace round trips while live
 // physics is drawing, and checks clipping, reachability and overflow together.
 await expect.poll(()=>page.evaluate(({views,control,viewport})=>{
  const issues=[],dock=document.querySelector('.mobile-stage-dock');
  if(!dock)return ['dock not ready'];
  const target=document.querySelector(control);target.scrollIntoView({block:'center'});
  const outer=dock.getBoundingClientRect();
  for(const id of views){
   const element=document.getElementById(id),r=element.getBoundingClientRect();
   const canvas=element.querySelector('canvas').getBoundingClientRect();
   if(r.y < -1||r.bottom>viewport.height+1||r.height<=85)issues.push(`${id}: outside viewport or too short`);
   if(canvas.height<Math.min(170,viewport.height*.20))issues.push(`${id}: render area too small`);
   const caption=element.querySelector('.physics-caption');
   if(caption&&canvas.bottom>caption.getBoundingClientRect().top+1)issues.push(`${id}: caption covers canvas`);
   if(r.left<outer.left-1||r.right>outer.right+1||r.top<outer.top-1||r.bottom>outer.bottom+1)issues.push(`${id}: clipped by dock`);
  }
  const r=target.getBoundingClientRect();
  if(r.top<0||r.bottom>viewport.height||r.left<0||r.right>viewport.width)issues.push(`${control}: outside viewport`);
  if(!target.contains(document.elementFromPoint(r.x+r.width/2,r.y+r.height/2)))issues.push(`${control}: obscured`);
  if(outer.height>viewport.height*.51||viewport.height-outer.height<230)issues.push('not enough room for controls');
  if(document.documentElement.scrollWidth>viewport.width||innerWidth!==viewport.width)issues.push('page overflow');
  return issues;
 },{views,control,viewport})).toEqual([]);
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
   expect(await page.evaluate(()=>{
    const dock=document.querySelector('.mobile-stage-dock'),outer=dock.getBoundingClientRect();
    return dock.scrollWidth<=dock.clientWidth&&[...dock.querySelectorAll('.subtle-button')].every(button=>{const r=button.getBoundingClientRect();return r.x>=outer.x&&r.right<=outer.right});
   })).toBe(true);
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
 // Keep narration interruptible long enough for layout sampling on software
 // renderers. Both MuJoCo worlds are real; production audio is unchanged.
 const wav=Buffer.alloc(44+3200);wav.write('RIFF');wav.writeUInt32LE(wav.length-8,4);wav.write('WAVE',8);wav.write('fmt ',12);wav.writeUInt32LE(16,16);wav.writeUInt16LE(1,20);wav.writeUInt16LE(1,22);wav.writeUInt32LE(16000,24);wav.writeUInt32LE(32000,28);wav.writeUInt16LE(2,32);wav.writeUInt16LE(16,34);wav.write('data',36);wav.writeUInt32LE(3200,40);
 const heldNarration=Buffer.alloc(44+16000*2*15);wav.copy(heldNarration,0,0,44);
 heldNarration.writeUInt32LE(heldNarration.length-8,4);heldNarration.writeUInt32LE(heldNarration.length-44,40);
 await page.route('**/demo-audio/*.wav*',route=>route.fulfill({contentType:'audio/wav',body:/\/duel-(left|right|end)\.wav$/.test(new URL(route.request().url()).pathname)?heldNarration:wav}));
 try{
  await page.goto(`/demos.html?room=${room}`);
  const secondClaim=page.waitForResponse(r=>new URL(r.url()).pathname.endsWith('/api/rooms/claim')&&r.request().method()==='POST');
  await page.locator('[data-demo=duel]').click();const secondRoom=(await(await secondClaim).json()).room;expect(secondRoom).not.toBe(room);
  for(const id of ['demo-viewport','demo-second'])await expect(page.locator(`#${id}`)).toHaveAttribute('data-rendered-scene','ball',{timeout:45000});
  await checkVisible(page,['demo-viewport','demo-second'],'#stop-demo');
  await page.screenshot({path:info.outputPath('dual-room-mobile.png')});
  await expect(page.locator('#demo-notice')).toBeHidden();await expect(page.locator('#stop-demo')).toBeEnabled();
  await page.locator('#stop-demo').tap();await expect(page.locator('#show-status')).toHaveText('演示已停止');
  // Mode selection re-enables immediately; stage selection waits for the actual
  // cancellation/renderer disposal/secondary-room release to finish.
  await expect(page.locator('#stage-play')).toBeEnabled({timeout:10000});
  await expect.poll(async()=>((await(await request.get('/api/rooms')).json()).rooms.find(r=>r.id===secondRoom)?.physics??false)).toBe(false);
 }finally{await page.close();await request.post(`/api/scenes/close?room=${room}`)}
});
