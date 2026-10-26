// A listing-only check: splitting jobs must not drop or duplicate a browser test.
import {execFileSync} from 'node:child_process';
import assert from 'node:assert/strict';

function collect(suites,found=[]){
  for(const suite of suites){
    for(const spec of suite.specs??[])found.push(spec.id);
    collect(suite.suites??[],found);
  }
  return found;
}
function list(dev,args=[]){
  const report=JSON.parse(execFileSync(process.execPath,
    ['node_modules/@playwright/test/cli.js','test','--list','--reporter=json',...args],
    {encoding:'utf8',env:{...process.env,DUCKKING_TEST_DEV:dev},maxBuffer:8*1024*1024}));
  assert.deepEqual(report.errors??[],[]);
  return collect(report.suites);
}
for(const dev of ['0','1']){
  const all=list(dev),groups={journey:['--grep','@journey'],stage:['--grep','@stage'],checks:['--grep-invert','@journey|@stage']};
  const collected=[];
  for(const [name,args] of Object.entries(groups)){
    const expected=list(dev,args),shards=[1,2].flatMap(shard=>list(dev,[...args,`--shard=${shard}/2`]));
    assert.ok(expected.length>0);
    assert.equal(new Set(shards).size,shards.length,`${name}: duplicate shard test`);
    assert.deepEqual(shards.sort(),expected.sort(),`${name}: omitted shard test`);
    collected.push(...shards);
  }
  assert.equal(new Set(collected).size,collected.length);
  assert.deepEqual(collected.sort(),all.sort());
  console.log(`${dev==='1'?'development':'production'}: ${all.length} tests across journey / stage / checks, each in two shards; no omissions or duplicates`);
}
