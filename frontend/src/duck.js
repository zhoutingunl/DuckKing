import {measurement,loadMetrics} from './experience.js';
import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { appURL } from './urls.js';
import { loadOfficialModel } from './model-loader.js';

// Official geometry, with deliberately scripted animation. No physics or policy inference here.
export function createDuckScene(container,{onLoad=()=>{}}={}) {
  const scene = new THREE.Scene(); scene.background = new THREE.Color('#edf0e5');
  const camera = new THREE.PerspectiveCamera(34, 1, .02, 50); camera.position.set(2.5, 1.9, 3.7);
  const renderer = new THREE.WebGLRenderer({ antialias: true });
  const gl=renderer.getContext(), debug=gl.getExtension('WEBGL_debug_renderer_info');
  let reduced=/swiftshader|llvmpipe|softpipe|software/i.test(debug?gl.getParameter(debug.UNMASKED_RENDERER_WEBGL):'');
  renderer.outputColorSpace=THREE.SRGBColorSpace; renderer.toneMapping=THREE.ACESFilmicToneMapping;
  renderer.shadowMap.enabled=!reduced; renderer.shadowMap.type=THREE.PCFShadowMap;
  container.appendChild(renderer.domElement);
  renderer.domElement.setAttribute('aria-label', '官方 MicroDuck 外观，脚本动画预览，非物理仿真');
  const status=document.createElement('div'); status.className='model-status'; status.setAttribute('role','status'); container.append(status);
  const controls=new OrbitControls(camera,renderer.domElement); controls.target.set(0,.65,0);
  controls.minDistance=1.4;controls.maxDistance=8;controls.maxPolarAngle=Math.PI/2.04;
  controls.enableDamping=true;controls.enablePan=false;controls.update();controls.saveState();
  scene.add(new THREE.HemisphereLight(0xffffff,0x78845c,2.6));
  const sun=new THREE.DirectionalLight(0xfff9e8,3);sun.position.set(-3,6,4);sun.castShadow=true;
  sun.shadow.mapSize.set(1024,1024);sun.shadow.camera.left=-3;sun.shadow.camera.right=3;sun.shadow.camera.top=3;sun.shadow.camera.bottom=-3;sun.shadow.normalBias=.002;scene.add(sun);
  const floor=new THREE.Mesh(new THREE.PlaneGeometry(100,100),new THREE.MeshStandardMaterial({color:'#edf0e5'}));floor.rotation.x=-Math.PI/2;floor.receiveShadow=true;scene.add(floor);
  const grid=new THREE.GridHelper(12,48,0xd9dfce,0xe0e5d7);grid.position.y=.001;scene.add(grid);
  const duck=new THREE.Group();duck.scale.setScalar(5);scene.add(duck);
  const basis=new THREE.Group();basis.rotation.x=-Math.PI/2;duck.add(basis);
  const joints=new Map(), geometries=[], materials=[];
  let loadExperience;
  let state={}, frame,timer,disposed=false,slowFrames=0,lastFrame=performance.now(),root,needsRender=true,poseKey='',pendingLoad;
  controls.addEventListener('change',()=>{needsRender=true});
  const abort=new AbortController();
  const quaternion=(target,[w,x,y,z])=>target.set(x,y,z,w);
  function report(metrics,started,result){
    const timing={result,...metrics,elapsed_ms:performance.now()-started,navigation_ms:performance.now()};
    for(const key of Object.keys(timing))if(typeof timing[key]==='number')timing[key]=Math.round(timing[key]);
    container.dataset.modelTiming=JSON.stringify(timing);console.info('[DuckKing:model-load]',timing);onLoad(timing);
    loadExperience?.finish(result==='ready'?'completed':'failed',{...loadMetrics(timing),model_ms:Math.round(timing.elapsed_ms),navigation_ms:Math.round(timing.navigation_ms)},{cache:timing.cache});
    fetch(appURL('api/models/load-metrics'),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(timing),keepalive:true}).catch(()=>{});
  }
  async function load(){
    loadExperience?.finish('cancelled');loadExperience=measurement('load');
    const started=performance.now(),metrics={cache:'unknown',manifest_ms:0,asset_ms:0,parse_ms:0,assemble_ms:0,first_frame_ms:0,transfer_bytes:0,encoded_bytes:0,decoded_bytes:0};
    status.textContent='正在加载官方 MicroDuck 外观…';status.hidden=false;container.dataset.model='loading';
    try {
      const model=await loadOfficialModel({signal:AbortSignal.any([abort.signal,AbortSignal.timeout(60000)]),metrics,
        progress:stage=>{status.textContent=stage==='cache'?'正在读取已缓存的官方 MicroDuck 外观…':stage==='assemble'?'正在绘制官方 MicroDuck 外观…':'正在下载官方 MicroDuck 外观…'}});
      if(disposed)return;
      const assembling=performance.now();
      basis.clear();joints.clear();geometries.splice(0).forEach(g=>g.dispose());materials.splice(0).forEach(m=>m.dispose());
      const nodes=new Map([[0,basis]]),meshes=new Map();
      for(const body of model.bodies){
        const base=new THREE.Group();base.position.fromArray(body.position);quaternion(base.quaternion,body.quaternion);nodes.get(body.parent).add(base);
        let node=base;
        for(const joint of body.joints){
          const pivot=new THREE.Group();pivot.position.fromArray(joint.position);node.add(pivot);
          const child=new THREE.Group();child.position.fromArray(joint.position).multiplyScalar(-1);pivot.add(child);node=child;
          joints.set(joint.name,{pivot,axis:new THREE.Vector3(...joint.axis),home:joint.home});
        }
        nodes.set(body.id,node);if(body.name==='trunk_base')root=base;
      }
      for(const [id,value] of Object.entries(model.meshes)){
        const g=new THREE.BufferGeometry();g.setAttribute('position',new THREE.BufferAttribute(value.positions,3));g.setIndex(new THREE.BufferAttribute(value.indices,1));g.computeVertexNormals();meshes.set(Number(id),g);geometries.push(g);
      }
      for(const geom of model.geoms){
        const geometry=meshes.get(geom.mesh);if(!geometry)continue;
        const material=new THREE.MeshStandardMaterial({color:new THREE.Color(...geom.rgba.slice(0,3)),roughness:.66,metalness:.08});materials.push(material);
        const mesh=new THREE.Mesh(geometry,material);mesh.position.fromArray(geom.position);quaternion(mesh.quaternion,geom.quaternion);mesh.castShadow=mesh.receiveShadow=true;nodes.get(geom.body).add(mesh);
      }
      metrics.assemble_ms=performance.now()-assembling;
      pendingLoad={metrics,started,assembled:performance.now()};needsRender=true;
    }catch(error){
      if(disposed)return;container.dataset.model='failed';status.textContent=`${error.message}。`;
      const retry=document.createElement('button');retry.className='text-button';retry.textContent='重新加载模型';retry.onclick=load;status.append(retry);
      report(metrics,started,'failed');
    }
  }
  load();
  function setJoint(name,delta){const j=joints.get(name);if(j)j.pivot.quaternion.setFromAxisAngle(j.axis,j.home+delta);}
  function resize(){const {width,height}=container.getBoundingClientRect();if(!width||!height)return;renderer.setPixelRatio(reduced?Math.min(1,640/width):Math.min(devicePixelRatio,2));renderer.setSize(width,height);camera.aspect=width/height;camera.updateProjectionMatrix();needsRender=true;}
  const observer=new ResizeObserver(resize);observer.observe(container);
  const clock=new THREE.Clock();
  function animate(){
    const started=performance.now(),t=clock.getElapsedTime(),p=state.pose??{};
    const moving=Math.abs(state.velocity?.forward??0)+Math.abs(state.velocity?.lateral??0)+Math.abs(state.velocity?.yaw??0)>.001;
    duck.position.set((p.x??0)*5,0,(p.z??0)*5);duck.rotation.y=-Math.PI/2+(p.yaw??0);
    for(const name of joints.keys())setJoint(name,0);
    setJoint('head_pitch',p.pitch??0);setJoint('head_yaw',p.head_yaw??0);setJoint('head_roll',p.head_roll??0);
    const gait=moving?Math.sin(t*11)*.16:0;
    setJoint('left_hip_pitch',gait);setJoint('right_hip_pitch',gait);
    setJoint('left_knee',-Math.max(0,gait)*1.2);setJoint('right_knee',Math.max(0,-gait)*1.2);
    if(root){root.position.z=.12+(p.body_z??0)+(moving?Math.abs(Math.sin(t*11))*.002:0);root.rotation.set(p.body_roll??0,p.body_pitch??0,0);}
    // A stationary official mesh does not change between snapshots. Avoid
    // monopolizing a software GPU while voice and other rooms need the CPU.
    controls.update();if(needsRender||moving){
      needsRender=false;renderer.render(scene,camera);
      if(pendingLoad){const load=pendingLoad;pendingLoad=null;requestAnimationFrame(()=>{
        if(disposed)return;load.metrics.first_frame_ms=performance.now()-load.assembled;
        container.dataset.model='official';status.hidden=true;report(load.metrics,load.started,'ready');
      });}
    }
    slowFrames=performance.now()-started>70||started-lastFrame>180?slowFrames+1:0;lastFrame=started;
    if(!reduced&&slowFrames>=3){reduced=true;renderer.shadowMap.enabled=false;materials.forEach(m=>m.needsUpdate=true);resize();}
    timer=setTimeout(()=>{frame=requestAnimationFrame(animate);},reduced?100:33);
  }animate();
  return {update(next){state=next;const key=JSON.stringify([next.pose,next.velocity]);if(key!==poseKey){poseKey=key;needsRender=true}},resetCamera(){controls.reset()},dispose(){loadExperience?.finish('cancelled');disposed=true;abort.abort();clearTimeout(timer);cancelAnimationFrame(frame);observer.disconnect();geometries.forEach(g=>g.dispose());materials.forEach(m=>m.dispose());renderer.dispose();controls.dispose();status.remove();}};
}
