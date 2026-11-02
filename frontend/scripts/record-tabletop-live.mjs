// Explicit live acceptance: configured Linx account, real calls, real statistics.
import {chromium,expect} from '@playwright/test';
import {mkdir,writeFile} from 'node:fs/promises';
import {resolve} from 'node:path';
import {execFileSync} from 'node:child_process';
import {installPageAudioRecorder,alignClockedAudio,contextTimeToWall,floatWav} from './recorded-audio.mjs';

const base=new URL(process.env.DUCKKING_DEMO_URL??'http://127.0.0.1:8895/');
if(!base.pathname.endsWith('/'))base.pathname+='/';
const output=resolve(process.env.DUCKKING_DEMO_OUTPUT??'../.duckking/competition-live');await mkdir(output,{recursive:true});
const room=process.env.DUCKKING_DEMO_ROOM??'1';
const angle=process.env.DUCKKING_CAPTURE_ANGLE??(process.platform==='darwin'?'metal':'default');
const browser=await chromium.launch({channel:process.env.DUCKKING_BROWSER_CHANNEL??'chrome',args:angle==='default'?[]:['--use-gl=angle',`--use-angle=${angle}`,...(angle==='swiftshader'?['--enable-unsafe-swiftshader']:[])]});
const context=await browser.newContext({viewport:{width:1600,height:1000}});
await context.addInitScript(installPageAudioRecorder);
const health=await(await context.request.get(new URL('api/health',base).href)).json();
const proof={recorded_at:new Date().toISOString(),base_url:base.href,release:health.release,source_commit:execFileSync('git',['rev-parse','HEAD'],{encoding:'utf8'}).trim(),room,validation_type:'live_tabletop',source:'Real Linx STT/MCP/TTS from shipped prerecorded command; actual MuJoCo; browser synthesis of Two Tigers',chapters:[],page_errors:[]};
const request=async path=>{const r=await context.request.get(new URL(path,base).href);if(!r.ok())throw Error(`${path}: ${r.status()}`);return r.json()};
const save=()=>writeFile(resolve(output,'recording.json'),JSON.stringify(proof,null,2)+'\n');
let page,chapter,started,capture;
async function open(id,path){
 page=await context.newPage();started=Date.now();chapter={id,page:path,started_at:new Date(started).toISOString(),segments:[],screenshots:[]};proof.chapters.push(chapter);
 // Keep Chrome's actual frame timestamps: inferring a clock from a WebM's
 // final frame can misalign separately captured page audio and event markers.
 const session=await context.newCDPSession(page),directory=resolve(output,'raw',id);await mkdir(directory,{recursive:true});
 capture={session,directory,frames:[],writes:[],accepting:true};const current=capture;
 session.on('Page.screencastFrame',event=>{
  void session.send('Page.screencastFrameAck',{sessionId:event.sessionId}).catch(()=>{});
  if(!current.accepting)return;
  const time=event.metadata.timestamp*1000;
  if(!Number.isFinite(time)||Math.abs(Date.now()-time)>10000)throw Error('Invalid capture wall clock');
  if(current.frames.length&&time-current.frames.at(-1).time<40)return;
  const file=resolve(directory,`frame-${String(current.frames.length).padStart(6,'0')}.jpg`);
  current.frames.push({file,time});current.writes.push(writeFile(file,Buffer.from(event.data,'base64')));
 });
 await session.send('Page.enable');await session.send('Page.startScreencast',{format:'jpeg',quality:90,maxWidth:1600,maxHeight:1000,everyNthFrame:1});
 page.on('pageerror',e=>proof.page_errors.push({chapter:id,message:e.message}));
 await page.goto(new URL(`${path}?room=${room}&measurement=verification`,base).href,{waitUntil:'domcontentloaded'});await save();
}
async function shot(name){
 const file=resolve(output,name+'.png'),at_seconds=(Date.now()-started)/1000;
 if(chapter.id!=='tabletop')await page.screenshot({path:file});
 chapter.screenshots.push({file,at_seconds,capture:chapter.id==='tabletop'?'recorded_video_frame':'browser_screenshot'});
}
async function mark(name,work){const segment={name,start_seconds:(Date.now()-started)/1000};chapter.segments.push(segment);await save();console.log('Recording',name);try{await work();segment.status='completed'}catch(e){segment.status='failed';segment.error=e.message;throw e}finally{segment.end_seconds=(Date.now()-started)/1000;await save()}}
async function close(){
 const audio=await page.evaluate(()=>window.finishRecordedAudio());chapter.audio=[];
 for(const [i,a] of audio.entries()){
  const bytes=Buffer.from(a.pcm_base64,'base64');await writeFile(resolve(output,`${chapter.id}-${i}-raw.f32`),bytes);await writeFile(resolve(output,`${chapter.id}-${i}-raw-clock.json`),JSON.stringify({...a,pcm_base64:undefined},null,2)+'\n');
  const aligned=alignClockedAudio({...a,pcm:new Float32Array(bytes.buffer,bytes.byteOffset,bytes.length/4)});
  const file=resolve(output,`${chapter.id}-${i}.wav`);await writeFile(file,floatWav(aligned));
  chapter.audio.push({file,mime:'audio/wav',sample_rate_hz:aligned.sampleRate,channels:2,started_elapsed_seconds:(aligned.started_wall_time_ms-started)/1000,clock_method:'AudioWorklet PCM + AudioContext.getOutputTimestamp wall-clock anchors',clock_segments:aligned.segments});
  const events=a.events.map(e=>({...e,wall_time_ms:contextTimeToWall(aligned,e.context_time)}));await writeFile(resolve(output,`${chapter.id}-${i}-clock.json`),JSON.stringify({events,anchors:a.anchors,states:a.states,segments:aligned.segments},null,2)+'\n');
  const show=chapter.result?.results.find(r=>r.name==='table_show');
  if(show){
   const starts=events.filter(e=>e.kind==='oscillator'&&e.method==='start'),stops=new Map();for(const e of events)if(e.kind==='oscillator'&&e.method==='stop')stops.set(e.id,e);
   if(!starts.length||!stops.size)throw Error('Missing actual music timing events');
   const first=Math.min(...starts.map(e=>e.wall_time_ms)),last=Math.max(...[...stops.values()].map(e=>e.wall_time_ms));
   chapter.sync_evidence={method:'Actual oscillator scheduling mapped through captured output-clock anchors',physical_start_wall_time_ms:show.started_at*1000,physical_end_wall_time_ms:show.finished_at*1000,music_start_wall_time_ms:first,music_end_wall_time_ms:last,start_delta_ms:first-show.started_at*1000,end_delta_ms:last-show.finished_at*1000,max_anchor_jitter_ms:Math.max(...aligned.segments.map(s=>s.max_anchor_jitter_ms))};
   if(Math.abs(chapter.sync_evidence.start_delta_ms)>350||Math.abs(chapter.sync_evidence.end_delta_ms)>350)throw Error('Music/physics start or end differs by over 350 ms; retain this attempt');
  }
 }
 const ended=Date.now();capture.accepting=false;await capture.session.send('Page.stopScreencast');await Promise.all(capture.writes);await page.close();
 const frames=capture.frames;if(!frames.length)throw Error('No actual screencast frames');
 const gaps=frames.slice(1).map((frame,i)=>(frame.time-frames[i].time)/1000);
 chapter.video_start_elapsed_seconds=(frames[0].time-started)/1000;
 chapter.capture={method:'Chrome CDP screencast with original wall-clock timestamps',frames:frames.length,max_frame_gap_seconds:Math.max(0,...gaps)};
 const show=chapter.result?.results.find(r=>r.name==='table_show');
 if(show){
  const moving=frames.filter(f=>f.time>=show.started_at*1000&&f.time<=show.finished_at*1000);
  const gaps=moving.slice(1).map((f,i)=>(f.time-moving[i].time)/1000);
  chapter.capture.performance_frames=moving.length;chapter.capture.performance_fps=moving.length/(show.finished_at-show.started_at);chapter.capture.performance_max_gap_seconds=Math.max(0,...gaps);
  if(chapter.capture.performance_fps<8||chapter.capture.performance_max_gap_seconds>2)throw Error('Actual performance capture is too sparse; retain this attempt and rerecord with GPU acceleration');
 }
 const listing=frames.flatMap((frame,i)=>[`file '${frame.file}'`,`duration ${Math.max(.001,((frames[i+1]?.time??ended)-frame.time)/1000)}`]);listing.push(`file '${frames.at(-1).file}'`);
 const listFile=resolve(capture.directory,'frames.txt');await writeFile(listFile,listing.join('\n')+'\n');chapter.video=resolve(capture.directory,'capture.webm');
 execFileSync('ffmpeg',['-y','-loglevel','error','-f','concat','-safe','0','-i',listFile,'-vf','fps=25','-c:v','libvpx-vp9','-deadline','realtime','-cpu-used','8','-crf','20','-b:v','0',chapter.video]);
 if(chapter.id==='tabletop'){
  const seconds=Number(execFileSync('ffprobe',['-v','error','-show_entries','format=duration','-of','default=noprint_wrappers=1:nokey=1',chapter.video],{encoding:'utf8'}));
  const offset=chapter.video_start_elapsed_seconds;
  for(const shot of chapter.screenshots)execFileSync('ffmpeg',['-y','-loglevel','error','-ss',String(Math.min(seconds-.05,Math.max(0,shot.at_seconds-offset))),'-i',chapter.video,'-frames:v','1',shot.file]);
 }
 chapter.finished_at=new Date().toISOString();await save();
}
try{
 const rooms=await request('api/rooms'),active=rooms.rooms.find(r=>r.id===room);
 if(!active||active.voice_busy||active.viewers)throw Error('Recording room is in use; select an idle bound room');
 const before=await request(`api/voice/statistics?room=${room}&backend=mujoco`);proof.before_turns=before.rounds.map(r=>r.turn);
 const beforeDiagnostics=await request(`api/voice/diagnostics?room=${room}`);
 const beforeEvent=beforeDiagnostics.events.at(-1)?.id??0;
 await open('tabletop','demos.html');await expect(page.locator('[data-demo]')).toHaveCount(13);
 await page.selectOption('#demo-mode','live');
 await mark('live-tabletop-two-tigers',async()=>{
  await shot('competition-live-selection');await page.waitForTimeout(1500);await page.locator('[data-table-song="tigers"]').click();
  await expect(page.locator('#table-panel')).toBeVisible({timeout:90000});await expect(page.locator('#table-song-title')).toContainText('两只老虎');
  await page.locator('.theatre-stage').scrollIntoViewIfNeeded();
  await expect.poll(async()=>(await request(`api/scenes/state?room=${room}`)).backend.tabletop?.elapsed??0,{timeout:60000}).toBeGreaterThan(3);
  await shot('competition-live-running');
  await expect(page.locator('#table-cue')).toContainText('楼下',{timeout:60000});await shot('competition-live-fall');
  await expect(page.locator('#show-status')).toHaveText('本幕完成 · 可重演或进入下一幕',{timeout:75000});
  const result=JSON.parse(await page.locator('#theatre-result').textContent());
  if(result.mode!=='live_linx'||result.cloud_audio_frames<1||!result.results.some(r=>r.name==='table_show'&&r.status==='completed'))throw Error('Missing actual cloud/physics result');
  chapter.result=result;chapter.timeline=await page.locator('#demo-timeline li').allTextContents();await shot('competition-live-result');await page.waitForTimeout(700);
 });await close();
 const after=await request(`api/voice/statistics?room=${room}&backend=mujoco`);
 proof.new_rounds=after.rounds.filter(r=>!proof.before_turns.includes(r.turn));
 if(proof.new_rounds.length<2||proof.new_rounds.some(r=>r.status!=='completed'))throw Error('Cloud rounds did not all finish normally');
 const diagnostics=await request(`api/voice/diagnostics?room=${room}`);
 proof.cloud_tool_events=diagnostics.events.filter(e=>e.id>beforeEvent&&['tool_start','tool_end','action_start','action_end'].includes(e.event));
 if(!proof.new_rounds.some(r=>r.actions.some(a=>a.tool==='duck_table_show'&&a.result==='completed')))throw Error('Missing real table tool action in statistics');
 if(!proof.cloud_tool_events.some(e=>e.event==='tool_end'&&e.tool==='duck_get_status'&&e.result==='ok'))throw Error('Missing real status query after the show');
 await open('experience','experience.html');await expect(page.locator('#experience-updated')).not.toBeEmpty();
 for(const [name,value] of [['hours','1'],['traffic','verification'],['page','demos'],['room',room],['backend','mujoco']])await page.selectOption(`select[name="${name}"]`,value);
 await page.locator('#refresh-experience').click();await expect(page.locator('#browser-experience')).toContainText('灵矽',{timeout:20000});
 await mark('persistent-experience',async()=>{
  await shot('competition-experience');chapter.summary=await request(`api/experience?hours=1&traffic=verification&page=demos&room=${room}&backend=mujoco`);
  await page.waitForTimeout(7000);await page.locator('#server-experience').scrollIntoViewIfNeeded();await shot('competition-experience-server');await page.waitForTimeout(8000);
 });await close();
 await open('statistics','statistics.html');await page.selectOption('#backend-filter','mujoco');await page.locator('#refresh-stats').click();await expect(page.locator('#round-text')).toContainText('桌上',{timeout:15000});
 await mark('round-timeline-and-latency',async()=>{
  chapter.statistics=await request(`api/voice/statistics?room=${room}&backend=mujoco`);
  await shot('competition-statistics');await page.waitForTimeout(7000);await page.locator('#latency-rows').scrollIntoViewIfNeeded();await shot('competition-statistics-latency');await page.waitForTimeout(8000);
 });await close();proof.completed=true;
}catch(e){proof.completed=false;proof.error=e.message;console.error(e.message);if(page&&!page.isClosed()){await shot('competition-recording-failure');await close()}}
finally{await context.request.post(new URL(`api/scenes/close?room=${room}`,base).href).catch(()=>{});await context.close();await browser.close();await save();console.log(resolve(output,'recording.json'))}
if(!proof.completed)process.exitCode=1;
