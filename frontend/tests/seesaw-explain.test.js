import {test} from 'node:test';
import assert from 'node:assert/strict';
import {outcome,trainingMatches} from '../src/seesaw-explain.js';

test('failed balance is distinguished from falling, cancellation and unscored exploration',()=>{
 assert.match(outcome({phase:'failed',result:{reason:'not_docked',weight_position_m:.2}}).badge,/未进入红色区/);
 assert.match(outcome({phase:'failed',result:{reason:'not_docked',weight_position_m:0,weight_velocity_m_s:.1}}).badge,/未刹住/);
 const near=outcome({phase:'failed',result:{reason:'not_docked',weight_position_m:0,weight_velocity_m_s:0,hold_seconds:.8}});
 assert.match(near.badge,/未连续停稳 1 秒/);assert.match(near.text,/0.8 s/);
 assert.match(outcome({phase:'failed',measurement:{edge_margin_m:-.01}}).badge,/越过板边缘/);
 assert.match(outcome({phase:'failed',measurement:{ground_contact:true}}).badge,/触地/);
 assert.match(outcome({phase:'cancelled'}).text,/不代表板面已经自然停稳/);
 assert.equal(outcome({phase:'explored'}).badge,'');
 assert.match(outcome({phase:'explored',result:{reason:'exploration_limit'}}).text,/不计成绩/);
 assert.match(outcome({phase:'running',result:{success:false,hold_seconds:1}}).text,/进行中/);
 assert.match(outcome({phase:'success'}).badge,/成功/);
});

test('historical driven scores and mismatched model hashes cannot appear as current docking results',()=>{
 const report={manifest:{contract:'seesaw-v4-passive-docking',model_sha256:'a'.repeat(64)}};
 assert.equal(trainingMatches(report),true);
 assert.equal(trainingMatches(report,'seesaw-'+'a'.repeat(24)),true);
 assert.equal(trainingMatches(report,'seesaw-'+'a'.repeat(24)+'-red1'),true);
 assert.equal(trainingMatches(report,'seesaw-'+'a'.repeat(24)+'-unknown'),false);
 assert.equal(trainingMatches(report,'seesaw-'+'b'.repeat(24)),false);
 assert.equal(trainingMatches({manifest:{...report.manifest,contract:'seesaw-v3-counterweight'}}),false);
 assert.equal(trainingMatches(null),false);
});
