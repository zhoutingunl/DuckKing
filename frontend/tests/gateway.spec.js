import {test,expect} from '@playwright/test';
import {spawn} from 'node:child_process';
import http from 'node:http';

test('real ai_gateway serves physical state through an ingress without Upgrade',async({page,context,baseURL})=>{
  test.skip(!process.env.DUCKKING_GATEWAY_REPO||process.env.DUCKKING_TEST_DEV==='1','Requires the local ai_gateway checkout and its Python environment.');
  test.setTimeout(90000);
  const upstream=new URL(baseURL),connections=new Set();let gatewayPort;
  const ingress=http.createServer((req,res)=>{
    const headers={...req.headers,connection:'close'};delete headers.upgrade;
    const remote=http.request({host:'127.0.0.1',port:gatewayPort,path:req.url,method:req.method,headers,agent:false},response=>{res.writeHead(response.statusCode,response.headers);response.pipe(res)});
    remote.on('error',()=>{if(!res.headersSent)res.writeHead(502);res.end()});req.pipe(remote);
  });
  ingress.on('connection',socket=>{connections.add(socket);socket.on('close',()=>connections.delete(socket));socket.on('error',()=>socket.destroy())});
  ingress.on('upgrade',(_req,socket)=>socket.end('HTTP/1.1 400 Upgrade unavailable\r\nContent-Length: 0\r\n\r\n'));
  await new Promise(resolve=>ingress.listen(0,'127.0.0.1',resolve));
  const origin=`http://127.0.0.1:${ingress.address().port}`,prefix=origin+'/duckking/';
  const repo=process.env.DUCKKING_GATEWAY_REPO;
  const source=`
import sys
from flask import Flask
from gevent.pywsgi import WSGIServer
from webui.duckking_proxy import register,Settings,DuckKingWSGIHandler
app=Flask(__name__)
register(app,lambda:Settings(sys.argv[1],sys.argv[2]))
server=WSGIServer(('127.0.0.1',0),app,handler_class=DuckKingWSGIHandler,log=None)
server.start()
print(server.server_port,flush=True)
server.serve_forever()
`;
  const gateway=spawn(repo+'/.venv/bin/python',['-c',source,upstream.origin,new URL(origin).host],{cwd:repo,stdio:['ignore','pipe','pipe']});
  let errors='';gateway.stderr.on('data',data=>errors+=data);
  try{
    gatewayPort=await new Promise((resolve,reject)=>{
      const timer=setTimeout(()=>reject(new Error('Gateway startup timeout: '+errors)),10000);
      gateway.stdout.once('data',data=>{clearTimeout(timer);resolve(Number(String(data).trim()))});
      gateway.once('exit',()=>{clearTimeout(timer);reject(new Error('Gateway exited: '+errors))});
    });
    const sockets=[];page.on('websocket',socket=>sockets.push(socket.url()));
    await page.goto(prefix+'?room=1');await expect(page.locator('#connection-label')).toHaveText('本地工作台已连接');
    await page.locator('[data-action="nod"]').click();await expect(page.locator('#activity-log')).toContainText('点头 · completed');
    // A second browser's local channel reserves the real backend device. Verify
    // release through HTTPS while its page/channel context remains alive.
    const held=await page.request.post(prefix+'_gateway/channels',{data:{endpoint:'voice'}});
    expect(held.status()).toBe(201);
    const heldURL=prefix+'_gateway/channels/'+(await held.json()).id;
    await page.request.post(heldURL,{data:{sequence:0,frames:[{binary:false,data:JSON.stringify({type:"join_room",room:"1"})}]}});
    await page.request.get(heldURL);
    await page.locator('#connect-voice').click();
    await expect(page.locator('#voice-badge')).toHaveText('本房间语音正在使用');
    await page.request.post(heldURL,{data:{sequence:1,frames:[{binary:false,data:JSON.stringify({type:'disconnect'})}]}});
    await expect.poll(async()=>{
      const r=await page.request.get(heldURL);
      return r.status()===410||(r.ok()&&(await r.json()).closed);
    }).toBe(true);
    await page.locator('#connect-voice').click();
    await expect(page.locator('#voice-badge')).toHaveText('连接异常');
    await expect(page.locator('#notice')).toContainText('连接未成功');
    await page.goto(prefix+'scenarios.html?room=1');await page.getByRole('button',{name:'单鸭定点踢球'}).click();
    await expect(page.locator('#sim-status')).toHaveText('MuJoCo 物理运行中',{timeout:30000});
    await expect(page.locator('#scene-placeholder')).toBeHidden();
    // Only cloud voice uses a labelled protocol fixture. HTTP, model loading,
    // action execution and scene state above traverse the actual gateway.
    const id='b'.repeat(32),pcm=[];let state='ready';
    await page.route('**/duckking/_gateway/channels',async route=>{
      if(route.request().postDataJSON()?.endpoint==='scene-voice')await route.fulfill({status:201,json:{id}});
      else await route.continue();
    });
    await page.route('**/duckking/_gateway/channels/'+id,async route=>{
      const req=route.request();
      if(req.method()==='DELETE'){await route.fulfill({status:204});return}
      if(req.method()==='POST'){
        const body=req.postDataJSON();
        for(const frame of body.frames){
          if(frame.binary)pcm.push(Buffer.from(frame.data,'base64'));
          else{const event=JSON.parse(frame.data);state=event.type==='listen_start'?'listening':'ready'}
        }
        await route.fulfill({json:{sequence:body.sequence+1}});return;
      }
      await new Promise(resolve=>setTimeout(resolve,100));
      await route.fulfill({json:{frames:[{binary:false,data:JSON.stringify({type:'voice_status',state})}],closed:false}});
    });
    await context.grantPermissions(['microphone'],{origin});
    await page.locator('#connect-voice').click();await expect(page.locator('#talk-button')).toBeEnabled();
    await page.locator('#talk-button').dispatchEvent('pointerdown',{pointerId:1});
    await expect.poll(()=>pcm.length).toBeGreaterThan(0);
    await page.locator('#talk-button').dispatchEvent('pointerup',{pointerId:1});
    expect(pcm.every(frame=>frame.length===1920)).toBe(true);
    await page.goto(prefix+'statistics.html');await expect(page.locator('#stats-updated')).toContainText('已更新');
    expect(sockets).toEqual([]);
  }finally{
    await page.close();gateway.kill();await new Promise(resolve=>gateway.exitCode===null?gateway.once('exit',resolve):resolve());
    for(const socket of connections)socket.destroy();await new Promise(resolve=>ingress.close(resolve));
  }
});
