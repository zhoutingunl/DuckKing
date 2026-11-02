import {test,expect} from '@playwright/test';

test('all pages keep the same navigation, room and rightmost source link',async({page})=>{
 test.setTimeout(60000);
 const labels=['动作训练场','演示场景','现场互动','训练新动作','使用体验','交互统计','部署记录'];
 for(const name of ['index','training','seesaw','balance','scenarios','demos','studio','experience','statistics','deploys']){
  await page.goto(`/${name==='index'?'':name+'.html'}?room=1`);
  await expect(page.locator('.site-topbar nav a')).toHaveText(labels);
  await expect(page.locator('.site-topbar .brand')).toHaveAttribute('aria-label','DuckKing 首页');
  for(const link of await page.locator('.site-topbar nav a').all()){
   const url=new URL(await link.getAttribute('href'));
   if(!url.pathname.endsWith('deploys.html'))expect(url.searchParams.get('room')).toBe('1');
  }
  const source=await page.locator('.site-topbar > .repo-link').boundingBox();
  const nav=await page.locator('.site-topbar nav').boundingBox();
  expect(nav.x+nav.width).toBeLessThanOrEqual(source.x);
 }
 await page.setViewportSize({width:390,height:844});await page.goto('/seesaw.html?room=1');
 const source=await page.locator('.site-topbar > .repo-link').boundingBox();
 const nav=await page.locator('.site-topbar nav').boundingBox();
 expect(nav.y).toBeGreaterThanOrEqual(source.y+source.height);
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
});
