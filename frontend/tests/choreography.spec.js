import { test, expect } from '@playwright/test';

test('named choreographies run real backend phases and return to neutral',async({page})=>{
  const frames=[];
  page.on('websocket',ws=>{
    if(!ws.url().endsWith('/ws'))return;
    ws.on('framereceived',event=>{
      if(typeof event.payload==='string')frames.push(JSON.parse(event.payload));
    });
  });
  await page.goto('/?room=1');
  await expect(page.getByText('本地工作台已连接')).toBeVisible();
  for(const [name,label,phase] of [['flash_step','闪身步','回闪'],['bear_shake','狗熊哆嗦毛','抖毛']]){
    const responsePromise=page.waitForResponse(response=>new URL(response.url()).pathname.endsWith('/api/actions')&&response.request().postDataJSON().name===name);
    await page.locator(`[data-action="${name}"]`).click();
    const id=(await (await responsePromise).json()).id;
    await expect.poll(async()=> (await (await page.request.get(`/api/actions/${id}`)).json()).status).toBe('completed');
    await expect(page.locator('#activity-log')).toContainText(`${label} · ${phase}`);
  }
  expect(frames.some(f=>Math.abs(f.backend?.velocity?.lateral??0)>.1)).toBe(true);
  expect(frames.some(f=>Math.abs(f.backend?.pose?.body_roll??0)>.04)).toBe(true);
  const state=await (await page.request.get('/api/state')).json();
  expect(state.backend.pose.body_z).toBe(0);
  expect(state.backend.pose.head_yaw).toBe(0);
  await expect(page.locator('#current-action')).toHaveText('待机');
});

test('mobile names fit and Escape cancels a choreography',async({page})=>{
  await page.setViewportSize({width:390,height:844});
  await page.goto('/?room=1');
  const accepted=page.waitForResponse(response=>new URL(response.url()).pathname.endsWith('/api/actions')&&response.request().postDataJSON().name==='bear_shake');
  await page.locator('[data-action="bear_shake"]').click();
  const id=(await (await accepted).json()).id;
  await page.keyboard.press('Escape');
  await expect.poll(async()=> (await (await page.request.get(`/api/actions/${id}`)).json()).status).toBe('cancelled');
  expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
});
