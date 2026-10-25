import { appURL } from './urls.js';
import { DuckSocket } from './transport.js';

export const stopped=()=>new DOMException('演示已停止','AbortError');
export function pause(ms,signal){return new Promise((resolve,reject)=>{
  if(signal?.aborted)return reject(stopped());
  const abort=()=>{clearTimeout(timer);reject(stopped())};
  const timer=setTimeout(()=>{signal?.removeEventListener('abort',abort);resolve()},ms);
  signal?.addEventListener('abort',abort,{once:true});
});}
export async function until(predicate,{signal,timeout=45000}={}){
  const end=performance.now()+timeout;
  while(!predicate()){if(performance.now()>end)throw new Error('等待超时，演示已停止，可重新点选此幕');await pause(50,signal)}
  if(signal?.aborted)throw stopped();
}
export async function api(path,room,{body,signal}={}){
  const url=appURL(path);url.searchParams.set('room',room);
  const response=await fetch(url,{method:body?'POST':'GET',headers:body?{'Content-Type':'application/json'}:{},
    body:body?JSON.stringify(body):undefined,signal:signal?AbortSignal.any([signal,AbortSignal.timeout(60000)]):AbortSignal.timeout(60000),cache:'no-store'});
  const data=response.status===204?null:await response.json();if(!response.ok)throw new Error(typeof data.detail==='string'?data.detail:'演示请求失败');return data;
}
export function pcmWave(buffer){
  const v=new DataView(buffer),str=(i,n)=>String.fromCharCode(...new Uint8Array(buffer,i,n));
  if(buffer.byteLength<44||str(0,4)!=='RIFF'||str(8,4)!=='WAVE')throw new Error('预录音频格式错误');
  let valid=false,pcm;
  for(let p=12;p+8<=buffer.byteLength;){
    const n=v.getUint32(p+4,true),end=p+8+n;if(end>buffer.byteLength)throw new Error('预录音频不完整');
    if(str(p,4)==='fmt ')valid=n>=16&&v.getUint16(p+8,true)===1&&v.getUint16(p+10,true)===1&&v.getUint32(p+12,true)===16000&&v.getUint16(p+22,true)===16;
    if(str(p,4)==='data'){if(n%2)throw new Error('预录音频长度错误');pcm=new Int16Array(buffer.slice(p+8,end))}
    p=end+n%2;
  }
  if(!valid||!pcm?.length||pcm.length>15*16000)throw new Error('预录指令必须为 15 秒以内的 16kHz 单声道 PCM');
  return pcm;
}
export function matchesCloudActions(records,expected,scene){
  if(records.some(r=>r.status!=='completed'))return false;
  const names=records.filter(r=>r.name!=='stop').map(r=>r.name);
  // Linx may explicitly prepare the already selected scene before its first
  // requested movement. Keep this in the evidence; never accept a mid-command
  // reset, a different scene, or an extra physical movement.
  if(['ball','carry','duo'].includes(scene)&&names[0]===`scene_${scene}`)names.shift();
  return JSON.stringify(names)===JSON.stringify(expected);
}
export class DemoVoice {
  constructor(room,output,onEvent){this.room=room;this.output=output;this.onEvent=onEvent;this.state='disconnected';this.generation=0;this.minimum=0;this.ended=0;this.received=0;this.error=null;this.closed=false;}
  send(value){if(this.socket?.readyState!==1)throw new Error('语音连接已关闭');this.socket.send(value instanceof ArrayBuffer?value:JSON.stringify(value))}
  async connect(signal){
    const channel=new DuckSocket('scene-voice');this.socket=channel;this.state='connecting';
    channel.onopen=()=>{this.send({type:'join_room',room:this.room});this.send({type:'connect'});this.heartbeat=setInterval(()=>{if(channel.readyState===1)this.send({type:'ping'})},10000)};
    channel.onmessage=event=>{
      const data=JSON.parse(event.data);
      if((data.generation??0)<this.minimum)return;
      this.generation=data.generation??this.generation;
      if(data.type==='voice_status'){
        // The initial disconnected status precedes the requested connection.
        if(data.state==='disconnected'&&this.state==='connecting')return;
        this.state=data.state;
        if(['error','busy','awaiting_binding','disconnected'].includes(data.state))this.error=data.error||'灵矽未就绪，请在工作台完成绑定后重试';
      }else if(data.type==='audio'){try{this.output.enqueue(data);this.received++}catch(e){this.error=e.message}}
      else if(data.type==='playback_end')this.ended++;
      else if(data.type==='error')this.error=data.message;
      this.onEvent(data);
    };
    channel.onclose=()=>{clearInterval(this.heartbeat);if(!this.closed)this.error='灵矽连接中断，演示已停止'};
    await this.wait(()=>this.state==='ready',signal);
  }
  async wait(predicate,signal,timeout=60000){await until(()=>{if(this.error)throw new Error(this.error);return predicate()},{signal,timeout})}
  async input(pcm,signal){
    await this.wait(()=>this.state==='ready',signal);
    this.send({type:'listen_start'});await this.wait(()=>this.state==='listening',signal);
    for(let i=0;i<pcm.length;i+=960){
      if(signal.aborted)throw stopped();const frame=new Int16Array(960);frame.set(pcm.subarray(i,i+960));this.send(frame.buffer);await pause(60,signal);
    }
    this.send({type:'listen_stop'});
  }
  async turn(pcm,signal){
    const before=this.ended,received=this.received;await this.input(pcm,signal);
    await this.wait(()=>this.ended>before&&this.state==='ready',signal,90000);
    if(this.received===received)throw new Error('灵矽没有返回本轮语音，演示未完成');
    await until(()=>!this.output.busy,{signal,timeout:15000});
  }
  async interrupt(signal){
    this.minimum=this.generation+1;this.output.clear();this.send({type:'interrupt'});
    await this.wait(()=>this.generation>=this.minimum&&this.state==='ready',signal);
  }
  close(){this.closed=true;clearInterval(this.heartbeat);this.output.clear();if(this.socket?.readyState===1){try{this.send({type:'disconnect'})}catch{}}this.socket?.close();}
}

// One generation owns the timeline. A replacement cannot continue an old script.
export class DemoRun {
  constructor(){this.controller=new AbortController();this.signal=this.controller.signal;this.rooms=new Set();this.voices=[];this.results=[];}
  abort(){this.controller.abort();for(const voice of this.voices)voice.close();}

}
export async function action(room,name,signal,options={}){
  signal.throwIfAborted();
  const submitted=await api('api/scenes/actions',room,{body:{name,request_id:crypto.randomUUID(),...options},signal});
  const end=performance.now()+(name==='seated_show'?50000:name==='table_show'?43000:15000);let result=submitted;
  while(result.status==='running'){
    if(performance.now()>end)throw new Error('物理动作超时，演示已停止');
    await pause(80,signal);result=await api('api/scenes/actions/'+submitted.id,room,{signal});
  }
  signal.throwIfAborted();return result;
}
