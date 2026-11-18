"""한영전환 오타 교정 코어 (두벌식 기준)

- eng_to_hangul("dkssud")  -> "안녕"
- hangul_to_eng("ㅗ디ㅣㅐ") -> "hello"
- fix_text(text)           -> 토큰 단위로 오타를 감지해 교정
"""
import os
import re

# ---------- 두벌식 키 매핑 ----------
KEY2JAMO = {
    'r': 'ㄱ', 'R': 'ㄲ', 's': 'ㄴ', 'e': 'ㄷ', 'E': 'ㄸ', 'f': 'ㄹ', 'a': 'ㅁ',
    'q': 'ㅂ', 'Q': 'ㅃ', 't': 'ㅅ', 'T': 'ㅆ', 'd': 'ㅇ', 'w': 'ㅈ', 'W': 'ㅉ',
    'c': 'ㅊ', 'z': 'ㅋ', 'x': 'ㅌ', 'v': 'ㅍ', 'g': 'ㅎ',
    'k': 'ㅏ', 'o': 'ㅐ', 'i': 'ㅑ', 'O': 'ㅒ', 'j': 'ㅓ', 'p': 'ㅔ', 'u': 'ㅕ',
    'P': 'ㅖ', 'h': 'ㅗ', 'y': 'ㅛ', 'n': 'ㅜ', 'b': 'ㅠ', 'm': 'ㅡ', 'l': 'ㅣ',
}
JAMO2KEY = {v: k for k, v in KEY2JAMO.items()}

CHO = list("ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ")
JUNG = list("ㅏㅐㅑㅒㅓㅔㅕㅖㅗㅘㅙㅚㅛㅜㅝㅞㅟㅠㅡㅢㅣ")
JONG = [''] + list("ㄱㄲㄳㄴㄵㄶㄷㄹㄺㄻㄼㄽㄾㄿㅀㅁㅂㅄㅅㅆㅇㅈㅊㅋㅌㅍㅎ")

VCOMP = {('ㅗ', 'ㅏ'): 'ㅘ', ('ㅗ', 'ㅐ'): 'ㅙ', ('ㅗ', 'ㅣ'): 'ㅚ',
         ('ㅜ', 'ㅓ'): 'ㅝ', ('ㅜ', 'ㅔ'): 'ㅞ', ('ㅜ', 'ㅣ'): 'ㅟ', ('ㅡ', 'ㅣ'): 'ㅢ'}
JCOMP = {('ㄱ', 'ㅅ'): 'ㄳ', ('ㄴ', 'ㅈ'): 'ㄵ', ('ㄴ', 'ㅎ'): 'ㄶ', ('ㄹ', 'ㄱ'): 'ㄺ',
         ('ㄹ', 'ㅁ'): 'ㄻ', ('ㄹ', 'ㅂ'): 'ㄼ', ('ㄹ', 'ㅅ'): 'ㄽ', ('ㄹ', 'ㅌ'): 'ㄾ',
         ('ㄹ', 'ㅍ'): 'ㄿ', ('ㄹ', 'ㅎ'): 'ㅀ', ('ㅂ', 'ㅅ'): 'ㅄ'}
# 겹모음/겹받침 -> 키 시퀀스 (역변환용)
COMPOUND2KEYS = {v: ''.join(JAMO2KEY[c] for c in k) for k, v in {**VCOMP, **JCOMP}.items()}

VOWELS = set(JUNG)
CHO_SET, JONG_SET = set(CHO), set(JONG[1:])


def _compose(jamos):
    out, i, n = [], 0, len(jamos)
    while i < n:
        c = jamos[i]
        if c not in CHO_SET or i + 1 >= n or jamos[i + 1] not in VOWELS:
            out.append(c)  # 낱자 그대로
            i += 1
            continue
        cho, v = c, jamos[i + 1]
        i += 2
        if i < n and (v, jamos[i]) in VCOMP:
            v = VCOMP[(v, jamos[i])]
            i += 1
        jong = ''
        if i < n and jamos[i] in JONG_SET and not (i + 1 < n and jamos[i + 1] in VOWELS):
            jong = jamos[i]
            i += 1
            if (i < n and (jong, jamos[i]) in JCOMP
                    and not (i + 1 < n and jamos[i + 1] in VOWELS)):
                jong = JCOMP[(jong, jamos[i])]
                i += 1
        out.append(chr(0xAC00 + (CHO.index(cho) * 21 + JUNG.index(v)) * 28 + JONG.index(jong)))
    return ''.join(out)


def eng_to_hangul(text):
    """영문 키 입력을 한글로. 매핑 안 되는 문자는 그대로 둠."""
    return _compose([KEY2JAMO.get(ch, ch) for ch in text])


def hangul_to_eng(text):
    """한글 입력을 같은 키의 영문으로."""
    out = []
    for ch in text:
        code = ord(ch) - 0xAC00
        if 0 <= code < 11172:
            cho, rest = divmod(code, 21 * 28)
            jung, jong = divmod(rest, 28)
            parts = [CHO[cho], JUNG[jung], JONG[jong]]
        else:
            parts = [ch]
        for p in parts:
            if not p:
                continue
            out.append(COMPOUND2KEYS.get(p) or JAMO2KEY.get(p, p))
    return ''.join(out)


# ---------- 오타 감지 ----------
_FALLBACK_WORDS = set("""the be to of and a in that have it for not on with he as you do at this but his by from they we
say her she or an will my one all would there their what so up out if about who get which go me when make can like time no
just him know take people into year your good some could them see other than then now look only come its over think also
back after use two how our work first well way even new want because any these give day most us hello world python code
file test is are was were has had been am i""".split())


def _load_words():
    here = os.path.dirname(os.path.abspath(__file__))
    for path in (os.environ.get("WORDLIST", ""), os.path.join(here, "..", "extension", "words.txt"),
                 "/usr/share/dict/words", "/usr/share/dict/american-english"):
        if path and os.path.exists(path):
            with open(path, encoding="utf-8", errors="ignore") as f:
                return {w.strip().lower() for w in f if len(w.strip()) > 1}
    return _FALLBACK_WORDS


WORDS = _load_words()
HANGUL_RE = re.compile(r"[가-힣ㄱ-ㅎㅏ-ㅣ]")
ALPHA_RE = re.compile(r"^[A-Za-z]+$")


def _has_stray_jamo(s):
    return any('ㄱ' <= c <= 'ㅣ' for c in s)


def fix_token(tok):
    """토큰 하나를 검사해 필요하면 변환. (결과, 바뀌었는지) 반환."""
    # 1) 영어 모드로 쳤는데 한글이어야 했던 경우
    if ALPHA_RE.match(tok) and tok.lower() not in WORDS:
        hangul = eng_to_hangul(tok)
        if not _has_stray_jamo(hangul):       # 온전한 음절로 조합되면 한글일 가능성 높음
            return hangul, True
    # 2) 한글 모드로 쳤는데 영어여야 했던 경우
    if HANGUL_RE.search(tok):
        eng = hangul_to_eng(tok)
        if ALPHA_RE.match(eng) and (eng.lower() in WORDS or _has_stray_jamo(tok)):
            return eng, True
    return tok, False


def fix_text(text):
    parts = re.split(r"(\s+)", text)
    return ''.join(fix_token(p)[0] if p.strip() else p for p in parts)


if __name__ == "__main__":
    for s in ["dkssudgktpdy", "ㅗ디ㅣㅐ dkssud", "tkfkdgody 한글", "ㅗ디ㅣㅐ 재기ㅇ", "Hello world"]:
        print(f"{s!r:30} -> {fix_text(s)!r}")
