// Explicit live acceptance: configured Linx account, real calls, real statistics.
import {chromium,expect} from '@playwright/test';
import {mkdir,writeFile} from 'node:fs/promises';
import {resolve} from 'node:path';
import {execFileSync} from 'node:child_process';

const base=new URL(process.env.DUCKKING_DEMO_URL??'http://127.0.0.1:8895/');
if(!base.pathname.endsWith('/'))base.pathname+='/';
const output=resolve(process.env.DUCKKING_DEMO_OUTPUT??'../.duckking/competition-live');await mkdir(output,{recursive:true});
const room=process.env.DUCKKING_DEMO_ROOM??'1';
const browser=await chromium.launch({channel:process.env.DUCKKING_BROWSER_CHANNEL??'chrome',args:['--use-gl=angle','--use-angle=swiftshader','--enable-unsafe-swiftshader']});
const context=await browser.newContext({viewport:{width:1600,height:1000},recordVideo:{dir:resolve(output,'raw'),size:{width:1600,height:1000}}});
await context.addInitScript(()=>{
 window.recordedAudio=[];const native=AudioNode.prototype.connect,taps=new Map();
 AudioNode.prototype.connect=function(target,...args){
  const result=native.call(this,target,...args);
  if(target===this.context.destination){
   let tap=taps.get(this.context);
   if(!tap){
    const destination=this.context.createMediaStreamDestination(),recorder=new MediaRecorder(destination.stream),chunks=[];
    tap={destination,recorder,chunks,started_at:Date.now()};taps.set(this.context,tap);window.recordedAudio.push(tap);
    recorder.ondataavailable=e=>{if(e.data.size)chunks.push(e.data)};recorder.start(250);
   }
   native.call(this,tap.destination);
  }
  return result;
 };
 window.finishRecordedAudio=async()=>Promise.all(window.recordedAudio.map(async tap=>{
  if(tap.recorder.state!=='inactive')await new Promise(r=>{tap.recorder.addEventListener('stop',r,{once:true});tap.recorder.stop()});
  const blob=new Blob(tap.chunks,{type:tap.recorder.mimeType});const bytes=new Uint8Array(await blob.arrayBuffer());
  let text='';for(let i=0;i<bytes.length;i+=8192)text+=String.fromCharCode(...bytes.subarray(i,i+8192));
  return {started_at:tap.started_at,mime:tap.recorder.mimeType,base64:btoa(text)};
 }));
});
const health=await(await context.request.get(new URL('api/health',base).href)).json();
const proof={recorded_at:new Date().toISOString(),base_url:base.href,release:health.release,source_commit:execFileSync('git',['rev-parse','HEAD'],{encoding:'utf8'}).trim(),room,validation_type:'live_tabletop',source:'Real Linx STT/MCP/TTS from shipped prerecorded command; actual MuJoCo; browser synthesis of Two Tigers',chapters:[],page_errors:[]};
const request=async path=>{const r=await context.request.get(new URL(path,base).href);if(!r.ok())throw Error(`${path}: ${r.status()}`);return r.json()};
const save=()=>writeFile(resolve(output,'recording.json'),JSON.stringify(proof,null,2)+'\n');
let page,chapter,started;
async function open(id,path){
 page=await context.newPage();started=Date.now();chapter={id,page:path,started_at:new Date(started).toISOString(),segments:[],screenshots:[]};proof.chapters.push(chapter);
 page.on('pageerror',e=>proof.page_errors.push({chapter:id,message:e.message}));
 await page.goto(new URL(`${path}?room=${room}&measurement=verification`,base).href,{waitUntil:'domcontentloaded'});await save();
}
async function shot(name){const file=resolve(output,name+'.png');await page.screenshot({path:file});chapter.screenshots.push({file,at_seconds:(Date.now()-started)/1000})}
async function mark(name,work){const segment={name,start_seconds:(Date.now()-started)/1000};chapter.segments.push(segment);await save();console.log('Recording',name);try{await work();segment.status='completed'}catch(e){segment.status='failed';segment.error=e.message;throw e}finally{segment.end_seconds=(Date.now()-started)/1000;await save()}}
async function close(){
 const audio=await page.evaluate(()=>window.finishRecordedAudio());chapter.audio=[];
 for(const [i,a] of audio.entries()){const file=resolve(output,`${chapter.id}-${i}.webm`);await writeFile(file,Buffer.from(a.base64,'base64'));chapter.audio.push({file,mime:a.mime,started_elapsed_seconds:(a.started_at-started)/1000})}
 const video=page.video();await page.close();chapter.video=await video.path();chapter.finished_at=new Date().toISOString();await save();
}
try{
 const rooms=await request('api/rooms'),active=rooms.rooms.find(r=>r.id===room);
 if(!active||active.voice_busy||active.viewers)throw Error('Recording room is in use; select an idle bound room');
 const before=await request(`api/voice/statistics?room=${room}&backend=mujoco`);proof.before_turns=before.rounds.map(r=>r.turn);
 await open('tabletop','demos.html');await expect(page.locator('[data-demo]')).toHaveCount(13);
 await page.selectOption('#demo-mode','live');await page.selectOption('#table-song','tigers');
 await mark('live-tabletop-two-tigers',async()=>{
  await shot('competition-live-selection');await page.locator('[data-demo="tabletop"]').click();
  await expect(page.locator('#table-panel')).toBeVisible({timeout:90000});await expect(page.locator('#table-song-title')).toContainText('两只老虎');
  await shot('competition-live-running');
  await expect(page.locator('#table-cue')).toContainText('楼下',{timeout:60000});await shot('competition-live-fall');
  await expect(page.locator('#show-status')).toHaveText('本幕完成 · 可重演或进入下一幕',{timeout:75000});
  const result=JSON.parse(await page.locator('#theatre-result').textContent());
  if(result.mode!=='live_linx'||result.cloud_audio_frames<1||!result.results.some(r=>r.name==='table_show'&&r.status==='completed'))throw Error('Missing actual cloud/physics result');
  chapter.result=result;chapter.timeline=await page.locator('#demo-timeline li').allTextContents();await shot('competition-live-result');await page.waitForTimeout(2000);
 });await close();
 const after=await request(`api/voice/statistics?room=${room}&backend=mujoco`);
 proof.new_rounds=after.rounds.filter(r=>!proof.before_turns.includes(r.turn));
 if(!proof.new_rounds.some(r=>r.actions.some(a=>a.tool==='duck_table_show'&&a.result==='completed')))throw Error('Missing real table tool action in statistics');
 await open('experience','experience.html');await expect(page.locator('#experience-updated')).not.toBeEmpty();
 for(const [name,value] of [['hours','1'],['traffic','verification'],['page','demos'],['room',room],['backend','mujoco']])await page.selectOption(`select[name="${name}"]`,value);
 await page.locator('#refresh-experience').click();await expect(page.locator('#browser-experience')).toContainText('灵矽',{timeout:20000});
 await mark('persistent-experience',async()=>{
  await shot('competition-experience');chapter.summary=await request(`api/experience?hours=1&traffic=verification&page=demos&room=${room}&backend=mujoco`);
  await page.waitForTimeout(7000);await page.locator('#server-experience').scrollIntoViewIfNeeded();await shot('competition-experience-server');await page.waitForTimeout(8000);
 });await close();
 await open('statistics','statistics.html');await page.selectOption('#backend-filter','mujoco');await page.locator('#refresh-stats').click();await expect(page.locator('#round-text')).toContainText('桌上',{timeout:15000});
 await mark('round-timeline-and-latency',async()=>{
  await shot('competition-statistics');await page.waitForTimeout(7000);await page.locator('#latency-rows').scrollIntoViewIfNeeded();await shot('competition-statistics-latency');await page.waitForTimeout(8000);
 });await close();proof.completed=true;
}catch(e){proof.completed=false;proof.error=e.message;console.error(e.message);if(page&&!page.isClosed()){await shot('competition-recording-failure');await close()}}
finally{await context.request.post(new URL(`api/scenes/close?room=${room}`,base).href).catch(()=>{});await context.close();await browser.close();await save();console.log(resolve(output,'recording.json'))}
if(!proof.completed)process.exitCode=1;
