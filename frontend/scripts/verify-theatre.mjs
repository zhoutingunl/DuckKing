// Actual shipped speech + real backend; no intercepted protocol or audio fixtures.
import {chromium,expect} from '@playwright/test';
import {writeFileSync,mkdirSync} from 'node:fs';
import {DEMOS} from '../src/demo-catalog.js';
const base=process.env.DUCKKING_DEMO_URL??'http://127.0.0.1:8765/';
const mode=process.env.DUCKKING_DEMO_MODE??'rehearsal';
const ids=(process.env.DUCKKING_DEMO_IDS??DEMOS.map(d=>d.id).join(',')).split(',');
if(!['rehearsal','live'].includes(mode)||ids.some(id=>!DEMOS.some(d=>d.id===id)))throw new Error('Invalid mode / scene selection');
const output=process.env.DUCKKING_DEMO_PROOF??'../.duckking/theatre-acceptance.json';
const browser=await chromium.launch({headless:true,...(process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE?{executablePath:process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE}:{})});
const context=await browser.newContext({viewport:{width:1440,height:1050}}),page=await context.newPage();
const proof={tested_at:new Date().toISOString(),base,mode,source:'shipped prerecorded speech, actual backend; no microphone or human listening',passed:false,scenes:[],page_errors:[]};
page.on('pageerror',e=>proof.page_errors.push(e.message));
await page.addInitScript(()=>{
 window.theatreAudio={buffers:0,nonzero:0,oscillators:0};
 const start=AudioBufferSourceNode.prototype.start;AudioBufferSourceNode.prototype.start=function(...args){
  window.theatreAudio.buffers++;if(this.buffer&&this.buffer.getChannelData(0).some(v=>Math.abs(v)>.001))window.theatreAudio.nonzero++;return start.apply(this,args);
 };
 const osc=OscillatorNode.prototype.start;OscillatorNode.prototype.start=function(...args){window.theatreAudio.oscillators++;return osc.apply(this,args)};
});
try{
 const health=await (await context.request.get(new URL('api/health',base).href)).json();proof.release=health.release;
 await page.goto(new URL('demos.html?room=1',base).href);await page.locator('#demo-mode').selectOption(mode);
 for(const id of ids){
  const started=Date.now();await page.locator(`[data-demo="${id}"]`).click();
  await expect(page.locator('#show-status')).toHaveText(/本幕完成|本幕未完成/,{timeout:240000});
  const error=await page.locator('#demo-notice').isVisible()?await page.locator('#demo-notice').textContent():null;
  if(error){proof.scenes.push({id,passed:false,error,elapsed_ms:Date.now()-started});throw new Error(id+': '+error)}
  await expect(page.locator('#demo-mode')).toBeEnabled({timeout:20000});
  const result=JSON.parse(await page.locator('#theatre-result').textContent());expect(result.scene).toBe(id);
  const row={id,passed:true,elapsed_ms:Date.now()-started,result,timeline:await page.locator('#demo-timeline li').allTextContents(),audio:await page.evaluate(()=>window.theatreAudio)};
  proof.scenes.push(row);console.log(JSON.stringify({id,passed:true,elapsed_ms:row.elapsed_ms,audio:row.audio}));
  if(['delivery','chorale','tabletop'].includes(id)){mkdirSync('../.duckking/theatre-images',{recursive:true});await page.screenshot({path:`../.duckking/theatre-images/${mode}-${id}.png`,fullPage:true});}
 }
 expect(proof.page_errors).toEqual([]);expect(proof.scenes.at(-1).audio.nonzero).toBeGreaterThan(0);proof.passed=true;
}finally{await browser.close();writeFileSync(output,JSON.stringify(proof,null,2)+'\n');}
