// Region-aware default UI language for the main workbench page.
// The backend decides the default from a local IP database; the visitor can
// always override with ?lang=zh|fr or the toggle button (stored locally).
// Logs, transcripts and cloud data stay as produced; only interface labels
// from the dictionary below are translated.

import {appURL} from './urls.js';

const STORAGE_KEY = 'duckking-ui-language';
const LANGUAGES = new Set(['zh', 'fr']);

let prefsPromise = null;

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

function savedLanguage() {
  try {return localStorage.getItem(STORAGE_KEY)} catch {return null}
}

// 只覆盖主工作台界面文案；键为页面或 voice.js 写入的原文，值即法语替换。
// 日志行、转写文本和错误提示保持原文，不冒充云端输出的语言。
export const FRENCH_STRINGS = new Map(Object.entries({
  'DuckKing · 语音与动作工作台': 'DuckKing · Atelier voix et mouvements',
  '让一句话，': 'Dites une phrase,',
  '变成一个动作。': 'elle devient une action.',
  '遇见你的虚拟小鸭。先打个招呼，再一起迈出第一步。':
    "Rencontre ton petit canard virtuel. Dis d'abord bonjour, puis ensemble faites le premier pas.",
  '正在连接工作台': "Connexion à l'atelier…",
  '语音 × PPO · 新实验': 'Voix × PPO · Nouvelle expérience',
  '训练新动作': 'Entraîner un nouveau mouvement',
  '转盘站稳，跷跷板停靠。用语音挑战 PPO，看小鸭怎样学会新技能。':
    "Tenir sur la roulette, se poser sur la balançoire. Défie le PPO avec la voix et regarde le canard apprendre.",
  '选择训练场景 ': "Choisir un scénario d'entraînement ",
  '动画预览': 'Aperçu animé',
  '■ 停止': '■ Stop',
  '停止当前动作': "Arrêter l'action en cours",
  '↺ 复位视角': '↺ Réinitialiser la vue',
  '复位视角': 'Réinitialiser la vue',
  '当前浏览器无法启动 WebGL。动作控制和状态面板仍然可用。':
    "WebGL ne démarre pas dans ce navigateur. Les commandes et le panneau d'état restent utilisables.",
  '正在等待你的指令': "En attente de ton instruction",
  '拖动旋转 · 滚轮缩放': 'Glisser pour tourner · molette pour zoomer',
  '当前动作': 'Action en cours',
  '待机': 'Repos',
  '前进指令': "Consigne d'avance",
  '已执行动作': 'Actions exécutées',
  '数据来源': 'Source des données',
  '本地预览': 'Aperçu local',
  '和小鸭聊聊': 'Parle au canard',
  '未连接灵矽': 'Linx non connecté',
  '连接灵矽后，按住说话，松开等待回答。':
    'Après connexion à Linx : maintiens pour parler, relâche et attends la réponse.',
  '启用语音后，按住说话；常用动作本地执行，未匹配时交给灵矽。':
    "Voix activée : maintiens pour parler ; les actions courantes s'exécutent en local, le reste passe à Linx.",
  '连接灵矽': 'Connecter Linx',
  '接入模块准备中': 'Préparation du module audio',
  '按住说话': 'Maintenir pour parler',
  '打断并说话': 'Interrompre et parler',
  '当前可以先用下方按钮探索动作。': "Explore d'abord les actions avec les boutons ci-dessous.",
  '识别方式': 'Mode de reconnaissance',
  '本地优先': "Local d'abord",
  '灵矽云端': 'Nuage Linx',
  '灵矽负责识别和回复。': 'Linx assure la reconnaissance et les réponses.',
  '启用 / 测试声音 ♪': 'Activer / tester le son ♪',
  '可先播放本地提示音，检查手机声音。': 'Joue le son de test pour vérifier le volume du téléphone.',
  '声音诊断': 'Diagnostic audio',
  '尚未初始化声音': 'Audio non initialisé',
  '重置语音 ↻': 'Réinitialiser la voix ↻',
  '连接诊断 ↗': 'Diagnostic de connexion ↗',
  '先动起来': 'Bouge un peu',
  '点点头': 'Hoche la tête',
  '和你打个招呼': 'Pour te dire bonjour',
  '向前走': 'Avance',
  '走一小段，自动停': 'Quelques pas, puis il s’arrête',
  '向左转': 'Tourne à gauche',
  '换个方向看看': 'Pour regarder ailleurs',
  '向右转': 'Tourne à droite',
  '再看看另一边': 'Pour voir de l’autre côté',
  '向后退': 'Recule',
  '后退一小段': 'Un petit pas en arrière',
  '向左挪': 'Décale à gauche',
  '向右挪': 'Décale à droite',
  '横移，不转身': 'Pas de côté, sans pivoter',
  '摇摇头': 'Secoue la tête',
  '轻轻说声不': 'Pour dire non en douceur',
  '歪歪头': 'Penche la tête',
  '好奇地想一想': 'Curieux, il réfléchit',
  '闪身步': 'Pas éclair',
  '左闪回闪，利落收势': 'Esquives gauche-droite, finition nette',
  '狗熊哆嗦毛': "L'ours qui frissonne",
  '四拍抖毛，轻轻收势': 'Secoue en quatre temps, finition douce',
  '停止动作': 'Arrêter l’action',
  '回到起点': 'Retour au départ',
  '交互记录': "Journal d'interaction",
  '清空显示': 'Effacer',
  '小鸭已经准备好了。试着让它点点头吧。': 'Le canard est prêt. Essaie de lui faire hocher la tête.',
  '使用官方 MicroDuck 外观的动画预览，不进行物理计算。灵矽语音尚未连接。':
    "Aperçu animé à l'apparence officielle du MicroDuck, sans calcul physique. La voix Linx n'est pas connectée.",
  // voice.js 状态徽标与连接按钮
  '正在断开连接': 'Déconnexion en cours',
  '正在连接': 'Connexion en cours',
  '正在恢复连接': 'Reconnexion en cours',
  '正在切换新指令': 'Passage à la nouvelle commande',
  '等待设备绑定': 'En attente du liage de l’appareil',
  '灵矽已连接': 'Linx connecté',
  '正在聆听': 'Écoute en cours',
  '正在思考': 'Réflexion en cours',
  '正在回答': 'Réponse en cours',
  '连接异常': 'Erreur de connexion',
  '本房间语音正在使用': 'Voix déjà utilisée dans ce salon',
  '正在释放语音…': 'Libération de la voix…',
  '断开连接': 'Déconnecter',
  '我已绑定，重新连接': 'Appareil lié, se reconnecter',
  '本房间释放后重试': 'Réessayer une fois le salon libéré',
  '启用语音': 'Activer la voix',
  '使用灵矽智能体': 'Via un agent Linx',
  '设备端语音连接': 'Connexion vocale sur l’appareil',
  '服务器离线识别 · 未匹配时交灵矽': "Reconnaissance hors ligne du serveur · sinon Linx",
  // voice.js 语音状态提示
  '连接后可进行真实语音对话。': 'Connecte-toi pour une vraie conversation vocale.',
  '按住按钮或空格说话，最长 15 秒。': 'Maintiens le bouton ou l’espace pour parler (15 s max).',
  '正在录音，松开后发送。': 'Enregistrement en cours, relâche pour envoyer.',
  '按住按钮可打断并说新命令；20 秒无响应会自动重连。':
    'Maintiens le bouton pour interrompre avec une nouvelle commande ; reconnexion auto après 20 s.',
  '上一轮已结束，正在重连。请连接成功后重新说话。':
    'Tour précédent terminé, reconnexion en cours. Parle à nouveau une fois connecté.',
  '按住按钮或空格，立即打断并说新命令。':
    'Maintiens le bouton ou l’espace pour interrompre et donner une nouvelle commande.',
  '常用动作在本地执行，聊天和未匹配的整句指令交给灵矽。':
    'Actions courantes en local ; discussions et phrases non reconnues passent à Linx.',
  '按住按钮可打断并说新命令。本地动作一旦开始，不再转交云端重复执行。':
    'Maintiens le bouton pour interrompre. Une action locale commencée n’est pas renvoyée au nuage.',
  '每个房间一次只供一个页面使用语音。可在顶部选择另一个房间，或在本房间的原页面断开后重试。':
    'Un seul onglet par salon peut utiliser la voix. Choisis un autre salon en haut, ou déconnecte l’onglet d’origine.',
  '旧回复已停止，正在接收新命令；松开后发送。':
    'Ancienne réponse stoppée, nouvelle commande en réception ; relâche pour envoyer.',
  '旧回复已停止，正在建立新一轮语音。': 'Ancienne réponse stoppée, nouveau tour vocal en préparation.',
  '正在关闭语音会话并释放占用，完成后可切换到其他设备。':
    'Fermeture de la session vocale et libération du salon ; tu pourras passer à un autre appareil.',
  '正在向浏览器申请麦克风；请允许网站使用麦克风。': 'Demande du micro au navigateur ; autorise le site.',
  '麦克风权限已获得，正在加载录音组件…': 'Micro autorisé, chargement du module d’enregistrement…',
  '麦克风已待命；仅按住时发送语音，松开即静音，断开连接释放麦克风。':
    'Micro prêt ; envoi uniquement bouton maintenu, relâche pour couper, déconnexion pour libérer.',
  '重新启用麦克风': 'Réactiver le micro',
  '正在准备麦克风…': 'Préparation du micro…',
  '已收到回复音频，播放尚未就绪。请点“启用 / 测试声音”。':
    'Réponse audio reçue, lecture pas encore prête. Clique « Activer / tester le son ».',
  '点“启用 / 测试声音”可检查手机声音。': 'Clique « Activer / tester le son » pour tester le son du téléphone.',
  '部分回复因播放受限已丢弃；请测试声音后重新说话。':
    'Réponses partiellement perdues (lecture limitée) ; teste le son puis parle à nouveau.',
  '声音通道已就绪；若仍听不到，请检查媒体音量、静音开关和蓝牙输出。':
    'Canal audio prêt ; sinon vérifie le volume média, le mode silencieux et le Bluetooth.',
}));

export const FRENCH_ARIA_LABELS = new Map([
  ['按住说话', 'Maintenir pour parler'],
  ['打断并说话', 'Interrompre et parler'],
  ['连接灵矽', 'Connecter Linx'],
  ['停止当前动作', "Arrêter l'action en cours"],
  ['复位视角', 'Réinitialiser la vue'],
  ['独立房间', 'Salons indépendants'],
  ['房间列表，可横向滚动', 'Liste des salons, défilement horizontal'],
  ['工作台导航', 'Navigation de l’atelier'],
  ['返回工作台', "Retour à l'atelier"],
  ['鸭子预览', 'Aperçu du canard'],
  ['清空显示', 'Effacer'],
]);

function translateTextNodes(root) {
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  for (let node = walker.nextNode(); node; node = walker.nextNode()) {
    const french = FRENCH_STRINGS.get(node.nodeValue.trim());
    if (french) node.nodeValue = french;
  }
}

function translateAriaLabels(root) {
  for (const element of root.querySelectorAll('[aria-label]')) {
    const french = FRENCH_ARIA_LABELS.get(element.getAttribute('aria-label'));
    if (french) element.setAttribute('aria-label', french);
  }
}

export function applyFrench(root = document) {
  if (typeof document === 'undefined') return;
  translateTextNodes(root);
  translateAriaLabels(root);
  document.documentElement.lang = 'fr';
}

function injectToggle(language) {
  const heading = document.querySelector('.voice-card .section-heading');
  if (!heading || document.getElementById('ui-language-toggle')) return;
  const toggle = document.createElement('button');
  toggle.id = 'ui-language-toggle';
  toggle.className = 'tag neutral';
  toggle.type = 'button';
  toggle.textContent = language === 'fr' ? '中文' : 'FR';
  toggle.setAttribute('aria-label', 'Switch interface language / 切换界面语言');
  toggle.addEventListener('click', () => {
    try {localStorage.setItem(STORAGE_KEY, language === 'fr' ? 'zh' : 'fr')} catch {}
    location.reload();
  });
  heading.append(toggle);
}

export async function initUILanguage() {
  const urlLang = new URLSearchParams(location.search).get('lang');
  if (LANGUAGES.has(urlLang)) {
    try {localStorage.setItem(STORAGE_KEY, urlLang)} catch {}
  }
  const prefs = await uiPreferences();
  const language = pickLanguage({urlLang, savedLang: savedLanguage(), serverLang: prefs?.language});
  injectToggle(language);
  if (language !== 'fr') {
    document.documentElement.lang = 'zh-CN';
    return language;
  }
  applyFrench();
  // voice.js rewrites its captions on every state change; reapply after each one.
  window.addEventListener('duckking-voice-state', () => applyFrench());
  return language;
}

