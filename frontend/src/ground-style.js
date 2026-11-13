import * as THREE from 'three';
export const GROUND_STYLES=['grid','checker','wood','track','stage'];
export function groundStyle(floor,grid,invalidate){
 const textures=new Map();
 function apply(key){
  if(!GROUND_STYLES.includes(key))return;
  grid.visible=key==='grid';floor.material.color.set(key==='grid'?'#edf0e5':'#ffffff');
  if(key!=='grid'&&!textures.has(key)){
   const canvas=document.createElement('canvas');canvas.width=canvas.height=256;const c=canvas.getContext('2d');
   if(key==='checker'){for(let y=0;y<8;y++)for(let x=0;x<8;x++){c.fillStyle=(x+y)%2?'#6f7d79':'#c7d3ce';c.fillRect(x*32,y*32,32,32)}}
   if(key==='wood'){c.fillStyle='#bd9666';c.fillRect(0,0,256,256);for(let y=0;y<8;y++){c.fillStyle=y%2?'#cda878':'#c29b69';c.fillRect(0,y*32,256,31);c.fillStyle='#94754d';c.fillRect((y%3)*80,y*32,1,32);for(let x=0;x<8;x++){c.fillStyle='#aa86512a';c.fillRect(x*31,y*32+6+(x%3)*5,27,1)}}}
   if(key==='track'){c.fillStyle='#a5624f';c.fillRect(0,0,256,256);c.fillStyle='#f7ecdb';c.fillRect(0,0,256,3);c.fillRect(0,128,256,3)}
   if(key==='stage'){c.fillStyle='#343b42';c.fillRect(0,0,256,256);c.fillStyle='#9a9b7330';c.fillRect(0,0,256,1);c.fillRect(0,0,1,256)}
   const texture=new THREE.CanvasTexture(canvas);texture.colorSpace=THREE.SRGBColorSpace;texture.wrapS=texture.wrapT=THREE.RepeatWrapping;texture.repeat.set(20,20);textures.set(key,texture);
  }
  floor.material.map=key==='grid'?null:textures.get(key);floor.material.needsUpdate=true;invalidate();
 }
 return {apply,dispose(){for(const t of textures.values())t.dispose();textures.clear()}};
}
