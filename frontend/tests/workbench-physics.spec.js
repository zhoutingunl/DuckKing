import {test, expect} from '@playwright/test';
import {existsSync} from 'node:fs';

test('workbench keeps training in the navigation and persists only manually chosen floor styles', async ({page}) => {
  await page.setViewportSize({width: 375, height: 812});
  await page.addInitScript(() => {
    Math.random = () => Number(sessionStorage.getItem('floor-test-draw') ?? '.65');
  });
  await page.goto('/index.html?room=1&lang=zh');
  const preview = page.locator('#viewport');
  await expect(page.locator('.balance-entry')).toHaveCount(0);
  await expect(page.locator('nav').getByRole('link', {name: '训练新动作'})).toHaveAttribute('href', /training\.html\?room=1$/);
  await expect(preview).toHaveAttribute('data-ground-style', 'track');
  await page.evaluate(() => sessionStorage.setItem('floor-test-draw', '.9'));
  await page.reload();
  await expect(preview).toHaveAttribute('data-ground-style', 'stage');
  await page.locator('#scene-settings-toggle').click();
  await page.locator('#ground-style').selectOption('wood');
  await expect(preview).toHaveAttribute('data-ground-style', 'wood');
  await page.reload();
  await expect(preview).toHaveAttribute('data-ground-style', 'wood');
  await page.goto('/features.html?room=1&lang=zh');
  await expect(page.locator('#ground-style')).toHaveValue('wood');
  await page.goto('/index.html?room=1&lang=zh');
  await page.locator('#scene-settings-toggle').click();
  await expect(page.locator('#ground-style')).toHaveValue('wood');
  await page.locator('#ground-style').selectOption('random');
  await expect(preview).toHaveAttribute('data-ground-style', 'stage');
  await page.locator('#scene-settings-toggle').click();
  await page.getByText('MuJoCo 平地动作', {exact: true}).click();
  for (const action of ['sit','roulade','hop','lift_left','recover_back','run','steps','try_trick','headstand','laugh']) {
    await expect(page.locator(`[data-flat-action=${action}]`)).toBeVisible();
  }
  await expect(page.locator('[data-flat-action^=stage_], [data-flat-action=duo_walk], [data-flat-action=collide], [data-flat-action=find_companion], [data-flat-action=chorus]')).toHaveCount(0);
  for (const viewport of [{width: 375, height: 812}, {width: 812, height: 375}]) {
    await page.setViewportSize(viewport);
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(viewport.width);
  }
});

test('workbench prepares once and keeps the same canvas, room and voice across single-duck actions', async ({page}) => {
  test.setTimeout(120000);
  const optional = existsSync(new URL('../../external/features/policies/hop/policy.onnx', import.meta.url));
  const voiceChannels = [], prepares = [], models = [];
  await page.routeWebSocket(/\/(?:scene-)?voice(?:\?|$)/, socket => {
    voiceChannels.push(new URL(socket.url()).pathname);
    socket.onMessage(message => {
      const {type} = JSON.parse(message);
      if (type === 'connect') socket.send(JSON.stringify({type: 'voice_status', state: 'ready'}));
      if (type === 'disconnect') socket.close();
    });
  });
  page.on('request', request => {
    const path = new URL(request.url()).pathname;
    if (path === '/api/features/prepare') prepares.push(request.postDataJSON().capability);
    if (path === '/api/scenes/model.dkm.gz') models.push(request.url());
  });
  await page.request.post('/api/scenes/close?room=1');
  try {
    await page.goto('/index.html?room=1&lang=zh');
    await expect(page.locator('#connection-label')).toHaveText('本地工作台已连接');
    expect((await page.request.get('/api/scenes/state?room=1')).status()).toBe(503);
    await page.locator('#scene-settings-toggle').click();
    await page.locator('#ground-style').selectOption('checker');
    await page.locator('#scene-settings-toggle').click();
    await page.getByText('MuJoCo 平地动作', {exact: true}).click();
    const stage = page.locator('#workbench-physics'), voice = page.locator('#connect-voice');
    async function perform(action, result, policy){
      const accepted = page.waitForResponse(response =>
        new URL(response.url()).pathname === '/api/features/command'
        && response.request().postDataJSON()?.action === action,
        {timeout: 85000});
      await page.locator(`[data-flat-action=${action}]`).click();
      const command = await accepted;
      expect(command.status()).toBe(202);
      await expect(stage).toBeInViewport();
      await expect(stage).toHaveAttribute('data-rendered-policy', policy);
      await expect(page.locator('#activity-log')).toContainText(result, {timeout: 12000});
      const {backend} = await (await page.request.get('/api/scenes/state?room=1')).json();
      expect(backend.revision).toBe(new URL(command.url()).searchParams.get('expected_revision'));
      expect(backend.ducks.map(duck => duck.id)).toEqual(['a']);
      const actionId = command.request().postDataJSON().request_id;
      expect(backend.feature.results.find(record => record.id === actionId)?.verified).toBe(true);
      return backend;
    }
    const first = await perform('sit', '坐下 · 已完成', 'movement');
    await stage.locator('canvas').evaluate(canvas => { window.firstWorkbenchCanvas = canvas; });
    await expect(stage).toHaveAttribute('data-ground-style', 'checker');
    await expect(page.locator('#viewport')).toBeHidden();
    await expect(page.locator('#backend-badge')).toHaveText('MuJoCo 仿真');

    await voice.click();
    await expect(voice).toHaveAttribute('data-state', 'ready');
    const next = optional
      ? await perform('recover_back', '仰卧起身 · 已完成', 'standup')
      : await perform('stand', '站起来 · 已完成', 'movement');
    expect(next.revision).toBe(first.revision);
    if(optional)expect((await perform('hop', '跳一下 · 已完成', 'hop')).revision).toBe(first.revision);
    else expect(next.feature.actions.hop.enabled).toBe(false);
    expect(prepares).toEqual(['workbench']);
    expect(models).toHaveLength(1);
    expect(await stage.locator('canvas').evaluate(canvas => window.firstWorkbenchCanvas === canvas)).toBe(true);
    expect(voiceChannels).toEqual(['/scene-voice']);
    await expect(voice).toHaveAttribute('data-state', 'ready');

    const stale = await page.request.post('/api/features/command?room=1&expected_revision=stale', {data: {action: 'nod'}});
    expect(stale.status()).toBe(409);
    await page.locator('#leave-physics').click();
    await expect(page.locator('#flat-action-notice')).toContainText('请先断开当前语音');
    await voice.click();
    await expect(voice).toHaveAttribute('data-state', 'disconnected');
    await page.locator('#leave-physics').click();
    await expect(page.locator('#backend-badge')).toHaveText('动画预览');
    expect((await page.request.get('/api/scenes/state?room=1')).status()).toBe(503);
    await voice.click();
    await expect(voice).toHaveAttribute('data-state', 'ready');
    expect(voiceChannels).toEqual(['/scene-voice', '/voice']);
  } finally {
    await page.request.post('/api/scenes/close?room=1');
  }
});

test('stopping while the scene prepares prevents the pending motion from starting', async ({page}) => {
  test.setTimeout(90000);
  await page.request.post('/api/scenes/close?room=1');
  const requests = [];
  const gate = Promise.withResolvers();
  await page.route('**/api/features/prepare?*', async route => {
    await gate.promise;
    await route.continue();
  });
  page.on('request', request => {
    const path = new URL(request.url()).pathname;
    if (path === '/api/scenes/actions' || path === '/api/features/command'){
      const body = request.postDataJSON();
      requests.push(body.name ?? body.action);
    }
  });
  try {
    await page.goto('/index.html?room=1&lang=zh');
    await page.getByText('MuJoCo 平地动作', {exact: true}).click();
    const preparing = page.waitForRequest(request => new URL(request.url()).pathname === '/api/features/prepare');
    await page.locator('[data-flat-action=sit]').click();
    await preparing;
    await page.keyboard.press('Escape');
    gate.resolve();
    await expect(page.locator('#workbench-physics-loading')).toContainText('已停止等待', {timeout: 45000});
    await expect(page.locator('#activity-log')).toContainText('停止已确认，场景保留');
    expect(requests).toEqual(['stop']);
    await expect(page.locator('#backend-badge')).toHaveText('MuJoCo 仿真');
    await expect(page.locator('#viewport')).toBeHidden();
  } finally {
    gate.resolve();
    await page.request.post('/api/scenes/close?room=1');
  }
});

test('an unavailable physical action stays in MuJoCo mode and displays the preparation error', async ({page}) => {
  await page.request.post('/api/scenes/close?room=1');
  await page.route('**/api/features/prepare?*', route => route.fulfill({
    status: 503, json: {detail: 'Missing jumping policy'},
  }));
  await page.goto('/index.html?room=1&lang=zh');
  await page.getByText('MuJoCo 平地动作', {exact: true}).click();
  await page.locator('[data-flat-action=hop]').click();
  await expect(page.locator('#workbench-physics-loading')).toContainText('Missing jumping policy');
  await expect(page.locator('#backend-badge')).toHaveText('MuJoCo 仿真');
  await expect(page.locator('#viewport')).toBeHidden();
  await expect(page.locator('#connect-voice')).toBeDisabled();
  await page.locator('#leave-physics').click();
  await expect(page.locator('#viewport')).toBeVisible();
  await expect(page.locator('#connect-voice')).toBeEnabled();
});
