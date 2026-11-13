import {test,expect} from '@playwright/test';

test('independent visitors cannot list, enter or stop each other’s rooms',async({browser,baseURL})=>{
 test.setTimeout(90000);
 const fresh={cookies:[],origins:[]};
 const first=await browser.newContext({baseURL,storageState:fresh}),second=await browser.newContext({baseURL,storageState:fresh});
 try{
  const a=(await(await first.request.post('/api/rooms/claim')).json()).room;
  const b=(await(await second.request.post('/api/rooms/claim')).json()).room;
  expect(a).not.toBe(b);
  const mine=await first.newPage(),other=await second.newPage();
  await Promise.all([mine.goto(`/index.html?room=${a}`),other.goto(`/index.html?room=${b}`)]);
  await expect(mine.locator('#connection-label')).toContainText('已连接');
  await expect(other.locator('#connection-label')).toContainText('已连接');
  await expect(mine.locator('.room-links a')).toHaveText([`房间 ${a}`]);
  await expect(other.locator('.room-links a')).toHaveText([`房间 ${b}`]);
  const accepted=mine.waitForResponse(r=>new URL(r.url()).pathname==='/api/actions'&&r.request().method()==='POST');
  await mine.locator('[data-action="nod"]').click();
  const action=(await(await accepted).json()).id;
  expect((await second.request.post(`/api/actions?room=${a}`,{data:{name:'stop'}})).status()).toBe(404);
  expect((await second.request.get(`/api/state?room=${a}`)).status()).toBe(404);
  expect((await second.request.get(`/api/actions/${action}?room=${a}`)).status()).toBe(404);
  await expect.poll(async()=>(await(await first.request.get(`/api/actions/${action}?room=${a}`)).json()).status).toBe('completed');
  await other.goto(`/index.html?room=${a}`);
  await expect(other.locator('#room-recovery')).toBeVisible();
  await expect(other.locator('body')).toHaveClass(/room-unavailable/);
  for(const endpoint of ['ws','scene-ws','voice','scene-voice']){
   const result=await other.evaluate(({endpoint,room})=>new Promise((resolve,reject)=>{
    const url=new URL('/'+endpoint,location.href);url.protocol=url.protocol==='https:'?'wss:':'ws:';url.searchParams.set('room',room);
    const messages=[],socket=new WebSocket(url),timer=setTimeout(()=>{socket.close();reject(Error('Socket did not reject foreign room'))},5000);
    socket.onmessage=event=>messages.push(JSON.parse(event.data));
    socket.onclose=event=>{clearTimeout(timer);resolve({messages,code:event.code})};
   }),{endpoint,room:a});
   expect(result).toEqual({messages:[{type:'room_expired',reason:'unavailable'}],code:1008});
  }
  const visible=(await(await second.request.get(`/api/rooms?room=${a}`)).json()).rooms.map(r=>r.id);
  expect(visible).toEqual([b]);
  await other.locator('#reconnect-room').click();
  await expect(other.locator('#connection-label')).toContainText('已连接');
  expect(new URL(other.url()).searchParams.get('room')).not.toBe(a);
 }finally{await first.close();await second.close()}
});
