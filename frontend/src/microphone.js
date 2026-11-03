// Request permission synchronously in the caller's click, before loading the
// worklet. Pending browser permission prompts cannot be cancelled, so stop any
// stream delivered after a timeout or disconnect.
export async function acquireMicrophone({signal,prepareWorklet,onPhase=()=>{},timeoutMs=12000,
  mediaDevices=globalThis.navigator?.mediaDevices}={}) {
  if(!mediaDevices?.getUserMedia)throw new Error('当前页面无法申请麦克风，请使用 HTTPS 地址打开。');
  const attempt=new AbortController();
  const abort=()=>attempt.abort(signal.reason??new DOMException('Cancelled','AbortError'));
  if(signal?.aborted)abort();else signal?.addEventListener('abort',abort,{once:true});
  let phase='permission',stream,complete=false;
  const stop=value=>value?.getTracks().forEach(track=>track.stop());
  const timer=setTimeout(()=>attempt.abort(new Error(phase==='permission'
    ?'浏览器未完成麦克风授权，请点“重新启用麦克风”再次申请。'
    :'录音组件加载超时，请点“重新启用麦克风”重试。')),timeoutMs);
  const wait=promise=>new Promise((resolve,reject)=>{
    const cancelled=()=>reject(attempt.signal.reason);
    attempt.signal.addEventListener('abort',cancelled,{once:true});
    Promise.resolve(promise).then(resolve,reject).finally(()=>attempt.signal.removeEventListener('abort',cancelled));
    if(attempt.signal.aborted)cancelled();
  });
  try{
    attempt.signal.throwIfAborted();onPhase(phase);
    // No await before this call: keep the initiating user gesture.
    const permission=mediaDevices.getUserMedia({audio:{channelCount:1,echoCancellation:true,noiseSuppression:true}});
    stream=await wait(Promise.resolve(permission).then(value=>{
      stream=value;
      value.getAudioTracks().forEach(track=>{track.enabled=false});
      if(attempt.signal.aborted){stop(value);throw attempt.signal.reason}
      return value;
    }));
    attempt.signal.throwIfAborted();phase='worklet';onPhase(phase);
    await wait(prepareWorklet());attempt.signal.throwIfAborted();
    complete=true;return stream;
  }finally{
    clearTimeout(timer);signal?.removeEventListener('abort',abort);
    if(!complete)stop(stream);
  }
}

export function microphoneError(error){
  if(/AudioSession.*compatible.*capture/i.test(error.message??''))return '音频播放模式与麦克风冲突，请重新启用麦克风；若仍异常，请刷新页面后重试。';
  if(error.name==='NotAllowedError')return '浏览器未允许此网站使用麦克风。请检查网站权限，再点“重新启用麦克风”。';
  if(error.name==='NotFoundError')return '未检测到可用麦克风，请连接麦克风后重试。';
  if(error.name==='NotReadableError')return '麦克风暂时无法使用，请结束其他录音或通话后重试。';
  return error.message||'麦克风准备失败，请重新启用。';
}
