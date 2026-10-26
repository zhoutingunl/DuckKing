import {test,expect} from '@playwright/test';
test.setTimeout(120000);

// Protocol/data fixtures are explicitly verification traffic, never production benchmarks.
test('persistent experience filters, nearest-rank table, trend, export and failure state',async({page,request})=>{
  const events=Array.from({length:20},(_,i)=>({id:crypto.randomUUID(),sequence:1,kind:'voice',status:'completed',page:'unknown',traffic:'verification',device:'mobile',route:'local',metrics:{stt_local_ms:(i+1)*10}}));
  expect((await request.post('/api/experience?room=9',{data:{events}})).status()).toBe(202);
  await page.goto('/experience.html');
  await expect(page.locator('#experience-empty')).toBeVisible();
  await page.locator('[name=traffic]').selectOption('verification');
  await page.locator('[name=page]').selectOption('unknown');
  await page.locator('[name=room]').selectOption('9');
  await page.locator('[name=device]').selectOption('mobile');
  await expect(page.locator('#browser-experience')).toContainText('105');
  await expect(page.locator('#browser-experience')).toContainText('190');
  await expect(page.locator('#trend-chart svg')).toBeVisible();
  const download=page.waitForEvent('download');await page.locator('#export-experience').click();
  expect((await download).suggestedFilename()).toContain('duckking-experience-');
  await page.setViewportSize({width:390,height:844});
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  await page.locator('[name=cache]').selectOption('network');
  await expect(page.locator('#experience-empty')).toBeVisible();
  await expect(page.locator('#trend-chart')).toContainText('有样本后');
  await page.route('**/api/experience?*',route=>route.fulfill({status:503,body:'test unavailable'}));
  await page.locator('#refresh-experience').click();
  await expect(page.locator('#experience-error')).toContainText('当前数值未更新');
});

test('real browser model loading persists without disconnecting the working page',async({page,context})=>{
  const posts=[];page.on('request',r=>{if(r.method()==='POST'&&new URL(r.url()).pathname==='/api/experience')posts.push(r.postDataJSON())});
  await page.goto('/?room=1');
  await expect(page.locator('#viewport')).toHaveAttribute('data-model','official',{timeout:90000});
  await expect.poll(()=>posts.flatMap(p=>p.events).some(e=>e.kind==='load'&&e.status==='completed')).toBe(true);
  const load=posts.flatMap(p=>p.events).find(e=>e.kind==='load'&&e.status==='completed');
  expect(load.traffic).toBe('verification');expect(load.metrics.model_ms).toBeGreaterThan(0);
  expect(load.metrics.navigation_ms).toBeGreaterThanOrEqual(load.metrics.model_ms);
  expect(JSON.stringify(load)).not.toContain('userAgent');
  const open=context.waitForEvent('page');await page.getByRole('link',{name:'使用体验',exact:true}).click();
  const stats=await open;await expect(stats.getByRole('heading',{name:'使用体验，持续记录。'})).toBeVisible();
  await stats.locator('[name=traffic]').selectOption('verification');
  await stats.locator('[name=page]').selectOption('home');
  await expect(stats.locator('#browser-experience')).toContainText('模型可见');
  await stats.close();
});

test('browser voice reports local and fallback timings from release, without speech content',async({page,context})=>{
  await context.grantPermissions(['microphone']);let owner,turnContext;
  const reports=[];page.on('request',r=>{if(r.method()==='POST'&&new URL(r.url()).pathname==='/api/experience')reports.push(r.postDataJSON())});
  await page.routeWebSocket('**/voice',socket=>{
    owner=socket;
    const send=d=>socket.send(JSON.stringify(d));
    socket.onMessage(raw=>{
      if(typeof raw!=='string')return;const d=JSON.parse(raw);
      if(d.type==='connect')send({type:'voice_status',state:'ready'});
      if(d.type==='listen_start'){turnContext=d.experience;send({type:'voice_status',state:'listening'})}
      if(d.type==='listen_stop'){
        send({type:'voice_status',state:'thinking'});
        setTimeout(()=>send({type:'transcript',role:'user',source:'local',text:'TEST PRIVATE UTTERANCE'}),30);
        setTimeout(()=>send({type:'voice_route',route:'cloud_fallback',reason:'unmatched'}),50);
        setTimeout(()=>send({type:'transcript',role:'user',text:'TEST PRIVATE UTTERANCE'}),90);
        setTimeout(()=>send({type:'voice_milestone',phase:'action_start'}),120);
        setTimeout(()=>{send({type:'audio',sample_rate:24000,pcm:Buffer.alloc(2880).toString('base64')});send({type:'playback_end',aborted:false});send({type:'voice_status',state:'ready'})},150);
      }
    });
  });
  await page.goto('/?room=2');await page.locator('#connect-voice').click();
  await expect(page.locator('#talk-button')).toBeEnabled();
  await page.locator('#talk-button').dispatchEvent('pointerdown',{pointerId:1});
  await expect(page.locator('#voice-badge')).toHaveText('正在聆听');
  await page.locator('#talk-button').dispatchEvent('pointerup',{pointerId:1});
  await expect.poll(()=>reports.flatMap(p=>p.events).some(e=>e.kind==='voice'&&e.status==='completed')).toBe(true);
  const result=reports.flatMap(p=>p.events).find(e=>e.kind==='voice'&&e.status==='completed');
  expect(result.id).toBe(turnContext.id);expect(result.route).toBe('cloud_fallback');
  expect(result.metrics.stt_local_ms).toBeGreaterThan(0);
  expect(result.metrics.stt_cloud_ms).toBeGreaterThan(result.metrics.stt_local_ms);
  expect(result.metrics.action_ms).toBeGreaterThan(result.metrics.stt_cloud_ms);
  expect(result.metrics.audio_ms).toBeGreaterThan(0);
  expect(JSON.stringify(reports)).not.toContain('PRIVATE UTTERANCE');
  owner.close();
});
