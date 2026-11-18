import {actionEventText, actionLabels, resultLabels} from './action-labels.js';
import {createChorus} from './chorus.js';
import {featureActionLabels} from './feature-action-labels.js';
import {FeatureAudio} from './feature-audio.js';
import {requestId} from './ids.js';
import {createLoadingState} from './loading-state.js';
import {createPhysicsModelLoader} from './model-loader.js';
import {sceneStateFeed} from './scene-state-feed.js';
import {stopRoomScene} from './scene-stop.js';
import {appURL} from './urls.js';

const groups = [
  {scene: 'skills', title: '动作练习场', actions: [
    'sit', 'stand', 'look_left', 'look_right', 'look_forward', 'look_down', 'roulade', 'ground_pick',
    'yawn', 'idle_on', 'idle_off',
  ]},
  {feature: 'hop', actions: ['hop']},
  {feature: 'running', actions: ['run']},
  {feature: 'footsteps', actions: ['steps']},
  {feature: 'runup_roll', actions: ['try_trick']},
  {feature: 'flamingo', title: '单脚站稳', actions: ['lift_left', 'lift_right', 'lower']},
  {feature: 'standup', title: '自己站起来', actions: ['recover_back', 'recover_front']},
  {feature: 'acrobatics', title: '倒立头旋连续技', actions: [
    'routine', 'backroll', 'headstand', 'spin_left', 'spin_right',
  ]},
  {feature: 'emotions', title: '小鸭的心情', actions: [
    'sad', 'devastated', 'curious', 'mmh', 'yes', 'yes_fast', 'no', 'defiant', 'angry', 'mock',
    'excited', 'impatient', 'laugh',
  ]},
  {scene: 'duo', title: '双鸭互动', actions: ['duo_walk', 'collide', 'find_companion', 'chorus']},
  {scene: 'stage', title: '四鸭舞台', actions: ['stage_gather', 'stage_roll', 'stage_dance', 'stage_poke']},
];
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
  let group, floor, viewer, feed, latest, revision, ready = false, pending, cancelLoad, stopping = false, chorus;
  let seenEvents = 0, seenResults = new Set();
  const matches = (candidate, state) => state && (candidate.feature
    ? state.scene === 'functional' && state.feature?.capability === candidate.feature
    : state.scene === candidate.scene);
  const guarded = path => `${path}?expected_revision=${encodeURIComponent(revision)}`;
  function stopSound() { sound.stop(); chorus?.stop(); }
  function enableChorus() {
    chorus ??= createChorus(text => appendLog(text, '本地演示'));
    return chorus.enable();
  }

  function updateButtons() {
    const busy = !!pending || stopping;
    for (const button of $('flat-action-groups').querySelectorAll('button')) button.disabled = busy;
    onBusy(busy);
    window.dispatchEvent(new Event('duckking-voice-readiness'));
  }

  function update(packet) {
    if (!group || !ready) return;
    const state = packet.backend;
    if (!matches(group, state) || state.revision !== revision) {
      ready = false;
      revision = null;
      latest = null;
      viewer.clear();
      stopSound();
      loading.reset('房间场景已更新，请重新选择动作。');
      onState(null, '场景已切换');
      updateButtons();
      return;
    }
    latest = state;
    viewer.update(state);
    if (!stopping) {
      sound.update(state.feature);
      chorus?.update(state.chorus);
    }
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

  async function prepare(candidate, signal) {
    ready = false;
    revision = null;
    latest = null;
    viewer?.clear();
    stopSound();
    onState(null, '正在准备场景');
    const session = loading.begin({cancel: () => void control('stop')});
    try {
      let packet = await api('api/scenes/state');
      if (!matches(candidate, packet.backend) || packet.backend.error) {
        if (candidate.feature) {
          packet = await api('api/features/prepare', {capability: candidate.feature, replace: true});
        } else {
          await waitForAction(await api('api/scenes/start', {
            name: `scene_${candidate.scene}`, request_id: requestId(),
          }));
          packet = await api('api/scenes/state');
        }
      }
      if (!matches(candidate, packet.backend)) throw Error('房间场景已更新，请重新选择动作。');
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
      viewer.frameScene(state.view_scene ?? state.scene);
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

  function run(candidate, name) {
    if (pending || stopping) return;
    const cloudOnly = !!candidate.feature || candidate.scene === 'stage';
    if ((candidate !== group || !ready || latest?.error) && !voice.setTarget('/scene-voice', cloudOnly, {requireIdle: true})) {
      notify('请先断开当前语音，再切换功能场景');
      return;
    }
    const soundReady = (candidate.feature === 'emotions' ? sound.enable().then(() => sound.load(name))
      : name === 'chorus' ? enableChorus() : null)?.then(() => null, error => error);
    group = candidate;
    onMode(true);
    feed ??= sceneStateFeed({
      readState: signal => api('api/scenes/state', null, signal),
      onState: update,
      onStatus: () => window.dispatchEvent(new Event('duckking-voice-readiness')),
    });
    const controller = cancelLoad = new AbortController();
    pending = (async () => {
      if (!ready || !matches(candidate, latest) || latest.error) await prepare(candidate, controller.signal);
      const audioError = await soundReady;
      controller.signal.throwIfAborted();
      if (audioError) throw audioError;
      const action = latest?.feature?.actions?.[name];
      if (action?.enabled === false) throw Error(action.reason);
      const body = {request_id: requestId()};
      if (candidate.scene === 'stage') {
        if (name === 'stage_poke') body.member = 'a';
        else body.members = ['a', 'b', 'c', 'd'];
      }
      await (candidate.feature
        ? api(guarded('api/features/command'), {...body, operation: 'start', action: name})
        : api(guarded('api/scenes/actions'), {...body, name}));
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
    stopSound();
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
    stopSound();
    updateButtons();
    try {
      if (revision) await api(guarded('api/scenes/close'), {});
    } catch (error) {
      if (error.code !== 'scene_changed') {
        voice.setTarget('/scene-voice', !!group.feature || group.scene === 'stage');
        notify(error.message);
        return;
      }
    } finally {
      stopping = false;
      updateButtons();
    }
    feed?.close();
    feed = latest = group = revision = null;
    ready = false;
    viewer?.dispose();
    viewer = null;
    onMode(false);
    updateButtons();
  });

  const singleMoves = document.createElement('div');
  singleMoves.className = 'flat-single-actions action-grid';
  for (const candidate of groups) {
    let grid = singleMoves;
    if (candidate.actions.length === 1) {
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
      button.addEventListener('click', () => run(candidate, name));
      grid.append(button);
    }
  }

  for (const id of ['connect-voice', 'enable-sound']) $(id).addEventListener('click', () => {
    if (group?.scene === 'duo') void enableChorus().catch(error => notify(error.message));
    if (group?.feature === 'emotions') {
      const actions = group.actions;
      void sound.enable().then(() => Promise.all(actions.map(name => sound.load(name))))
        .catch(error => notify(error.message));
    }
  });
  window.addEventListener('pagehide', () => {
    cancelLoad?.abort();
    feed?.close();
    viewer?.dispose();
    chorus?.dispose();
    void sound.close();
  }, {once: true});

  return {
    get active() { return !!group; },
    action(name) {
      if (name === 'stop' || name === 'reset') void control(name);
      else run(groups[0], name);
    },
    voiceUnavailable() {
      return group && (!ready || pending || stopping || !feed.fresh() || latest?.error)
        ? '请等小鸭显示后再开始。' : '';
    },
    setGround(style) { floor = style; element.dataset.groundStyle = style; viewer?.setGround(style); },
    resetCamera() { viewer?.reset(); },
  };
}
