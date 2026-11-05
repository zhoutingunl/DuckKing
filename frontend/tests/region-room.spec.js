import {test,expect} from '@playwright/test';

test('French default selects a free French voice room or clearly warns on fallback',async({page})=>{
  const claims=[];
  await page.route('**/api/ui-preferences',route=>route.fulfill({json:{
    language:'fr',region:'FR',french_voice_available:true,
  }}));
  page.on('request',request=>{
    if(request.method()==='POST'&&new URL(request.url()).pathname==='/api/rooms/claim')
      claims.push(new URL(request.url()).searchParams.get('language'));
  });
  await page.goto('/?measurement=verification');
  await expect.poll(()=>claims.length).toBe(1);expect(claims[0]).toBe('fr');
  await expect(page.locator('#ui-language-toggle')).toHaveText('中文');
  // The test backend has no French agent pool; French UI remains available and
  // the per-room cloud voice language mismatch is disclosed.
  await expect(page.locator('#room-language-note')).toHaveText(
    'Interface en français ; la langue vocale dépend de l’agent configuré pour ce salon.'
  );
  await page.evaluate(()=>{
    const row=document.createElement('div'),value=document.createElement('span');
    row.className='log-line';value.textContent='点点头';row.append(value);
    document.querySelector('#activity-log').append(row);
    window.dispatchEvent(new CustomEvent('duckking-voice-state',{detail:{state:'ready',mode:'cloud',route:'cloud'}}));
  });
  await expect(page.locator('#activity-log .log-line').filter({hasText:'点点头'})).toBeVisible();
});

test('explicit Chinese override does not reserve a French voice room',async({page})=>{
  const claims=[];
  await page.route('**/api/ui-preferences',route=>route.fulfill({json:{
    language:'fr',region:'FR',french_voice_available:true,
  }}));
  page.on('request',request=>{
    if(request.method()==='POST'&&new URL(request.url()).pathname==='/api/rooms/claim')
      claims.push(new URL(request.url()).searchParams.get('language'));
  });
  await page.goto('/?lang=zh&measurement=verification');
  await expect.poll(()=>claims.length).toBe(1);expect(claims[0]).toBe('zh');
  await expect(page.locator('#ui-language-toggle')).toHaveText('FR');
  await expect(page.locator('#room-language-note')).toBeHidden();
});
