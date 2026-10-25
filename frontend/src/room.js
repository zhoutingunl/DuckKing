import { appURL, setRoom } from './urls.js';

export async function setupRoom({claim=true}={}){
  const bar=document.createElement('div');bar.className='room-bar';bar.setAttribute('aria-label','独立房间');
  const label=document.createElement('strong');label.id='room-label';label.textContent='正在选择房间…';
  const links=document.createElement('span');links.className='room-links';
  const create=document.createElement('button');create.className='room-create';create.textContent='＋ 新建房间';create.id='create-room';
  const capacity=document.createElement('small');capacity.id='room-capacity';
  bar.append(label,links,create,capacity);document.querySelector('main').prepend(bar);
  let room=new URL(location.href).searchParams.get('room'),creating=false,signature='';
  const urlFor=id=>{const url=new URL(location.href);url.searchParams.set('room',id);return url};
  async function request(path,method='GET'){
    const response=await fetch(appURL(path),{method,cache:'no-store',signal:AbortSignal.timeout(10000)});
    if(response.status>=500)throw new Error(`本地后端请求失败（HTTP ${response.status}），请检查服务与端口并刷新。`);
    const data=await response.json();if(!response.ok)throw new Error(data.detail||'房间请求失败');return data;
  }
  function render(data){
    const next=JSON.stringify(data.rooms.map(r=>r.id));
    if(next!==signature){
      signature=next;links.replaceChildren();
      for(const {id} of data.rooms){
        const link=document.createElement('a');link.href=urlFor(id);link.textContent=`房间 ${id}`;link.dataset.room=id;
        if(id===room)link.setAttribute('aria-current','page');links.append(link);
      }
    }
    create.disabled=creating||data.rooms.length>=data.capacity;
    capacity.textContent=`${data.rooms.length} / ${data.capacity} 个房间 · 物理场景 ${data.physics_active} / ${data.physics_capacity}`;
    capacity.title=`无人使用 ${Math.round(data.idle_seconds/60)} 分钟后回收；共享链接可加入同一房间。`;
  }
  create.addEventListener('click',async()=>{
    creating=true;create.disabled=true;
    try{const data=await request('api/rooms','POST');location.assign(urlFor(data.room));}
    catch(error){label.textContent=error.message;creating=false;create.disabled=false;}
  });
  try{
    if(!room&&claim)room=(await request('api/rooms/claim','POST')).room;
    room??='1';const data=await request('api/rooms');render(data);
    if(!data.rooms.some(r=>r.id===room))throw new Error('房间不存在或已回收，请新建或选择已有房间');
    setRoom(room);history.replaceState(null,'',urlFor(room));label.textContent=`房间 ${room} · 独立语音与场景`;
    for(const link of document.querySelectorAll('a[href]')){
      const target=new URL(link.href);if(link.dataset.room||target.origin!==location.origin)continue;
      if(target.pathname.endsWith('deploys.html'))continue;
      target.searchParams.set('room',room);link.href=target;
    }
    const timer=setInterval(()=>{if(!document.hidden)request('api/rooms').then(render).catch(()=>{})},15000);
    window.addEventListener('pagehide',()=>clearInterval(timer),{once:true});
  }catch(error){
    label.textContent=error.message;
    document.querySelectorAll('main button:not(#create-room)').forEach(b=>b.disabled=true);
    // Keep room creation/navigation usable when a shared link has expired.
    await request('api/rooms').then(render).catch(()=>{});throw error;
  }
}
