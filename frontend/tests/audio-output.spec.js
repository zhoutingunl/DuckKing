import { test, expect } from '@playwright/test';

function protocol(page,frames,commands,reports) {
  return page.routeWebSocket('**/voice',socket=>socket.onMessage(message=>{
    if(typeof message!=='string'){frames.push(message);return}
    const data=JSON.parse(message);commands.push(data.type);
    const send=data=>socket.send(JSON.stringify(data));
    if(data.type==='playback_status')reports.push(data);
    if(data.type==='connect')send({type:'voice_status',state:'ready'});
    if(data.type==='listen_start')send({type:'voice_status',state:'listening'});
    if(data.type==='listen_stop'){
      const pcm=Buffer.alloc(4800);
      for(let i=0;i<pcm.length;i+=2)pcm.writeInt16LE(Math.round(Math.sin(i*.04)*8000),i);
      send({type:'audio',sample_rate:24000,pcm:pcm.toString('base64')});
      send({type:'playback_end',aborted:false});
      send({type:'voice_status',state:'ready'});
    }
    if(data.type==='disconnect')send({type:'voice_status',state:'disconnected'});
  }));
}

test('local sound check and two mic turns reuse one hardware-rate context and finish nonzero playback',async({page,context})=>{
  await context.grantPermissions(['microphone']);
  const frames=[],commands=[],reports=[];
  await protocol(page,frames,commands,reports);
  await page.addInitScript(()=>{
    const Native=window.AudioContext;window.audioAudit={contexts:[],closed:0,tracks:[]};
    window.AudioContext=new Proxy(Native,{construct(Target,args){
      const ctx=new Target(...args),close=ctx.close.bind(ctx);
      ctx.close=()=>{window.audioAudit.closed++;return close()};
      window.audioAudit.contexts.push(ctx);return ctx;
    }});
    const get=navigator.mediaDevices.getUserMedia.bind(navigator.mediaDevices);
    navigator.mediaDevices.getUserMedia=async constraints=>{
      const stream=await get(constraints);window.audioAudit.tracks.push(...stream.getTracks());return stream;
    };
  });
  await page.goto('/?room=1');
  await page.locator('#enable-sound').click();
  await expect(page.locator('#activity-log')).toContainText('本地测试提示音');
  expect(commands).toEqual([]);expect(frames).toEqual([]);
  await page.locator('#connect-voice').click();
  await expect(page.locator('#voice-badge')).toHaveText('灵矽已连接');
  for(let turn=0;turn<2;turn++){
    await page.locator('#talk-button').dispatchEvent('pointerdown',{pointerId:1});
    await expect(page.locator('#voice-badge')).toHaveText('正在聆听');
    const count=frames.length;
    await expect.poll(()=>frames.length).toBeGreaterThan(count+1);
    await page.locator('#talk-button').dispatchEvent('pointerup',{pointerId:1});
    await expect(page.locator('#voice-badge')).toHaveText('灵矽已连接');
    await expect.poll(()=>reports.at(-1)?.ended_frames).toBe(turn+1);
  }
  expect(frames.every(frame=>frame.length===1920)).toBe(true);
  expect(reports.at(-1).signal_peak_milli).toBeGreaterThan(0);
  expect(reports.at(-1).dropped_frames).toBe(0);
  const audit=await page.evaluate(()=>({contexts:audioAudit.contexts.length,closed:audioAudit.closed,
    rate:audioAudit.contexts[0].sampleRate,tracks:audioAudit.tracks.map(track=>track.readyState)}));
  expect(audit.contexts).toBe(1);expect(audit.closed).toBe(0);
  expect(audit.rate).toBeGreaterThan(16000);expect(audit.tracks).toEqual(['ended','ended']);
  await page.locator('#connect-voice').click();
  await expect(page.locator('#voice-badge')).toHaveText('未连接灵矽');
  await Promise.all([
    page.waitForEvent('domcontentloaded'),
    page.evaluate(()=>{
      window.dispatchEvent(new PageTransitionEvent('pagehide',{persisted:true}));
      window.dispatchEvent(new PageTransitionEvent('pageshow',{persisted:true}));
    }),
  ]);
  await page.locator('#enable-sound').click();
  await expect(page.locator('#activity-log')).toContainText('本地测试提示音');
  expect(commands.filter(command=>command==='connect')).toHaveLength(1);
});

test('a permanently suspended output never blocks connect or disconnect and shows a sound remedy',async({page})=>{
  await page.addInitScript(()=>{
    const Native=window.AudioContext;
    window.AudioContext=new Proxy(Native,{construct(Target,args){
      const ctx=new Target(...args);Object.defineProperty(ctx,'state',{get:()=> 'suspended'});
      ctx.resume=()=>new Promise(()=>{});return ctx;
    }});
  });
  await page.routeWebSocket('**/voice',socket=>socket.onMessage(message=>{
    if(typeof message!=='string')return;
    const {type}=JSON.parse(message);
    if(type==='connect'){
      socket.send(JSON.stringify({type:'voice_status',state:'ready'}));
      socket.send(JSON.stringify({type:'audio',sample_rate:16000,pcm:Buffer.alloc(1920).toString('base64')}));
    }
    if(type==='disconnect')socket.send(JSON.stringify({type:'voice_status',state:'disconnected'}));
  }));
  await page.goto('/?room=1');
  await page.locator('#connect-voice').click();
  await expect(page.locator('#voice-badge')).toHaveText('灵矽已连接');
  await expect(page.locator('#audio-status')).toContainText('已收到回复音频，播放尚未就绪');
  await page.locator('#enable-sound').click();
  await expect(page.locator('#activity-log')).toContainText('浏览器仍未允许声音播放');
  await page.locator('#connect-voice').click();
  await expect(page.locator('#voice-badge')).toHaveText('未连接灵矽');
});

test('late mic permission from a released press cannot start or stop the next recording',async({page,context})=>{
  await context.grantPermissions(['microphone']);
  const frames=[],commands=[],reports=[];await protocol(page,frames,commands,reports);
  await page.addInitScript(()=>{
    const get=navigator.mediaDevices.getUserMedia.bind(navigator.mediaDevices);
    window.pendingMics=[];window.micTracks=[];
    navigator.mediaDevices.getUserMedia=async constraints=>{
      const stream=await get(constraints);window.micTracks.push(...stream.getTracks());
      return new Promise(resolve=>window.pendingMics.push(()=>resolve(stream)));
    };
  });
  await page.goto('/?room=1');await page.locator('#connect-voice').click();
  await expect(page.locator('#voice-badge')).toHaveText('灵矽已连接');
  const talk=page.locator('#talk-button');
  await talk.dispatchEvent('pointerdown',{pointerId:1});
  await expect.poll(()=>page.evaluate(()=>pendingMics.length)).toBe(1);
  await talk.dispatchEvent('pointerup',{pointerId:1});
  await talk.dispatchEvent('pointerdown',{pointerId:1});
  await expect.poll(()=>page.evaluate(()=>pendingMics.length)).toBe(2);
  await page.evaluate(()=>pendingMics[0]());
  await expect.poll(()=>page.evaluate(()=>micTracks[0].readyState)).toBe('ended');
  expect(commands.filter(command=>command==='listen_start')).toHaveLength(0);
  await page.evaluate(()=>pendingMics[1]());
  await expect(page.locator('#voice-badge')).toHaveText('正在聆听');
  await expect.poll(()=>frames.length).toBeGreaterThan(0);
  await talk.dispatchEvent('pointerup',{pointerId:1});
  await expect(page.locator('#voice-badge')).toHaveText('灵矽已连接');
  expect(commands.filter(command=>command==='listen_start')).toHaveLength(1);
  expect(await page.evaluate(()=>micTracks.map(track=>track.readyState))).toEqual(['ended','ended']);
});
