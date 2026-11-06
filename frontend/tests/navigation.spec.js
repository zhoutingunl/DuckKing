import {test,expect} from '@playwright/test';

test('all pages keep the same navigation, room, source link and language menu',async({page})=>{
 test.setTimeout(60000);
 const errors=[];page.on('pageerror',error=>errors.push(error.message));
 const labels=['首页','动作训练场','演示场景','现场互动','训练新动作','交互统计','使用体验','部署记录','源代码 ↗'];
 for(const name of ['index','training','seesaw','balance','scenarios','demos','studio','experience','statistics','deploys']){
  await page.goto(`/${name==='index'?'':name+'.html'}?room=1`);
  await expect(page.locator('.site-topbar nav a')).toHaveText(labels);
  await expect(page.locator('.site-topbar .brand')).toHaveAttribute('aria-label','DuckKing 首页');
  for(const link of await page.locator('.site-topbar nav a').all()){
   const url=new URL(await link.getAttribute('href'));
   if(url.origin!==new URL(page.url()).origin){
    expect(url.href).toBe('https://github.com/zhoutingunl/DuckKing');
    expect(url.searchParams.has('room')).toBe(false);
   }else if(!url.pathname.endsWith('deploys.html'))expect(url.searchParams.get('room')).toBe('1');
  }
  // 源代码在语言菜单之前，语言菜单贴右缘。
  const source=await page.locator('.home-nav .repo-link').boundingBox();
  const lang=await page.locator('.lang-switch').boundingBox();
  expect(source.x+source.width).toBeLessThanOrEqual(lang.x);
  const nav=await page.locator('.home-nav').boundingBox();
  expect(Math.abs(nav.x+nav.width-lang.x-lang.width)).toBeLessThan(2);
  await page.getByRole('link',{name:'首页',exact:true}).click();
  await expect(page).toHaveURL(/\/index\.html\?room=1$/);
  await expect(page.locator('.action-grid')).toBeVisible();
  await expect(page.getByRole('link',{name:'首页',exact:true})).toHaveAttribute('aria-current','page');
 }
 await page.setViewportSize({width:390,height:844});await page.goto('/seesaw.html?room=1');
 const source=await page.locator('.home-nav .repo-link').boundingBox();
 const lang=await page.locator('.lang-switch').boundingBox();
 const brand=await page.locator('.brand').boundingBox();
 expect(Math.abs(lang.y+lang.height/2-brand.y-brand.height/2)).toBeLessThan(5);
 expect(source.y).toBeGreaterThan(lang.y+lang.height);
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
 expect(errors).toEqual([]);
});
