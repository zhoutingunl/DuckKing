import { test, expect } from '@playwright/test';

test('homepage opens real statistics API in a separate tab without disconnecting voice',async({page,context})=>{
  let disconnected = false;
  await page.routeWebSocket('**/voice',socket=>{
    socket.onClose(()=>{disconnected = true;});
    socket.onMessage(message=>{
      if(typeof message==='string'&&JSON.parse(message).type==='connect')socket.send(JSON.stringify({type:'voice_status',state:'ready'}));
    });
  });
  await page.goto('/?room=1');
  await page.locator('#connect-voice').click();
  await expect(page.locator('#voice-badge')).toHaveText('灵矽已连接');
  const opened = context.waitForEvent('page');
  await page.getByRole('link',{name:'交互统计'}).click();
  const stats = await opened;
  await expect(stats).toHaveURL(/\/statistics.html\?room=1$/);
  await expect(stats.getByRole('heading',{name:'一句话，花了多久？'})).toBeVisible();
  await expect(stats.locator('#stats-empty')).toBeVisible();
  await expect(stats.locator('#recognition-rate')).toHaveText('—');
  await expect(stats.locator('#backend-note')).toContainText('不进行物理仿真');
  expect(disconnected).toBe(false);
  await expect(page.locator('#talk-button')).toBeEnabled();
  await stats.setViewportSize({width:390,height:844});
  expect(await stats.evaluate(()=>document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await stats.close();
});

test('statistics renders labelled protocol fixtures, filters, selects rounds, and handles stale data',async({page,request})=>{
  const empty = await (await request.get('/api/voice/statistics')).json();
  const fixture = structuredClone(empty);
  fixture.rounds = [{turn:2,time:'2026-10-23T15:00:00Z',backend:'preview',status:'timeout',text:'协议测试：没有回复',timings:{listen_stop:1000},actions:[]},
    {turn:1,time:'2026-10-23T14:59:00Z',backend:'preview',status:'completed',text:'协议测试：前进再左转 <img src=x onerror=alert(1)>',timings:{listen_stop:1000,stt:1200,action_start:1500,first_audio:3300,reply_end:5000},actions:[{call:1,tool:'duck_walk_short',at_ms:1500,result:'completed',duration_ms:1200},{call:2,tool:'duck_turn_left',at_ms:2800,result:'completed',duration_ms:1200}]}];
  fixture.counts = {...fixture.counts,rounds:2,submitted:2,closed:2,cloud_closed:2,recognized:2,replied:1,timeouts:1,actions:2,finished_actions:2,completed_actions:2};
  fixture.latencies.stt = {count:1,p50_ms:200,p95_ms:200};
  fixture.routing.recognition_latency={local:{count:2,mean_ms:300,p50_ms:200,p90_ms:400,p95_ms:400},cloud:{count:1,mean_ms:800,p50_ms:800,p90_ms:800,p95_ms:800}};
  let failure = false;
  const queries = [];
  await page.route('**/api/voice/statistics?*',async route=>{
    const backend = new URL(route.request().url()).searchParams.get('backend');
    queries.push(backend);
    if(failure)await route.fulfill({status:503,body:'unavailable'});
    else await route.fulfill({json:backend==='robotd'?empty:fixture});
  });
  await page.goto('/statistics.html');
  await expect(page.locator('#reply-rate')).toHaveText('50.0%');
  await expect(page.locator('#recognition-latency')).toContainText('300 ms');
  await expect(page.locator('#recognition-latency')).toContainText('800 ms');
  await expect(page.locator('#round-label')).toContainText('第 2 轮');
  await expect(page.locator('#latency-rows')).toContainText('200 ms');
  await page.getByRole('button',{name:'查看第 1 轮时间线'}).click();
  await expect(page.locator('#round-text')).toContainText('<img src=x onerror=alert(1)>');
  expect(await page.locator('#round-text img').count()).toBe(0);
  await expect(page.locator('#round-timeline')).toContainText('前进受理');
  await expect(page.locator('#round-timeline')).toContainText('左转受理');
  await expect(page.locator('#round-timeline')).toContainText('500 ms');
  failure = true;
  await page.getByRole('button',{name:'刷新',exact:true}).click();
  await expect(page.locator('#stats-error')).toContainText('已有数值未更新');
  await expect(page.locator('#reply-rate')).toHaveText('50.0%');
  failure = false;
  await page.locator('#backend-filter').selectOption('robotd');
  await expect(page.locator('#stats-empty')).toBeVisible();
  await expect(page.locator('#stats-error')).toBeHidden();
  expect(queries).toContain('robotd');
});
