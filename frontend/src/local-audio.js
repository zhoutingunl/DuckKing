// Local music needs the same mobile playback session and gesture unlock as speech.
// Never replace an active microphone's duplex session or request a microphone here.
const primed=new WeakSet(),resuming=new WeakMap();
const notReady=()=>new Error('音频通道未就绪，请先点启用 / 测试声音');
function playbackSession(){
 try{
  const session=globalThis.navigator?.audioSession;
  if(session&&session.type!=='play-and-record')session.type='playback';
 }catch{/* Optional API; retain ordinary Web Audio on unsupported browsers. */}
}
export function createLocalAudioContext(){
 playbackSession();
 const Audio=globalThis.AudioContext||globalThis.webkitAudioContext;
 if(!Audio)throw notReady();
 try{return new Audio()}catch{throw notReady()}
}
export function resumeLocalAudio(context){
 playbackSession();
 try{
  if(!primed.has(context)||context.state!=='running'){
   // Run synchronously in the click handler, before downloads or backend requests.
   const silent=context.createBufferSource();
   silent.buffer=context.createBuffer(1,1,context.sampleRate);
   silent.connect(context.destination);silent.onended=()=>silent.disconnect();silent.start(0);
   primed.add(context);
  }
  if(context.state==='running')return Promise.resolve(true);
  if(resuming.has(context))return resuming.get(context);
  const resumed=context.resume();let timer;
  const pending=Promise.race([
   Promise.resolve(resumed).then(()=>context.state==='running',()=>false),
   new Promise(resolve=>{timer=setTimeout(()=>resolve(false),1500)}),
  ]).then(ready=>{if(!ready)throw notReady();return true}).finally(()=>{
   clearTimeout(timer);if(resuming.get(context)===pending)resuming.delete(context);
  });
  resuming.set(context,pending);return pending;
 }catch{return Promise.reject(notReady())}
}
