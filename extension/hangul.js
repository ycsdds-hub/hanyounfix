/*
 * 한영 변환 + 오타 판단 코어 (두벌식 기준)
 * content script, 테스트(node) 양쪽에서 쓰기 위해 globalThis.HanYoung 으로 노출합니다.
 */
(function (root) {
  'use strict';

  const KEY2JAMO = {
    r: 'ㄱ', R: 'ㄲ', s: 'ㄴ', e: 'ㄷ', E: 'ㄸ', f: 'ㄹ', a: 'ㅁ', q: 'ㅂ', Q: 'ㅃ',
    t: 'ㅅ', T: 'ㅆ', d: 'ㅇ', w: 'ㅈ', W: 'ㅉ', c: 'ㅊ', z: 'ㅋ', x: 'ㅌ', v: 'ㅍ', g: 'ㅎ',
    k: 'ㅏ', o: 'ㅐ', i: 'ㅑ', O: 'ㅒ', j: 'ㅓ', p: 'ㅔ', u: 'ㅕ', P: 'ㅖ', h: 'ㅗ',
    y: 'ㅛ', n: 'ㅜ', b: 'ㅠ', m: 'ㅡ', l: 'ㅣ',
  };
  const JAMO2KEY = {};
  for (const [k, v] of Object.entries(KEY2JAMO)) JAMO2KEY[v] = k;

  const CHO = [...'ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ'];
  const JUNG = [...'ㅏㅐㅑㅒㅓㅔㅕㅖㅗㅘㅙㅚㅛㅜㅝㅞㅟㅠㅡㅢㅣ'];
  const JONG = ['', ...'ㄱㄲㄳㄴㄵㄶㄷㄹㄺㄻㄼㄽㄾㄿㅀㅁㅂㅄㅅㅆㅇㅈㅊㅋㅌㅍㅎ'];

  const VCOMP = { 'ㅗㅏ': 'ㅘ', 'ㅗㅐ': 'ㅙ', 'ㅗㅣ': 'ㅚ', 'ㅜㅓ': 'ㅝ', 'ㅜㅔ': 'ㅞ', 'ㅜㅣ': 'ㅟ', 'ㅡㅣ': 'ㅢ' };
  const JCOMP = {
    'ㄱㅅ': 'ㄳ', 'ㄴㅈ': 'ㄵ', 'ㄴㅎ': 'ㄶ', 'ㄹㄱ': 'ㄺ', 'ㄹㅁ': 'ㄻ', 'ㄹㅂ': 'ㄼ',
    'ㄹㅅ': 'ㄽ', 'ㄹㅌ': 'ㄾ', 'ㄹㅍ': 'ㄿ', 'ㄹㅎ': 'ㅀ', 'ㅂㅅ': 'ㅄ',
  };
  const COMPOUND2KEYS = {};
  for (const [pair, c] of Object.entries({ ...VCOMP, ...JCOMP })) {
    COMPOUND2KEYS[c] = [...pair].map((j) => JAMO2KEY[j]).join('');
  }

  const VOWELS = new Set(JUNG);
  const CHO_SET = new Set(CHO);
  const JONG_SET = new Set(JONG.slice(1));

  const isSyllable = (c) => c >= '가' && c <= '힣';
  const isJamo = (c) => c >= 'ㄱ' && c <= 'ㅣ';

  function compose(jamos) {
    const out = [];
    const n = jamos.length;
    let i = 0;
    const vowelAt = (k) => k < n && VOWELS.has(jamos[k]);
    while (i < n) {
      const c = jamos[i];
      if (!CHO_SET.has(c) || !vowelAt(i + 1)) {
        out.push(c);
        i += 1;
        continue;
      }
      let v = jamos[i + 1];
      i += 2;
      if (i < n && VCOMP[v + jamos[i]]) {
        v = VCOMP[v + jamos[i]];
        i += 1;
      }
      let jong = '';
      if (i < n && JONG_SET.has(jamos[i]) && !vowelAt(i + 1)) {
        jong = jamos[i];
        i += 1;
        if (i < n && JCOMP[jong + jamos[i]] && !vowelAt(i + 1)) {
          jong = JCOMP[jong + jamos[i]];
          i += 1;
        }
      }
      out.push(String.fromCharCode(0xac00 + (CHO.indexOf(c) * 21 + JUNG.indexOf(v)) * 28 + JONG.indexOf(jong)));
    }
    return out.join('');
  }

  /** 영문 키 입력 → 한글 ("dkssud" → "안녕") */
  function engToHangul(text) {
    return compose([...text].map((ch) => KEY2JAMO[ch] || ch));
  }

  /** 한글 → 같은 키의 영문 ("ㅗ디ㅣㅐ" → "hello") */
  function hangulToEng(text) {
    let out = '';
    for (const ch of text) {
      let parts = [ch];
      if (isSyllable(ch)) {
        const code = ch.charCodeAt(0) - 0xac00;
        const jong = code % 28;
        const jung = Math.floor(code / 28) % 21;
        const cho = Math.floor(code / 28 / 21);
        parts = [CHO[cho], JUNG[jung], JONG[jong]];
      }
      for (const p of parts) {
        if (p) out += COMPOUND2KEYS[p] || JAMO2KEY[p] || p;
      }
    }
    return out;
  }

  // 한글 IME에서 Shift가 의미 있는 키(쌍자음, ㅒ, ㅖ)
  const SHIFT_KEYS = new Set([...'QWERTOP']);
  // 웃음/감정 표현처럼 일부러 자모만 쓰는 경우
  const EMOTE_JAMO = new Set([...'ㅋㅎㅠㅜㅡㄷ']);
  // 단독으로 쓰여도 자연스러운 모음 (ㅠㅠ, ㅜㅜ, ㅡㅡ)
  const COMMON_LONE_VOWELS = new Set([...'ㅠㅜㅡ']);

  // 키로 바꾸면 흔한 영어 단어가 되지만 실제로 쓰는 한글 단어 (영어로 바꾸지 않음)
  const KO_EXCEPTIONS = new Set([
    '재가', '재구', '무미', '모드', '해미', '애주', '개차', '래미', '두표', '책미', '미새',
    '소무', '소두', '노래', '애애', '야미', '채미', '여미', '샤차', '내차',
  ]);

  /**
   * 사전 조회 함수 묶음. 모두 소문자 영단어를 받습니다.
   * @typedef {object} Dict
   * @property {(w: string) => boolean} isWord    전체 사전에 있는 단어인가
   * @property {(w: string) => boolean} [isCommon] 흔한 단어인가 (없으면 isWord)
   * @property {(w: string) => boolean} [isPrefix] 더 긴 영단어의 앞부분인가 (없으면 false)
   */

  /**
   * 잘못된 입력 모드로 쳐진 단어인지 판단합니다.
   * @param {string} token  한 가지 문자 종류(영문만 또는 한글만)로 된 단어
   * @param {Dict|((w: string) => boolean)} dict
   * @param {{minLength?: number, midWord?: boolean}} [opts]
   *   midWord: 아직 단어를 치는 중(띄어쓰기 전)에 검사하는 경우
   * @returns {string|null} 교정된 단어, 교정이 필요 없으면 null
   */
  function decide(token, dict, opts = {}) {
    const minLength = opts.minLength ?? 3;
    const d = typeof dict === 'function' ? { isWord: dict } : dict;
    const isWord = d.isWord;
    const isCommon = d.isCommon || d.isWord;
    const isPrefix = d.isPrefix || (() => false);

    // 1) 영어로 입력됐지만 한글이어야 했던 경우
    if (/^[A-Za-z]+$/.test(token)) {
      if (token.length < minLength) return null;
      // 한글 IME에서 의미 없는 대문자(A, B, ...)가 있으면 의도적인 영어
      if ([...token].some((c) => c >= 'A' && c <= 'Z' && !SHIFT_KEYS.has(c))) return null;
      const lower = token.toLowerCase();
      if (isWord(lower)) return null;
      // 치는 중인 긴 영어 단어의 앞부분일 수 있으면 끝까지 기다림
      if (opts.midWord && isPrefix(lower)) return null;
      const hangul = engToHangul(token);
      return [...hangul].every(isSyllable) ? hangul : null;
    }

    // 2) 한글로 입력됐지만 영어여야 했던 경우
    if (/^[가-힣ㄱ-ㅣ]+$/.test(token)) {
      const chars = [...token];
      const jamos = chars.filter(isJamo);
      if (jamos.length === chars.length && chars.every((c) => EMOTE_JAMO.has(c) || c === chars[0])) {
        return null; // ㅋㅋㅋ, ㅠㅠ, ㅇㅇ 등
      }
      const eng = hangulToEng(token);
      if (!/^[A-Za-z]+$/.test(eng) || eng.length < minLength) return null;
      const lower = eng.toLowerCase();
      const hasStray = jamos.length > 0;
      const loneVowel = jamos.some((c) => VOWELS.has(c) && !COMMON_LONE_VOWELS.has(c));
      if (hasStray && isWord(lower)) return lower;
      // 온전한 한글 글자로만 된 경우: 흔한 영단어이고 알려진 한글 단어가 아닐 때만
      if (!hasStray && eng.length >= 4 && isCommon(lower) && !KO_EXCEPTIONS.has(token)) return lower;
      if (loneVowel && eng.length >= 4) return lower; // 사전에 없어도 한글로는 거의 쓰지 않는 형태
      return null;
    }
    return null;
  }

  root.HanYoung = { engToHangul, hangulToEng, decide, isSyllable, isJamo };
})(typeof globalThis !== 'undefined' ? globalThis : this);
