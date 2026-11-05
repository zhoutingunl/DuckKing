import test from 'node:test';
import assert from 'node:assert/strict';

import {pickLanguage, TRANSLATIONS, ARIA_LABELS} from '../src/ui-language.js';

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
      assert.notEqual(source, translations[language], `翻译与原文相同: ${source}`);
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
