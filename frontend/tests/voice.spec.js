import { test, expect } from '@playwright/test';

async function microphoneProtocol(page,commands=[]){
 await page.routeWebSocket('**/voice',socket=>socket.onMessage(message=>{
   if(typeof message!=='string')return;
   const {type}=JSON.parse(message);commands.push(type);
   const state=type==='join_room'?'disconnected':type==='connect'?'ready':type==='disconnect'?'disconnected':null;
   if(state)socket.send(JSON.stringify({type:'voice_status',state}));
 }));
}

test('microphone permission starts in the connection gesture before a delayed worklet and survives the initial room status',async({page,context})=>{
 await context.grantPermissions(['microphone']);await microphoneProtocol(page);
 await page.addInitScript(()=>{
   const native=navigator.mediaDevices.getUserMedia.bind(navigator.mediaDevices);window.micGestures=[];
   navigator.mediaDevices.getUserMedia=options=>{window.micGestures.push(navigator.userActivation.isActive);return native(options)};
   const NativeAudioContext=window.AudioContext;
   window.AudioContext=class extends NativeAudioContext{
     constructor(...args){
       super(...args);const load=this.audioWorklet.addModule.bind(this.audioWorklet);
       this.audioWorklet.addModule=(...options)=>new Promise(resolve=>setTimeout(resolve,6000)).then(()=>load(...options));
     }
   };
 });
 await page.goto('/index.html?room=1');await page.locator('#connect-voice').click();
 await expect.poll(()=>page.evaluate(()=>window.micGestures)).toEqual([true]);
 await expect(page.locator('#voice-caption')).toContainText('正在加载录音组件');
 await expect(page.locator('#talk-button')).toBeEnabled({timeout:15000});
 expect(await page.evaluate(()=>window.micGestures)).toEqual([true]);
 await page.locator('#connect-voice').click();await expect(page.locator('#voice-badge')).toHaveText('未连接灵矽');
});

test('microphone denial stays visible and a direct retry recovers without reconnecting or recording',async({page,context})=>{
 const commands=[];await context.grantPermissions(['microphone']);await microphoneProtocol(page,commands);
 await page.addInitScript(()=>{
   const native=navigator.mediaDevices.getUserMedia.bind(navigator.mediaDevices);let calls=0;
   navigator.mediaDevices.getUserMedia=options=>++calls===1?Promise.reject(new DOMException('Fixture denial','NotAllowedError')):native(options);
 });
 await page.goto('/index.html?room=1');await page.locator('#connect-voice').click();
 await expect(page.locator('#voice-caption')).toContainText('浏览器未允许此网站');
 await expect(page.locator('#talk-button')).toBeDisabled();
 await page.locator('#prepare-microphone').click();await expect(page.locator('#talk-button')).toBeEnabled();
 await expect(page.locator('#prepare-microphone')).toBeHidden();
 expect(commands.filter(type=>type==='connect')).toHaveLength(1);expect(commands).not.toContain('listen_start');
});

test('an unanswered microphone request stops waiting and exposes a retry without starting capture',async({page,context})=>{
 const commands=[];await context.grantPermissions(['microphone']);await microphoneProtocol(page,commands);
 await page.clock.install();
 await page.addInitScript(()=>{
   const native=navigator.mediaDevices.getUserMedia.bind(navigator.mediaDevices);let calls=0;
   navigator.mediaDevices.getUserMedia=options=>++calls===1?new Promise(()=>{}):native(options);
 });
 await page.goto('/index.html?room=1');await page.locator('#connect-voice').click();
 await expect(page.locator('#voice-badge')).toHaveText('灵矽已连接');
 await page.clock.fastForward(13000);
 await expect(page.locator('#voice-caption')).toContainText('浏览器未完成麦克风授权');
 await expect(page.locator('#prepare-microphone')).toBeEnabled();
 await page.locator('#prepare-microphone').click();await expect(page.locator('#talk-button')).toBeEnabled();
 expect(commands).not.toContain('listen_start');
});

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
  await page.goto('/index.html?room=1');
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
  await page.goto('/index.html?room=1');
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
  await page.goto('/index.html?room=1');
  await page.locator('#connect-voice').click();
  await expect(page.locator('#voice-badge')).toHaveText('连接异常');
  await expect(page.locator('#notice')).toContainText('本地语音通道连接失败');
  await expect(page.locator('#talk-button')).toBeDisabled();
  await page.locator('#connect-voice').click();
  await expect(page.locator('#voice-badge')).toHaveText('灵矽已连接');
  await expect(page.locator('#talk-button')).toBeEnabled();
});

test('stalled thinking can be reset and recovery never starts recording automatically',async({page,context})=>{
  await context.grantPermissions(['microphone']);
  const commands=[];
  let serverSocket;
  await page.routeWebSocket('**/voice',socket=>{
    serverSocket=socket;
    socket.onMessage(message=>{
      if(typeof message!=='string')return;
      const {type}=JSON.parse(message);commands.push(type);
      const state=type==='connect'?'ready':type==='listen_start'?'listening':type==='listen_stop'?'thinking':type==='reset'?'recovering':type==='disconnect'?'disconnected':null;
      if(type==='reset')socket.send(JSON.stringify({type:'playback_end',aborted:true}));
      if(state)socket.send(JSON.stringify({type:'voice_status',state}));
    });
  });
  await page.goto('/index.html?room=1');
  await page.locator('#connect-voice').click();
  await expect(page.locator('#talk-button')).toBeEnabled();
  await page.locator('#talk-button').dispatchEvent('pointerdown',{pointerId:1});
  await expect(page.locator('#voice-badge')).toHaveText('正在聆听');
  await page.locator('#talk-button').dispatchEvent('pointerup',{pointerId:1});
  await expect(page.locator('#voice-badge')).toHaveText('正在思考');
  await expect(page.locator('#voice-caption')).toContainText('20 秒');
  await page.locator('#reset-voice').click();
  await expect(page.locator('#voice-badge')).toHaveText('正在恢复连接');
  await expect(page.locator('#talk-button')).toBeDisabled();
  serverSocket.send(JSON.stringify({type:'voice_status',state:'ready'}));
  await expect(page.locator('#talk-button')).toBeEnabled();
  expect(commands.filter(type=>type==='listen_start')).toHaveLength(1);
  await expect(page.locator('#activity-log')).toContainText('正在恢复连接');
  await expect(page.getByRole('link',{name:'连接诊断'})).toHaveJSProperty('href',new URL('/api/voice/diagnostics?room=1',page.url()).href);
  const diagnostic=await page.request.get('/api/voice/diagnostics');
  expect(diagnostic.ok()).toBe(true);
  expect((await diagnostic.json()).events).toBeInstanceOf(Array);
  serverSocket.send(JSON.stringify({type:'voice_status',state:'recovering'}));
  await page.locator('#connect-voice').click();
  await expect(page.locator('#voice-badge')).toHaveText('未连接灵矽');
});
