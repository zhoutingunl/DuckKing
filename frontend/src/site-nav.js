import './style.css';
import './site-nav.css';
import './mobile-stage.js';
import {currentLanguage, setLanguage, initUILanguage} from './ui-language.js';

await initUILanguage();

// Every page shares the same destinations, order and room-preservation rules.
const destinations=[
 ['index.html','首页'],
 ['scenarios.html','动作训练场'],['demos.html','演示场景'],
 ['studio.html','现场互动'],['training.html','训练新动作'],
 ['statistics.html','交互统计',true],['experience.html','使用体验',true],
 ['deploys.html','部署记录',true],
];
const languages=[['zh','中文'],['en','English'],['fr','Français']];
const nav=document.querySelector('.site-topbar nav');
if(nav){
 const page=location.pathname.split('/').at(-1)||'index.html';
 const params=new URL(location.href).searchParams;
 const room=params.get('room');
 const links=document.createElement('div');links.className='nav-destinations';
 const actions=document.createElement('div');actions.className='nav-actions';
 nav.append(links,actions);
 for(const [path,label,newTab] of destinations){
  const link=document.createElement('a'),url=new URL('./'+path,location.href);
  if(room&&/^\d+$/.test(room)&&path!=='deploys.html')url.searchParams.set('room',room);
  link.href=url;link.textContent=label;
  if(newTab){link.target='_blank';link.rel='noopener';link.title='新标签页打开，保留当前语音与场景'}
  if(page===path)link.setAttribute('aria-current','page');
  else if(path==='training.html'&&['balance.html','seesaw.html'].includes(page))link.setAttribute('aria-current','location');
  links.append(link);
 }
 const repo=document.createElement('a');
 repo.href='https://github.com/zhoutingunl/DuckKing';repo.target='_blank';repo.rel='noopener';
 repo.className='repo-link';repo.textContent='源代码 ↗';repo.title='源代码 ↗';
 actions.append(repo);
 // Apply language in place; preserve the room, model and physical scene.
 const wrap=document.createElement('div');wrap.className='lang-switch';
 const button=document.createElement('button');
 button.type='button';button.className='lang-button';button.id='lang-switch-button';
 button.setAttribute('aria-haspopup','menu');button.setAttribute('aria-expanded','false');
 button.setAttribute('aria-label','语言 / Language');button.textContent='语言';
 const menu=document.createElement('div');menu.className='lang-menu';menu.hidden=true;
 menu.setAttribute('role','menu');

 for(const [code,name] of languages){
  const option=document.createElement('button');
  option.type='button';option.setAttribute('role','menuitem');option.textContent=name;option.dataset.lang=code;
  option.addEventListener('click',()=>{menu.hidden=true;button.setAttribute('aria-expanded','false');setLanguage(code)});
  menu.append(option);
 }
 const markCurrent=()=>{for(const option of menu.children)option.setAttribute('aria-current',option.dataset.lang===currentLanguage()?'true':'false')};
 markCurrent();
 button.addEventListener('click',()=>{menu.hidden=!menu.hidden;button.setAttribute('aria-expanded',String(!menu.hidden))});
 document.addEventListener('click',event=>{if(!wrap.contains(event.target)){menu.hidden=true;button.setAttribute('aria-expanded','false')}});
 window.addEventListener('duckking-language-changed',markCurrent);
 wrap.append(button,menu);
 actions.append(wrap);
 // On narrow screens the source link scrolls with the page links; only the
 // language menu stays beside the brand. Desktop keeps both controls at right.
 const narrow=matchMedia('(max-width:1150px)');
 const placeSource=()=>narrow.matches?links.append(repo):actions.prepend(repo);
 placeSource();narrow.addEventListener('change',placeSource);
}
