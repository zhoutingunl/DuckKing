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
  await page.locator('#connect-voice').click();
  await expect(page.locator('#talk-button')).toBeEnabled();
  await expect(page.locator('#voice-mode')).toBeDisabled();
  await page.locator('#talk-button').dispatchEvent('pointerdown',{pointerId:1});
  await expect.poll(()=>frames).toBeGreaterThan(0);
  await page.locator('#talk-button').dispatchEvent('pointerup',{pointerId:1});
  await expect(page.locator('#activity-log')).toContainText('本地反馈');
  await expect(page.locator('#voice-route')).toContainText('本地');
  await page.locator('#connect-voice').click();
  await expect(page.locator('#voice-mode')).toBeEnabled();
  await page.locator('#voice-mode').selectOption('cloud');
  await page.locator('#connect-voice').click();
  await expect(page.locator('#voice-badge')).toHaveText('灵矽已连接');
  expect(connects).toEqual(['local_first','cloud']);
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
