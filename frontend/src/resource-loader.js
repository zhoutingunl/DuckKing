// Fetch bodies are decoded by the browser: gzip Content-Length is NOT a progress total.
export async function readResource(response,{signal,totalBytes,progress=()=>{},phase='download',maxBytes=64*1024*1024}={}){
  const header=response.headers.get('x-model-decoded-bytes');
  const total=Number(totalBytes??header??(!response.headers.get('content-encoding')?response.headers.get('content-length'):0))||0;
  if(total<0||total>maxBytes)throw Error('模型数据大小无效');
  const reader=response.body?.getReader();let received=0;const chunks=[];
  const update=()=>progress({phase,loaded:received,totalBytes:total,decoded:true});
  if(!reader){const buffer=await response.arrayBuffer();signal?.throwIfAborted();if(buffer.byteLength>maxBytes)throw Error('模型数据超过大小上限');progress({phase,loaded:buffer.byteLength,totalBytes:total,decoded:true});return buffer;}
  const cancel=()=>{void reader.cancel().catch(()=>{})};signal?.addEventListener('abort',cancel,{once:true});
  try{
    signal?.throwIfAborted();update();
    while(true){const {done,value}=await reader.read();signal?.throwIfAborted();if(done)break;
      received+=value.byteLength;if(received>maxBytes){await reader.cancel();throw Error('模型数据超过大小上限');}
      chunks.push(value);update();
    }
    const buffer=new Uint8Array(received);let offset=0;for(const chunk of chunks){buffer.set(chunk,offset);offset+=chunk.byteLength}
    return buffer.buffer;
  }finally{signal?.removeEventListener('abort',cancel);reader.releaseLock()}
}

export async function resourceBytes(getResponse,{signal,progress=()=>{},timeoutMs=60000,retryDelayMs=300,...options}={}){
  for(let attempt=1;attempt<=2;attempt++){
    signal?.throwIfAborted();const timeout=AbortSignal.timeout(timeoutMs),requestSignal=signal?AbortSignal.any([signal,timeout]):timeout;
    try{
      const response=await getResponse(requestSignal);
      if(!response.ok){const error=Error('官方模型加载失败，请重试');error.retryable=[408,502,503,504].includes(response.status);throw error;}
      return await readResource(response,{...options,signal:requestSignal,progress});
    }catch(error){
      if(signal?.aborted||attempt===2||!(error.name==='TimeoutError'||error instanceof TypeError||error.retryable))throw error;
      progress({phase:'retry',attempt:2,totalAttempts:2});
      await new Promise(resolve=>setTimeout(resolve,retryDelayMs));signal?.throwIfAborted();
    }
  }
}
