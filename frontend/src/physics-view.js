import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';

export function physicsView(container) {
  let interaction=null,interactionMode="select",latest=null,pointerStart=null,selection=null,visible=true;
  const raycaster=new THREE.Raycaster(),cursor=new THREE.Vector2();
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
  let manualView=false,floorFramed=false,seatedView=false;controls.addEventListener('start',()=>{manualView=true});
  scene.add(new THREE.HemisphereLight(0xffffff,0x71815a,2.4));
  const sun=new THREE.DirectionalLight(0xfff6df,3);sun.position.set(1,2,1);sun.castShadow=true;sun.shadow.mapSize.set(1024,1024);sun.shadow.camera.left=-2;sun.shadow.camera.right=2;sun.shadow.camera.top=2;sun.shadow.camera.bottom=-2;sun.shadow.bias=-.0001;sun.shadow.normalBias=.001;scene.add(sun);
  const floor=new THREE.Mesh(new THREE.PlaneGeometry(20,20),new THREE.MeshStandardMaterial({color:'#edf0e5',roughness:1}));floor.rotation.x=-Math.PI/2;floor.receiveShadow=true;scene.add(floor);
  const grid=new THREE.GridHelper(8,80,0xcbd6bd,0xe0e6d7);grid.position.y=.0001;scene.add(grid);
  const world=new THREE.Group();world.rotation.x=-Math.PI/2;scene.add(world);
  let objects=new Map(),labels=new Map(),textures=[],geometries=[],materials=[],frame,timer,revision=null,slowFrames=0,lastFrame=performance.now(),pixelBudget=reduced?320:640,drawCost=0,drawPause=0;
  const instanceMatrix=new THREE.Matrix4();
  const visibility=new IntersectionObserver(entries=>{visible=entries[0]?.isIntersecting??true});visibility.observe(renderer.domElement);
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
    const batches=new Map(),primitives=new Map(),paint=new Map();
    for(const geom of model.geoms){
      let geometry=geom.type===7?meshes.get(geom.mesh):null;
      const primitiveKey=JSON.stringify([geom.type,geom.size]);
      if(geom.type===6||geom.type===2){
        geometry=primitives.get(primitiveKey);
        if(!geometry){geometry=geom.type===6?new THREE.BoxGeometry(...geom.size.map(v=>v*2)):new THREE.SphereGeometry(geom.size[0],32,20);primitives.set(primitiveKey,geometry);geometries.push(geometry)}
      }
      if(!geometry)continue;
      const color=geom.rgba.slice(0,3),paintKey=color.join(','),key=geometry.uuid+':'+paintKey;
      if(!paint.has(paintKey)){const material=new THREE.MeshStandardMaterial({color:new THREE.Color(...color),roughness:.66,metalness:.08});paint.set(paintKey,material);materials.push(material)}
      if(!batches.has(key))batches.set(key,{geometry,material:paint.get(paintKey),ids:[]});
      batches.get(key).ids.push(geom.id);
    }
    for(const batch of batches.values()){
      const object=new THREE.InstancedMesh(batch.geometry,batch.material,batch.ids.length);
      object.castShadow=object.receiveShadow=true;object.frustumCulled=false;object.userData.geoms=batch.ids;
      object.instanceMatrix.setUsage(THREE.DynamicDrawUsage);world.add(object);
      batch.ids.forEach((id,index)=>objects.set(id,{object,index}));
    }
    revision=model.revision;
  }
  function update(state){
    latest=state;
    if(state.stage&&(selection?.instance!==state.stage.instance||state.stage.selection_version>=selection.selection_version))selection=state.stage;
    if(state.revision!==revision)return;
    for(const duck of state.ducks){
      if(!labels.has(duck.id)){
        const canvas=document.createElement('canvas');canvas.width=192;canvas.height=72;const context=canvas.getContext('2d');context.fillStyle=({a:'#526d32',b:'#3f6580',c:'#987033',d:'#865872'}[duck.id]??'#526d32');context.fillRect(0,0,192,72);context.font='40px sans-serif';context.textAlign='center';context.fillStyle='#fff';context.fillText(`鸭 ${duck.id.toUpperCase()}`,96,51);
        const texture=new THREE.CanvasTexture(canvas);textures.push(texture);const material=new THREE.SpriteMaterial({map:texture,depthTest:false});materials.push(material);const sprite=new THREE.Sprite(material);sprite.scale.set(.105,.04,1);world.add(sprite);labels.set(duck.id,sprite);
      }
      const [x,y,z]=duck.position;labels.get(duck.id).position.set(x,y,z+.20);
    }
    const changed=new Set();
    for(const geom of state.geoms){const entry=objects.get(geom.id);if(!entry)continue;
      const {object,index}=entry,r=geom.rotation;
      instanceMatrix.set(r[0],r[1],r[2],geom.position[0],r[3],r[4],r[5],geom.position[1],r[6],r[7],r[8],geom.position[2],0,0,0,1);
      object.setMatrixAt(index,instanceMatrix);changed.add(object);
    }
    for(const object of changed){object.instanceMatrix.needsUpdate=true;object.computeBoundingSphere()}
    // Reveal the real fall without cropping feet on a narrow screen. Enlarge
    // the view only as needed; a user's orbit/zoom always takes precedence.
    if(state.scene==='table'&&state.tabletop?.dropped_at!=null&&!manualView){
      // The tumble can briefly need a much wider shot. Once D is standing,
      // frame the settled group again so its resumed footwork stays visible.
      if(state.tabletop.floor_dance?.started_at!=null&&!floorFramed){camera.position.set(1.35,.98,-1.35);camera.lookAt(controls.target);floorFramed=true;}
      const bounds=state.ducks.flatMap(({position:[x,y,z]})=>[-.16,.16].flatMap(dx=>[-.16,.16].flatMap(dy=>[Math.max(0,z-.17),z+.25].map(height=>new THREE.Vector3(x+dx,height,-y+dy)))));
      camera.updateMatrixWorld();
      for(let step=0;step<16;step++){
        if(bounds.every(p=>{const screen=p.clone().project(camera);return Math.abs(screen.x)<.90&&Math.abs(screen.y)<.88}))break;
        if(camera.position.distanceTo(controls.target)>=5.5)break;
        camera.position.sub(controls.target).multiplyScalar(1.05).add(controls.target);camera.updateMatrixWorld();
      }
      controls.update();
    }
  }
  const ringGeometry=new THREE.RingGeometry(.11,.125,48),ringMaterial=new THREE.MeshBasicMaterial({color:0xf2b744,side:THREE.DoubleSide,depthTest:false});
  const rings=new Map('abcd'.split('').map(id=>{const ring=new THREE.Mesh(ringGeometry,ringMaterial);ring.rotation.x=-Math.PI/2;ring.visible=false;scene.add(ring);return [id,ring]}));
  const stick=new THREE.Mesh(new THREE.CylinderGeometry(.005,.008,.34,12),new THREE.MeshStandardMaterial({color:0xd99336}));stick.rotation.z=-.65;stick.visible=false;scene.add(stick);
  function screenOrder(){camera.updateMatrixWorld();return (latest?.ducks??[]).map(d=>({id:d.id,x:new THREE.Vector3(d.position[0],d.position[2],-d.position[1]).project(camera).x})).sort((a,b)=>a.x-b.x||a.id.localeCompare(b.id)).map(d=>d.id)}
  function hit(event){
    if(!interaction||latest?.scene!=='stage')return null;
    const rect=renderer.domElement.getBoundingClientRect();cursor.set((event.clientX-rect.left)/rect.width*2-1,-(event.clientY-rect.top)/rect.height*2+1);raycaster.setFromCamera(cursor,camera);
    for(const candidate of raycaster.intersectObjects([...new Set([...objects.values()].map(entry=>entry.object))])){
      const id=latest.owners?.[candidate.object.userData.geoms[candidate.instanceId]];
      if(id){stick.position.copy(candidate.point).add(new THREE.Vector3(.1,.15,0));stick.visible=interactionMode!=='select';return id;}
    }stick.visible=false;return null;
  }
  renderer.domElement.addEventListener('pointerdown',event=>{pointerStart={x:event.clientX,y:event.clientY}});
  renderer.domElement.addEventListener('pointermove',event=>{if(!pointerStart&&interactionMode!=='select')hit(event)});
  renderer.domElement.addEventListener('pointerleave',()=>{stick.visible=false});
  renderer.domElement.addEventListener('pointerup',event=>{
    if(!pointerStart||Math.hypot(event.clientX-pointerStart.x,event.clientY-pointerStart.y)>6)return;
    pointerStart=null;const target=hit(event);if(target)interaction?.({target,order:screenOrder(),mode:interactionMode,revision:latest.revision,instance:latest.stage.instance});
  });
  function resize(){const {width,height}=container.getBoundingClientRect();if(width&&height){renderer.setPixelRatio(reduced?Math.min(1,pixelBudget/width):Math.min(devicePixelRatio,seatedView?1:2));renderer.setSize(width,height);camera.aspect=width/height;camera.updateProjectionMatrix();}}
  const observer=new ResizeObserver(resize);observer.observe(container);
  function animate(){
    const started=performance.now();controls.update();
    for(const [id,ring] of rings){
      const chosen=latest?.scene==='stage'&&selection?.selected.includes(id)?latest.ducks.find(d=>d.id===id):null;
      ring.visible=Boolean(chosen&&interaction);if(chosen)ring.position.set(chosen.position[0],.007,-chosen.position[1]);
    }
    if(visible)renderer.render(scene,camera);
    // WebGL can submit quickly while a software GPU blocks the next frame.
    // Include that delay, excluding our own idle interval, in the draw budget.
    const elapsed=Math.max(performance.now()-started,started-lastFrame-drawPause);
    drawCost=Math.max(drawCost*.85,elapsed);
    slowFrames=elapsed>70?slowFrames+1:0;lastFrame=started;
    if(!reduced&&slowFrames>=3){reduced=true;renderer.shadowMap.enabled=false;floor.material.needsUpdate=true;materials.forEach(m=>m.needsUpdate=true);resize();container.dataset.renderQuality='reduced';}
    if(reduced&&(slowFrames>=3||elapsed>250)&&pixelBudget>160){pixelBudget=Math.max(160,Math.floor(pixelBudget/2));slowFrames=0;resize();}
    // Leave an idle interval after each draw so software GPUs cannot starve input,
    // voice audio or the stream of physical state. Physics remains at 200 Hz.
    drawPause=reduced?Math.max(100,Math.min(2000,drawCost*2)):seatedView?66:33;
    timer=setTimeout(()=>{frame=requestAnimationFrame(animate);},drawPause);
  }animate();
  return {load,update,clear,screenOrder,selection(value){selection=value},interaction(callback,mode="select"){interaction=callback;interactionMode=mode;if(!callback){stick.visible=false;for(const ring of rings.values())ring.visible=false}},renderNow(){controls.update();renderer.render(scene,camera);},frameScene(scene){manualView=false;floorFramed=false;seatedView=scene==='seated';resize();const close=scene==='carry',seated=scene==='seated',table=scene==='table';camera.position.set(...(scene==='stage'||scene==='turntable'?[2.7,2.1,0]:seated?[1.05,.90,-1.05]:table?[1.35,.98,-1.35]:close?[.6,.4,.65]:[.85,.62,.95]));controls.target.set(close ? .12 : table ? .20 : 0,seated ? .52 : table ? .25 : .13,table ? -.10 : 0);controls.update();controls.saveState();},reset(){manualView=false;floorFramed=false;controls.reset();},dispose(){clearTimeout(timer);cancelAnimationFrame(frame);observer.disconnect();visibility.disconnect();clear();controls.dispose();renderer.dispose();ringGeometry.dispose();ringMaterial.dispose();stick.geometry.dispose();stick.material.dispose();}};
}
