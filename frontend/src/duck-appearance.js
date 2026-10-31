// Palette and part assignments adapted from Pollen Robotics' Microduck Simulator
// ad9d41a763f30dc770817c33d92dcfec0205db1e, Apache-2.0. See THIRD_PARTY.md.
// Colours below are linear RGB; UI swatches are the official press-kit sRGB values.
import * as THREE from 'three';
import {RoomEnvironment} from 'three/addons/environments/RoomEnvironment.js';

export const COLOURWAYS = {
  cream: {label:'奶油白 · Cream',swatch:'#f7e6cb',shell:[.888,.86,.798],eye:[1,.413,.007],beak:[1,.144,.008],sole:[1,.608,.021],inside:[1,.413,.007]},
  graphite: {label:'石墨灰 · Graphite',swatch:'#6c6a68',shell:[.028,.028,.033],eye:[.443,.308,.663],beak:[1,.608,.021],sole:[.221,.134,.465],inside:[.36,.23,.48]},
  lavender: {label:'薰衣草紫 · Lavender',swatch:'#bfa9cf',shell:[.462,.367,.688],eye:[.441,.613,.723],beak:[1,.608,.021],sole:[.221,.134,.465],inside:[.36,.23,.48]},
  sky: {label:'天空蓝 · Sky',swatch:'#a9dbe8',shell:[.441,.613,.723],eye:[1,.413,.007],beak:[1,.144,.008],sole:[1,.608,.021],inside:[1,.413,.007]},
};
const DEFAULTS = {a:'cream',b:'graphite',c:'lavender',d:'sky'};
const STORAGE_KEY = 'duckking-colourways-v1';
const SHELL = new Set(['top_head_shell','trunk_base','left_shell','right_shell','upper_leg_left','upper_leg_right']);
const BEAK = new Set(['bottom_head_shell','jaw','foot_left','foot_right','ankle_left','ankle_right','ankle_l_v1','ankle_r_v1','roller_blade']);
const DARK = new Set(['xl330','np_f970','m12_lens_holder','yaw2roll','bearing_roll','motor_support','speaker','tire']);

export function readColourways(storage) {
  let saved;
  try { saved=JSON.parse(storage?.getItem(STORAGE_KEY)??'null'); } catch { /* Optional browser preference. */ }
  return Object.fromEntries(Object.entries(DEFAULTS).map(([id,key])=>[id,Object.hasOwn(COLOURWAYS,saved?.[id])?saved[id]:key]));
}

export function appearanceFor(geom, colours=DEFAULTS) {
  const original={color:new THREE.Color(...geom.rgba.slice(0,3)),roughness:.66,metalness:.08};
  if(!geom.duck||!geom.part)return original;
  const v=COLOURWAYS[colours[geom.duck]]??COLOURWAYS.cream,part=geom.part;
  let color,roughness=.34,metalness=0;
  if(SHELL.has(part)){color=v.shell;roughness=.30;}
  else if(BEAK.has(part))color=v.beak;
  else if(part==='noenoeil')color=v.eye;
  else if(part==='sole_left'||part==='sole_right'||part==='rim'){color=v.sole;roughness=.56;}
  else if(part==='jaw_soft'||part==='soft_mouth_top'){color=v.inside;roughness=.52;}
  else if(part==='face_part'){color=[.328,.312,.283];roughness=.42;}
  else if(part==='lens'){color=[.01,.012,.02];roughness=.08;}
  else if(DARK.has(part)){color=[.012,.012,.014];roughness=.45;}
  else if(part.startsWith('seeed_bearing')||['upper_leg_rigidity_plate','neck'].includes(part)){
    color=[.55,.59,.64];roughness=.24;metalness=.85;
  }else if(['hip_l','leg','neck_pitch','yaw_roll_motion','power_support'].includes(part)){
    color=[.256,.256,.279];roughness=.36;metalness=.35;
  }else return original;
  return {color:new THREE.Color(...color),roughness,metalness};
}

// Render a small procedural studio once: no HDR download or per-frame cube capture.
export function studioEnvironment(renderer,scene,{reduced=false}={}) {
  if(reduced)return ()=>{};
  const room=new RoomEnvironment(),generator=new THREE.PMREMGenerator(renderer);
  let target;
  try { target=generator.fromScene(room,.04,.1,100,{size:64}); }
  finally { room.dispose();generator.dispose(); }
  scene.environment=target.texture;scene.environmentIntensity=.7;
  return ()=>{scene.environment=null;target.dispose();};
}

// Per-browser appearance only; changing colour must never submit a motion or reload geometry.
export function appearanceControls(container,onChange) {
  let storage;
  try { storage=globalThis.localStorage; } catch { /* Private/blocked storage is supported. */ }
  const colours=readColourways(storage);
  const panel=document.createElement('div');panel.className='duck-appearance';panel.hidden=true;
  panel.setAttribute('role','group');panel.setAttribute('aria-label','小鸭外观');
  const caption=document.createElement('span');caption.className='appearance-caption';caption.textContent='配色';panel.append(caption);
  const target=document.createElement('select');target.setAttribute('aria-label','选择换色的小鸭');panel.append(target);
  const swatches=document.createElement('div');swatches.className='appearance-swatches';swatches.setAttribute('role','group');swatches.setAttribute('aria-label','官方配色');panel.append(swatches);
  const buttons=new Map();
  for(const [key,colour] of Object.entries(COLOURWAYS)){
    const button=document.createElement('button');button.type='button';button.className='appearance-swatch';
    button.style.setProperty('--swatch',colour.swatch);button.title=colour.label;button.setAttribute('aria-label',colour.label);
    button.addEventListener('click',()=>{
      colours[target.value]=key;
      try { storage?.setItem(STORAGE_KEY,JSON.stringify(colours)); } catch { /* Keep the current-page choice. */ }
      refresh();onChange(colours);
    });
    buttons.set(key,button);swatches.append(button);
  }
  const label=document.createElement('span');label.className='appearance-name';panel.append(label);
  function refresh(){
    const key=colours[target.value];
    for(const [name,button] of buttons)button.setAttribute('aria-pressed',String(name===key));
    label.textContent=COLOURWAYS[key]?.label.split(' · ')[0]??'';
    container.dataset.colourways=JSON.stringify(colours);
  }
  target.addEventListener('change',refresh);container.append(panel);
  return {colours,setDucks(ids){
    const previous=target.value;target.replaceChildren();
    for(const id of [...new Set(ids)].filter(id=>Object.hasOwn(DEFAULTS,id))){const option=document.createElement('option');option.value=id;option.textContent=`鸭 ${id.toUpperCase()}`;target.append(option);}
    if([...target.options].some(option=>option.value===previous))target.value=previous;
    target.hidden=target.options.length<2;panel.hidden=!target.options.length;refresh();
  },dispose(){panel.remove();delete container.dataset.colourways;}};
}
