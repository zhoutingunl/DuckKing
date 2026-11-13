import {test,expect} from '@playwright/test';

for(const locale of ['zh','fr'])test(`${locale}: Japanese voice preserves the interface, closes old audio and survives reconnect and reload`,async({page,context})=>{
 test.setTimeout(90000);
 await context.grantPermissions(['microphone']);
 await page.route('**/api/voice/modes*',route=>route.fulfill({json:{local_first:true,available:true}}));
 const connects=[],commands=[];let channel;
 await page.routeWebSocket('**/voice',socket=>{
  channel=socket;
  socket.onMessage(raw=>{
   if(typeof raw!=='string')return;
   const data=JSON.parse(raw);commands.push(data.type);
   if(data.type==='join_room'||data.type==='disconnect')socket.send(JSON.stringify({type:'voice_status',state:'disconnected'}));
   if(data.type==='connect'){
    connects.push(data);socket.send(JSON.stringify({type:'voice_status',state:'ready',mode:data.mode,language:data.language}));
   }
  });
 });
 await page.goto(`/index.html?room=1&lang=${locale}`);
 await page.locator('#connect-voice').click();await expect(page.locator('#talk-button')).toBeEnabled();
 expect(connects.at(-1)).toMatchObject({language:locale,mode:locale==='zh'?'local_first':'cloud'});
 await page.locator('#lang-switch-button').click();await page.locator('[data-lang=ja]').click();
 await expect(page.locator('html')).toHaveAttribute('lang',locale==='zh'?'zh-CN':'fr');
 await expect(page.locator('html')).toHaveAttribute('data-voice-language','ja');
 await expect(page.locator('#talk-button')).toBeDisabled();
 await expect.poll(()=>commands.includes('disconnect')).toBe(true);
 await expect(page.locator('#voice-language-hint')).toContainText(locale==='zh'?'日语识别与回复':'japonais');
 await page.locator('#connect-voice').click();await expect(page.locator('#talk-button')).toBeEnabled();
 expect(connects.at(-1)).toMatchObject({language:'ja',mode:'cloud'});
 channel.send(JSON.stringify({type:'voice_status',state:'disconnected'}));
 await expect(page.locator('#talk-button')).toBeDisabled();
 await page.locator('#connect-voice').click();await expect(page.locator('#talk-button')).toBeEnabled();
 expect(connects.at(-1)).toMatchObject({language:'ja',mode:'cloud'});
 const count=connects.length;
 await page.reload();await expect(page.locator('html')).toHaveAttribute('data-voice-language','ja');
 expect(connects.length).toBe(count);
 await expect(page.locator('html')).toHaveAttribute('lang',locale==='zh'?'zh-CN':'fr');
 await page.locator('#lang-switch-button').click();await expect(page.locator('[data-lang=ja]')).toHaveAttribute('aria-current','true');
 await page.locator('[data-lang=zh]').click();
 await expect(page.locator('html')).toHaveAttribute('data-voice-language','zh');
 await expect(page.locator('#voice-mode')).toHaveValue('local_first');
});
