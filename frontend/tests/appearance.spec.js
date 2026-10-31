import {test,expect} from '@playwright/test';

test('official colours repaint the home canvas without reloading geometry, persist and fit mobile',async({page},testInfo)=>{
  test.setTimeout(90000);
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  let assets=0;page.on('request',r=>{if(r.url().includes('.dkm.gz'))assets++});
  await page.goto('/?room=1');
  const view=page.locator('#viewport');
  await expect(view).toHaveAttribute('data-model','official',{timeout:45000});
  const before=await view.locator('canvas').screenshot({path:testInfo.outputPath('cream-before.png')}),requests=assets;
  await view.getByRole('button',{name:'薰衣草紫 · Lavender',exact:true}).click();
  await expect(view.getByRole('button',{name:'薰衣草紫 · Lavender',exact:true})).toHaveAttribute('aria-pressed','true');
  await expect.poll(async()=>!before.equals(await view.locator('canvas').screenshot()),{timeout:20000}).toBe(true);
  expect(assets).toBe(requests);
  await page.screenshot({path:testInfo.outputPath('lavender-home.png'),fullPage:true});
  await page.reload();await expect(view).toHaveAttribute('data-model','official',{timeout:20000});
  await expect(view.getByRole('button',{name:'薰衣草紫 · Lavender',exact:true})).toHaveAttribute('aria-pressed','true');
  await page.setViewportSize({width:390,height:844});
  await view.getByRole('button',{name:'天空蓝 · Sky',exact:true}).click();
  await expect(view.getByRole('button',{name:'天空蓝 · Sky',exact:true})).toHaveAttribute('aria-pressed','true');
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  await view.screenshot({path:testInfo.outputPath('sky-home-mobile.png')});
  expect(errors).toEqual([]);
});

test('four physical ducks keep distinct identities and repaint independently without motion or reload',async({page},testInfo)=>{
  // Two real scene loads plus desktop/mobile captures share this total budget.
  // Keep the shorter per-load and first-render deadlines below unchanged.
  test.setTimeout(180000);
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  let assets=0,commands=0;page.on('request',r=>{
    if(r.url().includes('.dkm.gz'))assets++;
    if(r.method()==='POST'&&r.url().includes('/api/scenes/'))commands++;
  });
  await page.goto('/demos.html?room=1');
  await expect(page.locator('.program-item')).toHaveCount(13);
  await page.selectOption('#stage-play','interactive');await page.locator('[data-demo=stage]').click();
  await expect(page.locator('#show-status')).toContainText('现场互动已就绪',{timeout:45000});
  const view=page.locator('#demo-viewport');
  await view.scrollIntoViewIfNeeded();
  await expect(view).toHaveAttribute('data-rendered-scene','stage',{timeout:20000});
  const colours=()=>view.evaluate(el=>JSON.parse(el.dataset.colourways));
  expect(await colours()).toEqual({a:'cream',b:'graphite',c:'lavender',d:'sky'});
  await expect(view.locator('.appearance-swatch')).toHaveCount(4);
  await expect(view.getByRole('combobox',{name:'选择换色的小鸭'}).locator('option')).toHaveCount(4);
  await page.screenshot({path:testInfo.outputPath('four-official-colourways.png'),fullPage:true});
  const first=(await(await page.request.get('/api/scenes/state?room=1')).json()).backend;
  const requests=assets,actions=commands;
  await view.getByRole('combobox',{name:'选择换色的小鸭'}).selectOption('b');
  await view.getByRole('button',{name:'薰衣草紫 · Lavender',exact:true}).click();
  expect(await colours()).toEqual({a:'cream',b:'lavender',c:'lavender',d:'sky'});
  expect(assets).toBe(requests);expect(commands).toBe(actions);
  const next=(await(await page.request.get('/api/scenes/state?room=1')).json()).backend;
  expect(next.revision).toBe(first.revision);expect(next.physics).toBe(true);
  expect(next.ducks.map(d=>d.id)).toEqual(first.ducks.map(d=>d.id));
  await view.getByRole('button',{name:'石墨灰 · Graphite',exact:true}).click();
  await page.reload();
  await expect(page.locator('.program-item')).toHaveCount(13);
  await page.selectOption('#stage-play','interactive');await page.locator('[data-demo=stage]').click();
  await expect(page.locator('#show-status')).toContainText('现场互动已就绪',{timeout:45000});
  await view.scrollIntoViewIfNeeded();
  await expect(view).toHaveAttribute('data-rendered-scene','stage',{timeout:20000});
  await expect(view.locator('.duck-appearance')).toBeVisible({timeout:45000});
  expect(await colours()).toEqual({a:'cream',b:'graphite',c:'lavender',d:'sky'});
  await page.setViewportSize({width:390,height:844});
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  await view.screenshot({path:testInfo.outputPath('four-colours-mobile.png')});
  expect(errors).toEqual([]);
});
