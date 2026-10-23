import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { RoundedBoxGeometry } from 'three/addons/geometries/RoundedBoxGeometry.js';

export function createDuckScene(container) {
  const scene = new THREE.Scene();
  scene.background = new THREE.Color('#edf0e5');
  scene.fog = new THREE.Fog('#edf0e5', 9, 20);
  const camera = new THREE.PerspectiveCamera(34, 1, .1, 50);
  camera.position.set(3.3, 2.6, 4.9);
  const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false });
  renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.PCFSoftShadowMap;
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  container.appendChild(renderer.domElement);
  renderer.domElement.setAttribute('aria-label', '原创机器人鸭子动画示意，非物理仿真');
  const controls = new OrbitControls(camera, renderer.domElement);
  controls.target.set(0, .9, 0);
  controls.minDistance = 3; controls.maxDistance = 8;
  controls.maxPolarAngle = Math.PI / 2.04;
  controls.enableDamping = true; controls.enablePan = false;
  controls.update(); controls.saveState();
  scene.add(new THREE.HemisphereLight(0xffffff, 0x78845c, 2.6));
  const sun = new THREE.DirectionalLight(0xfff9e8, 4);
  sun.position.set(-3, 6, 4); sun.castShadow = true;
  sun.shadow.mapSize.set(2048, 2048);
  sun.shadow.camera.left = -4; sun.shadow.camera.right = 4;
  sun.shadow.camera.top = 4; sun.shadow.camera.bottom = -4;
  sun.shadow.bias = -.0005; sun.shadow.normalBias = .025;
  scene.add(sun);
  const fill = new THREE.DirectionalLight(0xe7f2ff, 1.6); fill.position.set(3, 2, -2); scene.add(fill);
  const mat = (color, roughness = .65, metalness = 0) => new THREE.MeshStandardMaterial({ color, roughness, metalness });
  const shell = mat('#f7f5e9'), edge = mat('#e0e2d6'), dark = mat('#313a34'), black = mat('#17201d', .3), orange = mat('#ed9751'), gold = mat('#ccdb76', .4);
  function mesh(geometry, material, parent, x=0, y=0, z=0) {
    const obj = new THREE.Mesh(geometry, material); obj.position.set(x,y,z);
    obj.castShadow = true; obj.receiveShadow = true; parent.add(obj); return obj;
  }
  const box = (w,h,d,r=.08) => new RoundedBoxGeometry(w,h,d,4,r);
  const floor = mesh(new THREE.PlaneGeometry(100,100), mat('#edf0e5'), scene);
  floor.rotation.x = -Math.PI/2; floor.castShadow = false;
  const grid = new THREE.GridHelper(12,24,0xd9dfce,0xe0e5d7); grid.position.y=.002; grid.material.transparent=true;grid.material.opacity=.65;scene.add(grid);
  const platform = mesh(new THREE.CylinderGeometry(1.6,1.62,.045,96),mat('#e2e8d4'),scene,0,.024,0);
  const rim = mesh(new THREE.TorusGeometry(1.58,.008,8,96),mat('#c5d2af'),scene,0,.052,0); rim.rotation.x=Math.PI/2;
  const duck = new THREE.Group(); scene.add(duck);
  const body = new THREE.Group(); body.position.y=.83; duck.add(body);
  mesh(box(.77,.65,.7,.21),shell,body);
  mesh(box(.66,.055,.59,.025),edge,body,0,-.24,0);
  const chest = mesh(box(.32,.16,.025,.035),dark,body,0,.02,.35);
  mesh(new THREE.SphereGeometry(.028,20,12),gold,chest,-.09,0,.025);
  mesh(box(.11,.018,.012,.005),edge,chest,.04,0,.025);
  const neck = mesh(new THREE.CylinderGeometry(.12,.15,.22,32),dark,body,0,.43,0);
  const head = new THREE.Group(); head.position.set(0,.62,.065); body.add(head);
  mesh(box(.93,.61,.73,.2),shell,head);
  mesh(box(.85,.035,.64,.015),edge,head,0,-.12,0);
  mesh(box(.67,.26,.045,.1),black,head,0,.03,.362);
  for(const x of [-.19,.19]) {
    mesh(new THREE.CapsuleGeometry(.042,.025,6,16),mat('#e7efcf'),head,x,.04,.397);
    const bolt = mesh(new THREE.CylinderGeometry(.025,.025,.018,20),dark,head,Math.sign(x)*.467,-.12,0);
    bolt.rotation.z=Math.PI/2;
  }
  mesh(box(.48,.13,.34,.06),orange,head,0,-.18,.43);
  mesh(box(.42,.018,.26,.009),mat('#9b6544'),head,0,-.195,.48);
  mesh(box(.17,.08,.14,.025),gold,head,0,.345,-.01);
  for(const x of [-.09,0,.09]) mesh(new THREE.ConeGeometry(.035,.12,4),gold,head,x,.42,-.01);
  const feet = [];
  for(const sign of [-1,1]) {
    const wing = mesh(box(.12,.33,.37,.06),edge,body,sign*.44,-.02,0); wing.rotation.z=sign*-.13;
    const joint=mesh(new THREE.CylinderGeometry(.105,.105,.14,32),dark,duck,sign*.25,.54,0);joint.rotation.z=Math.PI/2;
    const leg=new THREE.Group();leg.position.set(sign*.25,.52,0);duck.add(leg);
    mesh(box(.13,.33,.14,.03),shell,leg,0,-.17,0);
    const knee=mesh(new THREE.CylinderGeometry(.075,.075,.15,24),dark,leg,0,-.31,0);knee.rotation.z=Math.PI/2;
    mesh(box(.29,.11,.48,.04),orange,leg,0,-.42,.12);
    for(const dx of [-.065,.065]) mesh(box(.012,.007,.17,.003),mat('#ce7e42'),leg,dx,-.36,.23);
    feet.push(leg);
  }
  const tail=mesh(new THREE.ConeGeometry(.14,.33,4),edge,body,0,-.02,-.44);tail.rotation.x=-Math.PI/2;
  let state={pose:{x:0,z:0,yaw:0,pitch:0},velocity:{forward:0,yaw:0}}, frame;
  const clock = new THREE.Clock();
  const observer = new ResizeObserver(() => {
    const {width,height}=container.getBoundingClientRect(); if(!width||!height)return;
    renderer.setSize(width,height);camera.aspect=width/height;camera.updateProjectionMatrix();
  });observer.observe(container);
  function animate(){
    frame=requestAnimationFrame(animate);
    const t=clock.getElapsedTime(), p=state.pose??{}, moving=Math.abs(state.velocity?.forward??0)+Math.abs(state.velocity?.lateral??0)+Math.abs(state.velocity?.yaw??0)>.001;
    duck.position.x=THREE.MathUtils.lerp(duck.position.x,(p.x??0)*3,.16);
    duck.position.z=THREE.MathUtils.lerp(duck.position.z,(p.z??0)*3,.16);
    duck.rotation.y=THREE.MathUtils.lerp(duck.rotation.y,p.yaw??0,.2);
    head.rotation.x=-(p.pitch??0);
    head.rotation.y=p.head_yaw??0;
    head.rotation.z=-(p.head_roll??0);
    const gait=moving?Math.sin(t*11)*.19:0;
    feet[0].rotation.x=gait;feet[1].rotation.x=-gait;
    const sideGait=gait*Math.min(1,Math.abs(state.velocity?.lateral??0)/.28)*.65;
    feet[0].rotation.z=sideGait;feet[1].rotation.z=-sideGait;
    body.position.y=.83+(p.body_z??0)*5+(moving?Math.abs(Math.sin(t*11))*.025:Math.sin(t*2)*.006);
    body.rotation.z=-(p.body_roll??0);
    body.rotation.x=-(p.body_pitch??0);
    controls.update();renderer.render(scene,camera);
  }animate();
  return {update(next){state=next},resetCamera(){controls.reset()},dispose(){cancelAnimationFrame(frame);observer.disconnect();renderer.dispose();controls.dispose()}};
}
