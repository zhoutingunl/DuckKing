import {test,expect} from '@playwright/test';

test('expired deep link offers one-click recovery and retains choice without replay',async({page})=>{
  const commands=[];page.on('request',r=>{if(r.method()==='POST'&&new URL(r.url()).pathname.includes('/api/scenes/'))commands.push(r.url())});
  await page.goto('/demos.html?room=99&demo=identity');
  await expect(page.locator('#room-recovery')).toBeVisible();
  await expect(page.locator('#room-recovery')).toContainText('不会自动重放');
  await page.locator('#reconnect-room').click();
  await expect.poll(()=>new URL(page.url()).searchParams.get('room')).not.toBe('99');
  expect(new URL(page.url()).searchParams.get('demo')).toBe('identity');
  await expect(page.locator('#room-recovery')).toBeHidden();
  await expect(page.locator('[data-demo="identity"]')).toHaveClass(/restored-choice/);
  await expect(page.locator('#show-status')).toContainText('手动开始');
  expect(commands).toEqual([]);
});

test('a visible page detects a restarted service and freezes controls until recovery',async({page})=>{
  await page.goto('/?room=1');await expect(page.locator('#connection-label')).toContainText('已连接');
  await page.route('**/api/rooms?*',async route=>{
    const response=await route.fetch(),data=await response.json();data.instance='different-service';
    await route.fulfill({response,json:data});
  },{times:1});
  await page.evaluate(()=>document.dispatchEvent(new Event('visibilitychange')));
  await expect(page.locator('#room-recovery')).toContainText('服务已更新');
  await expect(page.locator('.workspace')).toHaveAttribute('inert','');
  await expect(page.locator('#reconnect-room')).toBeEnabled();
});

test('waiting for a model stays visible, can cancel, and does not retry a cancellation',async({page})=>{
  let attempts=0,release;
  const gate=new Promise(resolve=>{release=resolve});
  await page.route('**/api/models/microduck/assets/**',async route=>{
    attempts++;
    if(attempts===1){await gate;await route.abort().catch(()=>{});}else await route.continue();
  });
  await page.goto('/?room=1');
  await expect.poll(()=>attempts).toBe(1);
  await expect(page.locator('.model-status')).toContainText('已等待');
  await page.getByRole('button',{name:'停止等待'}).click();release();
  await expect(page.locator('#viewport')).toHaveAttribute('data-model','cancelled');
  await page.waitForTimeout(400);expect(attempts).toBe(1);
  await page.getByRole('button',{name:'重新加载模型'}).click();
  await expect(page.locator('#viewport')).toHaveAttribute('data-model','official',{timeout:45000});
  expect(attempts).toBe(2);
});

test('a scenario click shows preparation immediately, before the start request returns',async({page,request})=>{
  const {room}=await (await request.post('/api/rooms')).json();
  let entered=false;
  await page.route('**/api/scenes/start?*',async route=>{
    entered=true;await new Promise(resolve=>setTimeout(resolve,1800));
    await route.fulfill({status:503,json:{detail:'测试：场景暂时不可用'}}).catch(()=>{});
  });
  await page.goto(`/scenarios.html?room=${room}`);
  await expect(page.locator('[data-scene="ball"]')).toBeEnabled();
  await page.locator('[data-scene="ball"]').click();
  await expect.poll(()=>entered).toBe(true);
  await expect(page.locator('#scene-placeholder')).toBeVisible();
  await expect(page.locator('#scene-placeholder')).toContainText('服务器正在准备物理场景');
  await expect(page.locator('#scene-placeholder')).toContainText('已等待');
  await expect(page.locator('#scene-placeholder')).toContainText('加载未完成');
  await expect(page.locator('#scene-placeholder').getByRole('button',{name:/重新加载/})).toBeEnabled();
  expect(new URL(page.url()).searchParams.get('scene')).toBe('ball');
});

test('720p homepage keeps the complete canvas above the fold',async({page},info)=>{
  await page.setViewportSize({width:1280,height:720});
  await page.goto('/?room=1');
  await expect(page.locator('#viewport')).toHaveAttribute('data-model','official',{timeout:45000});
  const box=await page.locator('#viewport').boundingBox();
  expect(box.height).toBeLessThanOrEqual(400);expect(box.y+box.height).toBeLessThanOrEqual(720);
  await page.screenshot({path:info.outputPath('home-720p.png')});
  await page.setViewportSize({width:390,height:844});
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
});

test('loading an existing scene does not swallow a new scene selection',async({page,request})=>{
  test.setTimeout(60000);
  await request.post('/api/scenes/start?room=1',{data:{name:'scene_duo'}});
  let models=0,release;
  const gate=new Promise(resolve=>{release=resolve});
  await page.route('**/api/scenes/model.dkm.gz?*',async route=>{
    models++;
    if(models===1){await gate;await route.abort().catch(()=>{});}else await route.continue();
  });
  try{
    await page.goto('/scenarios.html?room=1');
    await expect.poll(()=>models).toBe(1);
    // Multiple live snapshots used to disable the selector between pointer down/up.
    await page.waitForTimeout(250);
    await expect(page.locator('[data-scene="ball"]')).toBeEnabled();
    const accepted=page.waitForRequest(r=>r.method()==='POST'&&new URL(r.url()).pathname==='/api/scenes/start');
    await page.locator('[data-scene="ball"]').click();
    expect((await accepted).postDataJSON().name).toBe('scene_ball');release();
    await expect(page.locator('#posture-controls')).toBeVisible();
    await expect(page.locator('#scene-placeholder')).toBeHidden({timeout:30000});
    await expect(page.locator('[data-sim-action="sit"]')).toBeEnabled();
  }finally{release()}
});
