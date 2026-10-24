import { test, expect } from '@playwright/test';

test('real MuJoCo left/right contacts, duo discovery/collision, chorus and stop',async({page})=>{
  test.setTimeout(90000);
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  let modelRequests=0;page.on('request',r=>{if(new URL(r.url()).pathname.endsWith('/api/scenes/model'))modelRequests++;});
  await page.goto('/scenarios.html?room=1');
  await page.getByRole('button',{name:'单鸭定点踢球'}).click();
  await expect(page.locator('#sim-status')).toHaveText('MuJoCo 物理运行中',{timeout:45000});
  await expect(page.locator('#scene-placeholder')).toBeHidden({timeout:20000});
  await page.getByRole('button',{name:'左脚踢球',exact:true}).click();
  await expect(page.locator('#action-result')).toContainText('左脚踢球 · 完成',{timeout:15000});
  await expect(page.locator('#ball-contact')).toHaveText('左脚');
  expect(parseFloat(await page.locator('#ball-distance').textContent())).toBeGreaterThan(.02);
  const requestsBeforeReset=modelRequests;
  await page.getByRole('button',{name:'重置场景',exact:true}).click();
  await expect(page.locator('#action-result')).toContainText('重置场景 · 完成');
  expect(modelRequests).toBe(requestsBeforeReset);
  await page.getByRole('button',{name:'右脚踢球',exact:true}).click();
  await expect(page.locator('#action-result')).toContainText('右脚踢球 · 完成',{timeout:15000});
  await expect(page.locator('#ball-contact')).toHaveText('右脚');
  await page.getByRole('button',{name:'双鸭互动',exact:false}).click();
  await expect(page.locator('#duo-controls')).toBeVisible();
  await page.getByRole('button',{name:'发现同伴',exact:true}).click();
  await expect(page.locator('#peer-status')).toContainText('鸭 A 发现鸭 B');
  await page.getByRole('button',{name:'相向碰面',exact:true}).click();
  await expect(page.locator('#action-result')).toContainText('相向碰面 · 完成',{timeout:15000});
  expect(Number(await page.locator('#duck-contact').textContent())).toBeGreaterThan(0);
  await page.getByRole('button',{name:'同步合唱 ♪'}).click();
  await expect(page.locator('#chorus-status')).toContainText('本地双声部正在合唱');
  await page.locator('#stop-scene').click();
  await expect(page.locator('#action-result')).toContainText('停止 · 完成');
  const state=await (await page.request.get('/api/scenes/state')).json();
  expect(state.backend.chorus).toBeNull();expect(state.backend.physics).toBe(true);
  expect(errors).toEqual([]);
  await page.setViewportSize({width:390,height:844});
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
});

test('physics startup failure is explicit and does not show a preview as success',async({page})=>{
  await page.route('**/api/scenes/start?*',route=>route.fulfill({status:503,json:{detail:'物理场景未就绪，请运行 scripts/setup_scenarios.sh'}}));
  await page.routeWebSocket('**/scene-ws',socket=>socket.send(JSON.stringify({type:'not_started'})));
  await page.goto('/scenarios.html?room=1');await page.getByRole('button',{name:'单鸭定点踢球'}).click();
  await expect(page.locator('#notice')).toContainText('setup_scenarios.sh');
  await expect(page.locator('#sim-status')).toHaveText('物理场景启动失败');
  await expect(page.locator('#stop-scene')).toBeDisabled();
});

test('a restarted server clears stale scene controls and measurements',async({page,request})=>{
  await request.post('/api/scenes/start',{data:{name:'scene_ball'}});
  const state=await (await request.get('/api/scenes/state')).json();
  let channel;
  await page.routeWebSocket('**/scene-ws',socket=>{channel=socket;socket.send(JSON.stringify({type:'state',...state}));});
  await page.goto('/scenarios.html?room=1');await expect(page.locator('#stop-scene')).toBeEnabled();
  channel.send(JSON.stringify({type:'not_started'}));
  await expect(page.locator('#stop-scene')).toBeDisabled();
  await expect(page.locator('#sim-status')).toHaveText('选择场景开始');
  await expect(page.locator('#ball-distance')).toHaveText('—');
});

test('a real origin rejection explains the local connection and recovers without Linx',async({page})=>{
  // Keep HTTP working, but send the socket to a different loopback hostname:
  // the actual backend must reject the mismatched Origin during its handshake.
  await page.addInitScript(()=>{
    window.sceneNativeWebSocket=window.WebSocket;
    window.WebSocket=new Proxy(window.WebSocket,{construct(Target,args){
      const url=new URL(args[0]);
      if(url.pathname==='/scene-ws'){url.hostname='localhost';args[0]=url.href;}
      return new Target(...args);
    }});
  });
  await page.goto('/scenarios.html?room=1');
  await expect(page.locator('#sim-status')).toHaveText('场景连接未建立 · 正在重试');
  await expect(page.locator('#notice')).toContainText('无需先连接灵矽');
  await expect(page.locator('#notice')).toContainText('Chrome 无痕窗口');
  await expect(page.getByRole('button',{name:'单鸭定点踢球'})).toBeDisabled();
  await expect(page.locator('#activity-log')).toContainText('握手未完成');
  await page.evaluate(()=>{window.WebSocket=window.sceneNativeWebSocket;});
  await expect(page.getByRole('button',{name:'单鸭定点踢球'})).toBeEnabled();
  await expect(page.locator('#notice')).toBeHidden();
});
