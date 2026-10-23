import { chromium } from '@playwright/test';
import { mkdir, writeFile, rm } from 'node:fs/promises';
import { spawnSync } from 'node:child_process';
import { resolve } from 'node:path';

// Explicit live acceptance recording. Uses the configured account and consumes cloud quota.
// Input is a supplied synthetic-speech WAV; the cloud, tool call and returned audio are real.
const input=process.env.DUCKKING_TEST_AUDIO;
const label=process.env.DUCKKING_RECORD_LABEL??'live-linx-voice';
const expected=process.env.DUCKKING_EXPECT_ACTION??'nod';
const baseURL=process.env.DUCKKING_DEMO_URL??'http://127.0.0.1:8765';
if(!/^[a-z0-9-]+$/.test(label))throw new Error('Record label must be a simple filename stem');
if(!input)throw new Error('Set DUCKKING_TEST_AUDIO to a Chinese speech WAV padded with silence');
const output=resolve('../docs/media');await mkdir(output,{recursive:true});
const browser=await chromium.launch({args:['--use-fake-ui-for-media-stream','--use-fake-device-for-media-stream',`--use-file-for-fake-audio-capture=${resolve(input)}`]});
const context=await browser.newContext({baseURL,permissions:['microphone'],viewport:{width:1320,height:1080},recordVideo:{dir:resolve('test-results/live-demo'),size:{width:1320,height:1080}}});
const started=Date.now(), page=await context.newPage(),transcripts=[],chunks=[];
let inputAt=0,audioAt=0,sampleRate=0;
page.on('websocket',socket=>{
  if(!socket.url().endsWith('/voice'))return;
  socket.on('framesent',frame=>{
    if(typeof frame.payload==='string'){
      const data=JSON.parse(frame.payload);
      if(data.type==='listen_start')inputAt=Date.now()-started;
    }
  });
  socket.on('framereceived',frame=>{
    if(typeof frame.payload!=='string')return;
    const data=JSON.parse(frame.payload);
    if(data.type==='transcript')transcripts.push({role:data.role,text:data.text});
    if(data.type==='audio'){
      audioAt ||= Date.now()-started;sampleRate=data.sample_rate;
      chunks.push(Buffer.from(data.pcm,'base64'));
    }
  });
});
try{
  await page.goto(baseURL);
  const initialState=await (await page.request.get('/api/state')).json();
  const eventBaseline=Math.max(0,...initialState.events.map(event=>event.id));
  await page.evaluate(()=>{document.querySelector('.subtitle').textContent='真实灵矽演示：输入为系统合成语音；识别、工具调用与回复来自真实云端。'});
  await page.locator('#connect-voice').click();
  await page.waitForFunction(()=>document.querySelector('#voice-badge').textContent==='灵矽已连接',null,{timeout:20000});
  await page.waitForTimeout(1800);
  await page.waitForFunction(()=>!document.querySelector('#talk-button').disabled);
  const position=await page.locator('#talk-button').boundingBox();
  await page.mouse.move(position.x+position.width/2,position.y+position.height/2);
  await page.mouse.down();await page.waitForTimeout(3000);await page.mouse.up();
  await page.waitForFunction(async({expected,eventBaseline})=>{
    const state=await (await fetch('/api/state')).json();
    for(const event of state.events.filter(event=>event.id>eventBaseline&&event.kind==='result')){
      const action=await (await fetch(`/api/actions/${event.action_id}`)).json();
      if(action.name===expected&&action.status==='completed')return true;
    }
    return false;
  },{expected,eventBaseline},{timeout:45000,polling:150});
  await page.waitForFunction(()=>document.querySelector('#voice-badge').textContent==='灵矽已连接',null,{timeout:45000});
  await page.waitForTimeout(3500);
  await page.locator('#activity-log').scrollIntoViewIfNeeded();
  await page.screenshot({path:resolve(output,label==='live-linx-voice'?'live-voice.png':`${label}.png`),fullPage:true});
  const finalState=await (await page.request.get('/api/state')).json();
  const ids=[...new Set(finalState.events.filter(event=>event.id>eventBaseline&&event.kind==='result').map(event=>event.action_id))];
  const actions=await Promise.all(ids.map(async id=>(await (await page.request.get(`/api/actions/${id}`)).json())));
  await page.locator('#connect-voice').click();
  await page.waitForTimeout(500);
  if(!chunks.length||!transcripts.some(t=>t.role==='user'))throw new Error('Missing real cloud audio/transcript');
  const video=page.video();await context.close();const source=await video.path();
  const raw=resolve('test-results/live-response.pcm');await writeFile(raw,Buffer.concat(chunks));
  const wav=resolve(output,label==='live-linx-voice'?'linx-response.wav':`${label}-response.wav`);
  let result=spawnSync('ffmpeg',['-y','-loglevel','error','-f','s16le','-ar',String(sampleRate),'-ac','1','-i',raw,wav],{stdio:'inherit'});
  if(result.status)throw new Error('Response audio encoding failed');
  const mix=`[1:a]adelay=${inputAt}:all=1[a1];[2:a]adelay=${audioAt}:all=1[a2];[a1][a2]amix=inputs=2:normalize=0,apad[a]`;
  result=spawnSync('ffmpeg',['-y','-loglevel','error','-i',source,'-i',resolve(input),'-i',wav,'-filter_complex',mix,'-map','0:v','-map','[a]','-c:v','libx264','-crf','25','-preset','veryfast','-c:a','aac','-b:a','96k','-pix_fmt','yuv420p','-shortest','-movflags','+faststart',resolve(output,`${label}.mp4`)],{stdio:'inherit'});
  if(result.status)throw new Error('Live video encoding failed');
  await writeFile(resolve(output,`${label}.json`),JSON.stringify({tested_at:new Date().toISOString(),input:'System-generated Chinese speech supplied through browser microphone capture',cloud:'Real Linx service',audio_note:'Audio track reconstructed from the actual input WAV and received PCM; approximate capture timestamps',expected_action:expected,actions,transcripts,sample_rate:sampleRate,audio_bytes:Buffer.concat(chunks).length},null,2));
  await rm(raw);await rm(source);
  console.log('Recorded real Linx voice + MCP action demonstration');
}finally{await browser.close()}
