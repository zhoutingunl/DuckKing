import {test,expect} from '@playwright/test';

test('two unassigned pages choose distinct rooms and actions and stats stay scoped',async({page,context})=>{
  const other=await context.newPage();
  try{
    await Promise.all([page.goto('/'),other.goto('/')]);
    await expect(page.locator('#connection-label')).toContainText('已连接');
    await expect(other.locator('#connection-label')).toContainText('已连接');
    const first=new URL(page.url()).searchParams.get('room'),second=new URL(other.url()).searchParams.get('room');
    expect(new Set([first,second]).size).toBe(2);
    await page.locator('[data-action="walk"]').click();
    await other.locator('[data-action="turn_left"]').click();
    await expect(page.locator('#current-action')).toHaveText('前进');
    await expect(other.locator('#current-action')).toHaveText('左转');
    await page.locator('[data-action="stop"]').click();
    await expect(page.locator('#current-action')).toHaveText('待机');
    await expect(other.locator('#activity-log')).not.toContainText('前进');
    expect(new URL(await other.getByRole('link',{name:'交互统计'}).getAttribute('href')).searchParams.get('room')).toBe(second);
    await page.locator('#connect-voice').click();
    await other.locator('#connect-voice').click();
    // Actual local backend, explicitly configured without a reachable cloud.
    await expect(page.locator('#notice')).toContainText('连接未成功');
    await expect(other.locator('#notice')).toContainText('连接未成功');
    await expect(other.locator('#voice-badge')).toHaveText('连接异常');
  }finally{await other.close()}
});

test('interrupt mutes queued speech, ignores stale generations, and captures new PCM',async({page,context})=>{
  await context.grantPermissions(['microphone']);
  const commands=[],frames=[];let server,generation=0;
  await page.routeWebSocket('**/voice',socket=>{
    server=socket;
    const send=data=>socket.send(JSON.stringify({generation,...data}));
    socket.onMessage(message=>{
      if(typeof message!=='string'){frames.push(message);return}
      const {type}=JSON.parse(message);commands.push(type);
      if(type==='connect')send({type:'voice_status',state:'ready'});
      if(type==='interrupt'){
        generation++;
        send({type:'voice_status',state:'interrupting'});
        send({type:'audio',generation:0,sample_rate:16000,pcm:Buffer.alloc(32000).toString('base64')});
        send({type:'transcript',generation:0,role:'assistant',text:'不应出现的旧回复'});
        send({type:'voice_status',generation:0,state:'speaking'});
      }
      if(type==='listen_start')send({type:'voice_status',state:'listening'});
      if(type==='listen_stop')send({type:'voice_status',state:'thinking'});
    });
  });
  // Instrument native browser audio only to count sources and tracks, not to
  // replace playback/capture; the cloud messages above are protocol fixtures.
  await page.addInitScript(()=>{
    window.audioAudit={active:0,stopped:0};
    const original=AudioContext.prototype.createBufferSource;
    AudioContext.prototype.createBufferSource=function(...args){
      const source=original.apply(this,args),stop=source.stop.bind(source),start=source.start.bind(source);
      source.start=(...args)=>{window.audioAudit.active++;return start(...args)};
      source.stop=(...args)=>{window.audioAudit.stopped++;window.audioAudit.active--;return stop(...args)};
      return source;
    };
  });
  await page.goto('/?room=2');await page.locator('#connect-voice').click();
  await expect(page.locator('#voice-badge')).toHaveText('灵矽已连接');
  server.send(JSON.stringify({type:'voice_status',state:'speaking',generation:0}));
  server.send(JSON.stringify({type:'audio',generation:0,sample_rate:16000,pcm:Buffer.alloc(160000).toString('base64')}));
  await expect.poll(()=>page.evaluate(()=>audioAudit.active)).toBe(1);
  await expect(page.locator('#talk-button')).toBeEnabled();
  await expect(page.locator('#talk-button')).toContainText('打断并说话');
  await page.locator('#talk-button').dispatchEvent('pointerdown',{pointerId:1});
  await expect.poll(()=>page.evaluate(()=>audioAudit.stopped)).toBe(1);
  await expect.poll(()=>frames.length).toBeGreaterThan(0);
  await page.locator('#talk-button').dispatchEvent('pointerup',{pointerId:1});
  await expect(page.locator('#voice-badge')).toHaveText('正在思考');
  expect(commands.indexOf('interrupt')).toBeLessThan(commands.indexOf('listen_start'));
  expect(commands.filter(c=>c==='interrupt')).toHaveLength(1);
  expect(frames.every(f=>f.length===1920)).toBe(true);
  expect(await page.evaluate(()=>audioAudit.active)).toBe(0);
  await expect(page.locator('#activity-log')).not.toContainText('不应出现的旧回复');
});
