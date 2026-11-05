// Real offline recognition via the microphone interface; read-only public coverage.
import {chromium,expect} from '@playwright/test';
import {mkdir,readFile,writeFile} from 'node:fs/promises';
import {resolve} from 'node:path';
import {execFileSync} from 'node:child_process';

const base=new URL(process.env.DUCKKING_DEMO_URL??'http://127.0.0.1:8901/');
const publicBase=new URL('https://ztmonitor.qbox.net/duckking/');
const output=resolve(process.env.DUCKKING_DEMO_OUTPUT??'../.duckking/finals-supplement-take1');
await mkdir(output,{recursive:true});
const input=await readFile(resolve('../.duckking/finals-input/local-skills.wav'));
const browser=await chromium.launch({channel:'chrome',args:process.platform==='darwin'?['--use-gl=angle','--use-angle=metal']:[]});
const context=await browser.newContext({viewport:{width:1600,height:1000}});
let localRoom=null;
await context.addInitScript(({wav})=>{
 // Disclosed synthetic microphone input. ASR, routing and motion stay real.
 const bytes=Uint8Array.from(atob(wav),c=>c.charCodeAt(0));
 navigator.mediaDevices.getUserMedia=async()=>{
  const ctx=new AudioContext(),destination=ctx.createMediaStreamDestination();
  const buffer=await ctx.decodeAudioData(bytes.buffer.slice(0));
  window.playRecordedInput=async()=>{
   await ctx.resume();const source=ctx.createBufferSource();source.buffer=buffer;source.connect(destination);
   await new Promise(done=>{source.onended=done;source.start(ctx.currentTime+.1)});
  };
  return destination.stream;
 };
},{wav:input.toString('base64')});
const proof={recorded_at:new Date().toISOString(),base_url:base.href,source_commit:execFileSync('git',['rev-parse','HEAD'],{encoding:'utf8'}).trim(),source:'Real local SenseVoice inference and MuJoCo using disclosed synthetic microphone input; public deployment coverage read-only',chapters:[],page_errors:[]};
if(process.env.DUCKKING_DEMO_RESUME){
 const previous=JSON.parse(await readFile(resolve(process.env.DUCKKING_DEMO_RESUME),'utf8'));
 if(previous.source_commit!==proof.source_commit)throw Error('Cannot resume supplements across source commits');
 proof.chapters=previous.chapters.filter(c=>c.id!==process.env.DUCKKING_DEMO_RERECORD&&c.video&&c.segments.length&&c.segments.every(s=>s.status==='completed'));
 proof.previous_recording={recorded_at:previous.recorded_at,completed:previous.completed};
}
const needed=id=>!proof.chapters.some(c=>c.id===id);
const save=()=>writeFile(resolve(output,'recording.json'),JSON.stringify(proof,null,2)+'\n');
const get=async(path,origin=base)=>{const r=await context.request.get(new URL(path,origin).href);if(!r.ok())throw Error(`${path}: ${r.status()}`);return r.json()};
let page,chapter,started,capture;
async function open(id,path,origin=base){
 page=await context.newPage();started=Date.now();chapter={id,page:path,started_at:new Date(started).toISOString(),screenshots:[],segments:[],audio:[],provenance:{base_url:origin.href,source_commit:origin===base?proof.source_commit:null,recorded_at:new Date().toISOString()}};proof.chapters.push(chapter);
 const session=await context.newCDPSession(page),directory=resolve(output,'raw',id);await mkdir(directory,{recursive:true});
 capture={session,directory,frames:[],writes:[],accepting:true};const current=capture;
 session.on('Page.screencastFrame',event=>{
  void session.send('Page.screencastFrameAck',{sessionId:event.sessionId}).catch(()=>{});
  if(!current.accepting)return;const time=event.metadata.timestamp*1000;
  if(current.frames.length&&time-current.frames.at(-1).time<40)return;
  const file=resolve(directory,`frame-${String(current.frames.length).padStart(6,'0')}.jpg`);
  current.frames.push({file,time});current.writes.push(writeFile(file,Buffer.from(event.data,'base64')));
 });
 await session.send('Page.enable');await session.send('Page.startScreencast',{format:'jpeg',quality:90,maxWidth:1600,maxHeight:1000,everyNthFrame:1});
 page.on('pageerror',e=>proof.page_errors.push({chapter:id,message:e.message}));
 await page.goto(new URL(path,origin).href,{waitUntil:'domcontentloaded'});await save();
}
async function shot(name){const file=resolve(output,name+'.png');await page.screenshot({path:file});chapter.screenshots.push({file,at_seconds:(Date.now()-started)/1000,capture:'browser_screenshot'})}
async function mark(name,work){const s={name,start_seconds:(Date.now()-started)/1000};chapter.segments.push(s);await save();console.log('Recording',name);try{await work();s.status='completed'}catch(e){s.status='failed';throw e}finally{s.end_seconds=(Date.now()-started)/1000;await save()}}
async function close(){
 const end=Date.now();capture.accepting=false;await capture.session.send('Page.stopScreencast');await Promise.all(capture.writes);await page.close();
 const frames=capture.frames;if(!frames.length)throw Error('No actual video frames');
 chapter.video_start_elapsed_seconds=(frames[0].time-started)/1000;
 chapter.capture={method:'Chrome CDP screencast with original wall-clock timestamps',frames:frames.length};
 const listing=frames.flatMap((f,i)=>[`file '${f.file}'`,`duration ${Math.max(.001,((frames[i+1]?.time??end)-f.time)/1000)}`]);listing.push(`file '${frames.at(-1).file}'`);
 const file=resolve(capture.directory,'frames.txt');await writeFile(file,listing.join('\n')+'\n');chapter.video=resolve(capture.directory,'capture.webm');
 execFileSync('ffmpeg',['-y','-v','error','-f','concat','-safe','0','-i',file,'-vf','fps=25,scale=1600:1000:force_original_aspect_ratio=decrease,pad=1600:1000,setsar=1','-c:v','libvpx-vp9','-deadline','realtime','-cpu-used','8','-crf','20','-b:v','0',chapter.video]);await save();
}
try{
 if(needed('local_asr')){
 const claim=await context.request.post(new URL('api/rooms/claim',base).href);
 if(!claim.ok())throw Error('Cannot claim a private recording room');localRoom=(await claim.json()).room;
 await open('local_asr',`scenarios.html?room=${localRoom}&measurement=verification`);
 await page.locator('[data-scene="skills"]').click();await expect(page.locator('#skills-controls')).toBeVisible({timeout:90000});
 await expect(page.locator('#voice-mode')).toBeEnabled();await page.selectOption('#voice-mode','local_first');await page.locator('#connect-voice').click();await expect(page.locator('#talk-button')).toBeEnabled({timeout:20000});
 await mark('real-local-asr-and-two-actions',async()=>{
  await shot('finals-local-asr-mode');await page.waitForTimeout(2500);
  await page.locator('#talk-button').dispatchEvent('pointerdown',{pointerId:1});await expect(page.locator('#voice-badge')).toHaveText('正在聆听');
  const playing=page.evaluate(()=>window.playRecordedInput());await page.locator('.scene-stage').scrollIntoViewIfNeeded();await playing;await page.waitForTimeout(200);await page.locator('#talk-button').dispatchEvent('pointerup',{pointerId:1});
  await expect(page.locator('#voice-route')).toContainText('本轮未调用灵矽',{timeout:45000});
  await shot('finals-local-asr-actions');
  const stats=await get(`api/voice/statistics?room=${localRoom}&backend=mujoco`);chapter.rounds=stats.rounds;
  if(stats.rounds.length!==1||stats.rounds[0].route!=='local'||stats.rounds[0].status!=='completed'||stats.rounds[0].uplink_frames||stats.rounds[0].downlink_frames||stats.rounds[0].actions.length!==2||stats.rounds[0].actions.some(a=>a.result!=='completed'))throw Error('Missing real local-only two-action result');
  chapter.state=await get(`api/scenes/state?room=${localRoom}`);
  await page.locator('#voice-route').scrollIntoViewIfNeeded();await page.waitForTimeout(2000);await shot('finals-local-asr-result');await page.waitForTimeout(1500);
 });await page.locator('#connect-voice').click();await close();await context.request.post(new URL(`api/scenes/close?room=${localRoom}`,base).href);
 }
 if(needed('training')){
 await open('training','balance.html?measurement=verification',publicBase);
 const trainingRelease=(await get('api/health',publicBase)).release;chapter.provenance.source_commit=trainingRelease.commit;chapter.provenance.release=trainingRelease;
 await page.locator('[data-level="2"]').click();
 await expect(page.locator('#run-select option[value="level2-cpu-v4"]')).toHaveCount(1,{timeout:20000});await page.selectOption('#run-select','level2-cpu-v4');
 await expect(page.locator('#gate-status')).toContainText('89/100',{timeout:20000});await page.locator('#training').scrollIntoViewIfNeeded();
 await mark('saved-cpu-training-and-ppo-explanation',async()=>{
  chapter.training={run:await page.locator('#run-select').inputValue(),gate:await page.locator('#gate-status').textContent(),capability:await page.locator('#training-capability').textContent(),evidence:await page.locator('#run-evidence').textContent()};
  await shot('finals-training-curves');await page.waitForTimeout(8000);
  await page.locator('#reward-equation').scrollIntoViewIfNeeded();await shot('finals-training-reward');await page.waitForTimeout(6000);
  await page.locator('[data-ppo="epsilon"]').click();await shot('finals-training-ppo');await page.waitForTimeout(7000);
 });await close();
 }
 if(needed('coverage')){
 await open('coverage','deploys.html',publicBase);await expect(page.locator('#deploy-rows')).toContainText('95.94',{timeout:20000});
 await mark('commit-bound-test-coverage',async()=>{
  const data=await get('api/deployments',publicBase);chapter.deployment=data.records.find(r=>r.status==='success'&&r.commit===data.current.commit);chapter.provenance.source_commit=data.current.commit;chapter.provenance.release=data.current;
  if(!chapter.deployment?.coverage)throw Error('No actual coverage for current deployment');
  await shot('finals-coverage-current');await page.waitForTimeout(7000);await page.locator('.stats-note').last().scrollIntoViewIfNeeded();await shot('finals-coverage-scope');await page.waitForTimeout(8000);
 });await close();
 }
 proof.completed=true;
}catch(e){proof.completed=false;proof.error=e.message;console.error(e.message);if(page&&!page.isClosed()){await shot('finals-supplement-failure');await close()}}
finally{if(localRoom)await context.request.post(new URL(`api/scenes/close?room=${localRoom}`,base).href).catch(()=>{});await context.close();await browser.close();await save();console.log(resolve(output,'recording.json'))}
if(!proof.completed)process.exitCode=1;
