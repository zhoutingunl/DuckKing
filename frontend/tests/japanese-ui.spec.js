import {test,expect} from '@playwright/test';
import {translate} from '../src/ui-language.js';
const pages=['index','features','training','balance','seesaw','scenarios','demos','studio','experience','statistics','deploys'];
async function switchLanguage(page,language){await page.locator('#lang-switch-button').click();await page.locator(`[data-lang=${language}]`).click();await expect(page.locator('html')).toHaveAttribute('lang',language);}
async function fixturePreparation(page){
 // Translation-only conflict fixtures avoid claiming physics or Linx evidence.
 for(const endpoint of ['balance','seesaw','features']){
  const message=endpoint==='features'?'本房间已有场景，请切换或新建房间。':`本房间已有其他场景。点击“切换为${endpoint==='balance'?'圆盘':'跷跷板'}”会结束原场景；也可新建房间。`;
  await page.route(`**/api/${endpoint}/prepare?*`,route=>route.fulfill({status:409,json:{detail:{code:'scene_conflict',message}}}));
 }
}
async function untranslated(page){
 const texts=await page.evaluate(()=>{const result=[],walker=document.createTreeWalker(document.body,NodeFilter.SHOW_TEXT);for(let n=walker.nextNode();n;n=walker.nextNode()){const p=n.parentElement;if(p.closest('script,style,code,pre,[translate="no"],[data-user-content],[role="log"],.activity-log,.lang-menu'))continue;if(p.checkVisibility({visibilityProperty:true})&&n.nodeValue.trim())result.push(n.nodeValue.trim());}return result;});
 return texts.filter(t=>translate(t,'ja')!==t||/[这们语场间显识连启设线录预试页鸭请]/.test(t));
}
test('Japanese localizes all page interfaces and dynamic labels',async({page})=>{
 test.setTimeout(120000);const errors=[];page.on('pageerror',error=>errors.push(error.message));await fixturePreparation(page);
 for(const name of pages){
  await page.goto(`/${name}.html?room=1&lang=ja`);await expect(page.locator('html')).toHaveAttribute('lang','ja');await expect(page.locator('#lang-switch-button')).toHaveText('言語');await expect(page.locator('.nav-destinations a').first()).toHaveText('ホーム');
  await expect.poll(()=>untranslated(page),{message:`${name}: untranslated visible interface`,timeout:15000}).toEqual([]);
  if(name==='index'){
   await expect(page.locator('#data-source')).toHaveText('ローカルプレビュー');
   expect(await page.evaluate(()=>new Promise(resolve=>{const values=[];const sample=()=>{values.push(document.querySelector('#data-source').textContent);if(values.length<35)requestAnimationFrame(sample);else resolve([...new Set(values)]);};sample();}))).toEqual(['ローカルプレビュー']);
  }
 }
 expect(errors).toEqual([]);
});

test('legacy voice_lang Japanese link selects Japanese UI and persists across navigation and refresh',async({page})=>{
 await fixturePreparation(page);
 await page.addInitScript(()=>{if(!sessionStorage.getItem('japanese-preference-test')){localStorage.setItem('duckking-ui-language','fr');localStorage.setItem('duckking-voice-language','zh')}});
 await page.goto('/features.html?sort=top&room=1&voice_lang=ja');
 await expect(page.locator('html')).toHaveAttribute('lang','ja');await expect(page.locator('html')).toHaveAttribute('data-voice-language','ja');await expect(page.locator('#lang-switch-button')).toHaveText('言語');await expect(page.locator('[data-capability=basketball]')).toContainText('ボールを見ずにバランス');
 await page.locator('#show-all-scenes').click();await expect(page.locator('[data-capability]:visible')).toHaveCount(41);await expect.poll(()=>untranslated(page)).toEqual([]);
 // Subsequent visits use the preference saved on this page, not the legacy fixture.
 await page.evaluate(()=>{sessionStorage.setItem('japanese-preference-test','set')});
 await page.locator('.nav-destinations a[href*="index.html"]').click();await expect(page.locator('html')).toHaveAttribute('lang','ja');await expect(page.locator('#data-source')).toHaveText('ローカルプレビュー');await page.reload();await expect(page.locator('html')).toHaveAttribute('lang','ja');
});

test('Japanese language changes disconnect cloud speech and preserve the mobile canvas and room',async({page,context})=>{
 test.setTimeout(60000);await page.setViewportSize({width:390,height:844});await context.grantPermissions(['microphone']);const commands=[];let channel;
 await page.routeWebSocket('**/voice',socket=>{channel=socket;socket.onMessage(raw=>{if(typeof raw!=='string')return;const data=JSON.parse(raw);commands.push(data);if(data.type==='join_room')socket.send(JSON.stringify({type:'voice_status',state:'disconnected'}));if(data.type==='connect')socket.send(JSON.stringify({type:'voice_status',state:'ready',mode:'cloud',language:data.language}));});});
 await page.goto('/index.html?room=1&lang=en');await expect(page.locator('#viewport canvas')).toBeVisible({timeout:45000});await page.evaluate(()=>{window.originalCanvas=document.querySelector('#viewport canvas')});
 await page.locator('#connect-voice').click();await expect(page.locator('#talk-button')).toBeEnabled({timeout:10000});
 await switchLanguage(page,'ja');await expect(page.locator('#talk-button')).toBeDisabled();expect(commands.some(c=>c.type==='disconnect')).toBe(true);expect(commands.filter(c=>c.type==='connect')).toHaveLength(1);
 channel.send(JSON.stringify({type:'voice_status',state:'disconnected'}));await page.locator('#connect-voice').click();await expect(page.locator('#talk-button')).toBeEnabled({timeout:10000});expect(commands.filter(c=>c.type==='connect').at(-1)).toMatchObject({language:'ja',mode:'cloud'});
 for(const [state,label] of [['listening','聞いています'],['thinking','考えています'],['speaking','応答中'],['ready','Linx 接続済み']]){channel.send(JSON.stringify({type:'voice_status',state,mode:'cloud',language:'ja'}));await expect(page.locator('#voice-badge')).toHaveText(label);await expect(page.locator('#data-source')).toHaveText('ローカルプレビュー');}
 channel.send(JSON.stringify({type:'transcript',role:'user',text:'点点头'}));await expect(page.locator('#activity-log')).toContainText('点点头');
 expect(await page.evaluate(()=>window.originalCanvas===document.querySelector('#viewport canvas'))).toBe(true);expect(new URL(page.url()).searchParams.get('room')).toBe('1');
 const brand=await page.locator('.site-topbar .brand').boundingBox(),language=await page.locator('#lang-switch-button').boundingBox();expect(Math.abs(brand.y-language.y)).toBeLessThan(35);expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
 await switchLanguage(page,'en');await expect(page.locator('#data-source')).toHaveText('Local preview');await switchLanguage(page,'ja');await expect(page.locator('#data-source')).toHaveText('ローカルプレビュー');
});
