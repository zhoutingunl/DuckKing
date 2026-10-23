import { test, expect } from '@playwright/test';

test('push-to-talk captures framed PCM, receives playback, and releases microphone',async({page,context})=>{
  await context.grantPermissions(['microphone']);
  const frames=[];
  let stopped=false;
  await page.routeWebSocket('**/voice',socket=>{
    const send=data=>socket.send(JSON.stringify(data));
    socket.onMessage(message=>{
      if(typeof message!=='string'){frames.push(message);return}
      const data=JSON.parse(message);
      if(data.type==='connect')send({type:'voice_status',state:'ready'});
      if(data.type==='listen_start')send({type:'voice_status',state:'listening'});
      if(data.type==='listen_stop'){
        stopped=true;
        send({type:'transcript',role:'user',text:'协议测试：你好'});
        send({type:'voice_status',state:'speaking'});
        send({type:'transcript',role:'assistant',text:'这是本地协议测试响应'});
        send({type:'audio',sample_rate:24000,pcm:Buffer.alloc(2880).toString('base64')});
        send({type:'playback_end',aborted:false});
        send({type:'voice_status',state:'ready'});
      }
      if(data.type==='disconnect')send({type:'voice_status',state:'disconnected'});
    });
  });
  await page.goto('/');
  await page.locator('#connect-voice').click();
  await expect(page.locator('#talk-button')).toBeEnabled();
  await page.locator('#talk-button').dispatchEvent('pointerdown',{pointerId:1});
  await expect.poll(()=>frames.length).toBeGreaterThan(0);
  await page.locator('#talk-button').dispatchEvent('pointerup',{pointerId:1});
  await expect.poll(()=>stopped).toBe(true);
  expect(frames.every(frame=>frame.length===1920)).toBe(true);
  await expect(page.locator('#activity-log')).toContainText('这是本地协议测试响应');
  await expect(page.locator('#talk-button')).toBeEnabled();
  await page.locator('#connect-voice').click();
  await expect(page.locator('#voice-badge')).toHaveText('未连接灵矽');
});

test('activation and connection failure stay explicit instead of faking a reply',async({page})=>{
  let count=0;
  await page.routeWebSocket('**/voice',socket=>socket.onMessage(message=>{
    if(typeof message==='string'&&JSON.parse(message).type==='connect'){
      count++;
      socket.send(JSON.stringify(count===1?{type:'voice_status',state:'awaiting_binding',activation_code:'123456'}:{type:'voice_status',state:'error',error:'协议测试：账号尚未绑定'}));
    }
  }));
  await page.goto('/');
  await page.locator('#connect-voice').click();
  await expect(page.locator('#activation')).toContainText('123456');
  await expect(page.locator('#talk-button')).toBeDisabled();
  await page.locator('#connect-voice').click();
  await expect(page.locator('#notice')).toContainText('账号尚未绑定');
  await expect(page.locator('#voice-badge')).toHaveText('连接异常');
});

test('a rejected local voice connection gives actionable feedback and can be retried',async({page})=>{
  let attempts=0;
  await page.routeWebSocket('**/voice',socket=>socket.onMessage(message=>{
    if(typeof message!=='string'||JSON.parse(message).type!=='connect')return;
    if(++attempts===1)socket.close({code:1008,reason:'Local protocol test rejection'});
    else socket.send(JSON.stringify({type:'voice_status',state:'ready'}));
  }));
  await page.goto('/');
  await page.locator('#connect-voice').click();
  await expect(page.locator('#voice-badge')).toHaveText('连接异常');
  await expect(page.locator('#notice')).toContainText('本地语音通道连接失败');
  await expect(page.locator('#talk-button')).toBeDisabled();
  await page.locator('#connect-voice').click();
  await expect(page.locator('#voice-badge')).toHaveText('灵矽已连接');
  await expect(page.locator('#talk-button')).toBeEnabled();
});
