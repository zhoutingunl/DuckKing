import {test,expect} from '@playwright/test';

for(const locale of [
  {language:'fr',region:'FR',label:'Langue',name:'Français',note:'La voix française n’est pas configurée. Demande son activation ; aucun repli automatique vers le chinois.'},
  {language:'en',region:'US',label:'Language',name:'English',note:'English voice is not configured. Ask the administrator to enable it; Chinese is not used as a fallback.'},
]){
test(`${locale.name} default claims its language and clearly warns on voice fallback`,async({page})=>{
  const claims=[];
  await page.route('**/api/ui-preferences',route=>route.fulfill({json:{
    language:locale.language,region:locale.region,french_voice_available:true,english_voice_available:true,
  }}));
  page.on('request',request=>{
    if(request.method()==='POST'&&new URL(request.url()).pathname==='/api/rooms/claim')
      claims.push(new URL(request.url()).searchParams.get('language'));
  });
  await page.goto('/index.html?measurement=verification');
  await expect.poll(()=>claims.length).toBe(1);expect(claims[0]).toBe(locale.language);
  await expect(page.locator('html')).toHaveAttribute('lang',locale.language);
  await expect(page.locator('#lang-switch-button')).toHaveText(locale.label);
  await page.locator('#lang-switch-button').click();
  await expect(page.getByRole('menuitem',{name:locale.name,exact:true})).toHaveAttribute('aria-current','true');
  await page.locator('#lang-switch-button').click();
  // No language-specific agents are provisioned in this test backend.
  await expect(page.locator('#room-language-note')).toHaveText(locale.note);
  await page.evaluate(()=>{
    const row=document.createElement('div'),value=document.createElement('span');
    row.className='log-line';value.textContent='点点头';row.append(value);
    document.querySelector('#activity-log').append(row);
    window.dispatchEvent(new CustomEvent('duckking-voice-state',{detail:{state:'ready',mode:'cloud',route:'cloud'}}));
  });
  await expect(page.locator('#activity-log .log-line').filter({hasText:'点点头'})).toBeVisible();
});

test(`explicit Chinese override does not claim the ${locale.name} voice room`,async({page})=>{
  const claims=[];
  await page.route('**/api/ui-preferences',route=>route.fulfill({json:{
    language:locale.language,region:locale.region,french_voice_available:true,english_voice_available:true,
  }}));
  page.on('request',request=>{
    if(request.method()==='POST'&&new URL(request.url()).pathname==='/api/rooms/claim')
      claims.push(new URL(request.url()).searchParams.get('language'));
  });
  await page.goto('/index.html?lang=zh&measurement=verification');
  await expect.poll(()=>claims.length).toBe(1);expect(claims[0]).toBe('zh');
  await expect(page.locator('html')).toHaveAttribute('lang','zh-CN');
  await expect(page.locator('#lang-switch-button')).toHaveText('语言');
  await page.locator('#lang-switch-button').click();
  await expect(page.getByRole('menuitem',{name:'中文',exact:true})).toHaveAttribute('aria-current','true');
  await expect(page.locator('#room-language-note')).toBeHidden();
});
}

test('language menu saves each choice across reloads and preserves the selected room',async({page})=>{
  await page.goto('/index.html?room=1&lang=zh&measurement=verification');
  await expect(page.locator('html')).toHaveAttribute('lang','zh-CN');
  for(const [language,name,htmlLang] of [['en','English','en'],['fr','Français','fr'],['zh','中文','zh-CN']]){
    await page.locator('#lang-switch-button').click();
    await page.getByRole('menuitem',{name,exact:true}).click();
    await expect(page.locator('.lang-menu')).toBeHidden();
    await expect(page.locator('html')).toHaveAttribute('lang',htmlLang);
    const url=new URL(page.url());
    expect(url.searchParams.get('room')).toBe('1');
    expect(url.searchParams.has('lang')).toBe(false);
    expect(await page.evaluate(()=>localStorage.getItem('duckking-ui-language'))).toBe(language);
    await page.reload();
    await expect(page.locator('html')).toHaveAttribute('lang',htmlLang);
  }
});
