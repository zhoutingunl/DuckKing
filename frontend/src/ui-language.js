// Region-aware language for every page and its real-time interface states.
// The backend decides the default from a local IP database; the visitor can
// always override with ?lang=zh|en|fr or the nav "语言" menu (stored locally).
// Human/cloud transcripts and diagnostic data retain their original content.

import {appURL} from './urls.js';
import {messages, patterns} from './ui-messages.js';

const STORAGE_KEY = 'duckking-ui-language';
const LANGUAGES = new Set(['zh', 'en', 'fr']);
const VOICE_STORAGE_KEY = 'duckking-voice-language';
const VOICE_LANGUAGES = new Set([...LANGUAGES, 'ja']);

let prefsPromise = null, readyPromise = null, observer = null;
let activeLanguage = 'zh';
let activeVoiceLanguage = 'zh';
export const currentLanguage = () => activeLanguage;
export const currentVoiceLanguage = () => activeVoiceLanguage;

export function pickVoiceLanguage({urlVoiceLang,urlLang,savedVoiceLang,interfaceLanguage='zh'}={}) {
  if (VOICE_LANGUAGES.has(urlVoiceLang)) return urlVoiceLang;
  if (LANGUAGES.has(urlLang)) return urlLang;
  if (VOICE_LANGUAGES.has(savedVoiceLang)) return savedVoiceLang;
  return interfaceLanguage;
}

function storeVoiceLanguage(language) {
  try {localStorage.setItem(VOICE_STORAGE_KEY,language)} catch {}
}

export function setVoiceLanguage(language) {
  if (!VOICE_LANGUAGES.has(language)) return;
  const previousVoiceLanguage=activeVoiceLanguage;
  activeVoiceLanguage=language;storeVoiceLanguage(language);
  document.documentElement.dataset.voiceLanguage=language;
  const url=new URL(location.href);
  if(language===activeLanguage)url.searchParams.delete('voice_lang');
  else url.searchParams.set('voice_lang',language);
  history.replaceState(history.state,'',url);
  if(previousVoiceLanguage!==language)window.dispatchEvent(new CustomEvent('duckking-language-changed',{
    detail:{language:activeLanguage,previous:activeLanguage,voiceLanguage:language,previousVoiceLanguage},
  }));
}

export function pickLanguage({urlLang, savedLang, serverLang} = {}) {
  for (const candidate of [urlLang, savedLang, serverLang]) {
    if (LANGUAGES.has(candidate)) return candidate;
  }
  return 'zh';
}

export function uiPreferences() {
  if (!prefsPromise) {
    prefsPromise = fetch(appURL('api/ui-preferences'), {cache: 'no-store', signal: AbortSignal.timeout(3000)})
      .then(response => (response.ok ? response.json() : null))
      .catch(() => null);
  }
  return prefsPromise;
}

export function savedLanguage() {
  try {return localStorage.getItem(STORAGE_KEY)} catch {return null}
}

export function storeLanguage(language) {
  try {localStorage.setItem(STORAGE_KEY, language)} catch {}
}

// Shared UI copy, including dynamic status/error labels. Authored transcripts
// stay in their original language and are never presented as translated cloud output.
export const TRANSLATIONS = new Map(Object.entries({
  'DuckKing · 语音与动作工作台': {
    en: 'DuckKing · Voice & Motion Workbench',
    fr: 'DuckKing · Atelier voix et mouvements',
  },
  '让一句话，': {en: 'Say one sentence, ', fr: 'Dites une phrase, '},
  '变成一个动作。': {en: 'make it an action.', fr: 'elle devient une action.'},
  '遇见你的虚拟小鸭。先打个招呼，再一起迈出第一步。': {
    en: 'Meet your virtual duck. Say hello, then take the first step together.',
    fr: "Rencontre ton petit canard virtuel. Dis d'abord bonjour, puis ensemble faites le premier pas.",
  },
  '正在连接工作台': {en: 'Connecting to the workbench…', fr: "Connexion à l'atelier…"},
  '语音 × PPO · 新实验': {en: 'Voice × PPO · New experiment', fr: 'Voix × PPO · Nouvelle expérience'},
  '训练新动作': {en: 'Train a new motion', fr: 'Entraîner un nouveau mouvement'},
  '转盘站稳，跷跷板停靠。用语音挑战 PPO，看小鸭怎样学会新技能。': {
    en: 'Balance on the wheel, dock on the seesaw. Challenge PPO with your voice and watch the duck learn.',
    fr: 'Tenir sur la roulette, se poser sur la balançoire. Défie le PPO avec la voix et regarde le canard apprendre.',
  },
  '选择训练场景 ': {en: 'Pick a training scene ', fr: "Choisir un scénario d'entraînement "},
  '动画预览': {en: 'Animation preview', fr: 'Aperçu animé'},
  '■ 停止': {en: '■ Stop', fr: '■ Stop'},
  '停止当前动作': {en: 'Stop the current action', fr: "Arrêter l'action en cours"},
  '↺ 复位视角': {en: '↺ Reset view', fr: '↺ Réinitialiser la vue'},
  '当前浏览器无法启动 WebGL。动作控制和状态面板仍然可用。': {
    en: 'WebGL cannot start in this browser. Controls and the status panel still work.',
    fr: "WebGL ne démarre pas dans ce navigateur. Les commandes et le panneau d'état restent utilisables.",
  },
  '正在等待你的指令': {en: 'Waiting for your command', fr: 'En attente de ton instruction'},
  '拖动旋转 · 滚轮缩放': {en: 'Drag to rotate · scroll to zoom', fr: 'Glisser pour tourner · molette pour zoomer'},
  '当前动作': {en: 'Current action', fr: 'Action en cours'},
  '待机': {en: 'Idle', fr: 'Repos'},
  '前进指令': {en: 'Forward command', fr: "Consigne d'avance"},
  '已执行动作': {en: 'Actions executed', fr: 'Actions exécutées'},
  '数据来源': {en: 'Data source', fr: 'Source des données'},
  '本地预览': {en: 'Local preview', fr: 'Aperçu local'},
  '和小鸭聊聊': {en: 'Talk to the duck', fr: 'Parle au canard'},
  '未连接灵矽': {en: 'Linx not connected', fr: 'Linx non connecté'},
  '连接灵矽后，按住说话，松开等待回答。': {
    en: 'After connecting to Linx, hold to talk, release and wait for the answer.',
    fr: 'Après connexion à Linx : maintiens pour parler, relâche et attends la réponse.',
  },
  '启用语音后，按住说话；常用动作本地执行，未匹配时交给灵矽。': {
    en: 'Voice enabled: hold to talk; common actions run locally, unmatched phrases go to Linx.',
    fr: "Voix activée : maintiens pour parler ; les actions courantes s'exécutent en local, le reste passe à Linx.",
  },
  '连接灵矽': {en: 'Connect Linx', fr: 'Connecter Linx'},
  '接入模块准备中': {en: 'Preparing the audio module', fr: 'Préparation du module audio'},
  '按住说话': {en: 'Hold to talk', fr: 'Maintenir pour parler'},
  '打断并说话': {en: 'Interrupt and talk', fr: 'Interrompre et parler'},
  '当前可以先用下方按钮探索动作。': {
    en: "Explore the actions with the buttons below first.",
    fr: "Explore d'abord les actions avec les boutons ci-dessous.",
  },
  '识别方式': {en: 'Recognition mode', fr: 'Mode de reconnaissance'},
  '本地优先': {en: 'Local first', fr: "Local d'abord"},
  '灵矽云端': {en: 'Linx cloud', fr: 'Nuage Linx'},
  '灵矽负责识别和回复。': {en: 'Linx handles recognition and replies.', fr: 'Linx assure la reconnaissance et les réponses.'},
  '启用 / 测试声音 ♪': {en: 'Enable / test sound ♪', fr: 'Activer / tester le son ♪'},
  '可先播放本地提示音，检查手机声音。': {
    en: 'Play the test tone first to check your phone sound.',
    fr: 'Joue le son de test pour vérifier le volume du téléphone.',
  },
  '声音诊断': {en: 'Sound diagnostics', fr: 'Diagnostic audio'},
  '尚未初始化声音': {en: 'Audio not initialized', fr: 'Audio non initialisé'},
  '重置语音 ↻': {en: 'Reset voice ↻', fr: 'Réinitialiser la voix ↻'},
  '连接诊断 ↗': {en: 'Connection diagnostics ↗', fr: 'Diagnostic de connexion ↗'},
  '先动起来': {en: 'Start moving', fr: 'Bouge un peu'},
  '点点头': {en: 'Nod', fr: 'Hoche la tête'},
  '和你打个招呼': {en: 'Says hello to you', fr: 'Pour te dire bonjour'},
  '向前走': {en: 'Walk forward', fr: 'Avance'},
  '走一小段，自动停': {en: 'A short walk, stops on its own', fr: 'Quelques pas, puis il s’arrête'},
  '向左转': {en: 'Turn left', fr: 'Tourne à gauche'},
  '换个方向看看': {en: 'Looks the other way', fr: 'Pour regarder ailleurs'},
  '向右转': {en: 'Turn right', fr: 'Tourne à droite'},
  '再看看另一边': {en: 'Checks the other side', fr: 'Pour voir de l’autre côté'},
  '向后退': {en: 'Step back', fr: 'Recule'},
  '后退一小段': {en: 'A short step backwards', fr: 'Un petit pas en arrière'},
  '向左挪': {en: 'Shift left', fr: 'Décale à gauche'},
  '向右挪': {en: 'Shift right', fr: 'Décale à droite'},
  '横移，不转身': {en: 'Sidestep, no turning', fr: 'Pas de côté, sans pivoter'},
  '摇摇头': {en: 'Shake head', fr: 'Secoue la tête'},
  '轻轻说声不': {en: 'Says no, gently', fr: 'Pour dire non en douceur'},
  '歪歪头': {en: 'Tilt head', fr: 'Penche la tête'},
  '好奇地想一想': {en: 'Curious, thinking', fr: 'Curieux, il réfléchit'},
  '闪身步': {en: 'Flash step', fr: 'Pas éclair'},
  '左闪回闪，利落收势': {en: 'Dodge left-right, crisp finish', fr: 'Esquives gauche-droite, finition nette'},
  '狗熊哆嗦毛': {en: 'Shivering bear', fr: "L'ours qui frissonne"},
  '四拍抖毛，轻轻收势': {en: 'Shakes in four beats, soft finish', fr: 'Secoue en quatre temps, finition douce'},
  '停止动作': {en: 'Stop action', fr: 'Arrêter l’action'},
  '回到起点': {en: 'Back to start', fr: 'Retour au départ'},
  '交互记录': {en: 'Activity log', fr: "Journal d'interaction"},
  '清空显示': {en: 'Clear', fr: 'Effacer'},
  '小鸭已经准备好了。试着让它点点头吧。': {
    en: 'Your duck is ready. Try making it nod.',
    fr: 'Le canard est prêt. Essaie de lui faire hocher la tête.',
  },
  '使用官方 MicroDuck 外观的动画预览，不进行物理计算。灵矽语音尚未连接。': {
    en: 'Animation preview with the official MicroDuck look, no physics. Linx voice is not connected.',
    fr: "Aperçu animé à l'apparence officielle du MicroDuck, sans calcul physique. La voix Linx n'est pas connectée.",
  },
  '界面为法语；本房间的语音语言取决于所配置的智能体。': {
    en: 'Interface is French; the voice language of this room depends on the configured agent.',
    fr: 'Interface en français ; la langue vocale dépend de l’agent configuré pour ce salon.',
  },
  '界面为英语；本房间的语音语言取决于所配置的智能体。': {
    en: 'Interface is English; the voice language of this room depends on the configured agent.',
    fr: 'Interface en anglais ; la langue vocale dépend de l’agent configuré pour ce salon.',
  },
  // site-nav 导航与语言菜单
  '动作训练场': {en: 'Training ground', fr: 'Terrain d’entraînement'},
  '演示场景': {en: 'Demo scenes', fr: 'Scènes de démo'},
  '现场互动': {en: 'Live interaction', fr: 'Interaction en direct'},
  '使用体验': {en: 'Experience', fr: 'Expérience'},
  '交互统计': {en: 'Usage statistics', fr: 'Statistiques d’usage'},
  '部署记录': {en: 'Deployments', fr: 'Déploiements'},
  '源代码 ↗': {en: 'Source code ↗', fr: 'Code source ↗'},
  '语言': {en: 'Language', fr: 'Langue'},
  // voice.js 状态徽标与连接按钮
  '正在断开连接': {en: 'Disconnecting', fr: 'Déconnexion en cours'},
  '正在连接': {en: 'Connecting', fr: 'Connexion en cours'},
  '正在恢复连接': {en: 'Reconnecting', fr: 'Reconnexion en cours'},
  '正在切换新指令': {en: 'Switching to the new command', fr: 'Passage à la nouvelle commande'},
  '等待设备绑定': {en: 'Waiting for device binding', fr: 'En attente du liage de l’appareil'},
  '灵矽已连接': {en: 'Linx connected', fr: 'Linx connecté'},
  '正在聆听': {en: 'Listening', fr: 'Écoute en cours'},
  '正在思考': {en: 'Thinking', fr: 'Réflexion en cours'},
  '正在回答': {en: 'Speaking', fr: 'Réponse en cours'},
  '连接异常': {en: 'Connection error', fr: 'Erreur de connexion'},
  '本房间语音正在使用': {en: 'Voice busy in this room', fr: 'Voix déjà utilisée dans ce salon'},
  '正在释放语音…': {en: 'Releasing voice…', fr: 'Libération de la voix…'},
  '断开连接': {en: 'Disconnect', fr: 'Déconnecter'},
  '我已绑定，重新连接': {en: 'Device bound, reconnect', fr: 'Appareil lié, se reconnecter'},
  '本房间释放后重试': {en: 'Retry once the room frees up', fr: 'Réessayer une fois le salon libéré'},
  '启用语音': {en: 'Enable voice', fr: 'Activer la voix'},
  '使用灵矽智能体': {en: 'Via a Linx agent', fr: 'Via un agent Linx'},
  '设备端语音连接': {en: 'On-device voice connection', fr: 'Connexion vocale sur l’appareil'},
  '服务器离线识别 · 未匹配时交灵矽': {en: 'Server offline recognition · otherwise Linx', fr: 'Reconnaissance hors ligne du serveur · sinon Linx'},
  // voice.js 语音状态提示
  '连接后可进行真实语音对话。': {en: 'Connect for a real voice conversation.', fr: 'Connecte-toi pour une vraie conversation vocale.'},
  '按住按钮或空格说话，最长 15 秒。': {en: 'Hold the button or space to talk, up to 15 seconds.', fr: 'Maintiens le bouton ou l’espace pour parler (15 s max).'},
  '正在录音，松开后发送。': {en: 'Recording, release to send.', fr: 'Enregistrement en cours, relâche pour envoyer.'},
  '按住按钮可打断并说新命令；20 秒无响应会自动重连。': {
    en: 'Hold the button to interrupt with a new command; auto-reconnects after 20 seconds without a response.',
    fr: 'Maintiens le bouton pour interrompre avec une nouvelle commande ; reconnexion auto après 20 s.',
  },
  '上一轮已结束，正在重连。请连接成功后重新说话。': {
    en: 'The previous turn ended, reconnecting. Talk again once connected.',
    fr: 'Tour précédent terminé, reconnexion en cours. Parle à nouveau une fois connecté.',
  },
  '按住按钮或空格，立即打断并说新命令。': {
    en: 'Hold the button or space to interrupt with a new command right away.',
    fr: 'Maintiens le bouton ou l’espace pour interrompre et donner une nouvelle commande.',
  },
  '常用动作在本地执行，聊天和未匹配的整句指令交给灵矽。': {
    en: 'Common actions run locally; chat and unmatched phrases go to Linx.',
    fr: 'Actions courantes en local ; discussions et phrases non reconnues passent à Linx.',
  },
  '按住按钮可打断并说新命令。本地动作一旦开始，不再转交云端重复执行。': {
    en: 'Hold the button to interrupt with a new command. A started local action is not re-sent to the cloud.',
    fr: 'Maintiens le bouton pour interrompre. Une action locale commencée n’est pas renvoyée au nuage.',
  },
  '每个房间一次只供一个页面使用语音。可在顶部选择另一个房间，或在本房间的原页面断开后重试。': {
    en: 'Only one tab per room can use voice. Pick another room above, or disconnect the original tab of this room.',
    fr: 'Un seul onglet par salon peut utiliser la voix. Choisis un autre salon en haut, ou déconnecte l’onglet d’origine.',
  },
  '旧回复已停止，正在接收新命令；松开后发送。': {
    en: 'Old reply stopped, receiving the new command; release to send.',
    fr: 'Ancienne réponse stoppée, nouvelle commande en réception ; relâche pour envoyer.',
  },
  '旧回复已停止，正在建立新一轮语音。': {
    en: 'Old reply stopped, starting a new voice turn.',
    fr: 'Ancienne réponse stoppée, nouveau tour vocal en préparation.',
  },
  '正在关闭语音会话并释放占用，完成后可切换到其他设备。': {
    en: 'Closing the voice session and freeing the room; you can then switch to another device.',
    fr: 'Fermeture de la session vocale et libération du salon ; tu pourras passer à un autre appareil.',
  },
  '正在向浏览器申请麦克风；请允许网站使用麦克风。': {
    en: 'Asking the browser for the microphone; please allow the site to use it.',
    fr: 'Demande du micro au navigateur ; autorise le site.',
  },
  '麦克风权限已获得，正在加载录音组件…': {
    en: 'Microphone granted, loading the capture module…',
    fr: 'Micro autorisé, chargement du module d’enregistrement…',
  },
  '麦克风已待命；仅按住时发送语音，松开即静音，断开连接释放麦克风。': {
    en: 'Micro ready; audio is sent only while held, muted on release, freed on disconnect.',
    fr: 'Micro prêt ; envoi uniquement bouton maintenu, relâche pour couper, déconnexion pour libérer.',
  },
  '重新启用麦克风': {en: 'Re-enable microphone', fr: 'Réactiver le micro'},
  '正在准备麦克风…': {en: 'Preparing the microphone…', fr: 'Préparation du micro…'},
  '已收到回复音频，播放尚未就绪。请点“启用 / 测试声音”。': {
    en: 'Reply audio received, playback not ready yet. Click “Enable / test sound”.',
    fr: 'Réponse audio reçue, lecture pas encore prête. Clique « Activer / tester le son ».',
  },
  '点“启用 / 测试声音”可检查手机声音。': {
    en: 'Click “Enable / test sound” to check your phone sound.',
    fr: 'Clique « Activer / tester le son » pour tester le son du téléphone.',
  },
  '部分回复因播放受限已丢弃；请测试声音后重新说话。': {
    en: 'Some replies were dropped because playback was limited; test the sound and talk again.',
    fr: 'Réponses partiellement perdues (lecture limitée) ; teste le son puis parle à nouveau.',
  },
  '声音通道已就绪；若仍听不到，请检查媒体音量、静音开关和蓝牙输出。': {
    en: 'Audio channel ready; if you still hear nothing, check media volume, the silent switch and Bluetooth.',
    fr: 'Canal audio prêt ; sinon vérifie le volume média, le mode silencieux et le Bluetooth.',
  },
}));

export const ARIA_LABELS = new Map(Object.entries({
  '按住说话': {en: 'Hold to talk', fr: 'Maintenir pour parler'},
  '打断并说话': {en: 'Interrupt and talk', fr: 'Interrompre et parler'},
  '连接灵矽': {en: 'Connect Linx', fr: 'Connecter Linx'},
  '停止当前动作': {en: 'Stop the current action', fr: "Arrêter l'action en cours"},
  '复位视角': {en: 'Reset view', fr: 'Réinitialiser la vue'},
  '独立房间': {en: 'Independent rooms', fr: 'Salons indépendants'},
  '房间列表，可横向滚动': {en: 'Room list, horizontally scrollable', fr: 'Liste des salons, défilement horizontal'},
  '工作台导航': {en: 'Workbench navigation', fr: 'Navigation de l’atelier'},
  '返回工作台': {en: 'Back to the workbench', fr: "Retour à l'atelier"},
  '鸭子预览': {en: 'Duck preview', fr: 'Aperçu du canard'},
  '清空显示': {en: 'Clear', fr: 'Effacer'},
}));

for (const [source, en, fr] of messages) TRANSLATIONS.set(source, {en, fr});

// Long sentences are often joined with a live status. Index by their first two
// characters, so translating an update does not scan the whole catalogue.
const sentencePrefixes = new Map();
for (const source of TRANSLATIONS.keys()) {
  if (source.length < 8 || !/[。；！？]$/.test(source)) continue;
  const key=source.slice(0,2), entries=sentencePrefixes.get(key)??[];
  entries.push(source);sentencePrefixes.set(key,entries);
}
for (const entries of sentencePrefixes.values()) entries.sort((a,b)=>b.length-a.length);

export function translate(text, language = activeLanguage) {
  if (typeof text !== 'string' || language === 'zh') return text;
  const source = text.trim();
  let translated = TRANSLATIONS.get(source)?.[language];
  if (!translated && !/[\u4e00-\u9fff]/.test(source)) return text;
  if (!translated) {
    const prefix=sentencePrefixes.get(source.slice(0,2))?.find(key=>source.startsWith(key));
    if(prefix) translated=TRANSLATIONS.get(prefix)[language]+' '+translate(source.slice(prefix.length).trim(),language);
  }
  if (!translated) {
    for (const [pattern, en, fr, allowContent, rawValues] of patterns) {
      const match = source.match(pattern);
      if (match) {
        const values = match.slice(1).map((value,index) => rawValues?.includes(index) ? value : translate(value, language));
        if (!allowContent && values.some(value => /[\u4e00-\u9fff]/.test(value ?? ''))) continue;
        translated = (language === 'fr' ? fr : en)(...values); break;
      }
    }
  }
  if (!translated && /^(?: ·|· |；)/.test(source)) {
    const prefix=source.match(/^(?:·\s*|；)/)?.[0];
    if(prefix) translated=prefix+translate(source.slice(prefix.length),language);
  }
  if (!translated && /[\u4e00-\u9fff]/.test(source) && /[。；\n]| · /.test(source)) {
    const parts = source.match(/[^。\n]+。?|\n/g) ?? [];
    if (parts.length > 1) {
      const values = parts.map(part => translate(part, language));
      if (values.some((value, index) => value !== parts[index])) translated = values.join('');
    }
    else if (source.includes('；')) translated=source.split('；').map(part=>translate(part,language)).join('; ');
    else if (source.includes(' · ')) translated = source.split(' · ').map(part => translate(part, language)).join(' · ');
  }
  if (!translated) return text;
  return text.slice(0, text.indexOf(source)) + translated + text.slice(text.indexOf(source) + source.length);
}
// Retain canonical UI copy per node, including when switching back to Chinese.
// If application code changes a node, that new value becomes its source.
const textSources = new WeakMap(), attributeSources = new WeakMap();
const transcriptLabels = new Set(['你说','灵矽','本地识别','本地反馈','本地任务提醒']);
export function setLogText(element, text, label) {
  element.setAttribute(transcriptLabels.has(label) ? 'data-user-content' : 'data-ui-text', '');
  element.textContent = text;
}
const protectedContent = 'script,style,code,pre:not([data-ui-text]),[translate="no"],[data-user-content]';
function translateNode(node, language) {
  if (node.parentElement?.closest(protectedContent)) return;
  // Transcripts are content, not UI. Explicitly marked status rows are translated.
  if (node.parentElement?.closest('[role="log"],.activity-log') && !node.parentElement?.closest('[data-ui-text],.log-label,.empty-log')) return;
  const previous = textSources.get(node);
  const source = previous?.rendered === node.nodeValue ? previous.source : node.nodeValue;
  const value = translate(source, language);
  textSources.set(node, {source, rendered:value});
  if (value !== node.nodeValue) node.nodeValue = value;
}
function translateTextNodes(root, language) {
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  for (let node = walker.nextNode(); node; node = walker.nextNode()) {
    translateNode(node, language);
  }
}

function translateAriaLabels(root, language) {
  const elements = [...(root.querySelectorAll?.('[aria-label],[title],[placeholder],[alt]') ?? [])];
  if (root.nodeType === 1) elements.push(root);
  for (const element of elements) {
    if (element.closest(protectedContent)) continue;
    const sources = attributeSources.get(element) ?? new Map();
    attributeSources.set(element, sources);
    for (const attribute of ['aria-label','title','placeholder','alt']) {
      const current = element.getAttribute(attribute), previous = sources.get(attribute);
      if (current === null) {sources.delete(attribute); continue;}
      const source = previous?.rendered === current ? previous.source : current;
      const value = ARIA_LABELS.get(source)?.[language] ?? translate(source, language);
      sources.set(attribute, {source, rendered:value});
      if (value !== current) element.setAttribute(attribute, value);
    }
  }
}

export function applyInterface(language, root = document) {
  if (typeof document === 'undefined') return;
  if (root.nodeType === 3) translateNode(root, language);
  else {translateTextNodes(root, language); translateAriaLabels(root, language);}
}

function translateChanges(records) {
  const roots = new Set();
  for (const record of records) {
    if (record.type === 'childList') for (const node of record.addedNodes) roots.add(node);
    else roots.add(record.target);
  }
  for (const root of roots) if (root.isConnected) applyInterface(activeLanguage, root);
}
const observeOptions = {subtree:true, childList:true, characterData:true,
  attributes:true, attributeFilter:['aria-label','title','placeholder','alt']};

export function setLanguage(language) {
  if (!LANGUAGES.has(language)) return;
  // Resolve pending UI writes using the old language before changing it.
  if (observer) translateChanges(observer.takeRecords());
  const previous = activeLanguage;
  const previousVoiceLanguage = activeVoiceLanguage;
  activeLanguage = language; storeLanguage(language);
  activeVoiceLanguage = language;storeVoiceLanguage(language);
  document.documentElement.lang = language === 'zh' ? 'zh-CN' : language;
  document.documentElement.dataset.voiceLanguage=language;
  const url = new URL(location.href); url.searchParams.delete('lang');
  url.searchParams.delete('voice_lang');
  history.replaceState(history.state, '', url);
  applyInterface(language);
  if (previous !== language || previousVoiceLanguage !== language) window.dispatchEvent(new CustomEvent('duckking-language-changed', {detail:{language, previous,voiceLanguage:language,previousVoiceLanguage}}));
}

export function initUILanguage() {
  if (readyPromise) return readyPromise;
  readyPromise = (async () => {
    const urlLang = new URLSearchParams(location.search).get('lang');
    if (LANGUAGES.has(urlLang)) storeLanguage(urlLang);
    const saved = savedLanguage();
    const prefs = LANGUAGES.has(urlLang) || LANGUAGES.has(saved) ? null : await uiPreferences();
    activeLanguage = pickLanguage({urlLang, savedLang:saved, serverLang:prefs?.language});
    let savedVoiceLang;try{savedVoiceLang=localStorage.getItem(VOICE_STORAGE_KEY)}catch{}
    const urlVoiceLang=new URLSearchParams(location.search).get('voice_lang');
    activeVoiceLanguage=pickVoiceLanguage({urlVoiceLang,urlLang,savedVoiceLang,interfaceLanguage:activeLanguage});
    storeVoiceLanguage(activeVoiceLanguage);
    document.documentElement.lang = activeLanguage === 'zh' ? 'zh-CN' : activeLanguage;
    document.documentElement.dataset.voiceLanguage=activeVoiceLanguage;
    document.getElementById('audio-diagnostics')?.setAttribute('data-ui-text','');
    applyInterface(activeLanguage);
    // Observe Chinese too: later language changes reuse the document and model.
    observer = new MutationObserver(translateChanges);
    observer.observe(document.documentElement, observeOptions);
    window.addEventListener('pagehide', () => observer.disconnect());
    window.addEventListener('pageshow', event => {
      if (!event.persisted) return;
      applyInterface(activeLanguage);
      observer.observe(document.documentElement, observeOptions);
    });
    return activeLanguage;
  })();
  return readyPromise;
}
