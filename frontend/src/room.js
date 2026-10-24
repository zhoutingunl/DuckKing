import { appURL, setRoom } from './urls.js';

export async function setupRoom({claim=true}={}){
  const bar=document.createElement('div');bar.className='room-bar';bar.setAttribute('aria-label','独立房间');
  const label=document.createElement('strong');label.id='room-label';label.textContent='正在选择房间…';bar.append(label);
  for(const id of ['1','2']){
    const link=document.createElement('a'),url=new URL(location.href);url.searchParams.set('room',id);
    link.href=url;link.textContent=`房间 ${id}`;link.dataset.room=id;bar.append(link);
  }
  document.querySelector('main').prepend(bar);
  let room=new URL(location.href).searchParams.get('room');
  try{
    if(!room&&claim){
      const response=await fetch(appURL('api/rooms/claim'),{method:'POST',signal:AbortSignal.timeout(8000)});
      const data=await response.json();if(!response.ok)throw new Error(data.detail||'房间分配失败');room=data.room;
    }
    room??='1';if(!['1','2'].includes(room))throw new Error('未知房间，请选择房间 1 或房间 2');
    setRoom(room);const url=new URL(location.href);url.searchParams.set('room',room);history.replaceState(null,'',url);
    label.textContent=`房间 ${room} · 独立语音与场景`;
    bar.querySelector(`[data-room="${room}"]`).setAttribute('aria-current','page');
    for(const link of document.querySelectorAll('a[href]')){
      const target=new URL(link.href);if(link.dataset.room||target.origin!==location.origin)continue;
      if(target.pathname.endsWith('deploys.html'))continue;
      target.searchParams.set('room',room);link.href=target;
    }
  }catch(error){label.textContent=error.message;document.querySelectorAll('main button').forEach(b=>b.disabled=true);throw error;}
}
