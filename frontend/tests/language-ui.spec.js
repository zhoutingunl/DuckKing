import {test,expect} from '@playwright/test';

const pages=['index','features','training','balance','seesaw','scenarios','demos','studio','experience','statistics','deploys'];
for(const [language,mobile] of [['fr',false],['en',false],['de',false],['de',true],['es',false],['es',true]])test(`${language}${mobile?' mobile':''}: every page localizes visible interface and dynamic state`,async({page})=>{
 test.setTimeout(90000);
 if(mobile)await page.setViewportSize({width:412,height:839});
 const errors=[];page.on('pageerror',e=>errors.push(e.message));
 // Exercise visible conflict recovery copy without starting three physical worlds.
 // Actual model/action lifecycle is covered in the dedicated scene tests.
 await page.request.post('/api/scenes/close?room=1');
 for(const endpoint of ['balance','seesaw','features']){
  const message=endpoint==='features'?'本房间已有场景，请切换或新建房间。':`本房间已有其他场景。点击“切换为${endpoint==='balance'?'圆盘':'跷跷板'}”会结束原场景；也可新建房间。`;
  await page.route(`**/api/${endpoint}/prepare?*`,route=>route.fulfill({status:409,json:{detail:{code:'scene_conflict',message}}}));
 }
 for(const name of pages){
  await page.goto(`/${name}.html?room=1&lang=${language}`);
  await expect(page.locator('html')).toHaveAttribute('lang',language);
  await expect(page.locator('#lang-switch-button')).toHaveText({fr:'Langue',en:'Language',de:'Sprache',es:'Idioma'}[language]);
  await expect(page.locator('.home-nav a')).toHaveCount(10);
  // A genuine server state update must not reintroduce Chinese between frames.
  if(name==='index'){
   await expect(page.locator('#data-source')).toHaveText({fr:'Non connecté',en:'Not connected',de:'Nicht verbunden',es:'Sin conexión'}[language]);
   const frames=await page.evaluate(()=>new Promise(resolve=>{
    const values=[];const sample=()=>{values.push(document.querySelector('#data-source').textContent);if(values.length<35)requestAnimationFrame(sample);else resolve(values)};sample();
   }));
   expect(new Set(frames)).toEqual(new Set([{fr:'Non connecté',en:'Not connected',de:'Nicht verbunden',es:'Sin conexión'}[language]]));
  }
  // Authored transcripts, equations/code and language names are content, not UI.
  const missing=await page.evaluate(()=>{
   const result=[],walker=document.createTreeWalker(document.body,NodeFilter.SHOW_TEXT);
   for(let n=walker.nextNode();n;n=walker.nextNode()){
    const p=n.parentElement;if(p.closest('script,style,code,pre,[translate="no"],[data-user-content],[role="log"],.lang-menu'))continue;
    if(p.checkVisibility({visibilityProperty:true})&&/\p{Script=Han}/u.test(n.nodeValue))result.push(n.nodeValue.trim());
   }return result;
  });
  expect(missing,`${name} untranslated UI`).toEqual([]);
  if(mobile)expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),`${name} horizontal overflow`).toBe(true);
  // Reverse translation must work on existing nodes, without a page reload.
  await page.locator('#lang-switch-button').click();
  await page.locator('[role=menuitem][data-lang=zh]').click();
  await expect(page.locator('.nav-destinations a').first()).toHaveText('首页');
  await expect(page.locator('#lang-switch-button')).toHaveText('语言');
  await page.locator('#lang-switch-button').click();
  await page.locator(`[role=menuitem][data-lang=${language}]`).click();
  await expect(page.locator('.nav-destinations a').first()).toHaveText({fr:'Accueil',en:'Home',de:'Startseite',es:'Inicio'}[language]);
  await expect(page.locator('#lang-switch-button')).toHaveText({fr:'Langue',en:'Language',de:'Sprache',es:'Idioma'}[language]);
 }
 expect(errors).toEqual([]);
});

for(const language of ['fr','en','de','es'])test(`${language}: voice handshake and changing voice states keep one interface language`,async({page,context})=>{
 await context.grantPermissions(['microphone']);
 const commands=[];let channel;
 await page.routeWebSocket('**/voice',socket=>{
  channel=socket;socket.onMessage(raw=>{
   if(typeof raw!=='string')return;const data=JSON.parse(raw);commands.push(data);
   if(data.type==='join_room')socket.send(JSON.stringify({type:'voice_status',state:'disconnected'}));
   if(data.type==='connect')socket.send(JSON.stringify({type:'voice_status',state:'ready',mode:'cloud',language}));
  });
 });
 await page.goto(`/index.html?view=preview&room=1&lang=${language}`);
 await page.locator('#connect-voice').click();
 await expect(page.locator('#talk-button')).toBeEnabled();
 expect(commands.find(x=>x.type==='connect')).toMatchObject({language,mode:'cloud'});
 for(const state of ['listening','thinking','speaking','ready']){
  channel.send(JSON.stringify({type:'voice_status',state,mode:'cloud',language}));
  await expect(page.locator('#voice-badge')).not.toHaveText(/[\u4e00-\u9fff]/);
  await expect(page.locator('#data-source')).toHaveText({fr:'Aperçu local',en:'Local preview',de:'Lokale Vorschau',es:'Vista previa local'}[language]);
 }
 channel.send(JSON.stringify({type:'transcript',role:'user',text:'点点头'}));
 await expect(page.locator('#activity-log')).toContainText('点点头');
});

test('missing language connection exits preparation and leaves a visible translated error',async({page})=>{
 await page.goto('/index.html?view=preview&room=1&lang=fr');
 await page.locator('#connect-voice').click();
 await expect(page.locator('#voice-badge')).toHaveText('Erreur de connexion');
 await expect(page.locator('#talk-button')).toBeDisabled();
 await expect(page.locator('#notice')).not.toHaveText(/[\u4e00-\u9fff]/);
 await expect(page.locator('#connect-voice')).toBeEnabled();
});

for(const language of ['fr','en','de','es'])for(const scene of ['balance','seesaw'])test(`${language}: ${scene} scene conflict stays localized and requires an explicit switch`,async({page})=>{
 const name=scene==='balance'?'圆盘':'跷跷板';
 const message=`本房间已有其他场景。点击“切换为${name}”会结束原场景；也可新建房间。`;
 await page.route(`**/api/${scene}/prepare?*`,route=>route.fulfill({status:409,json:{detail:{code:'scene_conflict',message}}}));
 await page.goto(`/${scene}.html?room=1&lang=${language}`);
 await expect(page.locator('#notice')).toBeVisible();
 await expect(page.locator('#notice')).toContainText({fr:'Un autre scénario',en:'Another scene',de:'In diesem Raum ist bereits eine andere Szene',es:/ya hay otra escena/i}[language]);
 await expect(page.locator('#notice')).not.toHaveText(/[\u4e00-\u9fff]/);
 await expect(page.locator('#connect-voice')).toBeDisabled();
 await expect(page.locator(scene==='balance'?'#prepare-balance':'#prepare')).toBeEnabled();
});
