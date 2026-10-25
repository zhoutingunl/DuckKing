import './style.css';
import './statistics.css';
import { appURL } from './urls.js';

import { setupRoom } from './room.js';
await setupRoom({claim:false});

const $ = id => document.getElementById(id);
const tools = {duck_walk_short:'前进',duck_turn_left:'左转',duck_turn_right:'右转',duck_nod:'点头',duck_stop:'停止',duck_flash_step:'闪身步',duck_bear_shake:'狗熊哆嗦毛'};
Object.assign(tools,{duck_set_scene:'切换场景',duck_kick:'踢球',duck_find_companion:'发现同伴',duck_duo_walk:'双鸭一起走',duck_collide:'相向碰面',duck_chorus:'同步合唱'});
const statuses = {listening:'录音中',waiting:'等待回复',completed:'已结束',timeout:'超时',interrupted:'已中断',error:'异常'};
const actionStatuses = {running:'进行中',completed:'完成',cancelled:'取消',failed:'失败'};
const routeNames={local:'本地执行',cloud:'灵矽云端',cloud_fallback:'转交灵矽',pending:'等待识别',no_speech:'未识别到语音'};
const routeReasons={matched:'完整匹配',unmatched:'整句未匹配',unsupported_context:'场景不支持',plan_limit:'超出动作范围',empty_or_long:'文本不足或过长',asr_timeout:'识别超时',asr_unavailable:'识别不可用',no_speech:'无清晰语音'};
const backendName = kind => ({robotd:'官方 robotd 仿真',mujoco:'MuJoCo 物理实验室',preview:'动画预览'})[kind] ?? kind;
const duration = ms => ms == null ? '—' : Math.abs(ms) < 1000 ? `${ms} ms` : `${(ms / 1000).toFixed(2)} s`;
const rate = (value,total) => total ? `${(100 * value / total).toFixed(1)}%` : '—';
const element = (tag,text,className) => {
  const node = document.createElement(tag);
  if (text != null) node.textContent = text;
  if (className) node.className = className;
  return node;
};
let data, selected = null, loading = false;

function showRound() {
  const row = data.rounds.find(row => row.turn === selected) ?? data.rounds[0];
  const timeline = $('round-timeline');
  timeline.replaceChildren();
  $('timeline-heading').textContent = selected && row ? `第 ${row.turn} 轮时间线` : '最近一轮';
  if (!row) {
    $('round-label').textContent = '等待样本';
    $('round-text').textContent = '先回到工作台，连接灵矽并说一句话。';
    for (const label of ['结束录音','识别返回','动作受理','首段语音']) {
      const step = element('div',null,'timeline-step');
      step.dataset.phase = 'missing';
      step.append(element('span',label),element('strong','—'));
      timeline.append(step);
    }
    return;
  }
  $('round-label').textContent = `第 ${row.turn} 轮 · ${routeNames[row.route??'cloud']} · ${backendName(row.backend)} · ${statuses[row.status]}`;
  $('round-text').textContent = row.text || '尚未收到非空识别文本';
  const stop = row.timings.listen_stop;
  const points = [
    {label:'结束录音',at:stop,phase:'stop'},
    {label:'识别返回',at:row.timings.stt,phase:'stt'},
    ...row.actions.map(a => ({label:`${tools[a.tool] ?? a.tool}受理`,at:a.at_ms,phase:'action',note:actionStatuses[a.result]})),
    {label:'首段语音',at:row.timings.first_audio,phase:'audio'},
    {label:'回复结束',at:row.timings.reply_end,phase:'audio'},
    {label:'本地执行结束',at:row.timings.local_end,phase:'action'},
  ].sort((a,b) => (a.at ?? Infinity) - (b.at ?? Infinity));
  for (const point of points) {
    const step = element('div',null,'timeline-step');
    step.dataset.phase = point.at == null ? 'missing' : point.phase;
    step.append(element('span',point.label),element('strong',duration(point.at == null || stop == null ? null : point.at - stop)));
    if (point.note) step.append(element('small',point.note));
    timeline.append(step);
  }
}

function render() {
  const c = data.counts;
  $('stats-scope').textContent = `本次服务启动于 ${new Date(data.started_at).toLocaleString('zh-CN')}；当前筛选 ${c.rounds} 轮，最多保留最近 ${data.capacity} 轮`;
  $('recognition-rate').textContent = rate(c.recognized,c.closed);
  $('recognition-count').textContent = `${c.recognized} / ${c.closed} 个已结束提交轮次`;
  $('reply-rate').textContent = rate(c.replied,c.cloud_closed??c.closed);
  $('reply-count').textContent = `${c.replied} / ${c.cloud_closed??c.closed} 个云端已结束轮次`;
  const routing=data.routing??{local:0,fallback:0,decided:0,reasons:{}};
  $('local-hit-rate').textContent=rate(routing.local,routing.decided);
  $('local-hit-count').textContent=`${routing.local} / ${routing.decided} 个已判定本地优先轮次`;
  $('fallback-count').textContent=routing.fallback;
  $('fallback-reasons').textContent=Object.entries(routing.reasons).filter(([k])=>k!=='matched').map(([k,n])=>`${routeReasons[k]??k} ${n}`).join(' · ')||'尚无转交或未识别记录';
  $('local-asr-time').textContent=duration(data.latencies.local_asr?.p50_ms);
  $('route-latency').replaceChildren();
  for(const [key,values] of Object.entries(routing.action_latency??{})){
    const tr=element('tr');for(const text of [routeNames[key],duration(values.p50_ms),duration(values.p95_ms),values.count])tr.append(element('td',text));$('route-latency').append(tr);
  }
  $('action-rate').textContent = rate(c.completed_actions,c.finished_actions);
  $('action-summary').textContent = `${c.completed_actions} / ${c.finished_actions} 个已结束动作`;
  $('timeout-count').textContent = c.timeouts;
  $('round-summary').textContent = `进行中 ${c.pending} · 中断 ${c.interrupted} · 异常 ${c.errors}`;
  $('latency-rows').replaceChildren();
  for (const [key,label] of [['stt','结束录音 → 识别返回'],['action_start','结束录音 → 首个动作受理'],['first_audio','结束录音 → 首段语音'],['reply_end','结束录音 → 回复结束'],['action_duration','动作受理 → 执行结束']]) {
    const values = data.latencies[key], tr = element('tr');
    for (const text of [label,duration(values.p50_ms),duration(values.p95_ms),values.count]) tr.append(element('td',text));
    $('latency-rows').append(tr);
  }
  const service = data.service;
  $('reconnect-count').textContent = `${service.reconnect_successes ?? 0} / ${service.reconnect_attempts ?? 0}`;
  $('connection-errors').textContent = service.connection_error ?? 0;
  $('reset-count').textContent = service.reset ?? 0;
  $('recovery-latency').textContent = duration(data.latencies.recovery.p50_ms);
  $('backend-note').textContent = data.current_backend === 'robotd'
    ? '当前服务使用官方 robotd 后端。动作完成反映控制流程状态，未测量物理反馈延迟。'
    : '当前服务使用原创动画预览，不进行物理仿真。灵矽语音与动作后端分别统计。';
  if($('backend-filter').value==='mujoco')$('backend-note').textContent='物理实验室使用 MuJoCo CPU 和官方 ONNX 策略，未经过 robotd。踢球和接触结果在场景页显示；此处统计语音链路的时间。';
  $('round-rows').replaceChildren();
  for (const row of data.rounds) {
    const tr = element('tr');
    if (row.turn === selected) tr.className = 'selected';
    const identity = element('td');
    const button = element('button',`第 ${row.turn} 轮`,'round-select');
    button.setAttribute('aria-label',`查看第 ${row.turn} 轮时间线`);
    button.setAttribute('aria-pressed',String(row.turn === selected));
    button.addEventListener('click',() => {selected = row.turn; showRound(); markSelected();});
    tr.dataset.turn = row.turn;
    identity.append(button,element('span',new Date(row.time).toLocaleTimeString('zh-CN'),'round-time'),element('span',`${backendName(row.backend)} · ${routeNames[row.route??'cloud']}`,'round-backend'));
    const actions = element('td');
    for (const action of row.actions) {
      const good = ['running','completed'].includes(action.result);
      actions.append(element('span',`${tools[action.tool] ?? action.tool} · ${actionStatuses[action.result]}` ,`action-token${good ? '' : ' error'}`));
    }
    if (!row.actions.length) actions.textContent = '未受理动作';
    const result = element('td',statuses[row.status],`round-result${['timeout','error','interrupted'].includes(row.status) ? ' error' : ''}`);
    tr.append(identity,element('td',row.text || '未返回识别文本'),actions,result);
    $('round-rows').append(tr);
  }
  $('stats-empty').hidden = Boolean(data.rounds.length);
  showRound();
}

function markSelected() {
  for (const tr of $('round-rows').children) {
    const active = Number(tr.dataset.turn) === selected;
    tr.classList.toggle('selected',active);
    tr.querySelector('button').setAttribute('aria-pressed',String(active));
  }
}

async function refresh() {
  if (loading) return;
  loading = true;
  const backend = $('backend-filter').value;
  $('refresh-stats').disabled = true;
  try {
    const response = await fetch(appURL(`/api/voice/statistics?backend=${backend}`),{cache:'no-store',signal:AbortSignal.timeout(8000)});
    if (!response.ok) throw new Error('statistics unavailable');
    const next = await response.json();
    if ($('backend-filter').value !== backend) return;
    const focusedRound = document.activeElement.closest?.('[data-turn]')?.dataset.turn;
    if (data && data.started_at !== next.started_at) selected = null;
    data = next;
    if (!data.rounds.some(r => r.turn === selected)) selected = null;
    render();
    if (focusedRound) document.querySelector(`[data-turn="${focusedRound}"] button`)?.focus({preventScroll:true});
    $('stats-updated').textContent = `${new Date().toLocaleTimeString('zh-CN')} 已更新 · 每 5 秒刷新`;
    $('stats-error').hidden = data.storage_ok;
    $('stats-error').textContent = '统计可用，但日志写入失败；请检查本地数据目录的权限或磁盘空间。';
  } catch {
    if ($('backend-filter').value !== backend) return;
    $('stats-error').hidden = false;
    $('stats-error').textContent = '统计读取失败，请检查本地服务后重试。已有数值未更新。';
    $('stats-updated').textContent = '更新失败';
  } finally {
    loading = false;
    $('refresh-stats').disabled = false;
    if ($('backend-filter').value !== backend) refresh();
  }
}

$('refresh-stats').addEventListener('click',refresh);
$('backend-filter').addEventListener('change',() => {selected = null; refresh();});
const timer = setInterval(() => {if (!document.hidden) refresh();},5000);
window.addEventListener('pagehide',() => clearInterval(timer),{once:true});
refresh();
