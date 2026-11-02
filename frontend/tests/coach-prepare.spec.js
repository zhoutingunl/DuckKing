import {test,expect} from '@playwright/test';

const selectors={balance:{prepare:'#prepare-balance',start:'#start-challenge',view:'#physics-viewport'},seesaw:{prepare:'#prepare',start:'#start',view:'#trained-viewport'}};
async function roomFor(request){const r=await request.post('/api/rooms/claim');expect(r.ok()).toBe(true);return (await r.json()).room}
async function state(request,room){return (await(await request.get(`/api/scenes/state?room=${room}`)).json()).backend}
test.afterEach(async({page,request})=>{
 const room=new URL(page.url()).searchParams.get('room');
 if(room)await request.post(`/api/scenes/close?room=${room}`);
});

for(const scene of ['balance','seesaw']){
 const ui=selectors[scene];
 test(`${scene} prepares on entry without a command, scroll or voice connection, and refresh preserves a run`,async({page,request})=>{
  test.setTimeout(60000);const room=await roomFor(request),commands=[],prepares=[],errors=[];
  page.on('pageerror',error=>errors.push(error.message));
  page.on('request',r=>{
   const url=new URL(r.url());
   if(r.method()==='POST'&&url.pathname.endsWith('/command'))commands.push(r.postDataJSON());
   if(url.pathname===`/api/${scene}/prepare`)prepares.push(url.searchParams.get('replace'));
  });
  await page.goto(`/${scene}.html?room=${room}`);
  await expect(page.locator(ui.start)).toBeEnabled({timeout:45000});
  await expect(page.locator(ui.view)).toHaveAttribute('data-rendered-scene',scene);
  expect(prepares).toEqual(['false']);expect(commands).toEqual([]);
  expect(await page.evaluate(()=>scrollY)).toBe(0);
  let b=await state(request,room);
  expect(b[scene].phase).toBe('idle');expect(b[scene].sim_time).toBe(0);
  await expect(page.locator('#voice-badge')).toHaveText('未连接灵矽');
  // Start via the real API, then reconnect a page while the same world runs.
  const body=scene==='balance'?{operation:'start',controller:'baseline',level:1,duration_seconds:20,seed:0}:{operation:'start',controller:'rule',mode:'compare',seed:0};
  expect((await request.post(`/api/${scene}/command?room=${room}`,{data:body})).ok()).toBe(true);
  await expect.poll(async()=> (await state(request,room))[scene].sim_time).toBeGreaterThan(.1);
  b=await state(request,room);const revision=b[scene].command_revision,time=b[scene].sim_time;
  await page.reload();await expect(page.locator(ui.start)).toBeEnabled({timeout:15000});
  const after=await state(request,room);
  expect(after[scene].command_revision).toBe(revision);expect(after[scene].sim_time).toBeGreaterThanOrEqual(time);
  expect(commands).toEqual([]);expect(prepares).toEqual(['false','false']);
  expect((await request.post(`/api/${scene}/command?room=${room}`,{data:{operation:'stop'}})).ok()).toBe(true);
  await page.goto(`/scenarios.html?room=${room}`);
  await expect(page.locator('#scene-title')).toHaveText(scene==='balance'?'本房间正在使用语音平衡教练':'本房间正在使用跷跷板教练');
  expect((await state(request,room)).scene).toBe(scene);expect(errors).toEqual([]);
 });

 test(`${scene} keeps an existing different scene until an explicit switch`,async({page,request})=>{
  test.setTimeout(60000);const room=await roomFor(request),other=scene==='balance'?'seesaw':'balance';
  expect((await request.post(`/api/${other}/prepare?room=${room}`,{data:{}})).ok()).toBe(true);
  const before=await state(request,room);
  await page.goto(`/${scene}.html?room=${room}`);
  await expect(page.locator(ui.prepare)).toHaveText(scene==='balance'?'切换为圆盘':'切换为跷跷板');
  await expect(page.locator(ui.start)).toBeDisabled();await expect(page.locator('#connect-voice')).toBeDisabled();
  await expect(page.locator('#notice')).toContainText('本房间已有其他场景');
  expect((await state(request,room)).revision).toBe(before.revision);
  expect((await state(request,room)).scene).toBe(other);
  await page.locator(ui.prepare).click();await expect(page.locator(ui.start)).toBeEnabled({timeout:45000});
  const after=await state(request,room);expect(after.scene).toBe(scene);expect(after[scene].phase).toBe('idle');
 });

 test(`${scene} exposes a retry after loading fails and never starts on retry`,async({page,request})=>{
  test.setTimeout(60000);const room=await roomFor(request);let prepares=0,commands=0;
  page.on('request',r=>{if(r.method()==='POST'&&new URL(r.url()).pathname.endsWith('/command'))commands++});
  await page.route(`**/api/${scene}/prepare?*`,route=>{
   prepares++;return prepares===1?route.fulfill({status:503,json:{detail:'加载暂时失败（测试注入）'}}):route.continue();
  });
  await page.goto(`/${scene}.html?room=${room}`);
  await expect(page.locator(ui.prepare)).toHaveText(/重试准备/);
  await expect(page.locator(ui.start)).toBeDisabled();await expect(page.locator('#connect-voice')).toBeDisabled();
  await expect(page.locator('#notice')).toContainText('加载暂时失败');
  await page.locator(ui.prepare).click();await expect(page.locator(ui.start)).toBeEnabled({timeout:45000});
  expect(prepares).toBe(2);expect(commands).toBe(0);
  expect((await state(request,room))[scene].phase).toBe('idle');
 });
}
