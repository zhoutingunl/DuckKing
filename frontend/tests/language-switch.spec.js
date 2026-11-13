import {test,expect} from '@playwright/test';

async function choose(page,language){
 await page.locator('#lang-switch-button').click();
 await page.locator(`[role=menuitem][data-lang=${language}]`).click();
 await expect(page.locator('html')).toHaveAttribute('lang',language==='zh'?'zh-CN':language);
 await expect(page.locator('.lang-menu')).toBeHidden();
}
async function localModes(page){
 await page.route('**/api/voice/modes*',route=>route.fulfill({json:{local_first:true,available:true}}));
}

test('language cycles preserve the document, canvas, room and canonical status logs',async({page,request})=>{
 test.setTimeout(60000);
 await localModes(page);
 // CI shares the preview room with earlier cases. Reproduce a completed
 // historical action so it cannot accidentally satisfy this round's wait.
 const prior=await request.post('/api/actions?room=1',{data:{name:'stop',request_id:crypto.randomUUID()}});
 expect(prior.ok()).toBe(true);
 let modelRequests=0;
 page.on('request',request=>{if(/(?:model|manifest|\.dkm|\.glb)/.test(request.url()))modelRequests++});
 await page.goto('/index.html?room=1&lang=zh&measurement=verification#duck');
 await expect(page.locator('#data-source')).toHaveText('本地预览');
 await expect(page.locator('#voice-mode')).toBeEnabled();
 await page.evaluate(()=>{window.originalCanvas=document.querySelector('#viewport canvas');window.originalDocument=document;});
 await expect(page.locator('#activity-log')).toContainText('stop · completed');
 await expect(page.locator('#viewport')).toHaveAttribute('data-model','official',{timeout:45000});
 await page.locator('#clear-log').click();
 await page.locator('[data-action=nod]').click();
 // Wait for this action's exact terminal record, not any old “completed” row.
 await expect(page.locator('.action-diagnostics code')).toHaveText(['开始动作 · nod','nod · completed']);
 const raw=await page.locator('.action-diagnostics code').allTextContents();
 const count=modelRequests;
 for(const [lang,source,action,diagnostic] of [['fr','Aperçu local','Début du mouvement','Diagnostic'],['en','Local preview','Starting action','Diagnostics'],['zh','本地预览','开始动作','诊断详情']]){
  await choose(page,lang);
  await expect(page.locator('#data-source')).toHaveText(source);
  await expect(page.locator('#activity-log')).toContainText(action);
  await expect(page.locator('.action-diagnostics summary').first()).toHaveText(diagnostic);
  expect(await page.locator('.action-diagnostics code').allTextContents()).toEqual(raw);
  expect(await page.evaluate(()=>document===window.originalDocument&&document.querySelector('#viewport canvas')===window.originalCanvas)).toBe(true);
  expect(new URL(page.url()).searchParams.get('room')).toBe('1');
  expect(new URL(page.url()).searchParams.get('measurement')).toBe('verification');
  expect(new URL(page.url()).hash).toBe('#duck');
  expect(modelRequests).toBe(count);
  if(lang==='en')await expect(page.locator('h1')).toHaveText('Say one sentence, make it an action.');
 }
});

test('temporary language and scene restrictions never overwrite the preferred voice mode',async({page})=>{
 await localModes(page);
 await page.goto('/index.html?room=1&lang=zh');
 await expect(page.locator('#voice-mode')).toBeEnabled();
 await page.selectOption('#voice-mode','local_first');
 for(const lang of ['fr','en']){
  await choose(page,lang);
  await expect(page.locator('#voice-mode')).toHaveValue('cloud');
  await expect(page.locator('#voice-language-hint')).toBeVisible();
  await expect(page.locator('#voice-language-hint')).not.toHaveText(/[\u4e00-\u9fff]/);
  expect(await page.evaluate(()=>sessionStorage.getItem('duckking.voice-mode'))).toBe('local_first');
 }
 await choose(page,'zh');
 await expect(page.locator('#voice-mode')).toHaveValue('local_first');
 await expect(page.locator('#voice-language-hint')).toBeHidden();
 await page.goto('/studio.html?room=1');
 await expect(page.locator('#voice-mode')).toBeEnabled();
 await expect(page.locator('#voice-mode')).toHaveValue('cloud');
 expect(await page.evaluate(()=>sessionStorage.getItem('duckking.voice-mode'))).toBe('local_first');
 await page.goto('/index.html?room=1');
 await expect(page.locator('#voice-mode')).toHaveValue('local_first');
 await page.selectOption('#voice-mode','cloud');
 await choose(page,'fr');await choose(page,'zh');
 await expect(page.locator('#voice-mode')).toHaveValue('cloud');
});

test('switching language cancels capture and old voice frames; reconnect uses the new language',async({page,context})=>{
 await context.grantPermissions(['microphone']);
 await localModes(page);
 const commands=[],channels=[];
 await page.routeWebSocket('**/voice',socket=>{
  channels.push(socket);socket.onMessage(raw=>{
   if(typeof raw!=='string')return;
   const data=JSON.parse(raw);commands.push(data);
   if(data.type==='connect')socket.send(JSON.stringify({type:'voice_status',state:'ready',mode:data.mode}));
  });
 });
 await page.goto('/index.html?room=1&lang=zh');
 await expect(page.locator('#voice-mode')).toBeEnabled();
 await page.selectOption('#voice-mode','cloud');
 await page.locator('#connect-voice').click();
 await expect(page.locator('#talk-button')).toBeEnabled();
 channels[0].send(JSON.stringify({type:'transcript',role:'user',text:'点点头'}));
 channels[0].send(JSON.stringify({type:'transcript',role:'assistant',text:'你好，我是灵矽。'}));
 await expect(page.locator('#activity-log')).toContainText('你好，我是灵矽。');
 // A programmatic pointer starts capture without hiding the language menu.
 await page.locator('#talk-button').dispatchEvent('pointerdown',{pointerId:1});
 await expect.poll(()=>commands.some(x=>x.type==='listen_start')).toBe(true);
 await choose(page,'fr');
 await expect(page.locator('#talk-button')).toBeDisabled();
 await expect(page.locator('#notice')).toContainText('Langue de conversation modifiée');
 expect(commands.some(x=>x.type==='disconnect')).toBe(true);
 expect(commands.some(x=>x.type==='listen_stop')).toBe(false);
 expect(commands.filter(x=>x.type==='connect')).toHaveLength(1);
 await expect(page.locator('#activity-log')).toContainText('点点头');
 await expect(page.locator('#activity-log')).toContainText('你好，我是灵矽。');
 // Late messages from the old transport cannot enable recording again.
 channels[0].send(JSON.stringify({type:'voice_status',state:'ready',mode:'cloud'}));
 await page.locator('#connect-voice').click();
 await expect(page.locator('#talk-button')).toBeEnabled();
 await expect(page.locator('#notice')).toBeHidden();
 expect(commands.filter(x=>x.type==='connect')).toEqual([
  {type:'connect',mode:'cloud',language:'zh'},{type:'connect',mode:'cloud',language:'fr'},
 ]);
 // A cloud idle close must not reset the next connection to Chinese.
 channels[1].close();
 await expect(page.locator('#connect-voice')).toHaveAttribute('data-state','disconnected');
 await page.locator('#connect-voice').click();
 await expect(page.locator('#talk-button')).toBeEnabled();
 expect(commands.filter(x=>x.type==='connect').at(-1)).toEqual({type:'connect',mode:'cloud',language:'fr'});
 await choose(page,'en');
 await expect(page.locator('#talk-button')).toBeDisabled();
 await expect(page.locator('#activity-log')).toContainText('你好，我是灵矽。');
});

for(const state of ['connecting','ready','speaking'])test(`language change disconnects ${state} without auto-reconnecting`,async({page,context})=>{
 await context.grantPermissions(['microphone']);await localModes(page);
 const commands=[];let channel;
 await page.routeWebSocket('**/voice',socket=>{channel=socket;socket.onMessage(raw=>{
  if(typeof raw!=='string')return;const data=JSON.parse(raw);commands.push(data);
  if(data.type==='connect')socket.send(JSON.stringify({type:'voice_status',state,language:'zh'}));
 })});
 await page.goto('/index.html?room=1&lang=zh');await expect(page.locator('#voice-mode')).toBeEnabled();
 await page.selectOption('#voice-mode','cloud');await page.locator('#connect-voice').click();
 await expect.poll(()=>commands.filter(x=>x.type==='connect').length).toBe(1);
 await expect(page.locator('#connect-voice')).toHaveAttribute('data-state',state);
 await choose(page,'fr');
 await expect(page.locator('#connect-voice')).toHaveAttribute('data-state','disconnected');
 await expect(page.locator('#talk-button')).toBeDisabled();
 await expect.poll(()=>commands.filter(x=>x.type==='disconnect').length).toBe(1);
 channel.send(JSON.stringify({type:'voice_status',state:'ready',language:'zh'}));
 channel.send(JSON.stringify({type:'transcript',role:'assistant',text:'obsolete-language-reply'}));
 await expect(page.locator('#activity-log')).not.toContainText('obsolete-language-reply');
 await expect(page.locator('#connect-voice')).toHaveAttribute('data-state','disconnected');
 expect(commands.filter(x=>x.type==='connect')).toHaveLength(1);
});

test('connection waiting shows real stage and elapsed time, cancels cleanly and resets on retry',async({page})=>{
 const commands=[];let channel;
 await page.routeWebSocket('**/voice',socket=>{channel=socket;socket.onMessage(raw=>{if(typeof raw==='string')commands.push(JSON.parse(raw))})});
 await page.goto('/index.html?room=1&lang=en');
 await page.locator('#connect-voice').click();
 const progress=page.locator('#voice-connection-progress');
 await expect(progress).toContainText('Waiting for the voice service');
 await expect(progress).toContainText(/[1-9]\d* s/,{timeout:5000});
 await expect(page.locator('#connect-voice')).toBeEnabled();
 await page.locator('#connect-voice').click();
 await expect(progress).toBeHidden();
 expect(commands.some(x=>x.type==='disconnect')).toBe(true);
 channel.send(JSON.stringify({type:'voice_status',state:'disconnected'}));
 await expect(page.locator('#connect-voice')).toBeEnabled();
 await page.locator('#connect-voice').click();
 await expect(progress).toContainText('0 s');
 channel.send(JSON.stringify({type:'error',message:'英语对话尚未配置，请联系管理员启用；不会自动切换成中文。'}));
 await expect(page.locator('#voice-badge')).toHaveText('Connection error');
 await expect(progress).toBeHidden();
 await expect(page.locator('#talk-button')).toBeDisabled();
 await expect(page.locator('#connect-voice')).toBeEnabled();
});

test('prepared MuJoCo scene keeps both canvases and translates painted labels without preparing again',async({page,request})=>{
 test.setTimeout(60000);
 await page.addInitScript(()=>{
  window.paintedLabels=[];
  const fill=CanvasRenderingContext2D.prototype.fillText;
  CanvasRenderingContext2D.prototype.fillText=function(text,...args){window.paintedLabels.push(text);return fill.call(this,text,...args)};
 });
 let prepares=0,models=0;
 page.on('request',r=>{if(r.url().includes('/api/balance/prepare'))prepares++;if(r.url().includes('model.dkm'))models++});
 await page.goto('/balance.html?room=2&lang=zh');
 await page.locator('#prepare-balance').click();
 await expect(page.locator('#start-challenge')).toBeEnabled({timeout:45000});
 await page.locator('[data-level="2"]').click();
 await expect(page.locator('#physics-viewport')).toHaveAttribute('data-heading-target','world:+X',{timeout:30000});
 await expect(page.locator('#start-challenge')).toBeEnabled();
 await page.evaluate(()=>{window.originalViews=[document.querySelector('#physics-viewport canvas'),document.querySelector('#baseline-viewport canvas')];window.paintedLabels=[]});
 const counts={prepares,models};
 await choose(page,'fr');
 await expect.poll(()=>page.evaluate(()=>window.paintedLabels)).toContain('Après entraînement');
 await expect.poll(()=>page.evaluate(()=>window.paintedLabels)).toContain('Non entraîné');
 expect(await page.evaluate(()=>window.paintedLabels.some(text=>/[\u4e00-\u9fff]/.test(text)))).toBe(false);
 expect(await page.evaluate(()=>window.originalViews[0]===document.querySelector('#physics-viewport canvas')&&window.originalViews[1]===document.querySelector('#baseline-viewport canvas'))).toBe(true);
 expect({prepares,models}).toEqual(counts);
 const state=(await(await request.get('/api/scenes/state?room=2')).json()).backend;
 expect(state.balance.phase).toBe('idle');
 await page.evaluate(()=>{window.paintedLabels=[]});
 await choose(page,'zh');
 await expect.poll(()=>page.evaluate(()=>window.paintedLabels)).toContain('目标朝向');
 expect({prepares,models}).toEqual(counts);
});

test('voice profiles follow the new language and stale or failed requests cannot restore old choices',async({page})=>{
 test.setTimeout(60000);
 let delayedFrench,frenchRequests=0;
 await page.route('**/api/voice/profiles?*',async route=>{
  const lang=new URL(route.request().url()).searchParams.get('language');
  if(lang==='fr'){
   if(++frenchRequests===1){delayedFrench=route;return}
   await route.fulfill({status:503,json:{detail:'暂时无法连接服务，请稍后重试。'}});return;
  }
  await route.fulfill({json:{voices:[{key:lang,label:lang+' voice'}],personas:[]}});
 });
 await page.goto('/studio.html?room=1&lang=zh');
 await page.locator('[data-studio="voice"]').click();
 await expect(page.locator('#voice-profile')).toHaveValue('zh',{timeout:45000});
 await choose(page,'fr');
 await expect.poll(()=>!!delayedFrench).toBe(true);
 await expect(page.locator('#voice-profile')).toBeDisabled();
 await choose(page,'en');
 await expect(page.locator('#voice-profile')).toHaveValue('en');
 await delayedFrench.fulfill({json:{voices:[{key:'fr',label:'old French voice'}],personas:[]}});
 await expect(page.locator('#voice-profile')).toHaveValue('en');
 await choose(page,'fr');
 await expect(page.locator('#notice')).toBeVisible();
 await expect(page.locator('#voice-profile')).toBeDisabled();
 await expect(page.locator('#voice-profile option')).toHaveCount(0);
 await expect(page.locator('#apply-voice')).toBeDisabled();
});
