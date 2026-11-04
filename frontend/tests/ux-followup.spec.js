import {test,expect} from '@playwright/test';

// Protocol fixtures exercise browser state only; these are not Linx acceptance tests.
async function voiceFixture(page,endpoint='voice',mode='cloud'){
  let socket,generation=0;const commands=[];
  const send=data=>socket.send(JSON.stringify({generation,...data}));
  await page.routeWebSocket(`**/${endpoint}`,ws=>{socket=ws;ws.onMessage(message=>{
    if(typeof message!=='string')return;const data=JSON.parse(message);commands.push(data.type);
    if(data.type==='connect')send({type:'voice_status',state:'ready',mode});
    if(data.type==='listen_start')send({type:'voice_status',state:'listening',mode});
    if(data.type==='listen_stop')send({type:'voice_status',state:'ready',mode});
    if(data.type==='disconnect')send({type:'voice_status',state:'disconnected',mode});
  })});
  return {commands,send,setGeneration:value=>{generation=value}};
}

for(const failure of ['network','http500'])test(`scene ${failure} recovery reloads geometry without replaying preparation`,async({page,context,request})=>{
  test.setTimeout(60000);await context.grantPermissions(['microphone']);
  await request.post('/api/scenes/close?room=1');
  const voice=await voiceFixture(page,'scene-voice');let fail=true,attempts=0,release;
  const gate=new Promise(resolve=>{release=resolve}),starts=[];
  page.on('request',r=>{if(r.method()==='POST'&&new URL(r.url()).pathname==='/api/scenes/start')starts.push(r.postDataJSON())});
  await page.route('**/api/scenes/model.dkm.gz?*',async route=>{
    attempts++;if(attempts===1)await gate;
    if(!fail)return route.continue();
    if(failure==='network')await route.abort();else await route.fulfill({status:500,body:'test failure'});
  });
  try{
    await page.goto('/scenarios.html?room=1');await page.locator('[data-scene="ball"]').click();
    await expect.poll(()=>attempts,{timeout:30000}).toBe(1);
    await page.locator('#connect-voice').click();await expect(page.locator('#voice-badge')).toHaveText('灵矽已连接');
    await expect(page.locator('#voice-caption')).toContainText('外观尚未就绪');
    await expect(page.locator('#talk-button')).toBeDisabled();await expect(page.locator('[data-sim-action="kick_left"]')).toBeDisabled();
    await expect(page.locator('#stop-scene')).toBeEnabled();await expect(page.locator('#release-scene')).toBeEnabled();
    await page.evaluate(()=>document.activeElement.blur());await page.keyboard.press('Space');
    expect(voice.commands).not.toContain('listen_start');
    await page.locator('#stop-scene').click();release();
    await expect(page.locator('#scene-placeholder')).toContainText('加载未完成');
    await expect(page.locator('#scene-placeholder')).not.toContainText('Failed to fetch');
    await expect(page.locator('#notice')).not.toContainText('Failed to fetch');
    const before=await (await request.get('/api/scenes/state?room=1')).json();
    fail=false;await page.getByRole('button',{name:'重新加载模型',exact:true}).click();
    await expect(page.locator('#scene-placeholder')).toBeHidden({timeout:30000});
    await expect(page.locator('[data-sim-action="kick_left"]')).toBeEnabled();await expect(page.locator('#talk-button')).toBeEnabled();
    expect(starts).toHaveLength(1);
    const after=await (await request.get('/api/scenes/state?room=1')).json();
    expect(after.backend.revision).toBe(before.backend.revision);expect(after.backend.sim_time).toBeGreaterThan(before.backend.sim_time);
    await page.locator('#talk-button').dispatchEvent('pointerdown',{pointerId:1});
    await expect.poll(()=>voice.commands.includes('listen_start')).toBe(true);
    await page.locator('#talk-button').dispatchEvent('pointerup',{pointerId:1});
  }finally{release();await page.close();await request.post('/api/scenes/close?room=1')}
});

test('cancelled scene download stays blocked and retries without restarting the world',async({page,request})=>{
  test.setTimeout(60000);await request.post('/api/scenes/close?room=1');let attempts=0,release;const gate=new Promise(resolve=>{release=resolve}),starts=[];
  page.on('request',r=>{if(r.method()==='POST'&&new URL(r.url()).pathname==='/api/scenes/start')starts.push(r.url())});
  await page.route('**/api/scenes/model.dkm.gz?*',async route=>{attempts++;if(attempts===1){await gate;await route.abort().catch(()=>{})}else await route.continue()});
  try{
    await page.goto('/scenarios.html?room=1');await page.locator('[data-scene="ball"]').click();await expect.poll(()=>attempts,{timeout:30000}).toBe(1);
    await page.getByRole('button',{name:'停止等待',exact:true}).click();release();
    await expect(page.locator('#scene-placeholder')).toContainText('已停止等待');await expect(page.locator('[data-sim-action="kick_left"]')).toBeDisabled();
    await page.waitForTimeout(400);expect(attempts).toBe(1);
    await page.getByRole('button',{name:'重新加载模型',exact:true}).click();await expect(page.locator('#scene-placeholder')).toBeHidden({timeout:30000});
    await expect(page.locator('[data-sim-action="kick_left"]')).toBeEnabled();expect(starts).toHaveLength(1);
  }finally{release();await page.close();await request.post('/api/scenes/close?room=1')}
});

test('Space preserves native controls and records only from the page or talk button',async({page,context})=>{
  await context.grantPermissions(['microphone']);const voice=await voiceFixture(page);
  await page.goto('/?room=1');await expect(page.locator('#connection-label')).toContainText('已连接');
  for(const selector of ['#enable-sound','[data-action="nod"]']){
    await page.locator(selector).evaluate(el=>{window.auditClicks=0;el.addEventListener('click',()=>window.auditClicks++)});
    await page.locator(selector).focus();await page.keyboard.press('Space');await expect.poll(()=>page.evaluate(()=>window.auditClicks)).toBe(1);
    await page.keyboard.press('Enter');await expect.poll(()=>page.evaluate(()=>window.auditClicks)).toBe(2);
  }
  await page.locator('#connect-voice').click();await expect(page.locator('#talk-button')).toBeEnabled();
  await page.locator('[data-action="nod"]').focus();await page.keyboard.press('Space');
  expect(voice.commands).not.toContain('listen_start');
  await page.evaluate(()=>{const edit=document.createElement('div');edit.contentEditable='true';edit.id='keyboard-edit';document.body.append(edit);edit.focus()});
  await page.keyboard.press('Space');expect(voice.commands).not.toContain('listen_start');
  expect(await page.locator('#keyboard-edit').textContent()).not.toBe('');
  for(const focus of ['body','#talk-button']){
    if(focus==='body')await page.evaluate(()=>document.activeElement.blur());else await page.locator(focus).focus();
    const count=voice.commands.filter(x=>x==='listen_start').length;
    await page.keyboard.down('Space');await expect.poll(()=>voice.commands.filter(x=>x==='listen_start').length).toBe(count+1);
    await page.keyboard.up('Space');await expect(page.locator('#talk-button')).not.toHaveClass(/recording/);
  }
});

test('routing follows fallback, new local turn, stale generation and disconnect',async({page,context})=>{
  await context.grantPermissions(['microphone']);await page.route('**/api/voice/modes*',r=>r.fulfill({json:{local_first:true,available:true}}));
  const voice=await voiceFixture(page,'voice','local_first');await page.goto('/?room=1');await page.locator('#connect-voice').click();await expect(page.locator('#talk-button')).toBeEnabled();
  voice.setGeneration(1);voice.send({type:'voice_status',state:'thinking',route:'local_recognizing'});voice.send({type:'voice_route',route:'cloud_fallback',reason:'unmatched'});voice.send({type:'voice_status',state:'connecting',route:'cloud_fallback'});
  await expect(page.locator('#voice-route')).toContainText('正在连接灵矽');
  voice.send({type:'voice_status',state:'speaking',route:'cloud_fallback'});await expect(page.locator('#voice-route')).toContainText('正在回复');
  voice.send({type:'voice_status',state:'ready',route:'cloud_fallback'});await expect(page.locator('#voice-route')).toHaveText('本轮由灵矽处理。');
  voice.setGeneration(2);voice.send({type:'voice_status',state:'listening',route:'local_recording'});await expect(page.locator('#voice-route')).not.toContainText('灵矽');
  voice.send({type:'voice_status',state:'thinking',route:'local_recognizing'});voice.send({type:'voice_route',route:'local',asr_ms:90});voice.send({type:'transcript',source:'local',role:'assistant',text:'本地已完成：点头'});voice.send({type:'voice_status',state:'ready',route:'local'});
  await expect(page.locator('#voice-route')).toHaveText('本地已完成：点头 · 本地反馈，本轮未调用灵矽。');
  voice.send({type:'voice_route',route:'cloud_fallback',generation:1});voice.send({type:'voice_status',state:'connecting',generation:1});
  await page.waitForTimeout(150);await expect(page.locator('#voice-route')).toContainText('本地已完成');
  await page.locator('#connect-voice').click();await expect(page.locator('#voice-badge')).toHaveText('语音未启用');await expect(page.locator('#voice-route')).not.toContainText('正在连接');await expect(page.locator('#voice-route')).not.toContainText('本地已完成');
});

test.describe('touch viewport',()=>{
test.use({isMobile:true,hasTouch:true});
for(const viewport of [{width:390,height:844},{width:430,height:932}])test(`mobile ${viewport.width} keeps the duck and stop beside speech and actions`,async({page,context},info)=>{
  await page.setViewportSize(viewport);await context.grantPermissions(['microphone']);const voice=await voiceFixture(page);
  await page.goto('/?room=1');await expect(page.locator('#viewport')).toHaveAttribute('data-model','official',{timeout:45000});
  await expect(page.locator('#connect-voice')).toBeInViewport();await expect(page.locator('.room-options')).toBeHidden();
  await page.screenshot({path:info.outputPath('mobile-first.png')});
  await page.locator('.room-toggle').click();await expect(page.locator('#create-room')).toBeVisible();await page.locator('.room-toggle').click();
  await page.locator('#connect-voice').click();await expect(page.locator('#talk-button')).toBeEnabled();
  for(const selector of ['#talk-button','[data-action="nod"]','.audio-details summary']){
    await page.locator(selector).scrollIntoViewIfNeeded();
    await expect(page.locator('#viewport')).toBeInViewport({ratio:1});await expect(page.locator('#mobile-stop')).toBeInViewport({ratio:1});
    if(selector==='#talk-button'){
      await page.locator(selector).tap();await expect.poll(()=>voice.commands.includes('listen_start')).toBe(true);
    }else await page.locator(selector).click();
    await expect(page.locator('#viewport')).toBeInViewport({ratio:1});
  }
  const accepted=page.waitForResponse(r=>new URL(r.url()).pathname==='/api/actions'&&r.request().postDataJSON()?.name==='stop');await page.locator('#mobile-stop').click();expect((await accepted).ok()).toBe(true);
  await page.locator('[data-action="nod"]').scrollIntoViewIfNeeded();await page.screenshot({path:info.outputPath('mobile-action.png')});
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
});
});

test('home and studio action results use Chinese while raw identifiers stay in details',async({page,request})=>{
  await page.goto('/?room=1');await page.locator('[data-action="nod"]').click();
  await expect.poll(()=>page.locator('#activity-log').innerText()).toContain('点头 · 已完成');
  expect(await page.locator('#activity-log').innerText()).not.toContain('completed');
  await page.locator('#activity-log .action-diagnostics').last().locator('summary').click();await expect(page.locator('#activity-log')).toContainText('nod · completed');
  // Use an actual physics frame and controlled action-result events; no cloud is claimed.
  await request.post('/api/scenes/start?room=1',{data:{name:'scene_ball'}});
  await expect.poll(async()=>{const r=await request.get('/api/scenes/state?room=1');return r.status()}).toBe(200);
  const state=await (await request.get('/api/scenes/state?room=1')).json();
  state.events=[{id:101,kind:'result',text:'tilt_head · completed',status:'completed'},{id:102,kind:'result',text:'walk · cancelled',status:'cancelled'},{id:103,kind:'result',text:'look_down · failed',status:'failed'}];
  await page.routeWebSocket('**/scene-ws',ws=>ws.send(JSON.stringify({type:'state',...state})));
  try{
    await page.goto('/studio.html?room=1');await expect.poll(()=>page.locator('#activity-log').innerText()).toContain('歪头 · 已完成');
    const text=await page.locator('#activity-log').innerText();expect(text).toContain('前进 · 已取消');expect(text).toContain('低头看 · 未完成');expect(text).not.toMatch(/tilt_head|cancelled|look_down/);
  }finally{await page.close();await request.post('/api/scenes/close?room=1')}
});
