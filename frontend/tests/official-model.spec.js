import { test, expect } from '@playwright/test';

test('homepage loads the official rig and still labels scripted motion as preview',async({page},testInfo)=>{
  test.setTimeout(60000);
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.goto('/?room=1');
  await expect(page.locator('#viewport')).toHaveAttribute('data-model','official',{timeout:45000});
  await expect(page.locator('#scope-note')).toContainText('官方 MicroDuck 外观');
  await expect(page.locator('#scope-note')).toContainText('不进行物理计算');
  await page.screenshot({path:testInfo.outputPath('official-home.png'),fullPage:true});
  await page.setViewportSize({width:390,height:844});
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  expect(errors).toEqual([]);
});

test('missing official visuals report failure and can be retried explicitly',async({page})=>{
  await page.route('**/api/models/microduck/manifest',route=>route.fulfill({status:503,json:{detail:'模型未安装'}}));
  await page.goto('/?room=1');
  await expect(page.locator('#viewport')).toHaveAttribute('data-model','failed');
  await expect(page.locator('.model-status')).toContainText('官方模型加载失败');
  await page.unroute('**/api/models/microduck/manifest');
  await page.getByRole('button',{name:'重新加载模型'}).click();
  await expect(page.locator('#viewport')).toHaveAttribute('data-model','official',{timeout:45000});
});

test('official model cache is shared by rooms and load timings reach the server',async({page})=>{
  test.setTimeout(60000);
  const timings=[];page.on('response',r=>{if(new URL(r.url()).pathname==='/api/models/load-metrics')timings.push(r.status())});
  await page.goto('/?room=1');await expect(page.locator('#viewport')).toHaveAttribute('data-model','official');
  const first=await page.locator('#viewport').evaluate(el=>JSON.parse(el.dataset.modelTiming));
  expect(first.result).toBe('ready');expect(first.encoded_bytes).toBeLessThan(4000000);
  await expect(page.locator('#activity-log')).toContainText('官方外观已显示');
  await page.goto('/?room=2');await expect(page.locator('#viewport')).toHaveAttribute('data-model','official');
  const second=await page.locator('#viewport').evaluate(el=>JSON.parse(el.dataset.modelTiming));
  expect(second.cache).toBe('persistent');expect(second.transfer_bytes).toBe(0);
  await expect.poll(()=>timings).toEqual([204,204]);
  const resources=await page.evaluate(()=>performance.getEntriesByType('resource').filter(r=>r.name.includes('.dkm.gz')).length);
  expect(resources).toBe(0);
});

test('corrupt cached geometry fails explicitly, is evicted, and retries the real model',async({page})=>{
  test.setTimeout(60000);
  await page.goto('/?room=1');await expect(page.locator('#viewport')).toHaveAttribute('data-model','official');
  await page.evaluate(async()=>{const cache=await caches.open('duckking-official-model-v1');for(const key of await cache.keys())await cache.put(key,new Response('invalid cached asset'))});
  await page.reload();await expect(page.locator('#viewport')).toHaveAttribute('data-model','failed');
  await expect(page.locator('#activity-log')).toContainText('官方外观加载失败');
  await page.getByRole('button',{name:'重新加载模型'}).click();
  await expect(page.locator('#viewport')).toHaveAttribute('data-model','official');
  expect(await page.locator('#viewport').evaluate(el=>JSON.parse(el.dataset.modelTiming).cache)).not.toBe('persistent');
});

test('unavailable persistent storage still loads the actual official asset',async({page})=>{
  await page.addInitScript(()=>{Object.defineProperty(window,'caches',{value:{open:()=>Promise.reject(new Error('Protocol fixture: storage denied'))}})});
  await page.goto('/?room=1');await expect(page.locator('#viewport')).toHaveAttribute('data-model','official');
  expect(await page.locator('#viewport').evaluate(el=>JSON.parse(el.dataset.modelTiming).result)).toBe('ready');
});

test('real beak contact, carry, release and scene controls',async({page},testInfo)=>{
  test.setTimeout(90000);
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.goto('/scenarios.html?room=1');
  await page.getByRole('button',{name:'嘴部搬运 · 实验'}).click();
  await expect(page.locator('#carry-controls')).toBeVisible({timeout:45000});
  await expect(page.locator('#scene-placeholder')).toBeHidden({timeout:20000});
  await expect(page.locator('[data-sim-action="carry"]')).toBeDisabled();
  await page.locator('[data-sim-action="pick_up"]').click();
  await expect(page.locator('#action-result')).toContainText('用嘴夹起 · 完成',{timeout:15000});
  await expect(page.locator('#grasp-phase')).toHaveText('夹持中');
  expect(parseFloat(await page.locator('#grasp-lift').textContent())).toBeGreaterThan(8);
  await page.screenshot({path:testInfo.outputPath('beak-holding.png'),fullPage:true});
  await page.locator('[data-sim-action="carry"]').click();
  await expect(page.locator('#action-result')).toContainText('夹持搬运 · 完成',{timeout:15000});
  expect(parseFloat(await page.locator('#grasp-distance').textContent())).toBeGreaterThan(10);
  await page.locator('[data-sim-action="put_down"]').click();
  await expect(page.locator('#action-result')).toContainText('放下物品 · 完成',{timeout:15000});
  await expect(page.locator('#grasp-phase')).toHaveText('已放稳');
  await page.screenshot({path:testInfo.outputPath('beak-released.png'),fullPage:true});
  expect(errors).toEqual([]);
});
