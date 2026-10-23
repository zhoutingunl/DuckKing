import { chromium } from '@playwright/test';
import { mkdir, rename, rm } from 'node:fs/promises';
import { spawnSync } from 'node:child_process';
import { resolve } from 'node:path';

const output=resolve('../docs/media');
const choreographed=process.env.DUCKKING_DEMO_SEQUENCE==='choreography';
const label=choreographed?'choreography-preview':'local-preview';
await mkdir(output,{recursive:true});
const browser=await chromium.launch();
const context=await browser.newContext({viewport:{width:1320,height:1080},recordVideo:{dir:resolve('test-results/demo'),size:{width:1320,height:1080}}});
const page=await context.newPage();
await page.goto(process.env.DUCKKING_DEMO_URL??'http://127.0.0.1:8765');
await page.waitForFunction(()=>document.querySelector('#connection-label')?.textContent==='本地工作台已连接');
await page.evaluate(choreographed=>{document.querySelector('.subtitle').textContent=choreographed?'闪身步 / 狗熊哆嗦毛 · 机器人改编动作 · 本段为动画预览。':'演示范围：本地动画预览与真实动作控制接口。未调用灵矽云端。'},choreographed);
await page.waitForTimeout(1500);
await page.screenshot({path:resolve(output,choreographed?'choreography-preview.png':'workbench.png'),fullPage:true});
for(const action of choreographed?['flash_step','bear_shake']:['nod','walk','turn_left','turn_right']){
  await page.locator(`[data-action="${action}"]`).click();
  await page.waitForTimeout(choreographed?3500:1900);
}
await page.locator(`[data-action="${choreographed?'flash_step':'walk'}"]`).click();
await page.waitForTimeout(choreographed?750:350);
await page.keyboard.press('Escape');
await page.waitForTimeout(1500);
await page.locator('[data-action="reset"]').click();
await page.waitForTimeout(1500);
await page.locator('#activity-log').scrollIntoViewIfNeeded();
await page.waitForTimeout(2000);
const video=page.video();
await context.close();
const source=await video.path();
await browser.close();
const target=resolve(output,`${label}.mp4`);
const encoded=spawnSync('ffmpeg',['-y','-loglevel','error','-i',source,'-an','-c:v','libx264','-crf','25','-preset','veryfast','-pix_fmt','yuv420p','-movflags','+faststart',target],{stdio:'inherit'});
if(encoded.status!==0){await rename(source,resolve(output,`${label}.webm`));throw new Error('ffmpeg failed; kept the original WebM')}
await rm(source);
console.log(target);
