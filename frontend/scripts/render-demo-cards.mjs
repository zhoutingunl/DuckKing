import {chromium} from '@playwright/test';
import {readFile,mkdir} from 'node:fs/promises';
import {resolve} from 'node:path';
const [scriptFile,output,identity]=process.argv.slice(2);
if(!scriptFile||!output||!identity)throw Error('Usage: render-demo-cards.mjs SCRIPT OUTPUT IDENTITY');
const script=JSON.parse(await readFile(scriptFile,'utf8'));await mkdir(output,{recursive:true});
const browser=await chromium.launch({channel:process.env.DUCKKING_BROWSER_CHANNEL??'chrome'});
const page=await browser.newPage({viewport:{width:1600,height:1100}});
const escape=s=>s.replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;');
for(const [i,c] of script.chapters.entries()){
 const staticCard=['intro','outro'].includes(c.id);
 await page.setContent(`<html lang="zh"><meta charset="utf-8"><style>*{box-sizing:border-box}body{margin:0;font-family:"PingFang SC","Microsoft YaHei",sans-serif;background:${staticCard?'#182226':'transparent'};color:#f6f3e8}.card{height:1100px;padding:100px;display:flex;flex-direction:column;justify-content:center}.brand{color:#d7ec8a;letter-spacing:5px;font-size:28px}.rule{height:5px;background:#d7ec8a;width:110px;margin:55px 0}h1{font-size:68px;line-height:1.45;max-width:1300px;margin:0 0 30px}.caption{font-size:28px;line-height:1.7;color:#ccd5d2;max-width:1350px}.identity{font-size:20px;color:#9cafaa;margin-top:60px}.footer{position:absolute;top:1000px;left:0;width:1600px;height:100px;background:#182226;padding:13px 32px}.footer h1{font-size:27px;margin:0 0 5px}.footer .caption{font-size:20px;max-width:1550px;color:#d5ddd5}.footer .identity{position:absolute;right:32px;top:0;font-size:16px;margin-top:17px}</style>${staticCard?`<div class="card"><div class="brand">DUCKKING / CURRENT EDITION</div><div class="rule"></div><h1>${escape(c.title)}</h1><div class="caption">${escape(c.caption)}</div><div class="identity">${escape(identity)}<br>中文合成解说 · 页面原声未收录</div></div>`:`<div class="footer"><h1>${escape(c.title)}</h1><div class="caption">${escape(c.caption)}</div></div>`}</html>`);
 await page.screenshot({path:resolve(output,`${i}.png`),omitBackground:!staticCard});
}await browser.close();
