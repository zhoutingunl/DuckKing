import {test} from 'node:test';
import assert from 'node:assert/strict';
import {outcome} from '../src/seesaw-explain.js';

test('failed balance is distinguished from falling, cancellation and unscored exploration',()=>{
 assert.match(outcome({phase:'failed',result:{reason:'not_balanced',balance_fraction:.3}}).badge,/不足 70%/);
 const near=outcome({phase:'failed',result:{reason:'not_balanced',balance_fraction:.99,hold_seconds:0}});
 assert.match(near.badge,/最后 0.5 秒/);assert.match(near.text,/99.0%/);
 assert.match(outcome({phase:'failed',measurement:{edge_margin_m:-.01}}).badge,/越过板边缘/);
 assert.match(outcome({phase:'failed',measurement:{ground_contact:true}}).badge,/触地/);
 assert.match(outcome({phase:'cancelled'}).text,/不代表板面已经自然停稳/);
 assert.equal(outcome({phase:'explored'}).badge,'');
 assert.match(outcome({phase:'explored',result:{reason:'exploration_limit'}}).text,/不计成绩/);
 assert.match(outcome({phase:'running',result:{success:false,hold_seconds:1}}).text,/进行中/);
 assert.match(outcome({phase:'success'}).badge,/成功/);
});
