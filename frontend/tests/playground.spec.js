import { test, expect } from '@playwright/test';

test('preview actions reach the backend and stop cancels a running walk', async ({page})=>{
  await page.goto('/');
  await expect(page.getByText('本地工作台已连接')).toBeVisible();
  await expect(page.locator('#backend-badge')).toHaveText('动画预览');
  await page.locator('[data-action="nod"]').click();
  await expect(page.locator('#current-action')).toHaveText('点头');
  await expect(page.locator('#action-count')).toHaveText('01');
  await page.locator('[data-action="walk"]').click();
  await expect(page.locator('#current-action')).toHaveText('前进');
  await page.keyboard.press('Escape');
  await expect(page.locator('#current-action')).toHaveText('待机');
  await expect(page.locator('#activity-log')).toContainText('cancelled');
  await expect(page.locator('#scope-note')).toContainText('不进行物理计算');
});

test('mobile controls fit the viewport and are operable',async({page})=>{
  await page.setViewportSize({width:390,height:844});
  await page.goto('/');
  await expect(page.getByText('本地工作台已连接')).toBeVisible();
  const before = Number(await page.locator('#action-count').textContent());
  await page.locator('[data-action="nod"]').click();
  await expect(page.locator('#action-count')).toHaveText(String(before + 1).padStart(2,'0'));
  expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
});
