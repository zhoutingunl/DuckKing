import test from 'node:test';
import assert from 'node:assert/strict';
import {actionEventText} from '../src/action-labels.js';
import {voiceRouteText} from '../src/voice-route.js';
import {loadingError} from '../src/loading-state.js';

test('action text preserves failures, cancellation and unknown identifiers without partial replacement',()=>{
  assert.equal(actionEventText({text:'tilt_head · completed'}),'歪头 · 已完成');
  assert.equal(actionEventText({text:'look_down · failed'}),'低头看 · 未完成');
  assert.equal(actionEventText({text:'walk · cancelled'}),'前进 · 已取消');
  assert.equal(actionEventText({text:'moonwalk · failed'}),'moonwalk · 未完成');
  assert.equal(actionEventText({kind:'action',text:'开始动作 · scene_carry'}),'正在准备场景 · 嘴部搬运');
  assert.equal(actionEventText({kind:'result',text:'scene_carry · failed',status:'failed'}),'场景准备未完成 · 嘴部搬运');
});
test('routing terminal copy does not claim action or audible playback success',()=>{
  const route={mode:'local_first',route:'cloud_fallback'};
  assert.equal(voiceRouteText({...route,state:'ready'}),'本轮由灵矽处理。');
  assert.doesNotMatch(voiceRouteText({...route,state:'disconnected'}),/正在|本轮由灵矽/);
  assert.match(voiceRouteText({...route,state:'error'}),/未完成/);
  assert.doesNotMatch(voiceRouteText({...route,state:'listening'}),/转交/);
});
test('download errors distinguish network, timeout and explicit validation failure in Chinese',()=>{
  assert.match(loadingError(new TypeError('Failed to fetch')),/下载中断/);
  assert.match(loadingError(new DOMException('timeout','TimeoutError')),/等待超时/);
  assert.equal(loadingError(new Error('模型数据超过大小上限')),'模型数据超过大小上限');
});
