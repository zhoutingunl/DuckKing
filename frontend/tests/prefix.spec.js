import { test, expect } from '@playwright/test';
import http from 'node:http';
import https from 'node:https';
import { execFileSync } from 'node:child_process';
import { mkdtempSync, readFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

// Only this local test proxy has a generated, untrusted certificate.
test.use({ignoreHTTPSErrors:true});
for(const secure of [false,true]){
test(`${secure?'HTTPS':'HTTP'} prefix serves pages, physical state, actions and microphone worklet`,async({page,context,baseURL})=>{
  test.skip(process.env.DUCKKING_TEST_DEV==='1','This checks the production bundle behind a path-stripping proxy.');
  test.setTimeout(60000);
  const target=new URL(baseURL),connections=new Set(),forwarded=[];
  const options=req=>({hostname:target.hostname,port:target.port,path:req.url.slice('/duckking'.length),method:req.method,headers:req.headers});
  const handle=(req,res)=>{
    if(!req.url.startsWith('/duckking/')){res.writeHead(404);res.end();return;}
    forwarded.push(req.url);
    const upstream=http.request(options(req),response=>{res.writeHead(response.statusCode,response.headers);response.pipe(res);});
    upstream.on('error',()=>{res.writeHead(502);res.end();});req.pipe(upstream);
  };
  let certificateDirectory;
  let proxy;
  if(secure){
    certificateDirectory=mkdtempSync(join(tmpdir(),'duckking-test-tls-'));
    const key=join(certificateDirectory,'key.pem'),cert=join(certificateDirectory,'cert.pem');
    execFileSync('openssl',['req','-x509','-newkey','rsa:2048','-nodes','-keyout',key,'-out',cert,'-days','1','-subj','/CN=localhost'],{stdio:'ignore'});
    proxy=https.createServer({key:readFileSync(key),cert:readFileSync(cert)},handle);
  }else proxy=http.createServer(handle);
  const track=socket=>{
    connections.add(socket);socket.on('close',()=>connections.delete(socket));
    // Chromium may reset a socket when leaving a page with live streams.
    // Handle that transport close; page assertions still verify active connections.
    socket.on('error',()=>socket.destroy());
  };
  proxy.on('connection',track);
  if(secure)proxy.on('secureConnection',track);
  proxy.on('upgrade',(req,socket,head)=>{
    if(!req.url.startsWith('/duckking/')){socket.destroy();return;}
    forwarded.push(req.url);
    const upstream=http.request(options(req));
    upstream.on('upgrade',(response,remote,remoteHead)=>{
      connections.add(remote);remote.on('close',()=>connections.delete(remote));
      socket.write(`HTTP/1.1 ${response.statusCode} ${response.statusMessage}\r\n`+Object.entries(response.headers).map(([k,v])=>`${k}: ${v}`).join('\r\n')+'\r\n\r\n');
      if(remoteHead.length)socket.write(remoteHead);if(head.length)remote.write(head);
      socket.pipe(remote);remote.pipe(socket);
      socket.on('close',()=>remote.destroy());remote.on('error',()=>socket.destroy());
    });
    upstream.on('response',response=>{socket.end(`HTTP/1.1 ${response.statusCode} Rejected\r\nContent-Length: 0\r\n\r\n`);});
    upstream.on('error',()=>socket.destroy());upstream.end();
  });
  await new Promise(resolve=>proxy.listen(0,'127.0.0.1',resolve));
  const origin=`${secure?'https':'http'}://127.0.0.1:${proxy.address().port}`,prefix=origin+'/duckking/';
  const requests=[];page.on('request',request=>requests.push(request.url()));
  const sockets=[];page.on('websocket',socket=>sockets.push(socket.url()));
  try{
    await page.goto(prefix);
    expect(await page.evaluate(()=>window.isSecureContext)).toBe(true);
    await expect(page.locator('#connection-label')).toHaveText('本地工作台已连接');
    await page.locator('[data-action="nod"]').click();
    await expect(page.locator('#activity-log')).toContainText('点头 · completed');
    await expect(page.getByRole('link',{name:'物理实验室'})).toHaveJSProperty('href',prefix+'scenarios.html');
    await page.goto(prefix+'scenarios.html');await page.getByRole('button',{name:'单鸭定点踢球'}).click();
    await expect(page.locator('#scene-placeholder')).toBeHidden({timeout:30000});
    await expect(page.locator('#sim-status')).toHaveText('MuJoCo 物理运行中');
    await context.grantPermissions(['microphone'],{origin});
    const frames=[];
    // Only cloud voice is replaced: framing and microphone worklet use the real page.
    await page.routeWebSocket('**/duckking/scene-voice',socket=>socket.onMessage(message=>{
      if(typeof message!=='string'){frames.push(message);return;}
      const type=JSON.parse(message).type;
      socket.send(JSON.stringify({type:'voice_status',state:type==='listen_start'?'listening':type==='disconnect'?'disconnected':'ready'}));
    }));
    await page.locator('#connect-voice').click();await expect(page.locator('#talk-button')).toBeEnabled();
    await page.locator('#talk-button').dispatchEvent('pointerdown',{pointerId:1});
    await expect.poll(()=>frames.length).toBeGreaterThan(0);
    await page.locator('#talk-button').dispatchEvent('pointerup',{pointerId:1});
    expect(frames.every(frame=>frame.length===1920)).toBe(true);
    await page.goto(prefix+'statistics.html');await expect(page.locator('#stats-updated')).toContainText('已更新');
    await page.goto(prefix+'deploys.html');await expect(page.locator('#release-state')).toHaveText('本地开发');
    expect(requests.filter(url=>url.startsWith(origin)).every(url=>url.startsWith(prefix))).toBe(true);
    expect(sockets.length).toBeGreaterThanOrEqual(2);
    expect(sockets.every(url=>url.startsWith(prefix.replace(/^http/,'ws')))).toBe(true);
    for(const path of ['ws','api/actions','scene-ws','api/scenes/start','api/scenes/model','capture-worklet.js','api/deployments'])expect(forwarded).toContain('/duckking/'+path);
  }finally{
    await page.close();for(const socket of connections)socket.destroy();await new Promise(resolve=>proxy.close(resolve));
    if(certificateDirectory)rmSync(certificateDirectory,{recursive:true,force:true});
  }
});
}
