import { appURL, currentRoom } from './urls.js';

const MAX_FRAME=256*1024,MAX_QUEUE=1024*1024,MAX_BATCH=32;
const encode=bytes=>{let text='';for(let i=0;i<bytes.length;i+=8192)text+=String.fromCharCode(...bytes.subarray(i,i+8192));return btoa(text)};
const decode=text=>Uint8Array.from(atob(text),c=>c.charCodeAt(0)).buffer;

// Both transports reach the same backend WebSocket. HTTPS polling is explicitly
// advertised by ai_gateway for ingress that removes the Upgrade header.
export class DuckSocket extends EventTarget {
  constructor(endpoint,{url=appURL(endpoint),fetch=globalThis.fetch.bind(globalThis),WebSocket=globalThis.WebSocket}={}){
    super();this.url=new URL(url);this.endpoint=endpoint.replace(/^\/+/, '');this.fetch=fetch;this.Native=WebSocket;
    this.readyState=0;this.binaryType='arraybuffer';this.queue=[];this.bufferedAmount=0;this.sequence=0;
    this.controllers=new Set();this.closed=false;this.native=null;this.channel=null;
    this.pagehide=()=>this.close();globalThis.addEventListener?.('pagehide',this.pagehide,{once:true});
    queueMicrotask(()=>this.open().catch(()=>this.finish('transport_unavailable')));
  }
  emit(type,fields={}){
    const event=Object.assign(new Event(type),fields);this.dispatchEvent(event);this['on'+type]?.(event);
  }
  async request(url,options={},timeout=20000){
    const controller=new AbortController();this.controllers.add(controller);
    const timer=setTimeout(()=>controller.abort(),timeout);
    try{
      const response=await this.fetch(url,{cache:'no-store',credentials:'same-origin',...options,signal:controller.signal});
      if(!response.ok)throw new Error('transport_request_failed');
      return response.status===204?null:await response.json();
    }finally{clearTimeout(timer);this.controllers.delete(controller)}
  }
  async open(){
    if(this.closed)return;
    let transport='websocket';
    if(this.url.pathname.startsWith('/duckking/')){
      const probe=new URL('_gateway/capabilities',this.url);
      const controller=new AbortController();this.controllers.add(controller);
      const timer=setTimeout(()=>controller.abort(),5000);
      try{
        const response=await this.fetch(probe,{cache:'no-store',signal:controller.signal});
        if(response.ok){
          const capabilities=await response.json();
          if(capabilities.protocol!==1||!['websocket','https-poll'].includes(capabilities.transport))throw new Error('unknown_transport');
          transport=capabilities.transport;
        }else if(response.status!==404)throw new Error('gateway_unavailable');
      }finally{clearTimeout(timer);this.controllers.delete(controller)}
    }
    if(this.closed)return;
    this.transport=transport;
    if(transport==='websocket'){
      const url=new URL(this.url);url.protocol=url.protocol==='https:'?'wss:':'ws:';
      this.native=new this.Native(url);this.native.binaryType=this.binaryType;
      this.native.onopen=()=>{this.readyState=1;this.emit('open')};
      this.native.onmessage=e=>this.emit('message',{data:e.data});
      this.native.onerror=()=>this.emit('error');
      this.native.onclose=e=>this.finish(e.reason,e.code);return;
    }
    // Do not abort creation on user cancellation: if it succeeds, DELETE its ID.
    const opened=await this.request(new URL('_gateway/channels',this.url),{
      method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({endpoint:this.endpoint})},7000);
    if(!/^[a-f0-9]{32}$/.test(opened.id))throw new Error('invalid_channel');
    this.channel=new URL('_gateway/channels/'+opened.id,this.url);
    if(this.closed){this.remove();return}
    this.readyState=1;this.emit('open');
    await this.poll();
  }
  async poll(){
    while(!this.closed){
      const packet=await this.request(this.channel);
      if(this.closed)return;
      if(!Array.isArray(packet.frames)||packet.frames.length>MAX_BATCH)throw new Error('invalid_frames');
      for(const frame of packet.frames){
        if(typeof frame.binary!=='boolean'||typeof frame.data!=='string'||frame.data.length>MAX_FRAME*4/3+4)throw new Error('invalid_frame');
        const data=frame.binary?decode(frame.data):frame.data;
        this.emit('message',{data:frame.binary&&this.binaryType==='blob'?new Blob([data]):data});
        if(this.closed)return;
      }
      if(packet.closed){this.finish(packet.reason);return}
    }
  }
  send(data){
    if(this.readyState!==1)throw new DOMException('Socket is not open','InvalidStateError');
    if(this.native){this.native.send(data);return}
    const binary=typeof data!=='string';
    const bytes=binary?(data instanceof ArrayBuffer?new Uint8Array(data):ArrayBuffer.isView(data)?new Uint8Array(data.buffer,data.byteOffset,data.byteLength):null):new TextEncoder().encode(data);
    if(!bytes)throw new TypeError('Expected text or binary audio');
    if(bytes.byteLength>MAX_FRAME||this.bufferedAmount+bytes.byteLength>MAX_QUEUE){this.finish('send_queue_full');return}
    this.bufferedAmount+=bytes.byteLength;
    this.queue.push({binary,data:binary?encode(bytes):data,size:bytes.byteLength});
    if(!this.sending&&!this.sendTimer)this.sendTimer=setTimeout(()=>{this.sendTimer=null;this.flush().catch(()=>this.finish('send_failed'))},15);
  }
  async flush(){
    this.sending=true;
    try{
      while(!this.closed&&this.queue.length){
        const batch=[];let size=0;
        // Bound the base64 JSON request as well as each individual frame.
        while(this.queue.length&&batch.length<MAX_BATCH&&size+this.queue[0].size<=512*1024){const frame=this.queue.shift();size+=frame.size;batch.push(frame)}
        const ack=await this.request(this.channel,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({sequence:this.sequence,frames:batch.map(({binary,data})=>({binary,data}))})},7000);
        if(this.closed)return;
        if(ack.sequence!==this.sequence+1)throw new Error('invalid_sequence');
        this.sequence++;this.bufferedAmount-=size;
      }
    }finally{this.sending=false}
  }
  remove(){
    if(this.channel){const url=this.channel;this.channel=null;this.fetch(url,{method:'DELETE',keepalive:true}).catch(()=>{})}
  }
  close(){this.finish('client_closed',1000)}
  finish(reason='',code=1006){
    if(this.closed)return;
    this.closed=true;this.readyState=3;clearTimeout(this.sendTimer);this.queue=[];this.bufferedAmount=0;
    // An in-flight creation may still return an ID. open() deletes it afterwards.
    if(this.channel)for(const controller of this.controllers)controller.abort();
    this.remove();this.native?.close();globalThis.removeEventListener?.('pagehide',this.pagehide);
    this.emit('close',{reason,code,wasClean:code===1000});
  }
}

export const createSocket=endpoint=>{
  const socket=new DuckSocket(endpoint);
  socket.addEventListener('open',()=>socket.send(JSON.stringify({type:'join_room',room:currentRoom??'1'})),{once:true});
  return socket;
};
