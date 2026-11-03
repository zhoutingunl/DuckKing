import {createRequire} from 'node:module';
const {chromium}=createRequire(import.meta.url)(process.env.DUCKKING_PLAYWRIGHT_MODULE||'@playwright/test');
import { mkdir, writeFile } from 'node:fs/promises';
const output=process.env.DUCKKING_BENCH_OUTPUT;
if(!output)throw new Error('Set DUCKKING_BENCH_OUTPUT outside the repository');
await mkdir(output,{recursive:true});
const browser=await chromium.launch({executablePath:process.env.DUCKKING_CHROMIUM_EXECUTABLE,headless:true});
const rows=[];
try{
 for(const [name,width,height] of [['desktop',1280,900],['narrow',390,844]]){
  const context=await browser.newContext({viewport:{width,height},deviceScaleFactor:1});
  const page=await context.newPage();const errors=[];page.on('pageerror',e=>errors.push(e.name));
  const begun=Date.now();await page.goto('https://duck.qbox.net/?measurement=verification',{waitUntil:'domcontentloaded'});
  await page.waitForFunction(()=>document.querySelector('#viewport')?.dataset.model==='official',null,{timeout:75000});
  const readyMs=Date.now()-begun;
  await page.evaluate(()=>{window.benchGaps=[];let last=performance.now();window.benchCollect=true;function tick(t){if(!window.benchCollect)return;window.benchGaps.push(t-last);last=t;requestAnimationFrame(tick)}requestAnimationFrame(tick)});
  await page.locator('[data-action="nod"]').click();
  await page.waitForTimeout(5000);
  const measured=await page.evaluate(()=>{
   window.benchCollect=false;const a=window.benchGaps.slice(1).sort((x,y)=>x-y),gl=document.querySelector('#viewport canvas')?.getContext('webgl2');
   return {room:new URL(location.href).searchParams.get('room'),model:JSON.parse(document.querySelector('#viewport').dataset.modelTiming),
    rafGapP95:a[Math.ceil(a.length*.95)-1],rafGapMax:a.at(-1),samples:a.length,viewport:innerWidth,
    horizontalOverflow:document.documentElement.scrollWidth>innerWidth,secureContext:isSecureContext,
    connection:document.querySelector('#connection-label')?.textContent,actionCount:document.querySelector('#action-count')?.textContent,
    graphicsRenderer:gl?.getParameter(gl.RENDERER)};
  });
  await page.screenshot({path:`${output}/${name}.png`});
  rows.push({name,readyMs,...measured,errors,scope:'one headless desktop Chromium; narrow viewport is not physical phone hardware'});
  console.log(JSON.stringify(rows.at(-1)));
  await context.close();
 }
 await writeFile(`${output}/browser.json`,JSON.stringify({at:new Date().toISOString(),rows},null,2));
}finally{await browser.close()}
