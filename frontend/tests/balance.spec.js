import {test,expect} from '@playwright/test';

test('balance classroom explains signs, displays real record boundaries and fits a phone',async({page})=>{
 const errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto('/balance.html?room=1');
 await expect(page.locator('#training-phase')).toHaveText('本关尚无训练记录',{timeout:15000});
 await page.locator('[data-term=slip]').click();
 await expect(page.locator('#term-description')).toContainText('脚的速度减去盘面的速度');
 await page.locator('#example-advantage').fill('-1');
 await expect(page.locator('#example-result')).toContainText('对坏动作');
 await page.locator('[data-level="3"]').click();
 await expect(page.locator('[data-level="3"]')).toHaveAttribute('aria-pressed','true');
 await expect(page.locator('#start-training')).toBeDisabled();
 await page.setViewportSize({width:390,height:844});
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
 expect(errors).toEqual([]);
});

test('real disk renders, a missing policy stays explicit, stop and scene switching recover',async({page,request})=>{
 test.setTimeout(120000);
 const errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto('/balance.html?room=2');
 await page.locator('#prepare-balance').click();
 await expect(page.locator('#start-challenge')).toBeEnabled({timeout:45000});
 await expect(page.locator('#physics-viewport')).toHaveAttribute('data-rendered-scene','balance',{timeout:20000});
 await page.locator('#start-challenge').click();
 await expect(page.locator('#notice')).toContainText('尚无');
 await page.selectOption('#controller','baseline');
 await page.locator('#start-challenge').click();
 await expect(page.locator('#challenge-status')).toContainText('挑战中');
 await expect(page.locator('#disc-time')).not.toHaveText('0.0 s');
 await page.locator('#stop-balance').click();
 await expect(page.locator('#challenge-status')).toContainText('人为干预不计成功',{timeout:10000});
 const response=await request.post('/api/scenes/start?room=2',{data:{name:'scene_ball',request_id:crypto.randomUUID()}});
 expect(response.ok()).toBe(true);
 await page.locator('#prepare-balance').click();
 await expect(page.locator('#start-challenge')).toBeEnabled({timeout:45000});
 await expect(page.locator('#challenge-status')).toContainText('等待指令');
 expect(errors).toEqual([]);
});
