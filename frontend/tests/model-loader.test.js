import {test} from 'node:test';
import assert from 'node:assert/strict';
import {unpackVisualModel} from '../src/model-loader.js';

function packet(bytes=2,change=()=>{}){
  const model={source:'official_microduck_visuals',physics:false,bodies:[],geoms:[],meshes:{0:{
    vertices:{offset:0,count:9,bytes:4},faces:{offset:36,count:3,bytes}}}};
  change(model);
  const json=new TextEncoder().encode(JSON.stringify(model)),start=8+Math.ceil(json.length/4)*4;
  const buffer=new ArrayBuffer(start+36+3*bytes);
  new Uint8Array(buffer).set(new TextEncoder().encode('DKM1'));
  new DataView(buffer).setUint32(4,json.length,true);new Uint8Array(buffer,8,json.length).set(json);
  new Float32Array(buffer,start,9).set([.125,0,0,1,0,0,0,1,0]);
  new (bytes===2?Uint16Array:Uint32Array)(buffer,start+36,3).set([0,1,bytes===4?65536:2]);
  return buffer;
}

test('DKM1 preserves float32 and both index widths without per-mesh buffer copies',()=>{
  for(const bytes of [2,4]){
    const buffer=packet(bytes),model=unpackVisualModel(buffer),mesh=model.meshes[0];
    assert.deepEqual([...mesh.positions],[.125,0,0,1,0,0,0,1,0]);
    assert.deepEqual([...mesh.indices],[0,1,bytes===4?65536:2]);
    assert.equal(mesh.indices.BYTES_PER_ELEMENT,bytes);
    assert.equal(mesh.positions.buffer,buffer);assert.equal(mesh.indices.buffer,buffer);
    assert.equal(model.physics,false);
  }
});

test('DKM1 rejects unsupported framing and invalid geometry views',()=>{
  for(const buffer of [new ArrayBuffer(0),packet().slice(0,20),packet().slice(0,-1)])assert.throws(()=>unpackVisualModel(buffer));
  const badMagic=packet();new Uint8Array(badMagic)[3]=50;assert.throws(()=>unpackVisualModel(badMagic));
  const hugeHeader=packet();new DataView(hugeHeader).setUint32(4,2**30,true);assert.throws(()=>unpackVisualModel(hugeHeader));
  for(const delta of [{offset:-4},{offset:1},{offset:1e9},{count:0},{count:1.5},{count:8},{count:1e12},{bytes:3}]){
    assert.throws(()=>unpackVisualModel(packet(2,m=>Object.assign(m.meshes[0].vertices,delta))));
  }
  assert.throws(()=>unpackVisualModel(packet(2,m=>{m.meshes[0].faces.bytes=1})));
  for(const patch of [{source:'unverified'},{physics:true},{bodies:null},{meshes:{}},{geoms:null}]){
    assert.throws(()=>unpackVisualModel(packet(2,m=>Object.assign(m,patch))));
  }
});
