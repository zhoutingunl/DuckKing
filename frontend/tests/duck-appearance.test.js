import {test} from 'node:test';
import assert from 'node:assert/strict';
import {appearanceFor,readColourways} from '../src/duck-appearance.js';

test('unavailable or invalid browser preferences preserve four distinct defaults',()=>{
  const defaults=readColourways({getItem(){throw new Error('storage denied')}});
  assert.equal(new Set(Object.values(defaults)).size,4);
  for(const raw of ['{','null','7','{"a":"constructor","b":"untrusted"}']){
    assert.deepEqual(readColourways({getItem:()=>raw}),defaults);
  }
  const chosen=readColourways({getItem:()=>' {"b":"sky","extra":"cream"}'});
  assert.deepEqual(chosen,{...defaults,b:'sky'});
});

test('recolouring is per robot, preserves scene objects, and leaves model data untouched',()=>{
  const colours=readColourways(),changed={...colours,a:'sky'};
  const a={duck:'a',part:'top_head_shell',rgba:[.85,.85,.84,1]};
  const b={...a,duck:'b'},ball={...a,duck:null},original=structuredClone([a,b,ball]);
  assert.notDeepEqual(appearanceFor(a,colours).color,appearanceFor(a,changed).color);
  assert.deepEqual(appearanceFor(b,colours),appearanceFor(b,changed));
  assert.deepEqual(appearanceFor(ball,colours),appearanceFor(ball,changed));
  assert.deepEqual(appearanceFor({...a,part:'unknown_part'},colours),appearanceFor(ball,colours));
  assert.deepEqual([a,b,ball],original);
  // Palette changes keep material properties compatible with existing instancing.
  for(const part of ['top_head_shell','lens','jaw','noenoeil','sole_left','neck']){
    const first=appearanceFor({...a,part},colours),next=appearanceFor({...a,part},changed);
    assert.equal(first.roughness,next.roughness);assert.equal(first.metalness,next.metalness);
  }
});
