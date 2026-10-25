import {test,expect} from '@playwright/test';

const sha=letter=>letter.repeat(40);
function fixture(){
  const coverage={commit:sha('e'),scope:'backend',source_url:'https://github.com/zhoutingunl/DuckKing/actions/runs/123',lines:{covered:3187,total:3281},branches:{covered:1069,total:1144}};
  const record={version:'deploy-test',commit:sha('e'),previous_commit:sha('b'),ts:'2026-10-25T12:00:00Z',status:'success',selftest:'passed',target:'yzh737',operator:'fixture',change_state:'available',change_count:5,coverage,
    changes:['e','d','c','b','a'].map(letter=>({commit:sha(letter),subject:letter==='a'?'<img src=x onerror="window.injected=true">':`change ${letter}`}))};
  return {state:'ok',current:record,warnings:[],records:[record,{...record,version:'old-release',coverage:null,changes:[],change_state:'unavailable',change_count:null},{...record,version:'different-commit',commit:sha('f'),changes:[],change_state:'identical',change_count:0},{...record,version:'rollback',commit:sha('b'),previous_commit:sha('e'),changes:[],change_state:'rollback',change_count:0,coverage:null}]};
}

test('deployment changes and coverage use safe links, retain expanded history and distinguish missing reports',async({page})=>{
  await page.route('**/api/deployments*',route=>route.fulfill({json:fixture()}));
  await page.goto('/deploys.html');
  for(const name of ['变更提交','行覆盖率','分支覆盖率'])await expect(page.getByRole('columnheader',{name,exact:true})).toBeVisible();
  const rows=page.locator('#deploy-rows tr'),current=rows.first();
  await expect(rows).toHaveCount(4);
  await expect(current.locator('.coverage-value')).toHaveText(['97.14%','93.44%']);
  await expect(current.locator('.coverage-value').first()).toHaveAttribute('href','https://github.com/zhoutingunl/DuckKing/actions/runs/123');
  await expect(current.locator('.compare-link')).toHaveAttribute('href',`https://github.com/zhoutingunl/DuckKing/compare/${sha('b')}...${sha('e')}`);
  await expect(rows.nth(1).locator('.deploy-coverage')).toHaveText(['未记录','未记录']);
  await expect(rows.nth(2).locator('.deploy-coverage')).toHaveText(['未记录','未记录']);
  await expect(rows.nth(3).locator('.compare-link')).toHaveAttribute('href',`https://github.com/zhoutingunl/DuckKing/compare/${sha('b')}...${sha('e')}`);
  await expect(rows.nth(3)).toContainText('被回退的提交');
  await current.locator('summary').click();
  await expect(current.locator('.deploy-changes')).toContainText('<img src=x');
  await expect(current.locator('.deploy-changes img')).toHaveCount(0);
  await page.locator('#refresh-deploys').click();
  await expect(current.locator('details')).toHaveAttribute('open','');
  expect(await page.evaluate(()=>window.injected)).toBeUndefined();
});

test('mobile release journal scrolls inside the table and handles legacy rows',async({page})=>{
  await page.setViewportSize({width:390,height:844});
  const data=fixture();delete data.records[1].changes;delete data.records[1].change_state;
  await page.route('**/api/deployments*',route=>route.fulfill({json:data}));
  await page.goto('/deploys.html');
  await expect(page.locator('#deploy-rows tr')).toHaveCount(4);
  await expect(page.locator('#deploy-rows tr').nth(1)).toContainText('尚未记录变更提交');
  const dimensions=await page.evaluate(()=>({page:document.documentElement.scrollWidth,viewport:innerWidth,table:document.querySelector('.table-scroll').scrollWidth,container:document.querySelector('.table-scroll').clientWidth}));
  expect(dimensions.page).toBeLessThanOrEqual(dimensions.viewport);
  expect(dimensions.table).toBeGreaterThan(dimensions.container);
});
