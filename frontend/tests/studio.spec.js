import {test,expect} from '@playwright/test';

test('live director cancels old plan and keeps prerecorded theatre available',async({page})=>{
 test.setTimeout(90000);
 const errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto('/studio.html?room=1');
 await page.locator('[data-studio=director]').click();
 await expect(page.locator('#scene-title')).toHaveText('临场小导演',{timeout:60000});
 await expect(page.locator('#physics-viewport canvas')).toBeVisible();
 await page.getByRole('button',{name:'排练：周一上班',exact:true}).click();
 await expect(page.locator('#task-status')).toContainText('正在执行');
 await page.getByRole('button',{name:'改成只用头',exact:true}).click();
 await expect(page.locator('#task-status')).toContainText('只用头部 · 已完成',{timeout:12000});
 const state=await page.request.get('/api/studio?room=1').then(r=>r.json());
 expect(state.task.results.map(r=>r.name)).toEqual(['tilt_head','look_down','shake_head']);
 expect(state.task.results.every(r=>r.status==='completed')).toBe(true);
 await page.getByRole('link',{name:'自动剧场',exact:true}).click();
 await expect(page.locator('#demo-mode option')).toHaveCount(2);
 expect(errors).toEqual([]);
});

test('mobile studio shows ten scenes and exposes honest audio audition',async({page})=>{
 test.setTimeout(90000);
 await page.setViewportSize({width:390,height:844});
 await page.goto('/studio.html?room=2');
 await expect(page.locator('[data-studio]')).toHaveCount(10);
 await page.locator('[data-studio=voice]').click();
 await expect(page.locator('#voice-lab')).toBeVisible({timeout:60000});
 await expect(page.locator('[data-voice-sample]')).toHaveCount(3);
 await expect(page.locator('#voice-lab')).toContainText('不是克隆后的实时回复');
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
});

test('conductor changes pending solo and gates audible part on actual standing',async({page})=>{
 test.setTimeout(90000);
 await page.goto('/studio.html?room=1');
 await page.locator('[data-studio=conductor]').click();
 await expect(page.locator('#scene-title')).toHaveText('评委当指挥',{timeout:60000});
 await page.getByRole('button',{name:'C 先唱，再 A',exact:true}).click();
 await expect.poll(async()=>{
  const s=await page.request.get('/api/scenes/state?room=1').then(r=>r.json());
  return s.backend.seated_choir?.phase==='solo'&&s.backend.seated_choir.solo==='c';
 },{timeout:12000,intervals:[100]}).toBe(true);
 await page.getByRole('button',{name:'下一位换 B',exact:true}).click();
 await expect(page.locator('#task-status')).toContainText('已完成',{timeout:22000});
 const music=JSON.parse(await page.locator('#physics-viewport').getAttribute('data-music-evidence'));
 expect([...new Set(music.map(n=>n.member))]).toEqual(['c','b']);
 const physical=await page.request.get('/api/scenes/state?room=1').then(r=>r.json());
 expect(physical.backend.seated_choir.completed_solos).toEqual(['c','b']);
});
