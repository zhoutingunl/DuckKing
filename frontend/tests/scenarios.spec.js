import { test, expect } from '@playwright/test';

test('real MuJoCo left/right contacts, duo discovery/collision, chorus and stop',async({page})=>{
  test.setTimeout(90000);
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  const measurements=[];page.on('request',r=>{if(r.method()==='POST'&&new URL(r.url()).pathname==='/api/experience')measurements.push(...r.postDataJSON().events)});
  let modelRequests=0;page.on('request',r=>{if(new URL(r.url()).pathname.endsWith('/api/scenes/model.dkm.gz'))modelRequests++;});
  await page.goto('/scenarios.html?room=1');
  await page.getByRole('button',{name:'单鸭定点踢球'}).click();
  await expect(page.locator('#sim-status')).toHaveText('MuJoCo 物理运行中',{timeout:45000});
  await expect(page.locator('#scene-placeholder')).toBeHidden({timeout:20000});
  await expect.poll(()=>measurements.some(e=>e.kind==='load'&&e.status==='completed'&&e.scene==='ball'&&e.metrics.scene_ms>0)).toBe(true);
  await page.getByRole('button',{name:'左脚踢球',exact:true}).click();
  await expect(page.locator('#action-result')).toContainText('左脚踢球 · 完成',{timeout:15000});
  await expect(page.locator('#ball-contact')).toHaveText('左脚');
  expect(parseFloat(await page.locator('#ball-distance').textContent())).toBeGreaterThan(.02);
  expect(modelRequests).toBeGreaterThan(0);
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
  const requestsBeforeReload=modelRequests;
  await page.reload();await expect(page.locator('#scene-placeholder')).toBeHidden({timeout:15000});
  expect(modelRequests).toBe(requestsBeforeReload);
  expect(JSON.parse(await page.locator('#physics-viewport').getAttribute('data-model-timing')).cache).toBe('persistent');
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

test('scene recovery clears stale failures without hiding an unrelated voice error',async({page,request})=>{
  await request.post('/api/scenes/start',{data:{name:'scene_ball'}});
  const actual=await (await request.get('/api/scenes/state')).json();
  const geometry=await (await request.get('/api/scenes/model.dkm.gz')).body();
  // Protocol fixtures reproduce failed discovery followed by success. These are
  // display/lifecycle checks, not evidence of a physical discovery or cloud call.
  const state={type:'state',action:null,error:null,events:[],backend:{scene:'duo',revision:actual.backend.revision,
    ball:null,grasp:null,discovered:[],contacts:{ducks:0},real_time_factor:1,error:null,chorus:null,ducks:[],geoms:[]}};
  let channel;
  await page.route('**/api/scenes/model.dkm.gz?*',route=>route.fulfill({body:geometry,contentType:'application/octet-stream'}));
  await page.routeWebSocket('**/scene-ws',socket=>{channel=socket;socket.send(JSON.stringify(state))});
  await page.routeWebSocket('**/scene-voice',socket=>socket.onMessage(message=>{
    if(typeof message==='string'&&JSON.parse(message).type==='connect'){
      socket.send(JSON.stringify({type:'voice_status',state:'busy',error:'协议测试：本房间语音正在使用'}));socket.close();
    }
  }));
  const send=()=>channel.send(JSON.stringify(state));
  await page.goto('/scenarios.html?room=1');await expect(page.locator('#scene-placeholder')).toBeHidden();
  state.error='视野内没有发现同伴';
  state.events=[{id:1,kind:'result',text:'find_companion · failed',status:'failed'}];send();
  await expect(page.locator('#notice')).toHaveText(state.error);
  state.error=null;state.backend.discovered=[{observer:'a',peer:'b',distance_m:.17}];
  state.events.push({id:2,kind:'result',text:'find_companion · completed',status:'completed'});send();
  await expect(page.locator('#peer-status')).toContainText('鸭 A 发现鸭 B，相距 0.17 m');
  await expect(page.locator('#action-result')).toHaveText('发现同伴 · 完成');
  await expect(page.locator('#notice')).toBeHidden();
  await expect(page.locator('#activity-log')).toContainText('发现同伴 · 未完成');
  state.backend.error='协议测试：物理推进异常';send();
  await expect(page.locator('#notice')).toHaveText(state.backend.error);
  state.backend.error=null;send();await expect(page.locator('#notice')).toBeHidden();
  state.error='视野内没有发现同伴';send();await expect(page.locator('#notice')).toBeVisible();
  await page.locator('#connect-voice').click();
  await expect(page.locator('#notice')).toHaveText('协议测试：本房间语音正在使用');
  state.error=null;send();
  await expect(page.locator('#notice')).toHaveText('协议测试：本房间语音正在使用');
  await expect(page.locator('#notice')).toBeVisible();
  state.error='视野内没有发现同伴';send();await expect(page.locator('#notice')).toHaveText(state.error);
  channel.send(JSON.stringify({type:'not_started'}));
  await expect(page.locator('#stop-scene')).toBeDisabled();
  await expect(page.locator('#notice')).toBeHidden();
});

test('official skills, natural idle, wheel skating and cancellation work from the page',async({page})=>{
  test.setTimeout(120000);
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.goto('/scenarios.html?room=1');
  await page.getByRole('button',{name:'动作练习场'}).click();
  await expect(page.locator('#skills-controls')).toBeVisible({timeout:30000});
  await expect(page.locator('#scene-placeholder')).toBeHidden({timeout:20000});
  for(const [name,label] of [['roulade','前滚翻'],['ground_pick','低头啄取'],['yawn','打个哈欠']]){
    await page.locator(`[data-sim-action="${name}"]`).click();
    await expect(page.locator('#action-result')).toContainText(`${label} · 完成`,{timeout:15000});
    const state=await(await page.request.get('/api/scenes/state?room=1')).json();
    expect(state.backend.skill.status).toBe('completed');
    expect(state.backend.skill.supported).toBe(true);
    await expect(page.locator('#skill-readouts')).toContainText(label);
  }
  await page.locator('[data-sim-action="idle_on"]').click();
  await expect(page.locator('#idle-status')).toContainText('看看四周',{timeout:10000});
  await page.locator('[data-sim-action="shake_head"]').click();
  await expect(page.locator('#action-result')).toContainText('摇头 · 完成');
  await page.locator('#stop-scene').click();
  await expect(page.locator('#idle-status')).toContainText('已关闭');
  await page.locator('[data-sim-action="roulade"]').click();
  await expect(page.locator('#action-result')).toContainText('前滚翻 · 进行中');
  await page.keyboard.press('Escape');
  await expect(page.locator('#action-result')).toContainText('停止 · 完成');
  await expect(page.locator('#activity-log')).toContainText('前滚翻 · 已取消');
  await page.getByRole('button',{name:'轮滑小鸭'}).click();
  await expect(page.locator('#rollers-controls')).toBeVisible();
  await expect(page.locator('#floor-moves')).toBeHidden();
  for(const [name,label] of [['skate','向前滑行'],['roller_crouch','轮滑下蹲']]){
    await page.locator(`[data-sim-action="${name}"]`).click();
    await expect(page.locator('#action-result')).toContainText(`${label} · 完成`,{timeout:15000});
  }
  await page.setViewportSize({width:390,height:844});
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  expect(errors).toEqual([]);
  await page.screenshot({path:'test-results/new-skills-mobile.png'});
});
