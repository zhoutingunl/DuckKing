import './style.css';
import './statistics.css';
import './experience.css';
import {appURL} from './urls.js';
const $=id=>document.getElementById(id),form=$('experience-filters');
const names={model_ms:'模型可见',scene_ms:'场景可见',navigation_ms:'首页首次可见',manifest_ms:'模型清单',asset_ms:'模型数据读取',parse_ms:'模型解析',assemble_ms:'模型组装',first_frame_ms:'首帧绘制等待',stt_local_ms:'本地识别文字返回',stt_cloud_ms:'灵矽识别文字返回',action_ms:'动作受理回执',audio_ms:'首段回复音频到达',reply_ms:'回复结束通知',asr_ms:'本地 ASR 工作进程'};
const routes={pending:'加载 / 尚未判定',local:'本地命中',cloud:'直连灵矽',cloud_fallback:'本地后转交灵矽',no_speech:'无清晰语音'};
const sourceName={browser:'浏览器',server:'服务器'},kindName={load:'加载',voice:'语音'};
const label=g=>`${names[g.metric]??g.metric}${g.route==='pending'&&!g.metric.includes('stt')?'':` · ${routes[g.route]}`}`;
const key=g=>[g.source,g.metric,g.route].join('|');
const num=v=>v==null?'—':Number(v).toLocaleString('zh-CN',{maximumFractionDigits:1});
function el(tag,text,cls){const e=document.createElement(tag);e.textContent=text??'';if(cls)e.className=cls;return e}
function row(table,values){const tr=el('tr');for(const v of values)tr.append(el('td',v));table.append(tr);return tr}
let data,loading=false,requested=false;
for(let n=1;n<=10;n++)form.elements.room.append(new Option(`房间 ${n}`,String(n)));
function render(){
 $('experience-empty').hidden=data.samples>0;
 $('experience-scope').textContent=`${data.collection_started_at?'开始采集于 '+new Date(data.collection_started_at*1000).toLocaleString('zh-CN'):'尚未收到采集记录'}；当前 ${data.samples} 条观测，含 ${data.hidden_samples} 条曾进入后台的记录`;
 $('experience-updated').textContent=`${new Date().toLocaleTimeString('zh-CN')} 更新 · 每 30 秒刷新`;
 $('experience-error').hidden=data.storage_ok&&data.dropped_since_start===0;
 $('experience-error').textContent=`${data.storage_ok?'':'统计存储暂不可用，请检查服务器磁盘。'}本次启动丢弃 ${data.dropped_since_start} 条上报，队列 ${data.queued} 条；统计可能不完整。`;
 const release=form.elements.release.value;form.elements.release.replaceChildren(new Option('全部版本','all'));
 for(const value of new Set([...data.releases,...(release!=='all'?[release]:[])]))form.elements.release.append(new Option(value==='development'?'本地开发':value.slice(0,10),value));form.elements.release.value=release;
 for(const source of ['browser','server']){
  const tbody=$(source+'-experience');tbody.replaceChildren();const groups=data.groups.filter(g=>g.source===source);
  for(const g of groups){const tr=row(tbody,[label(g),g.count,num(g.mean_ms),num(g.p50_ms),num(g.p90_ms),num(g.p95_ms)]);if(g.count<20)tr.firstChild.append(el('small','样本较少','sample-small'))}
  if(!groups.length)row(tbody,['尚无符合筛选的阶段样本','—','—','—','—','—']);
 }
 const selected=$('trend-metric').value;$('trend-metric').replaceChildren();
 for(const g of data.groups)$('trend-metric').append(new Option(`${sourceName[g.source]} · ${label(g)}`,key(g)));
 if(data.groups.some(g=>key(g)===selected))$('trend-metric').value=selected;
 renderTrend();
 const outcomes=new Map();
 for(const o of data.outcomes){const k=[o.source,o.kind,o.route].join('|');if(!outcomes.has(k))outcomes.set(k,{...o,counts:{}});const x=outcomes.get(k);x.counts[o.status]=(x.counts[o.status]??0)+o.count;}
 $('experience-outcomes').replaceChildren();
 for(const o of outcomes.values())row($('experience-outcomes'),[`${sourceName[o.source]} · ${kindName[o.kind]}${o.kind==='voice'?' · '+routes[o.route]:''}`,...['completed','failed','timeout','cancelled','abandoned'].map(s=>o.counts[s]??0),(o.counts.started??0)+(o.counts.waiting??0)]);
 if(!outcomes.size)row($('experience-outcomes'),['尚无记录','—','—','—','—','—','—']);
 $('export-experience').disabled=!data.groups.length;
}
function renderTrend(){
 const selected=$('trend-metric').value,points=data.trend.filter(g=>key(g)===selected);
 $('trend-rows').replaceChildren();for(const p of points)row($('trend-rows'),[new Date(p.at).toLocaleString('zh-CN'),p.count,num(p.mean_ms),num(p.p50_ms),num(p.p90_ms),num(p.p95_ms)]);
 const target=$('trend-chart');target.replaceChildren();
 $('trend-description').textContent=`${Number(form.elements.hours.value)<=24?'按小时':'按 UTC 日'}汇总，时段起点按浏览器时区显示。空白时段没有补零；图中的每一点可悬停查看样本数。`;
 if(!points.length){target.append(el('p','有样本后，这里会显示 P50 和 P95 的变化。','stats-empty'));return}
 const svg=document.createElementNS('http://www.w3.org/2000/svg','svg');svg.setAttribute('viewBox','0 0 1000 260');
 const make=(tag,attrs,text)=>{const n=document.createElementNS(svg.namespaceURI,tag);for(const [k,v] of Object.entries(attrs))n.setAttribute(k,v);n.textContent=text??'';svg.append(n);return n};
 const max=Math.max(1,...points.map(p=>p.p95_ms)),times=points.map(p=>Date.parse(p.at)),minTime=times[0],span=times.at(-1)-minTime;
 const x=i=>span?75+(times[i]-minTime)/span*880:510,y=v=>215-v/max*185;
 for(let i=0;i<=4;i++){const value=max*i/4;make('line',{x1:75,x2:955,y1:y(value),y2:y(value),stroke:'#dce4ce'});make('text',{x:64,y:y(value)+4,'text-anchor':'end'},num(value))}
 for(const [metric,color] of [['p50_ms','#5c783d'],['p95_ms','#517d9b']]){
  make('polyline',{points:points.map((p,i)=>`${x(i)},${y(p[metric])}`).join(' '),fill:'none',stroke:color,'stroke-width':2});
  points.forEach((p,i)=>{const c=make('circle',{cx:x(i),cy:y(p[metric]),r:4,fill:color});const t=document.createElementNS(svg.namespaceURI,'title');t.textContent=`${new Date(p.at).toLocaleString('zh-CN')} · ${metric==='p50_ms'?'P50':'P95'} ${num(p[metric])} ms · ${p.count} 个样本`;c.append(t)});
 }
 for(const i of new Set([0,points.length-1]))make('text',{x:x(i),y:246,'text-anchor':i===0?'start':'end'},new Date(points[i].at).toLocaleString('zh-CN',{month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit'}));
 target.append(svg);
}
async function refresh(){
 if(loading){requested=true;return}loading=true;requested=false;$('refresh-experience').disabled=true;
 const params=new URLSearchParams(new FormData(form)),url=appURL('api/experience');url.search=params.toString();
 try{const r=await fetch(url,{cache:'no-store',signal:AbortSignal.timeout(10000)});if(!r.ok)throw Error();const next=await r.json();if(!requested){data=next;render()}}
 catch{if(!requested){$('experience-error').hidden=false;$('experience-error').textContent='统计读取失败，当前数值未更新。请稍后刷新。'}}
 finally{loading=false;$('refresh-experience').disabled=false;if(requested)refresh()}
}
form.addEventListener('submit',e=>e.preventDefault());form.addEventListener('change',refresh);
$('refresh-experience').addEventListener('click',refresh);$('trend-metric').addEventListener('change',renderTrend);
$('export-experience').addEventListener('click',()=>{
 const lines=[['观测端','阶段','路径','样本','均值ms','P50','P90','P95',...Object.keys(data.filters)],...data.groups.map(g=>[sourceName[g.source],names[g.metric],routes[g.route],g.count,g.mean_ms,g.p50_ms,g.p90_ms,g.p95_ms,...Object.values(data.filters)])];
 const csv='\uFEFF'+lines.map(line=>line.map(v=>'"'+String(v??'').replaceAll('"','""')+'"').join(',')).join('\r\n');
 const url=URL.createObjectURL(new Blob([csv],{type:'text/csv;charset=utf-8'})),a=document.createElement('a');a.href=url;a.download='duckking-experience-'+new Date().toISOString().slice(0,10)+'.csv';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
});
const timer=setInterval(()=>{if(!document.hidden)refresh()},30000);window.addEventListener('pagehide',()=>clearInterval(timer));refresh();
