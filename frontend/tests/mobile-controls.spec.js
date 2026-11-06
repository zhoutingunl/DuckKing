import {test,expect} from '@playwright/test';

test.use({isMobile:true,hasTouch:true});
for(const language of ['zh','en','fr'])test(`${language}: mobile controls fit without accidental zoom and colour controls stay compact`,async({page},info)=>{
  test.setTimeout(60000);
  await page.route('**/api/voice/modes*',route=>route.fulfill({json:{local_first:true,available:true}}));
  await page.setViewportSize({width:390,height:844});
  await page.goto(`/?room=1&lang=${language}`);
  await expect(page.locator('#viewport')).toHaveAttribute('data-model','official',{timeout:30000});
  await expect(page.locator('#voice-mode')).toBeEnabled();
  const scale=await page.evaluate(()=>visualViewport.scale);
  for(const width of [320,390,430]){
    await page.setViewportSize({width,height:844});
    // Focusing the real select must not depend on the mobile browser enlarging a tiny font.
    await page.locator('#voice-mode').focus();
    expect(await page.locator('#voice-mode').evaluate(el=>parseFloat(getComputedStyle(el).fontSize))).toBeGreaterThanOrEqual(16);
    const grid=page.locator('.action-grid');
    await grid.scrollIntoViewIfNeeded();
    const bounds=await grid.boundingBox();
    for(const button of await grid.locator('button').all()){
      const box=await button.boundingBox();
      expect(box.x).toBeGreaterThanOrEqual(bounds.x-1);
      expect(box.x+box.width).toBeLessThanOrEqual(bounds.x+bounds.width+1);
      expect(box.width).toBeLessThanOrEqual(bounds.width/2);
      expect(await button.evaluate(el=>el.scrollWidth<=el.clientWidth)).toBe(true);
    }
    const before=await page.evaluate(()=>visualViewport.scale);
    // Repeated taps on an action must not smart-zoom the whole page.
    await page.locator('[data-action=nod]').tap();await page.locator('[data-action=nod]').tap();
    expect(await page.evaluate(()=>visualViewport.scale)).toBe(before);
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
    await expect(page.locator('#mobile-stop')).toHaveCount(0);
    const panel=page.locator('.duck-appearance');
    const palette=await panel.boundingBox();
    expect(palette.width).toBeLessThanOrEqual(150);expect(palette.height).toBeLessThanOrEqual(46);
    for(const swatch of await panel.locator('button').all()){
      const box=await swatch.boundingBox();expect(box.width).toBeGreaterThanOrEqual(32);expect(box.height).toBeGreaterThanOrEqual(36);
    }
    await panel.locator('button').last().tap({position:{x:2,y:2}});
    await expect(panel.locator('button').last()).toHaveAttribute('aria-pressed','true');
    await page.locator('[data-action=stop]').tap();
  }
  expect(await page.evaluate(()=>visualViewport.scale)).toBe(scale);
  // Preserve intentional pinch zoom; the 3D canvas retains its own orbit gestures.
  expect(await page.locator('meta[name=viewport]').getAttribute('content')).not.toMatch(/user-scalable\s*=\s*no|maximum-scale/);
  expect(await page.locator('[data-action=nod]').evaluate(el=>getComputedStyle(el).touchAction)).toBe('manipulation');
  await page.locator('[data-action=nod]').scrollIntoViewIfNeeded();
  await page.screenshot({path:info.outputPath(`mobile-actions-${language}.png`)});
});

test('one voice control exposes status, cancel, retry and disconnect on mobile',async({page,context})=>{
  await page.setViewportSize({width:390,height:844});await context.grantPermissions(['microphone']);
  await page.route('**/api/voice/modes*',route=>route.fulfill({json:{local_first:true,available:true}}));
  let socket;const commands=[];
  await page.routeWebSocket('**/voice',ws=>{socket=ws;ws.onMessage(raw=>{
    if(typeof raw!=='string')return;const data=JSON.parse(raw);commands.push(data.type);
    if(data.type==='disconnect')ws.send(JSON.stringify({type:'voice_status',state:'disconnected'}));
  })});
  await page.goto('/?room=1');
  const button=page.locator('#connect-voice');
  await expect(button).toHaveAccessibleName('启用语音');
  await expect(button.locator('#voice-badge')).toHaveText('语音未启用');
  await expect(page.locator('.section-heading #connect-voice')).toHaveCount(1);
  await button.tap();await expect(button.locator('#voice-badge')).toHaveText('正在连接');
  await expect(button).toHaveAccessibleName('断开连接');
  await button.tap();await expect(button).toHaveAccessibleName('启用语音');
  expect(commands).toContain('disconnect');
  await button.tap();socket.send(JSON.stringify({type:'voice_status',state:'error'}));
  await expect(button.locator('#voice-badge')).toHaveText('连接异常');await expect(button).toBeEnabled();
  await button.tap();socket.send(JSON.stringify({type:'voice_status',state:'ready',mode:'local_first'}));
  await expect(button.locator('#voice-badge')).toHaveText('本地优先 · 已就绪');
  await expect(button).toHaveAccessibleDescription('本地优先 · 已就绪');
  await expect(page.locator('#talk-button')).toBeEnabled();
  await button.tap();await expect(page.locator('#talk-button')).toBeDisabled();
  await expect(button).toHaveAccessibleName('启用语音');
});
