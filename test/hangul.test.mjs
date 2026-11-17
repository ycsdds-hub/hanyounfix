import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

await import('../extension/hangul.js');
const { engToHangul, hangulToEng, decide } = globalThis.HanYoung;

const words = new Set(
  readFileSync(new URL('../extension/words.txt', import.meta.url), 'utf8').split('\n').filter(Boolean),
);
const isWord = (w) => words.has(w);

test('영문 키 → 한글 조합', () => {
  assert.equal(engToHangul('dkssudgktpdy'), '안녕하세요');
  assert.equal(engToHangul('tkfkdgody'), '사랑해요');
  assert.equal(engToHangul('dhkswjs'), '완전');          // 겹모음
  assert.equal(engToHangul('dkswdk'), '앉아');          // 겹받침 ㄵ
  assert.equal(engToHangul('qkfqdk'), '밟아');          // 겹받침 ㄼ
  assert.equal(engToHangul('dlTek'), '있다');           // 쌍받침
  assert.equal(engToHangul('dlfrrh'), '읽고');          // 겹받침
  assert.equal(engToHangul('Rhc'), '꽃');               // 쌍자음 + 받침
});

test('한글 → 영문 키', () => {
  assert.equal(hangulToEng('ㅗ디ㅣㅐ'), 'hello');
  assert.equal(hangulToEng('안녕'), 'dkssud');
  assert.equal(hangulToEng('완전'), 'dhkswjs');
  assert.equal(hangulToEng('읽고'), 'dlfrrh');
});

test('왕복 변환', () => {
  for (const w of ['안녕하세요', '읽었다', '꽃밭에서', '괜찮아', '뷁']) {
    assert.equal(engToHangul(hangulToEng(w)), w);
  }
});

test('영어 모드에서 친 한글 → 교정', () => {
  assert.equal(decide('dkssudgktpdy', isWord), '안녕하세요');
  assert.equal(decide('gksrmf', isWord), '한글');
  assert.equal(decide('Rhc', isWord), '꽃');
});

test('진짜 영어는 그대로', () => {
  for (const w of ['hello', 'world', 'keyboard', 'the', 'github', 'Seoul', 'Tom', 'API', 'iPhone', 'lol', 'omg']) {
    assert.equal(decide(w, isWord), null, w);
  }
});

test('한글 모드에서 친 영어 → 교정', () => {
  assert.equal(decide('ㅗ디ㅣㅐ', isWord), 'hello');
  assert.equal(decide('재기ㅇ', isWord), 'world');
  assert.equal(decide('ㅅㄷㄴㅅ', isWord), 'test');
  assert.equal(decide('햐소ㅕㅠ', isWord), 'github');   // 사전에 없어도 단독 모음 ㅕ
  assert.equal(decide('캐ㅐㅡ', isWord), 'zoom');
});

test('진짜 한글은 그대로', () => {
  for (const w of ['안녕하세요', '한글', '사랑해', 'ㅋㅋㅋ', 'ㅠㅠ', 'ㅎㅎㅎ', 'ㅇㅇ', 'ㄱㄱ', '감사합니다', '진짜', '우리', '오늘']) {
    assert.equal(decide(w, isWord), null, w);
  }
});

test('섞인 단어, 짧은 단어는 건드리지 않음', () => {
  assert.equal(decide('안녕hi', isWord), null);
  assert.equal(decide('gk', isWord), null);
});
