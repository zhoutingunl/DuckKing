import {translate} from './ui-language.js';
import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import {appearanceControls,appearanceFor,studioEnvironment} from './duck-appearance.js';
import {renderScheduler} from './render-scheduler.js';

export function physicsView(container,{label=null,onCameraChange}={}) {
  let interaction=null,interactionMode="select",latest=null,pointerStart=null,selection=null,visible=true,disposed=false,scheduler;
  const invalidate=()=>scheduler?.invalidate();
  let syncingCamera=false;
  const raycaster=new THREE.Raycaster(),cursor=new THREE.Vector2();
  const scene=new THREE.Scene();scene.background=new THREE.Color('#edf0e5');
  const renderer=new THREE.WebGLRenderer({antialias:true});renderer.setPixelRatio(Math.min(devicePixelRatio,2));
  const gl=renderer.getContext(),debug=gl.getExtension('WEBGL_debug_renderer_info');
  const reduced=/swiftshader|llvmpipe|softpipe|software/i.test(debug?gl.getParameter(debug.UNMASKED_RENDERER_WEBGL):'');
  container.dataset.renderQuality=reduced?'reduced':'full';
  renderer.toneMapping=THREE.ACESFilmicToneMapping;renderer.toneMappingExposure=1;
  renderer.shadowMap.enabled=!reduced;renderer.shadowMap.type=THREE.PCFShadowMap;
  renderer.shadowMap.autoUpdate=false;
  container.append(renderer.domElement);renderer.domElement.setAttribute('aria-label','官方 MicroDuck 模型，位置与关节姿态来自 MuJoCo');
  const camera=new THREE.PerspectiveCamera(38,1,.01,30);camera.position.set(.85,.62,.95);
  const controls=new OrbitControls(camera,renderer.domElement);controls.target.set(0,.13,0);controls.minDistance=.35;controls.maxDistance=6;controls.maxPolarAngle=Math.PI/2.02;controls.enableDamping=true;controls.update();controls.saveState();
  let manualView=false,floorFramed=false,seatedView=false;
  const cameraState=()=>({position:camera.position.toArray(),target:controls.target.toArray(),zoom:camera.zoom});
  const cameraChanged=()=>{invalidate();if(!syncingCamera)onCameraChange?.(cameraState())};
  const manual=()=>{manualView=true};controls.addEventListener('start',manual);controls.addEventListener('change',cameraChanged);
  scene.add(new THREE.HemisphereLight(0xffffff,0x71815a,1.2));
  const sun=new THREE.DirectionalLight(0xfff6df,2);sun.position.set(1,2,1);sun.castShadow=true;sun.shadow.mapSize.set(1024,1024);sun.shadow.camera.left=-2;sun.shadow.camera.right=2;sun.shadow.camera.top=2;sun.shadow.camera.bottom=-2;sun.shadow.bias=-.0001;sun.shadow.normalBias=.001;scene.add(sun);
  const disposeEnvironment=studioEnvironment(renderer,scene,{reduced});
  const floor=new THREE.Mesh(new THREE.PlaneGeometry(20,20),new THREE.MeshStandardMaterial({color:'#edf0e5',roughness:1}));floor.rotation.x=-Math.PI/2;floor.receiveShadow=true;scene.add(floor);
  const grid=new THREE.GridHelper(8,80,0xcbd6bd,0xe0e6d7);grid.position.y=.0001;scene.add(grid);
  const world=new THREE.Group();world.rotation.x=-Math.PI/2;scene.add(world);
  let objects=new Map(),labels=new Map(),annotations=new Map(),textures=[],geometries=[],materials=[],revision=null;
  let renderBatches=[],readyToRender=false,headingGuide=null,headingTexture=null,centerGuide=null;
  const appearance=appearanceControls(container,repaint);
  function repaint(){
    for(const {object,geoms} of renderBatches){
      geoms.forEach((geom,index)=>object.setColorAt(index,appearanceFor(geom,appearance.colours).color));
      object.instanceColor.needsUpdate=true;
    }
    invalidate();
  }
  const instanceMatrix=new THREE.Matrix4();
  let parts={};
  function setParts(value){parts=value;container.dataset.choraleParts=JSON.stringify(parts);for(const [id,sprite] of labels){paintLabel(sprite.material.map.image,id);sprite.material.map.needsUpdate=true}invalidate()}
  function paintLabel(canvas,id){const context=canvas.getContext('2d');context.clearRect(0,0,192,72);context.fillStyle=({a:'#526d32',b:'#3f6580',c:'#987033',d:'#865872'}[id]??'#526d32');context.fillRect(0,0,192,72);context.font=parts[id]?'28px sans-serif':'40px sans-serif';context.textAlign='center';context.fillStyle=parts[id]?.active===false?'#d4d9ce':'#fff';context.fillText(translate(label??`鸭 ${id.toUpperCase()}`),96,parts[id]?29:51,180);if(parts[id])context.fillText(translate(parts[id].part),96,61,180)}
  function setLabel(text){
    if(disposed||text===label)return;label=text;container.dataset.duckLabel=text??'';
    for(const [id,sprite] of labels){paintLabel(sprite.material.map.image,id);sprite.material.map.needsUpdate=true}invalidate();
  }
  if(label)container.dataset.duckLabel=label;
  function paintHeading(canvas){
    const context=canvas.getContext('2d');context.fillStyle='#155d85';context.fillRect(0,0,384,96);
    context.font='bold 48px sans-serif';context.textAlign='center';context.fillStyle='#fff';context.fillText(translate('目标朝向'),192,65,360);
  }
  function paintAnnotation(sprite){const canvas=sprite.material.map.image,ctx=canvas.getContext('2d');ctx.clearRect(0,0,256,64);ctx.fillStyle='#fffef1';ctx.fillRect(0,0,256,64);ctx.fillStyle='#435d37';ctx.textAlign='center';ctx.font='32px sans-serif';ctx.fillText(translate(sprite.userData.text),128,44,240);sprite.material.map.needsUpdate=true}
  function refreshLanguage(){
    for(const [id,sprite] of labels){paintLabel(sprite.material.map.image,id);sprite.material.map.needsUpdate=true}
    for(const sprite of annotations.values())paintAnnotation(sprite);
    if(headingTexture){paintHeading(headingTexture.image);headingTexture.needsUpdate=true}
    invalidate();
  }
  function updateHeadingGuide(state){
    // Level 2's explicit facing task targets world +X (yaw=0). Paint this on
    // the floor outside the disc, never as an obstacle or floating label.
    // This annotation belongs to world, never to the moving
    // disc, robot, or camera. World's Z-up -> Y-up conversion preserves +X.
    const active=state.scene==='balance'&&state.balance?.level===2;
    if(active&&!headingGuide){
      headingGuide=new THREE.Group();world.add(headingGuide);
      // A rectangle plus triangle keeps the overlay small and avoids a shape
      // triangulator in the shared renderer bundle.
      const geometry=new THREE.BufferGeometry();
      geometry.setAttribute('position',new THREE.Float32BufferAttribute([-.12,-.010,0,.04,-.010,0,.04,.010,0,-.12,.010,0,.04,-.030,0,.12,0,0,.04,.030,0],3));
      geometry.setIndex([0,1,2,0,2,3,4,5,6]);geometries.push(geometry);
      for(const [colour,scale,height,order] of [[0xffffff,1.12,.002,10],[0x155d85,1,.003,11]]){
        const material=new THREE.MeshBasicMaterial({color:colour,side:THREE.DoubleSide,depthWrite:false});materials.push(material);
        const arrow=new THREE.Mesh(geometry,material);arrow.position.set(.56,0,height);arrow.scale.setScalar(scale);arrow.renderOrder=order;headingGuide.add(arrow);
      }
      const canvas=document.createElement('canvas');canvas.width=384;canvas.height=96;
      paintHeading(canvas);
      const texture=new THREE.CanvasTexture(canvas);texture.colorSpace=THREE.SRGBColorSpace;textures.push(texture);headingTexture=texture;
      const material=new THREE.MeshBasicMaterial({map:texture,side:THREE.DoubleSide,depthWrite:false});materials.push(material);
      const plane=new THREE.PlaneGeometry(.22,.055);geometries.push(plane);
      const text=new THREE.Mesh(plane,material);text.position.set(.56,-.075,.003);text.renderOrder=12;headingGuide.add(text);
      invalidate();
    }
    if(headingGuide&&headingGuide.visible!==active){headingGuide.visible=active;invalidate()}
    const target=active?'world:+X':'none';
    if(container.dataset.headingTarget!==target){
      container.dataset.headingTarget=target;
      container.dataset.headingSurface=active?'ground':'none';
      renderer.domElement.setAttribute('aria-label','官方 MicroDuck 模型，位置与关节姿态来自 MuJoCo'+(active?'；地面蓝色目标朝向标记固定在圆盘外，躯干应沿箭头方向保持朝向':''));
    }
  }
  function updateCenterGuide(state){
    const target=state.scene==='balance'&&state.balance?.level===3?state.center_target:null;
    if(target&&!centerGuide){
      centerGuide=new THREE.Group();centerGuide.matrixAutoUpdate=false;world.add(centerGuide);
      // The fill and its inner boundary both use the physical target radius.
      // This is paint on the moving disc, with no collision geometry.
      for(const [geometry,opacity] of [[new THREE.CircleGeometry(1,64),.24],[new THREE.RingGeometry(.95,1,64),1]]){
        const material=new THREE.MeshBasicMaterial({color:0xc04929,transparent:true,opacity,side:THREE.DoubleSide,depthWrite:false});
        const mesh=new THREE.Mesh(geometry,material);mesh.renderOrder=8;centerGuide.add(mesh);geometries.push(geometry);materials.push(material);
      }
    }
    if(centerGuide){
      if(centerGuide.visible!==Boolean(target)){centerGuide.visible=Boolean(target);invalidate()}
      if(target){
        const r=target.rotation,p=target.position,s=target.radius_m;
        instanceMatrix.set(r[0]*s,r[1]*s,r[2],p[0],r[3]*s,r[4]*s,r[5],p[1],r[6]*s,r[7]*s,r[8],p[2],0,0,0,1);
        if(!centerGuide.matrix.equals(instanceMatrix)){centerGuide.matrix.copy(instanceMatrix);centerGuide.matrixWorldNeedsUpdate=true;invalidate()}
      }
    }
    container.dataset.centerTarget=target?String(target.radius_m):'none';
    container.dataset.centerSurface=target?'disc':'none';
  }
  const setVisibility=()=>scheduler?.visible(visible&&!document.hidden);
  const visibility=new IntersectionObserver(entries=>{visible=entries[0]?.isIntersecting??true;setVisibility()});visibility.observe(renderer.domElement);
  document.addEventListener('visibilitychange',setVisibility);
  function clear(){
    // Geometry disposal does not release InstancedMesh's matrix/colour buffers.
    for(const {object} of renderBatches)object.dispose();
    world.clear();geometries.forEach(g=>g.dispose());materials.forEach(m=>m.dispose());textures.forEach(t=>t.dispose());
    geometries=[];materials=[];textures=[];renderBatches=[];readyToRender=false;revision=null;latest=null;selection=null;headingGuide=null;headingTexture=null;centerGuide=null;
    floor.position.set(0,0,0);grid.position.set(0,.0001,0);
    objects.clear();labels.clear();annotations.clear();parts={};delete container.dataset.choraleParts;renderer.renderLists.dispose();appearance.setDucks([]);delete container.dataset.renderedScene;
    delete container.dataset.headingTarget;
    delete container.dataset.headingSurface;
    delete container.dataset.centerTarget;
    delete container.dataset.centerSurface;
    renderer.shadowMap.needsUpdate=true;invalidate();
  }
  function load(model){
    if(disposed)return;
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
      if([2,3,4,5,6].includes(geom.type)){
        geometry=primitives.get(primitiveKey);
        if(!geometry){
          geometry=geom.type===3?new THREE.CapsuleGeometry(geom.size[0],geom.size[1]*2,6,12):geom.type===4?new THREE.SphereGeometry(1,24,16):geom.type===6?new THREE.BoxGeometry(...geom.size.map(v=>v*2)):geom.type===5?new THREE.CylinderGeometry(geom.size[0],geom.size[0],geom.size[1]*2,64):new THREE.SphereGeometry(geom.size[0],32,20);
          // MuJoCo cylinders use local Z, Three.js cylinders use local Y.
          if(geom.type===5||geom.type===3)geometry.rotateX(Math.PI/2);
          if(geom.type===4)geometry.scale(...geom.size);
          primitives.set(primitiveKey,geometry);geometries.push(geometry)
        }
      }
      if(!geometry)continue;
      const spec=appearanceFor(geom,appearance.colours),paintKey=`${spec.roughness}:${spec.metalness}`,key=geometry.uuid+':'+paintKey;
      if(!paint.has(paintKey)){const material=new THREE.MeshStandardMaterial({color:0xffffff,roughness:spec.roughness,metalness:spec.metalness});paint.set(paintKey,material);materials.push(material)}
      if(!batches.has(key))batches.set(key,{geometry,material:paint.get(paintKey),geoms:[]});
      batches.get(key).geoms.push(geom);
    }
    for(const batch of batches.values()){
      const object=new THREE.InstancedMesh(batch.geometry,batch.material,batch.geoms.length);
      object.castShadow=object.receiveShadow=true;object.frustumCulled=false;object.userData.geoms=batch.geoms.map(geom=>geom.id);
      object.instanceMatrix.setUsage(THREE.DynamicDrawUsage);world.add(object);
      batch.geoms.forEach((geom,index)=>objects.set(geom.id,{object,index}));
      renderBatches.push({object,geoms:batch.geoms});
    }
    repaint();appearance.setDucks(model.geoms.map(geom=>geom.duck));
    revision=model.revision;
  }
  function update(state){
    if(disposed)return;
    latest=state;
    if(state.stage&&(selection?.instance!==state.stage.instance||state.stage.selection_version>selection.selection_version)){selection=state.stage;invalidate()}
    if(state.revision!==revision)return;
    updateHeadingGuide(state);
    updateCenterGuide(state);
    for(const duck of state.ducks){
      if(!labels.has(duck.id)){
        const canvas=document.createElement('canvas');canvas.width=192;canvas.height=72;paintLabel(canvas,duck.id);
        const texture=new THREE.CanvasTexture(canvas);textures.push(texture);const material=new THREE.SpriteMaterial({map:texture,depthTest:false});materials.push(material);const sprite=new THREE.Sprite(material);sprite.scale.set(.105,.04,1);world.add(sprite);labels.set(duck.id,sprite);invalidate();
      }
      const [x,y,z]=duck.position;labels.get(duck.id).position.set(x,y,z+.20);
    }
    for(const point of state.annotations??[]){
      let sprite=annotations.get(point.id);
      if(!sprite){const canvas=document.createElement('canvas');canvas.width=256;canvas.height=64;const texture=new THREE.CanvasTexture(canvas);textures.push(texture);const material=new THREE.SpriteMaterial({map:texture,depthTest:false});materials.push(material);sprite=new THREE.Sprite(material);sprite.scale.set(.18,.045,1);world.add(sprite);annotations.set(point.id,sprite)}
      if(sprite.userData.text!==point.text){sprite.userData.text=point.text;paintAnnotation(sprite);invalidate()}
      sprite.position.set(...point.position);
    }
    const changed=new Set();
    for(const geom of state.geoms){const entry=objects.get(geom.id);if(!entry)continue;
      const {object,index}=entry,r=geom.rotation;
      // Paused backends still send snapshots. Do not upload identical transforms.
      if(entry.pose&&geom.position.every((v,i)=>v===entry.pose.position[i])&&r.every((v,i)=>v===entry.pose.rotation[i]))continue;
      entry.pose=geom;
      instanceMatrix.set(r[0],r[1],r[2],geom.position[0],r[3],r[4],r[5],geom.position[1],r[6],r[7],r[8],geom.position[2],0,0,0,1);
      object.setMatrixAt(index,instanceMatrix);changed.add(object);
    }
    // Raycasting computes the bounds lazily; rendering has frustumCulled=false.
    for(const object of changed){object.instanceMatrix.needsUpdate=true;object.boundingSphere=null}
    if(changed.size){readyToRender=true;renderer.shadowMap.needsUpdate=true;invalidate()}
    // Follow only the running trial and preserve the viewer's chosen orbit.
    if(state.scene==='functional'&&state.feature?.capability==='running'&&Array.isArray(state.camera_follow)&&state.camera_follow.length===3&&state.camera_follow.every(Number.isFinite)&&!manualView){
      const [x,y,z]=state.camera_follow,target=new THREE.Vector3(x,z+.08,-y),delta=target.clone().sub(controls.target);
      camera.position.add(delta);controls.target.copy(target);floor.position.set(x,0,-y);grid.position.set(Math.round(x*10)/10,.0001,-Math.round(y*10)/10);controls.update();invalidate();
    }
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
    // Hidden/static views may not have rendered the latest scene yet. Raycasting
    // must use current world/camera transforms without waiting for a GPU frame.
    world.updateMatrixWorld(true);camera.updateMatrixWorld();
    const rect=renderer.domElement.getBoundingClientRect();cursor.set((event.clientX-rect.left)/rect.width*2-1,-(event.clientY-rect.top)/rect.height*2+1);raycaster.setFromCamera(cursor,camera);
    for(const candidate of raycaster.intersectObjects([...new Set([...objects.values()].map(entry=>entry.object))])){
      const id=latest.owners?.[candidate.object.userData.geoms[candidate.instanceId]];
      if(id){stick.position.copy(candidate.point).add(new THREE.Vector3(.1,.15,0));stick.visible=interactionMode!=='select';return id;}
    }stick.visible=false;return null;
  }
  const events=new AbortController(),listen={signal:events.signal};
  window.addEventListener('duckking-language-changed',refreshLanguage,listen);
  renderer.domElement.addEventListener('pointerdown',event=>{pointerStart={x:event.clientX,y:event.clientY}},listen);
  renderer.domElement.addEventListener('pointermove',event=>{if(!pointerStart&&interactionMode!=='select'){hit(event);invalidate()}},listen);
  renderer.domElement.addEventListener('pointerleave',()=>{stick.visible=false;invalidate()},listen);
  renderer.domElement.addEventListener('pointercancel',()=>{pointerStart=null},listen);
  renderer.domElement.addEventListener('pointerup',event=>{
    const start=pointerStart;pointerStart=null;
    if(!start||Math.hypot(event.clientX-start.x,event.clientY-start.y)>6)return;
    const target=hit(event);invalidate();if(target)interaction?.({target,order:screenOrder(),mode:interactionMode,revision:latest.revision,instance:latest.stage.instance});
  },listen);
  // Keep at least one physical pixel per CSS pixel, including on software GPUs.
  // Model parsing, shader compilation and background-tab delays are not evidence
  // that the image should be permanently shrunk to a 160px-wide thumbnail.
  function resize(){if(disposed)return;const {width,height}=container.getBoundingClientRect();if(width&&height){renderer.setPixelRatio(reduced?1:Math.min(devicePixelRatio,2));renderer.setSize(width,height);camera.aspect=width/height;camera.updateProjectionMatrix();invalidate();}}
  const observer=new ResizeObserver(resize);observer.observe(container);
  function draw(){
    const moving=controls.update();
    for(const [id,ring] of rings){
      const chosen=latest?.scene==='stage'&&selection?.selected?.includes(id)?latest.ducks.find(d=>d.id===id):null;
      ring.visible=Boolean(chosen&&interaction);if(chosen)ring.position.set(chosen.position[0],.007,-chosen.position[1]);
    }
    renderer.render(scene,camera);if(readyToRender)container.dataset.renderedScene=latest.scene;
    return moving;
  }
  scheduler=renderScheduler(draw,{interval:()=>reduced?100:seatedView?66:33});setVisibility();resize();
  return {load,update,clear,screenOrder,setLabel,setParts,
    syncCamera(state){
      if(disposed)return;syncingCamera=true;manualView=true;controls.enableDamping=false;controls.update();
      camera.position.fromArray(state.position);controls.target.fromArray(state.target);camera.zoom=state.zoom;camera.updateProjectionMatrix();controls.update();controls.enableDamping=true;syncingCamera=false;invalidate();
    },
    selection(value){selection=value;invalidate()},
    interaction(callback,mode="select"){interaction=callback;interactionMode=mode;if(!callback){stick.visible=false;for(const ring of rings.values())ring.visible=false}invalidate()},
    renderNow(){scheduler.flush()},
    frameScene(scene){if(disposed)return;manualView=false;floorFramed=false;seatedView=scene==='seated';resize();controls.enableDamping=false;controls.update();const close=scene==='carry',seated=scene==='seated',table=scene==='table';camera.position.set(...(scene==='long_jump'?[1.1,.85,1.3]:scene==='basketball'?[.95,.85,1.1]:scene==='swing'?[1.25,.85,1.3]:scene==='circus'?[1.15,.75,1.15]:scene==='navigation'?[1.5,1.3,1.6]:scene==='stage'?[2.7,2.1,0]:scene==='choir'?[1.15,.70,.15]:seated?[1.05,.90,-1.05]:table?[1.35,.98,-1.35]:close?[.6,.4,.65]:scene==='seesaw'?[.72,.85,-1.15]:scene==='balance'?[1.25,.82,1.35]:[.85,.62,.95]));controls.target.set(scene==='long_jump' ? .28 : close ? .12 : table ? .20 : 0,scene==='basketball' ? .3 : scene==='long_jump' ? .24 : scene==='swing' ? .42 : scene==='circus' ? .22 : scene==='seesaw' ? .22 : scene==='balance' ? .13 : seated ? .52 : table ? .25 : .13,table ? -.10 : 0);controls.update();controls.saveState();controls.enableDamping=true;invalidate()},
    reset(){if(disposed)return;manualView=false;floorFramed=false;controls.enableDamping=false;controls.update();controls.reset();controls.enableDamping=true;invalidate()},
    dispose(){
      if(disposed)return;disposed=true;scheduler.dispose();events.abort();observer.disconnect();visibility.disconnect();document.removeEventListener('visibilitychange',setVisibility);
      controls.removeEventListener('start',manual);controls.removeEventListener('change',cameraChanged);controls.dispose();
      clear();appearance.dispose();disposeEnvironment();sun.shadow.dispose();
      floor.geometry.dispose();floor.material.dispose();grid.geometry.dispose();grid.material.dispose();
      ringGeometry.dispose();ringMaterial.dispose();stick.geometry.dispose();stick.material.dispose();
      scene.clear();renderer.dispose();renderer.forceContextLoss();renderer.domElement.remove();
      delete container.dataset.duckLabel;
    },
  };
}
