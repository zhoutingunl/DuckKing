import {series,metricLabels} from './balance-explain.js';
const NS='http://www.w3.org/2000/svg';
const node=(name,attrs={})=>{const e=document.createElementNS(NS,name);for(const[k,v]of Object.entries(attrs))e.setAttribute(k,v);return e};
export function drawChart(container,rows,key,onSelect){
 const points=series(rows,key);container.replaceChildren();
 if(!points.length){const p=document.createElement('p');p.className='chart-empty';p.textContent='等待真实采样。尚无数据时不绘制曲线。';container.append(p);return}
 const success=key==='success_rate',w=620,h=220,left=62,right=18,top=20,bottom=36;
 const xmax=Math.max(1024,...points.map(p=>p.step));let ymin=success?0:Math.min(0,...points.map(p=>p.value)),ymax=success?1:Math.max(...points.map(p=>p.value));if(ymax-ymin<1e-9)ymax=ymin+1;
 const x=v=>left+v/xmax*(w-left-right),y=v=>h-bottom-(v-ymin)/(ymax-ymin)*(h-top-bottom);
 const svg=node('svg',{viewBox:`0 0 ${w} ${h}`,role:'img','aria-label':`${metricLabels[key]?.[0]??key}随训练步数变化`});
 for(let i=0;i<=4;i++){
  const value=ymin+(ymax-ymin)*i/4,yy=y(value);svg.append(node('line',{x1:left,y1:yy,x2:w-right,y2:yy,class:'chart-grid'}));
  const text=node('text',{x:left-10,y:yy+4,'text-anchor':'end'});text.textContent=success?`${Math.round(value*100)}%`:Number(value.toPrecision(3));svg.append(text);
 }
 for(const step of [0,xmax/2,xmax]){const text=node('text',{x:x(step),y:h-10,'text-anchor':'middle'});text.textContent=String(Math.round(step));svg.append(text)}
 const line=points.map((p,i)=>`${i?'L':'M'}${x(p.step)},${y(p.value)}`).join(' ');svg.append(node('path',{d:line,fill:'none',class:'chart-line'}));
 if(success)for(const p of points){if(p.row.ci95)svg.append(node('line',{x1:x(p.step),x2:x(p.step),y1:y(p.row.ci95[0]),y2:y(p.row.ci95[1]),class:'chart-ci'}))}
 const cursor=node('line',{y1:top,y2:h-bottom,class:'chart-cursor',visibility:'hidden'});svg.append(cursor);
 const label=document.createElement('p');label.className='chart-reading';label.textContent=`${points.length} 个实测点 · 横轴：训练环境步数${success?' · 竖线：Wilson 95% 区间':''}`;
 function choose(p){cursor.setAttribute('x1',x(p.step));cursor.setAttribute('x2',x(p.step));cursor.setAttribute('visibility','visible');label.textContent=`${p.step.toLocaleString()} 步：${success?(p.value*100).toFixed(1)+'%':p.value.toPrecision(4)}${success?`（${p.row.successes}/${p.row.episodes}）`:''} · 记录耗时 ${(p.row.elapsed_s/60).toFixed(1)} 分钟`;onSelect?.(p.row)}
 for(const p of points){const circle=node('circle',{cx:x(p.step),cy:y(p.value),r:4,tabindex:'0',role:'button','aria-label':`${p.step}步 ${p.value}`,class:'chart-point'});circle.addEventListener('focus',()=>choose(p));circle.addEventListener('click',()=>choose(p));circle.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' ')choose(p)});svg.append(circle)}
 svg.addEventListener('pointermove',event=>{const rect=svg.getBoundingClientRect(),at=(event.clientX-rect.left)/rect.width*w;choose(points.reduce((a,b)=>Math.abs(x(a.step)-at)<Math.abs(x(b.step)-at)?a:b))});
 container.append(svg,label);
}
