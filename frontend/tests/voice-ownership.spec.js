import {test,expect} from '@playwright/test';

test('a mobile page retries after the other browser releases the real server owner',async({page,browser,baseURL})=>{
  // Hold only the local device channel; this test never connects to Linx.
  await page.goto('/');
  await page.evaluate(async()=>{
    const url=new URL('/voice',location.href);url.protocol=url.protocol==='https:'?'wss:':'ws:';
    window.testOwner=new WebSocket(url);
    await new Promise((resolve,reject)=>{window.testOwner.onmessage=e=>JSON.parse(e.data).state==='disconnected'?resolve():reject(Error('Unexpected owner status'));window.testOwner.onerror=reject});
  });
  const mobile=await browser.newContext({baseURL,viewport:{width:390,height:844},isMobile:true,hasTouch:true});
  const phone=await mobile.newPage();
  try{
    await phone.goto('/');await phone.locator('#connect-voice').click();
    await expect(phone.locator('#voice-badge')).toHaveText('其他页面正在使用语音');
    await expect(phone.locator('#voice-caption')).toContainText('Mac');
    await expect(phone.locator('#talk-button')).toBeDisabled();
    expect(await phone.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
    await page.evaluate(()=>new Promise(resolve=>{
      window.testOwner.onclose=resolve;window.testOwner.send(JSON.stringify({type:'disconnect'}));
    }));
    // The desktop page remains open. The test backend has no cloud credentials,
    // so the next attempt must reach its explicit cloud error instead of busy.
    await phone.locator('#connect-voice').click();
    await expect(phone.locator('#voice-badge')).toHaveText('连接异常');
    await expect(phone.locator('#notice')).toContainText('连接未成功');
    await expect(phone.locator('#talk-button')).toBeDisabled();
    // A terminal error also releases ownership without closing the phone page.
    await expect.poll(async()=>{
      const r=await phone.request.get('/api/voice/diagnostics');return (await r.json()).state;
    }).toBe('disconnected');
    expect(await page.evaluate(()=>document.documentElement.scrollWidth>0)).toBe(true);
  }finally{await mobile.close();await page.evaluate(()=>window.testOwner?.close())}
});

test('voice heartbeats stop on disconnect and a cloud error remains visible after close',async({page})=>{
  const commands=[];let channel;
  await page.clock.install();
  await page.routeWebSocket('**/voice',socket=>{
    channel=socket;
    socket.onMessage(message=>{
      if(typeof message!=='string')return;
      const type=JSON.parse(message).type;commands.push(type);
      if(type==='connect')socket.send(JSON.stringify({type:'voice_status',state:'ready'}));
      if(type==='ping')socket.send(JSON.stringify({type:'pong'}));
      if(type==='disconnect'){
        socket.send(JSON.stringify({type:'voice_status',state:'disconnected'}));socket.close();
      }
    });
  });
  await page.goto('/');await page.locator('#connect-voice').click();
  await expect(page.locator('#voice-badge')).toHaveText('灵矽已连接');
  await page.clock.fastForward(11000);await expect.poll(()=>commands.filter(c=>c==='ping').length).toBe(1);
  await page.locator('#connect-voice').click();await expect(page.locator('#voice-badge')).toHaveText('未连接灵矽');
  await page.clock.fastForward(30000);expect(commands.filter(c=>c==='ping')).toHaveLength(1);
  await page.locator('#connect-voice').click();await expect(page.locator('#voice-badge')).toHaveText('灵矽已连接');
  channel.send(JSON.stringify({type:'voice_status',state:'error',error:'协议测试：云端连接中断'}));channel.close();
  await expect(page.locator('#voice-badge')).toHaveText('连接异常');
  await expect(page.locator('#notice')).toContainText('云端连接中断');
  await page.clock.fastForward(30000);expect(commands.filter(c=>c==='ping')).toHaveLength(1);
});
