import {test,expect} from '@playwright/test';

test('functional catalogue prepares without starting, cancels, releases and reopens',async({page})=>{
 test.setTimeout(90000);
 const errors=[];page.on('pageerror',error=>errors.push(error.message));
 await page.request.post('/api/scenes/close?room=1');
 await page.goto('/features.html?room=1&lang=en');
 await expect(page.locator('[data-capability]')).toHaveCount(15);
 await expect(page.locator('#scene-placeholder')).toBeHidden({timeout:45000});
 await expect(page.locator('[data-feature-action=walk]')).toBeEnabled();
 const state=await (await page.request.get('/api/scenes/state?room=1')).json();
 expect(state.backend.scene).toBe('functional');expect(state.backend.feature.status).toBe('idle');
 await page.locator('#feature-duration').fill('10');
 await page.locator('[data-feature-action=walk]').click();
 await expect(page.locator('#task-status')).toHaveText(/Executing|Running|In progress|正在执行/,{timeout:5000});
 await page.locator('#stop-feature').click();
 await expect(page.locator('#task-status')).toHaveText('Task cancelled',{timeout:10000});
 await page.locator('#release-feature').click();
 await expect(page.locator('#scene-placeholder')).toBeVisible();
 await expect(page.locator('[data-feature-action=walk]')).toBeDisabled();
 await expect(page.locator('#scene-placeholder')).not.toContainText('first frame');
 await page.locator('#prepare-feature').click();
 await expect(page.locator('#scene-placeholder')).toBeHidden({timeout:45000});
 await page.setViewportSize({width:390,height:844});
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
 await page.locator('#feature-duration').scrollIntoViewIfNeeded();
 expect(await page.locator('#physics-viewport').evaluate(el=>el.getBoundingClientRect().bottom>0)).toBe(true);
 expect(errors).toEqual([]);
 await page.request.post('/api/scenes/close?room=1');
});

test('missing functional policy has a recovery action and no preview fallback',async({page})=>{
 await page.route('**/api/features/prepare?*',route=>route.fulfill({status:503,json:{detail:'Missing functional policy'}}));
 await page.goto('/features.html?room=1&lang=en');
 await expect(page.locator('#notice')).toHaveText('Missing functional policy');
 await expect(page.locator('[data-feature-action=walk]')).toBeDisabled();
 await expect(page.locator('#prepare-feature')).toBeEnabled();
 await expect(page.locator('#scene-placeholder')).toBeVisible();
});
