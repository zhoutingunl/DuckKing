import {test,expect} from '@playwright/test';

test('local-first source stays explicit and cloud mode remains selectable',async({page,context})=>{
  await context.grantPermissions(['microphone']);
  await page.route('**/api/voice/modes*',route=>route.fulfill({json:{local_first:true,available:true}}));
  const connects=[];
  let frames=0;
  await page.routeWebSocket('**/voice',socket=>{
    const send=data=>socket.send(JSON.stringify(data));
    socket.onMessage(message=>{
      if(typeof message!=='string'){frames++;return}
      const d=JSON.parse(message);
      if(d.type==='connect'){connects.push(d.mode);send({type:'voice_status',state:'ready',mode:d.mode})}
      if(d.type==='listen_start')send({type:'voice_status',state:'listening'});
      if(d.type==='listen_stop'){
        send({type:'voice_route',route:'local',reason:'matched',asr_ms:123});
        send({type:'transcript',role:'user',source:'local',text:'协议测试：点头'});
        send({type:'transcript',role:'assistant',source:'local',text:'本地已完成：点头'});
        send({type:'voice_status',state:'ready'});
      }
      if(d.type==='disconnect')send({type:'voice_status',state:'disconnected'});
    });
  });
  await page.goto('/?room=1');
  await expect(page.locator('#voice-mode')).toHaveValue('local_first');
  await expect(page.locator('#connect-voice')).toHaveAccessibleName('启用语音');
  await expect(page.locator('#connect-voice svg')).toHaveCount(1);
  await page.locator('#connect-voice').click();
  await expect(page.locator('#talk-button')).toBeEnabled();
  await expect(page.locator('#connect-voice')).toHaveAccessibleName('断开连接');
  await expect(page.locator('#voice-badge')).toHaveClass(/connected/);
  await expect(page.locator('#voice-mode')).toBeDisabled();
  await page.locator('#talk-button').dispatchEvent('pointerdown',{pointerId:1});
  await expect.poll(()=>frames).toBeGreaterThan(0);
  await page.locator('#talk-button').dispatchEvent('pointerup',{pointerId:1});
  await expect(page.locator('#activity-log')).toContainText('本地反馈');
  await expect(page.locator('#activity-log')).not.toContainText('灵矽已连接');
  await expect(page.locator('#scope-note')).toContainText('本地优先语音已启用');
  await expect(page.locator('#scope-note')).not.toContainText('灵矽语音已连接');
  await expect(page.locator('#voice-route')).toContainText('本地');
  await page.locator('#connect-voice').click();
  await expect(page.locator('#voice-mode')).toBeEnabled();
  await expect(page.locator('#voice-badge')).not.toHaveClass(/connected/);
  await page.locator('#voice-mode').selectOption('cloud');
  await expect(page.locator('#connect-voice')).toHaveAccessibleName('连接灵矽');
  await expect(page.locator('#connect-voice svg')).toHaveCount(1);
  await page.locator('#connect-voice').click();
  await expect(page.locator('#voice-badge')).toHaveText('灵矽已连接');
  expect(connects).toEqual(['local_first','cloud']);
});

test('scene voice retry keeps local labels, button icon and connection state',async({page})=>{
  await page.route('**/api/voice/modes*',route=>route.fulfill({json:{local_first:true,available:true}}));
  let attempts=0;
  await page.routeWebSocket('**/scene-voice',socket=>socket.onMessage(message=>{
    if(typeof message!=='string')return;
    const data=JSON.parse(message);
    if(data.type==='connect')socket.send(JSON.stringify(++attempts===1
      ?{type:'voice_status',state:'error',error:'协议测试：连接暂不可用'}
      :{type:'voice_status',state:'ready',mode:data.mode}));
    if(data.type==='disconnect')socket.send(JSON.stringify({type:'voice_status',state:'disconnected'}));
  }));
  await page.goto('/scenarios.html?room=1');
  const button=page.locator('#connect-voice'),badge=page.locator('#voice-badge');
  await expect(button).toHaveAccessibleName('启用语音');
  await button.click();
  await expect(badge).toHaveText('连接异常');
  await expect(badge).not.toHaveClass(/connected/);
  await expect(button).toHaveAccessibleName('启用语音');
  await button.click();
  await expect(badge).toHaveText('本地优先 · 已就绪');
  await expect(badge).toHaveClass(/connected/);
  await expect(button).toHaveAccessibleName('断开连接');
  await expect(button.locator('svg')).toHaveCount(1);
  await button.click();
  await expect(badge).toHaveText('语音未启用');
  await expect(badge).not.toHaveClass(/connected/);
  await expect(button).toHaveAccessibleName('启用语音');
});

test('late capability response cannot switch an already connected cloud session',async({page})=>{
  let release;
  const gate=new Promise(resolve=>release=resolve);
  await page.route('**/api/voice/modes*',async route=>{await gate;await route.fulfill({json:{local_first:true,available:true}})});
  await page.routeWebSocket('**/voice',socket=>socket.onMessage(message=>{
    if(typeof message==='string'&&JSON.parse(message).type==='connect')socket.send(JSON.stringify({type:'voice_status',state:'ready'}));
  }));
  await page.goto('/?room=1');
  await page.locator('#connect-voice').click();
  await expect(page.locator('#voice-badge')).toHaveText('灵矽已连接');
  release();
  await expect(page.locator('#voice-mode')).toHaveValue('cloud');
  await expect(page.locator('#voice-badge')).toHaveText('灵矽已连接');
});
