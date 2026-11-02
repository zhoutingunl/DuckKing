import {test} from 'node:test';
import assert from 'node:assert/strict';
import {outcome,humanStatus,humanMotion,trainingMatches} from '../src/seesaw-explain.js';

test('issued direction never masks measured drift or calls zero speed stationary',()=>{
 const state={mode:'duel',human_command:{direction:'forward',actual_motion:'backward',actual_speed_m_s:-.08}};
 assert.match(humanMotion(state),/前进指令；实际向后 8.0 cm\/s/);
 state.human_command.direction='hold';
 assert.match(humanMotion(state),/零速指令 · 未辅助；实际向后/);
 state.human_command.assist_enabled=true;
 assert.match(humanMotion(state),/辅助站定 · 小步纠偏；实际向后/);
 state.human_command.actual_motion='paused';
 assert.match(humanMotion(state),/物理已暂停/);
});

test('human PK preserves terminal results and reports each side independently',()=>{
 const state={mode:'duel',execution:'running',comparison:{execution:'paused',phase:'failed',measurement:{edge_margin_m:-.01}}};
 assert.match(humanStatus(state),/左鸭失败 · 脚部越过板边缘/);
 assert.match(humanStatus(state),/右侧继续自主控制/);
 assert.doesNotMatch(humanStatus(state),/选择.*开始|站定/);
 assert.match(humanStatus({...state,comparison:{execution:'paused',phase:'success'}}),/左鸭成功/);
 assert.match(humanStatus({...state,execution:'paused',comparison:{execution:'paused',phase:'cancelled'}}),/左鸭已暂停 · 右侧本轮已结束/);
 assert.match(humanStatus({...state,execution:'paused',comparison:{execution:'running'},human_command:{direction:'backward',remaining_seconds:1}}),/后退，剩余 1.0 秒 · 右侧本轮已结束/);
 assert.match(humanStatus({mode:'compare'}),/选择.*开始/);
});

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
