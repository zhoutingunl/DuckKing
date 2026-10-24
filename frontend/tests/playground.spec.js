import { test, expect } from '@playwright/test';

test('preview actions reach the backend and stop cancels a running walk', async ({page})=>{
  await page.goto('/?room=1');
  await expect(page.getByText('本地工作台已连接')).toBeVisible();
  await expect(page.locator('#backend-badge')).toHaveText('动画预览');
  const acceptedNod=page.waitForResponse(response=>new URL(response.url()).pathname.endsWith('/api/actions')&&response.request().postDataJSON().name==='nod');
  await page.locator('[data-action="nod"]').click();
  const nodId=(await (await acceptedNod).json()).id;
  await expect.poll(async()=> (await (await page.request.get(`/api/actions/${nodId}`)).json()).status).toBe('completed');
  await expect(page.locator('#activity-log')).toContainText('点头 · completed');
  // Keep the production bounds; use the supported 3s duration to avoid testing a
  // renderer scheduling race on CPU-only CI runners.
  await page.route('**/api/actions?*',async route=>{
    const data=route.request().postDataJSON();
    await route.continue({postData:JSON.stringify(data.name==='walk'?{...data,duration:3}:data)});
  });
  await Promise.all([
    page.waitForResponse(response=>new URL(response.url()).pathname.endsWith('/api/actions')&&response.request().postDataJSON().name==='walk'),
    page.locator('[data-action="walk"]').click(),
  ]);
  await page.keyboard.press('Escape');
  await expect(page.locator('#current-action')).toHaveText('待机');
  await expect(page.locator('#activity-log')).toContainText('cancelled');
  await expect(page.locator('#scope-note')).toContainText('不进行物理计算');
});

test('mobile controls fit the viewport and are operable',async({page})=>{
  await page.setViewportSize({width:390,height:844});
  await page.goto('/?room=1');
  await expect(page.getByText('本地工作台已连接')).toBeVisible();
  const accepted=page.waitForResponse(response=>new URL(response.url()).pathname.endsWith('/api/actions')&&response.request().postDataJSON().name==='nod');
  await page.locator('[data-action="nod"]').click();
  const id=(await (await accepted).json()).id;
  await expect.poll(async()=> (await (await page.request.get(`/api/actions/${id}`)).json()).status).toBe('completed');
  expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
});

test('action errors stay readable and a failed request does not block the next action',async({page})=>{
  await page.goto('/?room=1');
  await page.route('**/api/actions?*',route=>route.fulfill({status:503,contentType:'text/plain',body:'Service unavailable'}));
  await page.locator('[data-action="nod"]').click();
  await expect(page.locator('#notice')).toContainText('HTTP 503');
  await page.unroute('**/api/actions?*');
  await page.route('**/api/actions?*',route=>route.fulfill({status:409,json:{detail:'测试：动作请求冲突'}}));
  await page.locator('[data-action="nod"]').click();
  await expect(page.locator('#notice')).toHaveText('测试：动作请求冲突');
  await page.unroute('**/api/actions?*');
  const accepted=page.waitForResponse(response=>new URL(response.url()).pathname.endsWith('/api/actions'));
  await page.locator('[data-action="nod"]').click();
  const id=(await (await accepted).json()).id;
  await expect.poll(async()=> (await (await page.request.get(`/api/actions/${id}`)).json()).status).toBe('completed');
});
