import {test} from 'node:test';
import assert from 'node:assert/strict';
import {clippedExample,series,observationGroups,compatibleRuns,balanceFailureReason,balanceOutcome} from '../src/balance-explain.js';

test('PPO clipping preserves the pessimistic bound for both advantage signs',()=>{
 assert.equal(clippedExample(1.5,2,.2).objective,2.4);
 assert.equal(clippedExample(.5,2,.2).objective,1);
 assert.equal(clippedExample(.5,-2,.2).objective,-1.6);
 assert.equal(clippedExample(1.5,-2,.2).objective,-3);
});
test('success chart never invents zero success at ordinary optimizer updates',()=>{
 assert.deepEqual(series([{steps:0,success_rate:0},{steps:1024,kind:'update'},{steps:2048,success_rate:.5}], 'success_rate').map(p=>[p.step,p.value]),[[0,0],[2048,.5]]);
 assert.equal(series([{steps:1,success_rate:NaN}], 'success_rate').length,0);
});
test('observation explanation covers every input exactly once',()=>{
 const indices=observationGroups.flatMap(([a,b])=>Array.from({length:b-a},(_,i)=>i+a));
 assert.deepEqual(indices,Array.from({length:25},(_,i)=>i));
});

test('an owned worker stays visible before its manifest and on startup failure',()=>{
 const current={id:'current',level:2,contract:'balance-v4-gain-bodyframe'};
 const preparing={id:'new',level:2,phase:'preparing',contract:null};
 const legacy={id:'legacy',level:2,contract:'balance-v3-gain'};
 const list={runs:[preparing,current,legacy,{...current,id:'other',level:3}],active_run:'new'};
 assert.deepEqual(compatibleRuns(list,2),[preparing,current]);
 preparing.phase='failed';assert.deepEqual(compatibleRuns(list,2),[preparing,current]);
 list.active_run=null;assert.deepEqual(compatibleRuns(list,2),[current]);
});

test('a boundary stop reports measured overshoot without inventing a full fall',()=>{
 const result={reason:'fell_or_left_disc',rim_margin:-.00437279,body_contact:false,upright:.9987,height:.1147};
 assert.equal(balanceFailureReason(result),'脚部越过盘缘 4.4 mm');
 assert.equal(balanceFailureReason({...result,rim_margin:.02,body_contact:true}),'非脚部触盘或机器人触地');
 assert.equal(balanceFailureReason({...result,rim_margin:.02,height:.06}),'身体失稳');
 assert.match(balanceFailureReason({...result,rim_margin:.02}),/连续失去脚部支撑/);
 assert.match(balanceFailureReason({reason:'criteria_not_met'}),/条件未全部达标/);
 for(const value of [null,{reason:'success'},{reason:'cancelled'}])assert.equal(balanceFailureReason(value),'');
});

test('visible outcome waits for measured contact and clears for a new run',()=>{
 const b={phase:'failed',result:{rim_margin:-.004},aftermath:{phase:'running',ground_contact:false,measurements:{body_contact:false}}};
 assert.equal(balanceOutcome(b).state,'falling');
 assert.doesNotMatch(balanceOutcome(b).detail,/落地|盘面/);
 b.aftermath.ground_contact=true;
 assert.deepEqual(balanceOutcome(b),{state:'failed',title:'挑战失败',detail:'已掉落触地'});
 b.aftermath.ground_contact=false;b.aftermath.measurements.body_contact=true;
 assert.match(balanceOutcome(b).detail,/倒在盘面/);
 b.aftermath.measurements.body_contact=false;b.aftermath.phase='finished';
 assert.equal(balanceOutcome(b).detail,'脚部越过盘缘');
 b.aftermath.reason='user_stop';assert.match(balanceOutcome(b).detail,/已停止/);
 assert.equal(balanceOutcome({...b,error:'physics clock reset'}).title,'运行异常');
 for(const phase of ['idle','running','stopping'])assert.equal(balanceOutcome({phase}),null);
 assert.equal(balanceOutcome({phase:'completed'}).title,'挑战成功');
 assert.equal(balanceOutcome({phase:'cancelled'}).title,'已停止');
});
