"""두벌식 한영 변환 + 오타 판단 (extension/hangul.js 와 같은 규칙)

두 구현이 똑같이 판단하는지는 test/cases.json 으로 함께 검사합니다.
"""
from __future__ import annotations

import bisect
import os
import sys

KEY2JAMO = {
    'r': 'ㄱ', 'R': 'ㄲ', 's': 'ㄴ', 'e': 'ㄷ', 'E': 'ㄸ', 'f': 'ㄹ', 'a': 'ㅁ', 'q': 'ㅂ', 'Q': 'ㅃ',
    't': 'ㅅ', 'T': 'ㅆ', 'd': 'ㅇ', 'w': 'ㅈ', 'W': 'ㅉ', 'c': 'ㅊ', 'z': 'ㅋ', 'x': 'ㅌ', 'v': 'ㅍ', 'g': 'ㅎ',
    'k': 'ㅏ', 'o': 'ㅐ', 'i': 'ㅑ', 'O': 'ㅒ', 'j': 'ㅓ', 'p': 'ㅔ', 'u': 'ㅕ', 'P': 'ㅖ', 'h': 'ㅗ',
    'y': 'ㅛ', 'n': 'ㅜ', 'b': 'ㅠ', 'm': 'ㅡ', 'l': 'ㅣ',
}
JAMO2KEY = {v: k for k, v in KEY2JAMO.items()}

CHO = list('ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ')
JUNG = list('ㅏㅐㅑㅒㅓㅔㅕㅖㅗㅘㅙㅚㅛㅜㅝㅞㅟㅠㅡㅢㅣ')
JONG = [''] + list('ㄱㄲㄳㄴㄵㄶㄷㄹㄺㄻㄼㄽㄾㄿㅀㅁㅂㅄㅅㅆㅇㅈㅊㅋㅌㅍㅎ')

VCOMP = {'ㅗㅏ': 'ㅘ', 'ㅗㅐ': 'ㅙ', 'ㅗㅣ': 'ㅚ', 'ㅜㅓ': 'ㅝ', 'ㅜㅔ': 'ㅞ', 'ㅜㅣ': 'ㅟ', 'ㅡㅣ': 'ㅢ'}
JCOMP = {
    'ㄱㅅ': 'ㄳ', 'ㄴㅈ': 'ㄵ', 'ㄴㅎ': 'ㄶ', 'ㄹㄱ': 'ㄺ', 'ㄹㅁ': 'ㄻ', 'ㄹㅂ': 'ㄼ',
    'ㄹㅅ': 'ㄽ', 'ㄹㅌ': 'ㄾ', 'ㄹㅍ': 'ㄿ', 'ㄹㅎ': 'ㅀ', 'ㅂㅅ': 'ㅄ',
}
COMPOUND2KEYS = {c: ''.join(JAMO2KEY[j] for j in pair) for pair, c in {**VCOMP, **JCOMP}.items()}

VOWELS = set(JUNG)
CHO_SET = set(CHO)
JONG_SET = set(JONG[1:])

SHIFT_KEYS = set('QWERTOP')          # 한글 IME에서 Shift가 의미 있는 키
EMOTE_JAMO = set('ㅋㅎㅠㅜㅡㄷ')       # ㅋㅋ, ㅎㅎ, ㅠㅠ 처럼 일부러 쓰는 자모
COMMON_LONE_VOWELS = set('ㅠㅜㅡ')
KO_EXCEPTIONS = {
    '재가', '재구', '무미', '모드', '해미', '애주', '개차', '래미', '두표', '책미', '미새',
    '소무', '소두', '노래', '애애', '야미', '채미', '여미', '샤차', '내차',
}


def is_syllable(c: str) -> bool:
    return '가' <= c <= '힣'


def is_jamo(c: str) -> bool:
    return 'ㄱ' <= c <= 'ㅣ'


def _compose(jamos: list[str]) -> str:
    out, i, n = [], 0, len(jamos)

    def vowel_at(k: int) -> bool:
        return k < n and jamos[k] in VOWELS

    while i < n:
        c = jamos[i]
        if c not in CHO_SET or not vowel_at(i + 1):
            out.append(c)
            i += 1
            continue
        v = jamos[i + 1]
        i += 2
        if i < n and v + jamos[i] in VCOMP:
            v = VCOMP[v + jamos[i]]
            i += 1
        jong = ''
        if i < n and jamos[i] in JONG_SET and not vowel_at(i + 1):
            jong = jamos[i]
            i += 1
            if i < n and jong + jamos[i] in JCOMP and not vowel_at(i + 1):
                jong = JCOMP[jong + jamos[i]]
                i += 1
        out.append(chr(0xAC00 + (CHO.index(c) * 21 + JUNG.index(v)) * 28 + JONG.index(jong)))
    return ''.join(out)


def eng_to_hangul(text: str) -> str:
    """영문 키 입력 → 한글 ("dkssud" → "안녕")"""
    return _compose([KEY2JAMO.get(ch, ch) for ch in text])


def hangul_to_eng(text: str) -> str:
    """한글 → 같은 키의 영문 ("ㅗ디ㅣㅐ" → "hello")"""
    out = []
    for ch in text:
        parts = [ch]
        if is_syllable(ch):
            code = ord(ch) - 0xAC00
            parts = [CHO[code // 588], JUNG[(code // 28) % 21], JONG[code % 28]]
        for p in parts:
            if p:
                out.append(COMPOUND2KEYS.get(p) or JAMO2KEY.get(p, p))
    return ''.join(out)


def ime_keys(keys: str) -> str:
    """한글 IME에서는 Shift가 의미 없는 키(예: A)를 소문자로 취급"""
    return ''.join(c if c in SHIFT_KEYS else c.lower() for c in keys)


def _all_ascii_letters(s: str) -> bool:
    return bool(s) and s.isascii() and s.isalpha()


def _all_hangul(s: str) -> bool:
    return bool(s) and all(is_syllable(c) or is_jamo(c) for c in s)


class Dictionary:
    """영어 사전. words: 정렬된 전체 단어 목록, common: 흔한 단어 집합"""

    def __init__(self, words: list[str], common: set[str] | None = None, user_words=None):
        self.sorted = sorted(words)
        self.all = set(self.sorted)
        self.common = common if common is not None else self.all
        self.user_words: set[str] = set(user_words or [])

    @classmethod
    def load(cls, folder: str | None = None, user_words=None) -> 'Dictionary':
        folder = folder or default_data_dir()

        def read(name):
            with open(os.path.join(folder, name), encoding='utf-8') as f:
                return [w.strip() for w in f if w.strip()]

        return cls(read('words.txt'), set(read('common.txt')), user_words)

    def is_word(self, w: str) -> bool:
        return w in self.user_words or w in self.all

    def is_common(self, w: str) -> bool:
        return w in self.user_words or w in self.common

    def is_prefix(self, w: str) -> bool:
        i = bisect.bisect_left(self.sorted, w)
        while i < len(self.sorted) and self.sorted[i].startswith(w):
            if len(self.sorted[i]) > len(w):
                return True
            i += 1
        return False


def default_data_dir() -> str:
    """단어 목록 위치: exe로 묶었을 때는 번들 안, 소스 실행 시에는 ../../extension"""
    if getattr(sys, 'frozen', False):
        return getattr(sys, '_MEIPASS', os.path.dirname(sys.executable))
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.normpath(os.path.join(here, '..', '..', 'extension'))


def decide(token: str, d: Dictionary, mid_word: bool = False, min_length: int = 3) -> str | None:
    """잘못된 입력 모드로 쳐진 단어면 교정된 단어를, 아니면 None을 반환 (hangul.js decide와 동일)"""
    if token.lower() in d.user_words:
        return None

    # 1) 영어로 입력됐지만 한글이어야 했던 경우
    if _all_ascii_letters(token):
        if len(token) < min_length:
            return None
        if any('A' <= c <= 'Z' and c not in SHIFT_KEYS for c in token):
            return None
        lower = token.lower()
        if d.is_word(lower):
            return None
        if mid_word and d.is_prefix(lower):
            return None
        hangul = eng_to_hangul(token)
        return hangul if all(is_syllable(c) for c in hangul) else None

    # 2) 한글로 입력됐지만 영어여야 했던 경우
    if _all_hangul(token):
        chars = list(token)
        jamos = [c for c in chars if is_jamo(c)]
        if len(jamos) == len(chars) and all(c in EMOTE_JAMO or c == chars[0] for c in chars):
            return None
        eng = hangul_to_eng(token)
        if not _all_ascii_letters(eng) or len(eng) < min_length:
            return None
        lower = eng.lower()
        has_stray = bool(jamos)
        lone_vowel = any(c in VOWELS and c not in COMMON_LONE_VOWELS for c in jamos)
        if has_stray and d.is_word(lower):
            return lower
        if not has_stray and len(eng) >= 4 and d.is_common(lower) and token not in KO_EXCEPTIONS:
            return lower
        if lone_vowel and len(eng) >= 4:
            return lower
        return None
    return None
