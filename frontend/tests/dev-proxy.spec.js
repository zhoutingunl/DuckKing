import { test, expect } from '@playwright/test';
import { createServer, createLogger } from 'vite';

test('development proxy preserves HTTP origin checks and action bounds', async ({ request }) => {
  const foreign = await request.post('/api/actions', {
    headers: { Origin: 'https://untrusted.example' }, data: { name: 'walk' },
  });
  expect(foreign.status()).toBe(403);
  const invalid = await request.post('/api/actions', { data: { name: 'walk', duration: 999 } });
  expect(invalid.status()).toBe(422);
});

test('development proxy rejects foreign origins on both WebSockets', async ({ request }) => {
  for (const path of ['/ws', '/voice']) {
    const response = await request.get(path, { headers: {
      Origin: 'https://untrusted.example',
      Connection: 'Upgrade', Upgrade: 'websocket',
      'Sec-WebSocket-Version': '13', 'Sec-WebSocket-Key': 'dGhlIHNhbXBsZSBub25jZQ==',
    } });
    expect(response.status()).toBe(403);
  }
});

test('voice proxy reaches the local protocol without connecting to the cloud', async ({ page }) => {
  await page.goto('/index.html?room=1');
  const events = await page.evaluate(() => new Promise((resolve, reject) => {
    const events = [];
    const ws = new WebSocket(`ws://${location.host}/voice?room=1`);
    const timeout = setTimeout(() => { ws.close(); reject(new Error('Voice proxy timed out')); }, 5000);
    ws.onerror = () => { clearTimeout(timeout); reject(new Error('Voice proxy failed')); };
    ws.onmessage = event => {
      const data = JSON.parse(event.data);
      events.push(data);
      if (events.length === 1) ws.send(JSON.stringify({ type: 'listen_start' }));
      else { clearTimeout(timeout); ws.close(); resolve(events); }
    };
  }));
  expect(events[0]).toMatchObject({ type: 'voice_status', state: 'disconnected' });
  expect(events[1]).toMatchObject({ type: 'error', message: '请等待灵矽连接就绪或回答结束' });
});

test('unavailable API returns a proxy error and actionable feedback', async ({ request, page }) => {
  const server = await createServer({
    // Keep the project's actual proxy configuration, overriding only its target
    // with a port that cannot serve HTTP. Do not stop the shared test backend.
    customLogger: { ...createLogger(), error() {} },
    server: { port: 0, proxy: { '/api': { target: 'http://127.0.0.1:0' } } },
  });
  try {
    await server.listen();
    const response = await request.get(new URL('/api/health', server.resolvedUrls.local[0]).href);
    expect(response.status()).toBe(502);
    expect(await response.text()).not.toContain('"backend":"preview"');
    await page.goto(server.resolvedUrls.local[0]+'?room=1');
    await expect(page.locator('#room-label')).toHaveText('房间暂不可用');
    await expect(page.locator('#room-recovery')).toBeVisible();
    await expect(page.locator('#room-recovery')).toContainText('暂时无法连接服务，请稍后重试。');
    // Recovery freezes the entire workspace with inert; the individual button's
    // disabled attribute is no longer the mechanism that blocks stale actions.
    await expect(page.locator('.workspace')).toHaveAttribute('inert','');
    await page.locator('[data-action="nod"]').evaluate(button=>button.focus());
    expect(await page.locator('[data-action="nod"]').evaluate(button=>document.activeElement===button)).toBe(false);
    await expect(page.locator('#reconnect-room')).toBeEnabled();
    await page.locator('#reconnect-room').click();
    await expect(page.locator('#reconnect-room')).toHaveText('重试连接');
    await expect(page.locator('#room-recovery')).toBeVisible();
    await expect(page.locator('.workspace')).toHaveAttribute('inert','');
  } finally {
    await page.close();
    await server.close();
  }
});
