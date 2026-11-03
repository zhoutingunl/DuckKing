import {appURL,setRoom,setServiceInstance,setRoomUnavailable} from './urls.js';

export function rememberChoice(key,value){const url=new URL(location.href);url.searchParams.set(key,value);history.replaceState(null,'',url)}
export const savedChoice=key=>new URL(location.href).searchParams.get(key);

export async function setupRoom({claim=true}={}){
  const main=document.querySelector('main'),bar=document.createElement('div');bar.className='room-bar';bar.setAttribute('aria-label','独立房间');
  const label=document.createElement('strong');label.id='room-label';label.textContent='正在选择房间…';
  const links=document.createElement('span');links.className='room-links';links.tabIndex=0;links.setAttribute('aria-label','房间列表，可横向滚动');
  const create=document.createElement('button');create.className='room-create';create.textContent='＋ 新建房间';create.id='create-room';
  const capacity=document.createElement('small');capacity.id='room-capacity';
  bar.append(label,links,create,capacity);main.prepend(bar);
  const banner=document.createElement('section');banner.id='room-recovery';banner.className='room-recovery';banner.hidden=true;banner.setAttribute('role','alert');
  const heading=document.createElement('strong'),explanation=document.createElement('p'),reconnect=document.createElement('button');reconnect.id='reconnect-room';reconnect.textContent='重新连接房间';
  banner.append(heading,explanation,reconnect);bar.after(banner);
  let room=new URL(location.href).searchParams.get('room'),creating=false,signature='',instance=null,lost=false,polling=false,timer;
  const urlFor=id=>{const url=new URL(location.href);url.searchParams.set('room',id);return url};
  async function request(path,method='GET'){
    const response=await fetch(appURL(path),{method,cache:'no-store',signal:AbortSignal.timeout(10000)});
    if(response.status>=500)throw new Error('暂时无法连接服务，请稍后重试。');
    const data=await response.json();if(!response.ok)throw new Error(data.detail||'房间请求失败');return data;
  }
  function unavailable(text){
    heading.textContent=text;explanation.textContent='服务可能刚更新，或房间已被回收。当前页面及链接中的选择会保留；重新连接后请手动继续，不会自动重放动作、演出或录音。';banner.hidden=false;
    label.textContent='房间暂不可用';document.body.classList.add('room-unavailable');
    for(const child of main.children)if(child!==bar&&child!==banner)child.inert=true;
    setRoomUnavailable(true);
    if(!lost){lost=true;window.dispatchEvent(new Event('duckking-room-lost'));}
  }
  function render(data){
    const next=JSON.stringify(data.rooms.map(r=>r.id));
    if(next!==signature){signature=next;links.replaceChildren();for(const {id} of data.rooms){
      const link=document.createElement('a');link.href=urlFor(id);link.textContent=`房间 ${id}`;link.dataset.room=id;
      if(id===room)link.setAttribute('aria-current','page');links.append(link);
    }}
    create.disabled=creating||data.rooms.length>=data.capacity;
    capacity.textContent=`${data.rooms.length} / ${data.capacity} 个房间 · 物理场景 ${data.physics_active} / ${data.physics_capacity}`;
    capacity.title=`无人使用 ${data.idle_seconds} 秒后回收；共享链接可加入同一房间。`;
  }
  async function recover(fresh=false){
    if(creating)return;creating=true;create.disabled=reconnect.disabled=true;reconnect.textContent='正在重新连接…';
    try{const data=await request(fresh?'api/rooms':'api/rooms/claim','POST');const url=urlFor(data.room);url.searchParams.set('reconnected','1');location.assign(url);}
    catch(error){heading.textContent=error.message;banner.hidden=false;creating=false;reconnect.disabled=false;reconnect.textContent='重试连接';create.disabled=false;}
  }
  reconnect.addEventListener('click',()=>recover());create.addEventListener('click',()=>recover(true));
  window.addEventListener('duckking-room-expired',()=>unavailable('服务已更新，请重新连接房间'));
  async function poll(){
    if(polling||lost||document.hidden)return;polling=true;
    try{const data=await request(`api/rooms?room=${encodeURIComponent(room)}`);render(data);
      if(instance&&data.instance&&data.instance!==instance)unavailable('服务已更新，请重新连接房间');
      else if(!data.rooms.some(r=>r.id===room))unavailable('原房间已回收，请重新连接');
    }catch{/* A transient network outage must not discard a live room. */}
    finally{polling=false}
  }
  try{
    if(!room&&claim)room=(await request('api/rooms/claim','POST')).room;
    room??='1';const data=await request(`api/rooms?room=${encodeURIComponent(room)}`);render(data);
    if(!data.rooms.some(r=>r.id===room))throw new Error('原房间不存在或已回收');
    instance=data.instance??null;setServiceInstance(instance);setRoomUnavailable(false);setRoom(room);
    history.replaceState(null,'',urlFor(room));label.textContent=`房间 ${room} · 独立语音与场景`;
    for(const link of document.querySelectorAll('a[href]')){const target=new URL(link.href);
      if(link.dataset.room||target.origin!==location.origin||target.pathname.endsWith('deploys.html'))continue;
      target.searchParams.set('room',room);link.href=target;
    }
    timer=setInterval(poll,15000);document.addEventListener('visibilitychange',poll);
    window.addEventListener('pagehide',()=>{clearInterval(timer);document.removeEventListener('visibilitychange',poll)},{once:true});
  }catch(error){
    unavailable(error.message);await request('api/rooms').then(render).catch(()=>{});
    // Keep recovery interactive without running application code in a missing room.
    return new Promise(()=>{});
  }
}
