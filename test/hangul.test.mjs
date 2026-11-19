import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

await import('../extension/hangul.js');
const { engToHangul, hangulToEng, decide } = globalThis.HanYoung;

const list = (f) => readFileSync(new URL(`../extension/${f}`, import.meta.url), 'utf8').split(/\r?\n/).filter(Boolean);
const sorted = list('words.txt');
const all = new Set(sorted);
const common = new Set(list('common.txt'));
const isPrefix = (w) => {
  let lo = 0;
  let hi = sorted.length;
  while (lo < hi) {
    const m = (lo + hi) >> 1;
    if (sorted[m] < w) lo = m + 1;
    else hi = m;
  }
  for (let i = lo; i < sorted.length && sorted[i].startsWith(w); i++) if (sorted[i].length > w.length) return true;
  return false;
};
const dict = { isWord: (w) => all.has(w), isCommon: (w) => common.has(w), isPrefix };
const cases = JSON.parse(readFileSync(new URL('./cases.json', import.meta.url), 'utf8'));

test('단어 목록은 정렬되어 있음 (접두사 이진 탐색 전제)', () => {
  for (let i = 1; i < sorted.length; i++) assert.ok(sorted[i - 1] < sorted[i], sorted[i]);
});

test('영문 키 → 한글 조합', () => {
  for (const [keys, hangul] of cases.convert) assert.equal(engToHangul(keys), hangul, keys);
});

test('한글 → 영문 키', () => {
  assert.equal(hangulToEng('ㅗ디ㅣㅐ'), 'hello');
  for (const [keys, hangul] of cases.convert) assert.equal(hangulToEng(hangul), keys.replace(/[A-Z]/g, (c) => ('QWERTOP'.includes(c) ? c : c.toLowerCase())), hangul);
});

test('왕복 변환', () => {
  for (const w of ['안녕하세요', '읽었다', '꽃밭에서', '괜찮아', '뷁']) assert.equal(engToHangul(hangulToEng(w)), w);
});

test('공통 판단 사례 (cases.json)', () => {
  for (const [token, midWord, expect] of cases.decide) {
    assert.equal(decide(token, dict, { midWord }), expect, `${token} (midWord=${midWord})`);
  }
});

test('6글자 중간 검사: 7자 이상 영어 단어를 앞부분에서 잘못 바꾸지 않음', () => {
  const bad = sorted.filter((w) => w.length >= 7 && decide(w.slice(0, 6), dict, { midWord: true }));
  assert.deepEqual(bad.slice(0, 10), []);
});

test('예전 호출 방식(함수 하나)도 동작', () => {
  assert.equal(decide('dkssud', (w) => all.has(w)), '안녕');
});
