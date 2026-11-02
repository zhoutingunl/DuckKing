import './style.css';
import './site-nav.css';

// Every page shares the same destinations, order and room-preservation rules.
const destinations=[
 ['training.html','训练新动作'],['scenarios.html','动作练习场'],
 ['demos.html','演示场景'],['studio.html','现场互动'],
 ['experience.html','使用体验',true],['statistics.html','交互统计',true],
 ['deploys.html','部署记录',true],
];
const nav=document.querySelector('.site-topbar nav');
if(nav){
 const page=location.pathname.split('/').at(-1)||'index.html';
 const room=new URL(location.href).searchParams.get('room');
 for(const [path,label,newTab] of destinations){
  const link=document.createElement('a'),url=new URL('./'+path,location.href);
  if(room&&/^\d+$/.test(room)&&path!=='deploys.html')url.searchParams.set('room',room);
  link.href=url;link.textContent=label;
  if(newTab){link.target='_blank';link.rel='noopener';link.title='新标签页打开，保留当前语音与场景'}
  if(page===path)link.setAttribute('aria-current','page');
  else if(path==='training.html'&&['balance.html','seesaw.html'].includes(page))link.setAttribute('aria-current','location');
  nav.append(link);
 }
}
