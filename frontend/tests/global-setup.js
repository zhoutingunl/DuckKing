import {request} from '@playwright/test';
import assert from 'node:assert/strict';
import {mkdir} from 'node:fs/promises';
import path from 'node:path';

export default async function setup(config){
 const port=process.env.DUCKKING_TEST_PORT??'8875';
 const session=await request.newContext({baseURL:`http://127.0.0.1:${port}`});
 let timer;
 try{
  // Functional browser tests share one legitimate visitor. Separate-context
  // access tests verify that other visitors cannot see or enter these rooms.
  const first=await session.post('/api/rooms/claim');assert.ok(first.ok());
  assert.equal((await first.json()).room,'1');
  const second=await session.post('/api/rooms');assert.ok(second.ok());
  assert.equal((await second.json()).room,'2');
  const file=config.projects[0].use.storageState;
  await mkdir(path.dirname(file),{recursive:true});
  await session.storageState({path:file});
  // Like two open workbench tabs, keep the fixture visitor's permanent rooms
  // alive while long physics tests run. Other rooms retain normal idle expiry.
  timer=setInterval(()=>{
   void session.get('/api/rooms?room=1').catch(()=>{});
   void session.get('/api/rooms?room=2').catch(()=>{});
  },15000);
  return async()=>{clearInterval(timer);await session.dispose()};
 }catch(error){clearInterval(timer);await session.dispose();throw error}
}
