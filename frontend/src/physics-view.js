import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';

export function physicsView(container) {
  const scene=new THREE.Scene();scene.background=new THREE.Color('#edf0e5');
  const renderer=new THREE.WebGLRenderer({antialias:true});renderer.setPixelRatio(Math.min(devicePixelRatio,2));
  const gl=renderer.getContext(),debug=gl.getExtension('WEBGL_debug_renderer_info');
  let reduced=/swiftshader|llvmpipe|softpipe|software/i.test(debug?gl.getParameter(debug.UNMASKED_RENDERER_WEBGL):'');
  container.dataset.renderQuality=reduced?'reduced':'full';
  renderer.toneMapping=THREE.ACESFilmicToneMapping;renderer.toneMappingExposure=1;
  renderer.shadowMap.enabled=!reduced;renderer.shadowMap.type=THREE.PCFShadowMap;
  container.append(renderer.domElement);renderer.domElement.setAttribute('aria-label','官方 MicroDuck 模型，位置与关节姿态来自 MuJoCo');
  const camera=new THREE.PerspectiveCamera(38,1,.01,30);camera.position.set(.85,.62,.95);
  const controls=new OrbitControls(camera,renderer.domElement);controls.target.set(0,.13,0);controls.minDistance=.35;controls.maxDistance=6;controls.maxPolarAngle=Math.PI/2.02;controls.enableDamping=true;controls.update();controls.saveState();
  scene.add(new THREE.HemisphereLight(0xffffff,0x71815a,2.4));
  const sun=new THREE.DirectionalLight(0xfff6df,3);sun.position.set(1,2,1);sun.castShadow=true;sun.shadow.mapSize.set(1024,1024);sun.shadow.camera.left=-2;sun.shadow.camera.right=2;sun.shadow.camera.top=2;sun.shadow.camera.bottom=-2;sun.shadow.bias=-.0001;sun.shadow.normalBias=.001;scene.add(sun);
  const floor=new THREE.Mesh(new THREE.PlaneGeometry(20,20),new THREE.MeshStandardMaterial({color:'#edf0e5',roughness:1}));floor.rotation.x=-Math.PI/2;floor.receiveShadow=true;scene.add(floor);
  const grid=new THREE.GridHelper(8,80,0xcbd6bd,0xe0e6d7);grid.position.y=.0001;scene.add(grid);
  const world=new THREE.Group();world.rotation.x=-Math.PI/2;scene.add(world);
  let objects=new Map(),labels=new Map(),textures=[],geometries=[],materials=[],frame,timer,revision=null,slowFrames=0,lastFrame=performance.now();
  const matrix=new THREE.Matrix4();
  function clear(){world.clear();geometries.forEach(g=>g.dispose());materials.forEach(m=>m.dispose());textures.forEach(t=>t.dispose());geometries=[];materials=[];textures=[];objects.clear();labels.clear();}
  function load(model){
    clear();const meshes=new Map(),shared=new Map();
    const decode=value=>Uint8Array.from(atob(value),char=>char.charCodeAt(0)).buffer;
    for(const [id,value] of Object.entries(model.meshes)){
      const key=value.positions&&value.indices?`${value.positions.byteOffset}:${value.positions.length}:${value.indices.byteOffset}:${value.indices.length}`:null;
      if(key&&shared.has(key)){meshes.set(Number(id),shared.get(key));continue;}
      const geometry=new THREE.BufferGeometry();geometry.setAttribute('position',new THREE.BufferAttribute(value.positions??new Float32Array(decode(value.vertices)),3));geometry.setIndex(new THREE.BufferAttribute(value.indices??new Uint32Array(decode(value.faces)),1));geometry.computeVertexNormals();meshes.set(Number(id),geometry);geometries.push(geometry);
      if(key)shared.set(key,geometry);
    }
    for(const geom of model.geoms){
      let geometry=geom.type===7?meshes.get(geom.mesh):null;
      if(geom.type===6){geometry=new THREE.BoxGeometry(...geom.size.map(v=>v*2));geometries.push(geometry);}
      if(geom.type===2){geometry=new THREE.SphereGeometry(geom.size[0],32,20);geometries.push(geometry);}
      if(!geometry)continue;
      const material=new THREE.MeshStandardMaterial({color:new THREE.Color(...geom.rgba.slice(0,3)),roughness:.66,metalness:.08});materials.push(material);
      const object=new THREE.Mesh(geometry,material);object.castShadow=object.receiveShadow=true;world.add(object);objects.set(geom.id,object);
    }
    revision=model.revision;
  }
  function update(state){
    if(state.revision!==revision)return;
    for(const duck of state.ducks){
      if(!labels.has(duck.id)){
        const canvas=document.createElement('canvas');canvas.width=192;canvas.height=72;const context=canvas.getContext('2d');context.fillStyle=({a:'#526d32',b:'#3f6580',c:'#987033',d:'#865872'}[duck.id]??'#526d32');context.fillRect(0,0,192,72);context.font='40px sans-serif';context.textAlign='center';context.fillStyle='#fff';context.fillText(`鸭 ${duck.id.toUpperCase()}`,96,51);
        const texture=new THREE.CanvasTexture(canvas);textures.push(texture);const material=new THREE.SpriteMaterial({map:texture,depthTest:false});materials.push(material);const sprite=new THREE.Sprite(material);sprite.scale.set(.105,.04,1);world.add(sprite);labels.set(duck.id,sprite);
      }
      const [x,y,z]=duck.position;labels.get(duck.id).position.set(x,y,z+.20);
    }
    for(const geom of state.geoms){const object=objects.get(geom.id);if(!object)continue;
      object.position.fromArray(geom.position);const r=geom.rotation;matrix.set(r[0],r[1],r[2],0,r[3],r[4],r[5],0,r[6],r[7],r[8],0,0,0,0,1);object.quaternion.setFromRotationMatrix(matrix);
    }
  }
  function resize(){const {width,height}=container.getBoundingClientRect();if(width&&height){renderer.setPixelRatio(reduced?Math.min(1,640/width):Math.min(devicePixelRatio,2));renderer.setSize(width,height);camera.aspect=width/height;camera.updateProjectionMatrix();}}
  const observer=new ResizeObserver(resize);observer.observe(container);
  function animate(){
    const started=performance.now();controls.update();renderer.render(scene,camera);
    slowFrames=performance.now()-started>70||started-lastFrame>180?slowFrames+1:0;lastFrame=started;
    if(!reduced&&slowFrames>=3){reduced=true;renderer.shadowMap.enabled=false;floor.material.needsUpdate=true;materials.forEach(m=>m.needsUpdate=true);resize();container.dataset.renderQuality='reduced';}
    // Leave an idle interval after each draw so software GPUs cannot starve input,
    // voice audio or the stream of physical state. Physics remains at 200 Hz.
    timer=setTimeout(()=>{frame=requestAnimationFrame(animate);},reduced?100:33);
  }animate();
  return {load,update,clear,frameScene(scene){const close=scene==='carry',table=scene==='table';camera.position.set(...(table?[1.6,1.10,-1.6]:close?[.6,.4,.65]:[.85,.62,.95]));controls.target.set(close ? .12 : table ? .20 : 0,table ? .25 : .13,table ? -.10 : 0);controls.update();controls.saveState();},reset(){controls.reset();},dispose(){clearTimeout(timer);cancelAnimationFrame(frame);observer.disconnect();clear();controls.dispose();renderer.dispose();}};
}
