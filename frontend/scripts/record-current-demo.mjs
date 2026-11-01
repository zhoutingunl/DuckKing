// Record the deployed UI and its real results. No API interception or scripted poses.
import {chromium,expect} from '@playwright/test';
import {mkdir,readFile,writeFile} from 'node:fs/promises';
import {resolve} from 'node:path';

const base=new URL(process.env.DUCKKING_DEMO_URL??'https://ztmonitor.qbox.net/duckking/');
if(!base.pathname.endsWith('/'))base.pathname+='/';
const output=resolve(process.env.DUCKKING_DEMO_OUTPUT??'../.duckking/current-demo');
await mkdir(output,{recursive:true});
const browser=await chromium.launch({channel:process.env.DUCKKING_BROWSER_CHANNEL??'chrome',args:['--use-gl=angle','--use-angle=swiftshader','--enable-unsafe-swiftshader']});
const context=await browser.newContext({viewport:{width:1600,height:1000},recordVideo:{dir:resolve(output,'raw'),size:{width:1600,height:1000}}});
const health=await(await context.request.get(new URL('api/health',base).href)).json();
const roomResponse=await context.request.post(new URL('api/rooms',base).href);
if(!roomResponse.ok())throw new Error(`Cannot allocate recording room: ${roomResponse.status()}`);
const {room}=await roomResponse.json();
const proof={recorded_at:new Date().toISOString(),base_url:base.href,release:health.release,room,viewport:{width:1600,height:1000},source:'actual deployed browser UI; buttons and local rehearsal; no cloud session or microphone',audio:'New editorial narration is added separately; page audio is not captured.',chapters:[],page_errors:[]};
if(process.env.DUCKKING_DEMO_RESUME){
 const previous=JSON.parse(await readFile(process.env.DUCKKING_DEMO_RESUME,'utf8'));
 if(previous.release.commit!==health.release.commit)throw Error('Cannot resume across different releases');
 proof.chapters=previous.chapters.filter(c=>c.video&&c.segments.length&&c.segments.every(s=>s.status==='completed')&&(c.id!=='balance'||['completed','failed'].includes(c.custom?.phase)));
 proof.attempts=[...(previous.attempts??[]),{recorded_at:previous.recorded_at,completed:previous.completed,error:previous.error?.split('\n')[0]}];
}
const needed=id=>!proof.chapters.some(c=>c.id===id);
await writeFile(resolve(output,'recording.json'),JSON.stringify(proof,null,2));
let page,started,chapter;
const save=()=>writeFile(resolve(output,'recording.json'),JSON.stringify(proof,null,2)+'\n');
async function open(id,path){
 page=await context.newPage();started=Date.now();chapter={id,page:path,started_at:new Date(started).toISOString(),segments:[],screenshots:[]};
 proof.chapters.push(chapter);page.on('pageerror',e=>proof.page_errors.push({chapter:id,message:e.message}));
 await page.goto(new URL(`${path}?room=${room}`,base).href,{waitUntil:'domcontentloaded',timeout:60000});
 await save();console.log('Opened',id);
}
async function mark(name,fn){
 const segment={name,start_seconds:(Date.now()-started)/1000};chapter.segments.push(segment);
 await save();console.log('Recording',name);
 try{await fn();segment.status='completed'}catch(e){segment.status='failed';segment.error=e.message;throw e}finally{segment.end_seconds=(Date.now()-started)/1000;await save()}
}
async function shot(name){const path=resolve(output,name+'.png');await page.screenshot({path});chapter.screenshots.push({file:path,at_seconds:(Date.now()-started)/1000});}
async function close(){
 const video=page.video();await page.close();chapter.video=await video.path();chapter.finished_at=new Date().toISOString();await save();
}
async function state(){const response=await context.request.get(new URL(`api/scenes/state?room=${room}`,base).href);if(!response.ok())throw Error('No scene state');return response.json()}
async function release(){await context.request.post(new URL(`api/scenes/close?room=${room}`,base).href)}
async function sceneAction(name,target='a'){
 const response=page.waitForResponse(r=>r.request().method()==='POST'&&new URL(r.url()).pathname.endsWith('/api/scenes/actions'));
 await page.locator(`[data-sim-action="${name}"]`).filter({visible:true}).click();
 let record=await(await response).json();const deadline=Date.now()+45000;
 while(record.status==='running'&&Date.now()<deadline){await page.waitForTimeout(150);record=await(await context.request.get(new URL(`api/scenes/actions/${record.id}?room=${room}`,base).href)).json()}
 if(record.status!=='completed')throw Error(JSON.stringify(record));
 (chapter.actions??=[]).push(record);
 await expect(page.locator('#action-result')).toContainText(/完成|未完成/,{timeout:45000});
 const text=await page.locator('#action-result').textContent();if(text.includes('未完成'))throw Error(text);
 return text;
}
async function stageAction(id){
 const response=page.waitForResponse(r=>r.request().method()==='POST'&&new URL(r.url()).pathname.endsWith('/api/scenes/actions'));
 await page.locator(id).click();let record=await(await response).json();const deadline=Date.now()+100000;
 while(record.status==='running'&&Date.now()<deadline){await page.waitForTimeout(200);record=await(await context.request.get(new URL(`api/scenes/actions/${record.id}?room=${room}`,base).href)).json()}
 (chapter.actions??=[]).push(record);if(record.status!=='completed')throw Error(JSON.stringify(record));
 await expect(page.locator('#show-status')).toContainText('本地操作完成',{timeout:10000});
}
try{
 if(needed('home')){
 await open('home','');
 await expect(page.locator('#viewport')).toHaveAttribute('data-model','official',{timeout:90000});
 await page.locator('.stage-card').scrollIntoViewIfNeeded();
 await mark('appearance-and-preview',async()=>{
  for(const colour of ['奶油白 · Cream','石墨灰 · Graphite','薰衣草紫 · Lavender','天空蓝 · Sky']){await page.getByRole('button',{name:colour,exact:true}).click();await page.waitForTimeout(1800)}
  await page.getByRole('button',{name:'奶油白 · Cream',exact:true}).click();await shot('current-workbench');
  await page.locator('[data-action="flash_step"]').click();await page.waitForTimeout(3300);await page.keyboard.press('Escape');await page.waitForTimeout(1200);
 });await close();}

 if(needed('physics')){
 await open('physics','scenarios.html');await page.locator('[data-scene="ball"]').click();
 await expect(page.locator('#posture-controls')).toBeVisible({timeout:90000});
 await page.locator('.scene-stage').scrollIntoViewIfNeeded();
 await mark('real-kick-and-measurements',async()=>{
  await sceneAction('kick_left');await page.waitForTimeout(3000);await shot('current-physics');chapter.kick=(await state()).backend.ball;
  await page.locator('[data-scene="skills"]').click();await expect(page.locator('#skills-controls')).toBeVisible({timeout:60000});
  await sceneAction('roulade');await page.waitForTimeout(1200);await shot('current-practice');
 });await close();await release();}

 if(needed('theatre')){
 await open('theatre','demos.html');await expect(page.locator('[data-demo]')).toHaveCount(13);
 await page.selectOption('#demo-mode','rehearsal');await page.selectOption('#stage-play','interactive');
 await page.locator('[data-demo="stage"]').click();await expect(page.locator('#show-status')).toContainText('现场互动已就绪',{timeout:90000});
 await page.locator('.theatre-stage').count().then(async n=>{if(n)await page.locator('.theatre-stage').scrollIntoViewIfNeeded()});
 await mark('four-duck-interactive-stage',async()=>{
  await shot('current-theatre');await stageAction('#stage-gather');await shot('current-stage-lineup');
  for(const member of ['a','d'])await page.locator(`[data-stage-member][value="${member}"]`).uncheck();
  for(const member of ['b','c'])await page.locator(`[data-stage-member][value="${member}"]`).check();
  await stageAction('#stage-roll');
  await page.waitForTimeout(3500);chapter.stage=(await state()).backend.stage;
 });await close();await release();}

 if(needed('studio')){
 await open('studio','studio.html');await page.locator('[data-studio="director"]').click();
 await expect(page.locator('#studio-controls button').first()).toBeEnabled({timeout:90000});
 await page.locator('.scene-stage').scrollIntoViewIfNeeded();
 await mark('local-rehearsal-with-head-only-constraint',async()=>{
  await page.getByRole('button',{name:'改成只用头',exact:true}).click();
  await expect(page.locator('#task-status')).toContainText('已完成',{timeout:30000});await shot('current-studio');chapter.studio=(await state()).studio;await page.waitForTimeout(2500);
 });await close();await release();}

 if(needed('balance')){
 await open('balance','balance.html');await page.locator('[data-level="2"]').click();await page.locator('#challenge-seed').fill('0');await page.locator('#challenge-duration').fill('13');
 await page.locator('#prepare-balance').click();await expect(page.locator('#start-challenge')).toBeEnabled({timeout:120000});
 await page.locator('.balance-arena').scrollIntoViewIfNeeded();
 await mark('paired-standard-13-seconds',async()=>{
  await page.locator('#start-challenge').click();await expect(page.locator('#challenge-status')).toHaveAttribute('data-phase','running',{timeout:15000});await page.waitForTimeout(5000);await shot('current-balance-running');
  await expect(page.locator('#comparison-status')).toContainText('对照结束',{timeout:90000});await page.waitForTimeout(2000);chapter.standard=(await state()).backend.balance;await shot('current-balance-result');
 });
 await mark('paired-custom-30-seconds',async()=>{
  await page.locator('#challenge-duration').fill('30');await page.locator('#start-challenge').click();
  await expect(page.locator('#challenge-status')).toHaveAttribute('data-phase','running',{timeout:15000});
  await expect(page.locator('#comparison-status')).toContainText('对照结束',{timeout:120000});await page.waitForTimeout(2500);chapter.custom=(await state()).backend.balance;await shot('current-balance-custom');
  if(chapter.custom.duration_seconds!==30||!['completed','failed'].includes(chapter.custom.phase)||!['completed','failed'].includes(chapter.custom.comparison.baseline.phase))throw Error('Custom comparison has not actually finished');
 });
 await mark('training-evidence-and-reward-explanation',async()=>{
  await page.locator('#training').scrollIntoViewIfNeeded();await page.waitForTimeout(2000);await shot('current-training');
  chapter.training={gate:await page.locator('#gate-status').textContent(),capability:await page.locator('#training-capability').textContent(),run:await page.locator('#run-select').inputValue()};
  await page.locator('#reward-equation').scrollIntoViewIfNeeded();await page.locator('[data-ppo="epsilon"]').click();await page.waitForTimeout(4500);await shot('current-learning');
 });await close();await release();}
 proof.completed=true;
}catch(e){proof.completed=false;proof.error=e.stack;console.error(e);if(page&&!page.isClosed()){await shot('recording-failure');await close()}}
finally{await release().catch(()=>{});await context.close();await browser.close();await save();console.log(resolve(output,'recording.json'))}
if(!proof.completed)process.exitCode=1;
