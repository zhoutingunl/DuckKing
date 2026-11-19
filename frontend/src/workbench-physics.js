import {actionEventText, actionLabels, resultLabels} from './action-labels.js';
import {featureActionLabels} from './feature-action-labels.js';
import {FeatureAudio} from './feature-audio.js';
import {requestId} from './ids.js';
import {createLoadingState} from './loading-state.js';
import {createPhysicsModelLoader} from './model-loader.js';
import {sceneStateFeed} from './scene-state-feed.js';
import {stopRoomScene} from './scene-stop.js';
import {appURL} from './urls.js';

const groups = [
  {title: '动作练习场', actions: [
    'sit', 'stand', 'look_left', 'look_right', 'look_forward', 'look_down', 'roulade', 'ground_pick',
    'yawn', 'idle_on', 'idle_off',
  ]},
  {actions: ['hop', 'run', 'steps', 'try_trick']},
  {title: '单脚站稳', actions: ['lift_left', 'lift_right', 'lower']},
  {title: '自己站起来', actions: ['recover_back', 'recover_front']},
  {title: '倒立头旋连续技', actions: [
    'routine', 'backroll', 'headstand', 'spin_left', 'spin_right',
  ]},
  {title: '小鸭的心情', actions: [
    'sad', 'devastated', 'curious', 'mmh', 'yes', 'yes_fast', 'no', 'defiant', 'angry', 'mock',
    'excited', 'impatient', 'laugh',
  ]},
];
const emotions = groups.at(-1).actions;
const label = name => name === 'try_trick' ? '助跑前滚翻' : actionLabels[name] ?? featureActionLabels[name] ?? name;

async function api(path, body, signal = AbortSignal.timeout(95000)) {
  const response = await fetch(appURL(path), {
    signal, cache: 'no-store',
    ...(body && {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)}),
  });
  if (response.status === 204) return null;
  if (!body && response.status === 503 && path === 'api/scenes/state') return {type: 'not_started'};
  const data = await response.json();
  if (!response.ok) {
    const error = Error(typeof data.detail === 'string' ? data.detail : data.detail?.message ?? '场景请求未完成');
    error.code = data.detail?.code;
    throw error;
  }
  return data;
}

async function waitForAction(record) {
  const signal = AbortSignal.timeout(85000);
  while (record.status === 'running') {
    await new Promise(resolve => setTimeout(resolve, 100));
    record = await api(`api/scenes/actions/${encodeURIComponent(record.id)}`, null, signal);
  }
  if (record.status !== 'completed') throw Error(record.error ?? resultLabels[record.status]);
}

export function setupWorkbenchPhysics({voice, notify, appendLog, onState, onMode, onBusy, onCompleted}) {
  const $ = id => document.getElementById(id);
  const element = $('workbench-physics'), loading = createLoadingState($('workbench-physics-loading'));
  const sound = new FeatureAudio(), loadModel = createPhysicsModelLoader();
  let active = false, floor, viewer, feed, latest, revision, ready = false, pending, cancelLoad, stopping = false;
  let seenEvents = 0, seenResults = new Set();
  const matches = state => state?.scene === 'functional' && state.feature?.capability === 'workbench';
  const guarded = path => `${path}?expected_revision=${encodeURIComponent(revision)}`;

  function updateButtons() {
    const busy = !!pending || stopping;
    for (const button of $('flat-action-groups').querySelectorAll('button')) button.disabled = busy;
    onBusy(busy);
    window.dispatchEvent(new Event('duckking-voice-readiness'));
  }

  function update(packet) {
    if (!active || !ready) return;
    const state = packet.backend;
    if (!matches(state) || state.revision !== revision) {
      ready = false;
      revision = null;
      latest = null;
      viewer.clear();
      sound.stop();
      loading.reset('房间场景已更新，请重新选择动作。');
      onState(null, '场景已切换');
      updateButtons();
      return;
    }
    latest = state;
    viewer.update(state);
    if (!stopping) sound.update({...state.feature, capability: state.workbench_policy});
    for (const event of packet.events ?? []) {
      if (event.id <= seenEvents) continue;
      seenEvents = event.id;
      if (event.status === 'completed') onCompleted();
      appendLog(actionEventText(event), event.kind === 'result' ? '执行结果' : '动作请求', event.status === 'failed', event.text);
    }
    const feature = state.feature;
    for (const result of feature?.results ?? []) {
      if (seenResults.has(result.id)) continue;
      seenResults.add(result.id);
      if (result.status === 'completed') onCompleted();
      appendLog(`${label(result.action)} · ${resultLabels[result.status]} · ${result.message}`,
        '执行结果', result.status === 'failed');
    }
    if (seenResults.size > 120) seenResults.delete(seenResults.values().next().value);
    const action = packet.action?.name ?? (feature?.status === 'running' ? feature.action : null);
    onState(state, label(action), state.error ?? packet.error
      ?? (feature && feature.status !== 'idle' ? feature.message : null));
  }

  async function prepare(signal) {
    ready = false;
    revision = null;
    latest = null;
    viewer?.clear();
    sound.stop();
    onState(null, '正在准备场景');
    const session = loading.begin({cancel: () => void control('stop')});
    try {
      let packet = await api('api/scenes/state');
      if (!matches(packet.backend) || packet.backend.error || packet.backend.feature.recovery_required) {
        packet = await api('api/features/prepare', {capability: 'workbench', replace: true});
      }
      if (!matches(packet.backend)) throw Error('房间场景已更新，请重新选择动作。');
      const state = packet.backend;
      revision = state.revision;
      signal.throwIfAborted();
      if (!viewer) {
        const {physicsView} = await import('./physics-view.js');
        signal.throwIfAborted();
        viewer = physicsView(element);
      }
      viewer.setGround(floor);
      const model = await loadModel(appURL('api/scenes/model.dkm.gz'), revision, {
        signal, progress: session.progress,
      });
      signal.throwIfAborted();
      viewer.load(model);
      viewer.frameScene('skills');
      viewer.update(state);
      viewer.renderNow();
      seenEvents = packet.events?.at(-1)?.id ?? 0;
      seenResults = new Set(state.feature?.results?.map(result => result.id));
      ready = true;
      session.ready();
      update(packet);
    } catch (error) {
      if (signal.aborted) session.cancelled();
      else {
        session.fail(error);
        onState(null, '准备未完成', error.message);
        throw error;
      }
    }
  }

  function run(name) {
    if (pending || stopping) return;
    const needsPreparation = !ready || latest?.error || latest?.feature?.recovery_required;
    if (needsPreparation && !voice.setTarget('/scene-voice', false, {requireIdle: true})) {
      notify('请先断开当前语音，再切换功能场景');
      return;
    }
    const soundReady = emotions.includes(name)
      ? sound.enable().then(() => sound.load(name)).then(() => null, error => error)
      : null;
    active = true;
    onMode(true);
    feed ??= sceneStateFeed({
      readState: signal => api('api/scenes/state', null, signal),
      onState: update,
      onStatus: () => window.dispatchEvent(new Event('duckking-voice-readiness')),
    });
    const controller = cancelLoad = new AbortController();
    pending = (async () => {
      if (needsPreparation) await prepare(controller.signal);
      const audioError = await soundReady;
      controller.signal.throwIfAborted();
      const action = latest?.feature?.actions?.[name];
      if (action?.enabled === false) throw Error(action.reason);
      if (audioError) throw audioError;
      await api(guarded('api/features/command'), {operation: 'start', action: name, duration: 1.2, request_id: requestId()});
      await feed.refresh();
    })().catch(error => { if (!controller.signal.aborted) notify(error.message); }).finally(() => {
      pending = cancelLoad = null;
      updateButtons();
    });
    updateButtons();
  }

  async function control(name) {
    if (stopping || (name !== 'stop' && pending)) return;
    stopping = true;
    cancelLoad?.abort();
    sound.stop();
    updateButtons();
    try {
      await pending;
      if (!revision) return;
      if (name === 'stop') {
        await stopRoomScene(api, {revision, id: requestId(), signal: AbortSignal.timeout(12000)});
        appendLog('停止已确认，场景保留', '执行结果');
      } else {
        await waitForAction(await api(guarded('api/scenes/actions'), {name, request_id: requestId()}));
      }
    } catch (error) {
      notify(error.message);
    } finally {
      stopping = false;
      if (feed) void feed.refresh();
      updateButtons();
    }
  }

  $('leave-physics').addEventListener('click', async () => {
    if (pending || stopping) return;
    if (!voice.setTarget('/voice', false, {requireIdle: true})) {
      notify('请先断开当前语音，再切换功能场景');
      return;
    }
    stopping = true;
    sound.stop();
    updateButtons();
    try {
      if (revision) await api(guarded('api/scenes/close'), {});
    } catch (error) {
      if (error.code !== 'scene_changed') {
        voice.setTarget('/scene-voice', false);
        notify(error.message);
        return;
      }
    } finally {
      stopping = false;
      updateButtons();
    }
    feed?.close();
    feed = latest = revision = null;
    active = ready = false;
    viewer?.dispose();
    viewer = null;
    onMode(false);
    updateButtons();
  });

  const singleMoves = document.createElement('div');
  singleMoves.className = 'flat-single-actions action-grid';
  for (const candidate of groups) {
    let grid = singleMoves;
    if (!candidate.title) {
      if (!singleMoves.isConnected) $('flat-action-groups').append(singleMoves);
    } else {
      const fieldset = document.createElement('fieldset');
      const legend = document.createElement('legend');
      grid = document.createElement('div');
      fieldset.className = 'flat-action-group';
      grid.className = 'action-grid';
      legend.textContent = candidate.title;
      fieldset.append(legend, grid);
      $('flat-action-groups').append(fieldset);
    }
    for (const name of candidate.actions) {
      const button = document.createElement('button');
      button.type = 'button';
      button.dataset.flatAction = name;
      button.textContent = label(name);
      button.addEventListener('click', () => run(name));
      grid.append(button);
    }
  }

  for (const id of ['connect-voice', 'enable-sound']) $(id).addEventListener('click', () => {
    if (active && (latest?.feature?.actions?.[emotions[0]]?.enabled ?? false)) {
      void sound.enable().then(() => Promise.all(emotions.map(name => sound.load(name))))
        .catch(error => notify(error.message));
    }
  });
  window.addEventListener('pagehide', () => {
    cancelLoad?.abort();
    feed?.close();
    viewer?.dispose();
    void sound.close();
  }, {once: true});

  return {
    get active() { return active; },
    action(name) {
      if (name === 'stop' || name === 'reset') void control(name);
      else run(name);
    },
    voiceUnavailable() {
      return active && (!ready || pending || stopping || !feed.fresh() || latest?.error || latest?.feature?.recovery_required)
        ? '请等小鸭显示后再开始。' : '';
    },
    setGround(style) { floor = style; element.dataset.groundStyle = style; viewer?.setGround(style); },
    resetCamera() { viewer?.reset(); },
  };
}
