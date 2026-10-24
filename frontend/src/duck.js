import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { appURL } from './urls.js';

// Official geometry, with deliberately scripted animation. No physics or policy inference here.
export function createDuckScene(container) {
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
  let state={}, frame,timer,disposed=false,slowFrames=0,lastFrame=performance.now(),root;
  const abort=new AbortController();
  const quaternion=(target,[w,x,y,z])=>target.set(x,y,z,w);
  async function load(){
    status.textContent='正在加载官方 MicroDuck 外观…';status.hidden=false;container.dataset.model='loading';
    try {
      const response=await fetch(appURL('/api/models/microduck'),{signal:AbortSignal.any([abort.signal,AbortSignal.timeout(60000)])});
      if(!response.ok)throw new Error('官方模型加载失败，请确认已安装场景资源');
      const model=await response.json();if(disposed)return;
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
      const decode=v=>Uint8Array.from(atob(v),c=>c.charCodeAt(0)).buffer;
      for(const [id,value] of Object.entries(model.meshes)){
        const g=new THREE.BufferGeometry();g.setAttribute('position',new THREE.BufferAttribute(new Float32Array(decode(value.vertices)),3));g.setIndex(new THREE.BufferAttribute(new Uint32Array(decode(value.faces)),1));g.computeVertexNormals();meshes.set(Number(id),g);geometries.push(g);
      }
      for(const geom of model.geoms){
        const geometry=meshes.get(geom.mesh);if(!geometry)continue;
        const material=new THREE.MeshStandardMaterial({color:new THREE.Color(...geom.rgba.slice(0,3)),roughness:.66,metalness:.08});materials.push(material);
        const mesh=new THREE.Mesh(geometry,material);mesh.position.fromArray(geom.position);quaternion(mesh.quaternion,geom.quaternion);mesh.castShadow=mesh.receiveShadow=true;nodes.get(geom.body).add(mesh);
      }
      container.dataset.model='official';status.hidden=true;
    }catch(error){
      if(disposed)return;container.dataset.model='failed';status.textContent=`${error.message}。`;
      const retry=document.createElement('button');retry.className='text-button';retry.textContent='重新加载模型';retry.onclick=load;status.append(retry);
    }
  }
  load();
  function setJoint(name,delta){const j=joints.get(name);if(j)j.pivot.quaternion.setFromAxisAngle(j.axis,j.home+delta);}
  function resize(){const {width,height}=container.getBoundingClientRect();if(!width||!height)return;renderer.setPixelRatio(reduced?Math.min(1,640/width):Math.min(devicePixelRatio,2));renderer.setSize(width,height);camera.aspect=width/height;camera.updateProjectionMatrix();}
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
    controls.update();renderer.render(scene,camera);
    slowFrames=performance.now()-started>70||started-lastFrame>180?slowFrames+1:0;lastFrame=started;
    if(!reduced&&slowFrames>=3){reduced=true;renderer.shadowMap.enabled=false;materials.forEach(m=>m.needsUpdate=true);resize();}
    timer=setTimeout(()=>{frame=requestAnimationFrame(animate);},reduced?100:33);
  }animate();
  return {update(next){state=next},resetCamera(){controls.reset()},dispose(){disposed=true;abort.abort();clearTimeout(timer);cancelAnimationFrame(frame);observer.disconnect();geometries.forEach(g=>g.dispose());materials.forEach(m=>m.dispose());renderer.dispose();controls.dispose();status.remove();}};
}
