import { appURL } from './urls.js';

export const MODEL_CACHE='duckking-official-model-v1';

// Revisions identify immutable geometry, independently of its live poses.
// Bounded page-local storage: server restarts issue fresh revisions.
export function createPhysicsModelLoader({fetcher=fetch,capacity=6}={}){
  const models=new Map();
  return async function load(url,revision,{signal,metrics={}}={}){
    if(models.has(revision)){metrics.cache='memory';return models.get(revision);}
    metrics.cache='network';const began=performance.now();
    let cache,cached;
    const key=new URL(url);key.searchParams.set('revision',revision);
    try{cache=await globalThis.caches?.open('duckking-physics-model-v1');cached=await cache?.match(key);}
    catch{cache=null;}
    if(cached)metrics.cache='persistent';
    const response=cached??await fetcher(url,{signal,cache:'no-store'});
    if(!response.ok)throw new Error('官方场景模型加载失败，请重新加载');
    const buffer=await response.arrayBuffer();metrics.asset_ms=performance.now()-began;
    metrics.encoded_bytes=Number(response.headers.get('content-length'))||0;
    metrics.decoded_bytes=buffer.byteLength;
    const parsing=performance.now();let model;
    try{model=unpackVisualModel(buffer,{physics:true});}
    catch(error){if(cached)await cache.delete(key).catch(()=>{});throw error;}
    metrics.parse_ms=performance.now()-parsing;
    if(model.revision!==revision){if(cached)await cache.delete(key).catch(()=>{});throw new Error('场景已切换，正在获取最新模型');}
    models.set(revision,model);
    if(models.size>capacity)models.delete(models.keys().next().value);
    if(cache&&!cached){
      try{
        await cache.put(key,new Response(buffer));
        const keys=await cache.keys();
        for(const old of keys.slice(0,Math.max(0,keys.length-capacity)))await cache.delete(old);
      }catch{/* Storage denial must not prevent displaying a validated model. */}
    }
    return model;
  };
}
const sharedURL=path=>{const url=appURL(path);url.searchParams.delete('room');return url};
const invalid=()=>new Error('官方模型数据无效，请重新加载');

export function unpackVisualModel(buffer,{physics=false}={}){
  if(buffer.byteLength<8||new TextDecoder().decode(new Uint8Array(buffer,0,4))!=='DKM1')throw invalid();
  const size=new DataView(buffer).getUint32(4,true),start=8+Math.ceil(size/4)*4;
  if(size>1024*1024||start>buffer.byteLength)throw invalid();
  const model=JSON.parse(new TextDecoder().decode(new Uint8Array(buffer,8,size)));
  if(model.source!==(physics?'official_microduck_physics':'official_microduck_visuals')||model.physics!==physics||(!physics&&!Array.isArray(model.bodies))||!Array.isArray(model.geoms)||!model.meshes||!Object.keys(model.meshes).length)throw invalid();
  function array(info,vertex){
    const {offset,count,bytes}=info??{};
    if(!Number.isSafeInteger(offset)||offset<0||offset%4||!Number.isSafeInteger(count)||count<=0||count%3||
      (vertex?bytes!==4:![2,4].includes(bytes))||start+offset+count*bytes>buffer.byteLength)throw invalid();
    return new (vertex?Float32Array:bytes===2?Uint16Array:Uint32Array)(buffer,start+offset,count);
  }
  for(const [id,mesh] of Object.entries(model.meshes))model.meshes[id]={positions:array(mesh.vertices,true),indices:array(mesh.faces,false)};
  return model;
}

export async function loadOfficialModel({signal,metrics,progress}){
  const began=performance.now();
  let phase='manifest_ms',phaseStarted=began;
  try{
    const response=await fetch(sharedURL('api/models/microduck/manifest'),{signal,cache:'no-cache'});
    if(!response.ok)throw new Error('官方模型加载失败，请确认已安装场景资源');
    const manifest=await response.json();
    if(manifest.format!=='dkm1'||!/^[a-f0-9]{64}$/.test(manifest.version)||
      !Number.isSafeInteger(manifest.decoded_bytes)||manifest.decoded_bytes<8||manifest.decoded_bytes>32*1024*1024||
      !Number.isSafeInteger(manifest.encoded_bytes)||manifest.encoded_bytes<1||manifest.encoded_bytes>32*1024*1024)throw invalid();
    Object.assign(metrics,{manifest_ms:performance.now()-began,encoded_bytes:manifest.encoded_bytes,decoded_bytes:manifest.decoded_bytes});
    const url=sharedURL(`api/models/microduck/assets/${manifest.version}.dkm.gz`),reading=performance.now();
    phase='asset_ms';phaseStarted=reading;
    let cache,cached;
    try{cache=await globalThis.caches?.open(MODEL_CACHE);cached=await cache?.match(url)}
    catch{cache=null;console.warn('[DuckKing:model-cache] 缓存不可用，本次从官方模型接口加载');}
    metrics.cache=cached?'persistent':'network';progress(cached?'cache':'download');
    const asset=cached??await fetch(url,{signal,cache:'force-cache'});
    if(!asset.ok)throw new Error('官方模型下载失败，请重新加载');
    const buffer=await asset.arrayBuffer();metrics.asset_ms=performance.now()-reading;
    const resource=cached?null:performance.getEntriesByName(url.href).at(-1);
    metrics.transfer_bytes=cached?0:resource?.transferSize??0;
    if(resource?.transferSize===0&&resource.decodedBodySize>0)metrics.cache='http';
    const parsing=performance.now();let model;
    phase='parse_ms';phaseStarted=parsing;
    try{if(buffer.byteLength!==manifest.decoded_bytes)throw invalid();model=unpackVisualModel(buffer)}
    catch(error){if(cached)await cache.delete(url).catch(()=>{});throw error}
    metrics.parse_ms=performance.now()-parsing;
    if(cache&&!cached){
      try{
        // Store the decoded, validated binary. Keep one version, shared by rooms.
        await cache.put(url,new Response(buffer,{headers:{'Content-Type':'application/octet-stream'}}));
        for(const key of await cache.keys())if(key.url!==url.href)await cache.delete(key);
      }catch{console.warn('[DuckKing:model-cache] 未能保存模型缓存，下次将重新下载');}
    }
    progress('assemble');return model;
  }catch(error){metrics[phase]=performance.now()-phaseStarted;throw error}
}
