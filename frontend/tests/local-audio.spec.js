import {test,expect} from '@playwright/test';
import {existsSync} from 'node:fs';

// Live WebGL snapshotting can delay the three-second physical chorus past its audio window.
// Keep API traces; the signal proof runs on the real audio rendering thread.
test.use({isMobile:true,hasTouch:true,viewport:{width:390,height:844},trace:{mode:'retain-on-failure',snapshots:false,screenshots:false}});

// Controlled mobile-policy fixture, not an iPhone speaker test. The context,
// decoded clips, oscillator signal and physical scene remain real browser/CPU work.
async function mobileAudioPolicy(page){
 const worklet=`
  registerProcessor('local-audio-proof',class extends AudioWorkletProcessor{
   constructor(){super();this.peak=0}
   process(inputs){let peak=0;for(const channel of inputs[0]??[])for(const sample of channel)peak=Math.max(peak,Math.abs(sample));if(peak>this.peak){this.peak=peak;this.port.postMessage(peak)}return true}
  });
 `;
 await page.addInitScript(worklet=>{
  const proofURL=URL.createObjectURL(new Blob([worklet],{type:'application/javascript'}));
  const Native=globalThis.AudioContext,session={type:'auto'};
  const audit=window.localAudioAudit={contexts:[],primes:0,notes:0,clips:0,microphones:0,blocked:false,peak:0,proofErrors:[]};
  Object.defineProperty(navigator,'audioSession',{configurable:true,value:session});
  navigator.mediaDevices.getUserMedia=()=>{audit.microphones++;return Promise.reject(Error('Unexpected microphone request'))};
  const connect=AudioNode.prototype.connect;
  AudioNode.prototype.connect=function(destination,...args){
   if(destination===this.context.destination&&this.context.auditAnalyser&&this!==this.context.auditAnalyser)return connect.call(this,this.context.auditAnalyser,...args);
   return connect.call(this,destination,...args);
  };
  globalThis.AudioContext=class extends Native{
   constructor(...args){
    super(...args);this.unlocked=false;this.modeAtCreation=session.type;this.auditAnalyser=this.createAnalyser();this.auditAnalyser.fftSize=512;connect.call(this.auditAnalyser,this.destination);audit.contexts.push(this);
    // Measure on the audio rendering thread so short notes survive slow WebGL/trace work.
    // The proof node emits silence; the original audible route remains unchanged.
    this.audioWorklet.addModule(proofURL).then(()=>{
     const proof=new AudioWorkletNode(this,'local-audio-proof');proof.port.onmessage=event=>{audit.peak=Math.max(audit.peak,event.data)};
     connect.call(this.auditAnalyser,proof);connect.call(proof,this.destination);
    }).catch(error=>audit.proofErrors.push(error.message));
   }
   get state(){return audit.blocked||!this.unlocked||!['playback','play-and-record'].includes(session.type)?'suspended':super.state}
   createBufferSource(){
    const node=super.createBufferSource(),start=node.start.bind(node);
    node.start=(...args)=>{if(node.buffer?.length===1){this.unlocked=true;audit.primes++}else audit.clips++;return start(...args)};
    return node;
   }
   createOscillator(){const node=super.createOscillator(),start=node.start.bind(node);node.start=(...args)=>{audit.notes++;return start(...args)};return node}
   resume(){if(audit.blocked||!this.unlocked||!['playback','play-and-record'].includes(session.type))return new Promise(()=>{});return super.resume()}
  };
 },worklet);
}
const peak=page=>page.evaluate(()=>Math.max(0,...window.localAudioAudit.contexts.map(ctx=>{
 const samples=new Float32Array(ctx.auditAnalyser.fftSize);ctx.auditAnalyser.getFloatTimeDomainData(samples);return Math.max(...samples.map(Math.abs));
})));
async function assertLocalSound(page,voiceSockets){
 try{await expect.poll(()=>page.evaluate(()=>window.localAudioAudit.peak),{timeout:20000}).toBeGreaterThan(.0001)}catch(error){
  const state=await page.evaluate(()=>({mode:navigator.audioSession.type,primes:window.localAudioAudit.primes,notes:window.localAudioAudit.notes,clips:window.localAudioAudit.clips,proofErrors:window.localAudioAudit.proofErrors,contexts:window.localAudioAudit.contexts.map(ctx=>({state:ctx.state,time:ctx.currentTime,unlocked:ctx.unlocked,created:ctx.modeAtCreation})),notice:document.getElementById('notice')?.textContent,status:document.getElementById('task-status')?.textContent}));
  throw Error(JSON.stringify(state),{cause:error});
 }
 expect(await page.evaluate(()=>({mode:navigator.audioSession.type,microphones:window.localAudioAudit.microphones,modes:window.localAudioAudit.contexts.map(ctx=>ctx.modeAtCreation),primes:window.localAudioAudit.primes}))).toMatchObject({mode:'playback',microphones:0,modes:['playback']});
 expect(voiceSockets).toEqual([]);
}
test.describe('local mobile sound without Linx',()=>{
 for(const scene of [
  {id:'director',action:'conduct'},
  {id:'theremin',action:'play',optional:'../../external/features/upstream/src'},
  {id:'emotions',action:'curious',optional:'../../external/features/emotions/sounds/curious.wav'},
 ])test(`${scene.id}: a scene action generates local audio without microphone or cloud`,async({page,request})=>{
  test.skip(!!scene.optional&&!existsSync(new URL(scene.optional,import.meta.url)),'Requires the corresponding optional feature assets');
  test.setTimeout(90000);await mobileAudioPolicy(page);
  const voiceSockets=[];page.on('websocket',socket=>{if(/\/(?:scene-)?voice(?:\?|$)/.test(socket.url()))voiceSockets.push(socket.url())});
  await request.post('/api/scenes/close?room=1');
  try{
   await page.goto(`/features.html?room=1&feature=${scene.id}&lang=zh`);
   const action=page.locator(`[data-feature-action=${scene.action}]`);await expect(action).toBeEnabled({timeout:45000});
   if(scene.id==='director')await page.locator('#feature-order').fill('A');
   await action.tap();await assertLocalSound(page,voiceSockets);
   await page.locator('#stop-feature').tap();
   await expect.poll(()=>peak(page),{timeout:5000}).toBeLessThan(.00001);
   await expect(page.locator('#voice-badge')).toHaveText('未连接灵矽');
  }finally{await page.close();await request.post('/api/scenes/close?room=1')}
 });

 test('dual-duck chorus starts local audio directly from its action button',async({page,request})=>{
  test.setTimeout(90000);await mobileAudioPolicy(page);
  const voiceSockets=[];page.on('websocket',socket=>{if(/\/(?:scene-)?voice(?:\?|$)/.test(socket.url()))voiceSockets.push(socket.url())});
  await request.post('/api/scenes/close?room=1');
  try{
   await page.goto('/scenarios.html?room=1&lang=zh');await page.locator('[data-scene=duo]').tap();
   const chorus=page.locator('[data-sim-action=chorus]');await expect(chorus).toBeEnabled({timeout:45000});
   await chorus.tap();await assertLocalSound(page,voiceSockets);
   await page.locator('#stop-scene').tap();await expect.poll(()=>peak(page)).toBeLessThan(.00001);
  }finally{await page.close();await request.post('/api/scenes/close?room=1')}
 });

 test('blocked audio activation reports failure without starting a silent task, then retries locally',async({page,request})=>{
  test.setTimeout(90000);await mobileAudioPolicy(page);const starts=[];
  page.on('request',request=>{if(new URL(request.url()).pathname==='/api/features/command'&&request.postDataJSON()?.operation==='start')starts.push(request.postDataJSON())});
  await request.post('/api/scenes/close?room=1');
  try{
   await page.goto('/features.html?room=1&feature=director&lang=zh');const action=page.locator('[data-feature-action=conduct]');
   await expect(action).toBeEnabled({timeout:45000});await page.locator('#feature-order').fill('A');
   await page.evaluate(()=>window.localAudioAudit.blocked=true);await action.tap();
   await expect(page.locator('#notice')).toHaveText('音频通道未就绪，请先点启用 / 测试声音');expect(starts).toEqual([]);
   await page.evaluate(()=>window.localAudioAudit.blocked=false);await action.tap();
   await expect.poll(()=>page.evaluate(()=>window.localAudioAudit.peak),{timeout:20000}).toBeGreaterThan(.0001);expect(starts).toHaveLength(1);
   await page.locator('#stop-feature').tap();
  }finally{await page.close();await request.post('/api/scenes/close?room=1')}
 });
});
