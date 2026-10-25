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
  const all=list(dev),journey=list(dev,['--grep','@journey']),checks=list(dev,['--grep-invert','@journey']);
  assert.ok(journey.length>0&&checks.length>0);
  assert.equal(new Set([...journey,...checks]).size,journey.length+checks.length);
  assert.deepEqual([...journey,...checks].sort(),all.sort());
  console.log(`${dev==='1'?'development':'production'}: ${all.length} tests = ${journey.length} journey + ${checks.length} checks; no omissions or duplicates`);
}
