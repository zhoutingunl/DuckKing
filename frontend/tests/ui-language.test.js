import test from 'node:test';
import assert from 'node:assert/strict';

import {pickVoiceLanguage, pickLanguage, TRANSLATIONS, ARIA_LABELS, translate} from '../src/ui-language.js';

test('language pick prefers explicit URL over saved choice over server default', () => {
  assert.equal(pickLanguage({urlLang: 'fr', savedLang: 'zh', serverLang: 'zh'}), 'fr');
  assert.equal(pickLanguage({urlLang: 'en', savedLang: 'fr', serverLang: 'fr'}), 'en');
  assert.equal(pickLanguage({savedLang: 'en', serverLang: 'fr'}), 'en');
  assert.equal(pickLanguage({serverLang: 'fr'}), 'fr');
  assert.equal(pickLanguage({serverLang: 'en'}), 'en');
  assert.equal(pickLanguage({}), 'zh');
  assert.equal(pickLanguage({urlLang: 'de', savedLang: 'xx', serverLang: 'ja'}), 'zh');
});

test('every entry provides distinct non-empty English and French translations', () => {
  assert.ok(TRANSLATIONS.size > 85);
  for (const [source, translations] of TRANSLATIONS) {
    assert.ok(source.trim().length > 0, '键不能为空');
    for (const language of ['en', 'fr']) {
      assert.ok(
        (translations[language] ?? '').length > 0,
        `缺少${language === 'en' ? '英语' : '法语'}翻译: ${source}`,
      );
      if (/[\u4e00-\u9fff]/.test(source)) assert.notEqual(source, translations[language], `翻译与原文相同: ${source}`);
      assert.doesNotMatch(translations[language], /[\u4e00-\u9fff]/, `未翻译完整: ${source}`);
    }
  }
  for (const [source, translations] of ARIA_LABELS) {
    for (const language of ['en', 'fr']) {
      assert.ok(
        (translations[language] ?? '').length > 0 && source !== translations[language],
        `aria 翻译无效: ${source}`,
      );
    }
  }
});

test('key voice-panel copy and nav destinations stay covered', () => {
  // 防止页面、voice.js 或导航改文案后字典悄悄失效——改动文案时必须同步更新字典。
  for (const key of [
    '连接灵矽后，按住说话，松开等待回答。',
    '按住说话',
    '小鸭已经准备好了。试着让它点点头吧。',
    '连接后可进行真实语音对话。',
    '按住按钮或空格说话，最长 15 秒。',
    '麦克风已待命；仅按住时发送语音，松开即静音，断开连接释放麦克风。',
    '界面为法语；本房间的语音语言取决于所配置的智能体。',
    '界面为英语；本房间的语音语言取决于所配置的智能体。',
    '部署记录',
    '源代码 ↗',
    '语言',
  ]) {
    assert.ok(TRANSLATIONS.has(key), `字典缺少原文: ${key}`);
  }
});


test('dynamic labels and multiline translation are idempotent', () => {
  for (const language of ['en','fr']) {
    for (const text of ['本地预览','房间 12 · 独立语音与场景',
      '3 / 32 个房间 · 物理场景 1 / 4','未收录内容\n保持原样',
      '使用官方 MicroDuck 外观的动画预览，不进行物理计算。灵矽语音已连接。']) {
      const once=translate(text,language);
      assert.equal(translate(once,language),once);
    }
    assert.doesNotMatch(translate('房间 12 · 独立语音与场景',language),/[\u4e00-\u9fff]/);
    assert.doesNotMatch(translate('本地预览',language),/[\u4e00-\u9fff]/);
  }
});

test('joined explanation and live status translate without losing sentences',()=>{
  const explanation='4 × exp(−(距停靠中心 / 12 cm)²)。配重越靠近红色区中心，得分越高；奖励的是配重的位置，不是鸭子回中。';
  for(const language of ['fr','en']){
    const result=translate(explanation+' 等候实际采样。',language);
    assert.doesNotMatch(result,/[\u4e00-\u9fff]/);
    assert.equal(translate(result,language),result);
    assert.match(result,/4 × exp/);
  }
});

test('localized status preserves user-authored cue names even when they match a UI phrase',()=>{
  assert.equal(translate('当前口令：点点头；通过 2，拒绝 1','fr'),'Mot-clé actuel : 点点头 ; acceptés 2, refusés 1');
  assert.equal(translate('待确认暗号：下班，第 2 版','en'),'Shortcut awaiting confirmation: 下班, version 2');
});


test('Japanese voice choice is independent from interface locale and explicit choices win',()=>{
 assert.equal(pickVoiceLanguage({urlVoiceLang:'ja',urlLang:'fr',savedVoiceLang:'zh'}),'ja');
 assert.equal(pickVoiceLanguage({urlLang:'en',savedVoiceLang:'ja'}),'en');
 assert.equal(pickVoiceLanguage({savedVoiceLang:'ja',interfaceLanguage:'fr'}),'ja');
 assert.equal(pickVoiceLanguage({urlVoiceLang:'invalid',savedVoiceLang:'invalid',interfaceLanguage:'fr'}),'fr');
});
