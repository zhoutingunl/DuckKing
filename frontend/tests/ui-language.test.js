import test from 'node:test';
import assert from 'node:assert/strict';

import {pickLanguage, FRENCH_STRINGS, FRENCH_ARIA_LABELS} from '../src/ui-language.js';

test('language pick prefers explicit URL over saved choice over server default', () => {
  assert.equal(pickLanguage({urlLang: 'fr', savedLang: 'zh', serverLang: 'zh'}), 'fr');
  assert.equal(pickLanguage({urlLang: 'zh', savedLang: 'fr', serverLang: 'fr'}), 'zh');
  assert.equal(pickLanguage({savedLang: 'fr', serverLang: 'zh'}), 'fr');
  assert.equal(pickLanguage({serverLang: 'fr'}), 'fr');
  assert.equal(pickLanguage({}), 'zh');
  assert.equal(pickLanguage({urlLang: 'de', savedLang: 'xx', serverLang: 'ja'}), 'zh');
});

test('french dictionary entries are non-empty and actually differ from the source text', () => {
  assert.ok(FRENCH_STRINGS.size > 40);
  for (const [source, french] of FRENCH_STRINGS) {
    assert.ok(source.trim().length > 0, '键不能为空');
    assert.ok(french.length > 0, `缺少法语翻译: ${source}`);
    assert.notEqual(source, french, `法语翻译与原文相同: ${source}`);
  }
  for (const [source, french] of FRENCH_ARIA_LABELS) {
    assert.ok(french.length > 0 && source !== french, `aria 翻译无效: ${source}`);
  }
});

test('key voice-panel copy from index.html and voice.js stays covered', () => {
  // 防止页面或 voice.js 改文案后字典悄悄失效——改动文案时必须同步更新字典。
  for (const key of [
    '连接灵矽后，按住说话，松开等待回答。',
    '按住说话',
    '小鸭已经准备好了。试着让它点点头吧。',
    '连接后可进行真实语音对话。',
    '按住按钮或空格说话，最长 15 秒。',
    '麦克风已待命；仅按住时发送语音，松开即静音，断开连接释放麦克风。',
  ]) {
    assert.ok(FRENCH_STRINGS.has(key), `字典缺少原文: ${key}`);
  }
});
