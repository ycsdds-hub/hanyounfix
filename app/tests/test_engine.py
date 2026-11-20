"""가짜 한글 IME + 텍스트 상자로 엔진 전체 동작을 시험합니다."""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'app'))
from hanyoung.core import Dictionary, eng_to_hangul, ime_keys  # noqa: E402
from hanyoung.engine import EN, KO, Engine, Key, KeyEvent, Platform, Settings  # noqa: E402

DICT_FILES = Dictionary.load(os.path.join(ROOT, 'extension'))
CHAR2VK = {' ': 0x20, '\n': 0x0D, ',': 0xBC, '.': 0xBE, '1': 0x31, '-': 0xBD}


class FakeIME:
    """두벌식 IME 흉내: 한글 모드에서는 조합 중인 키를 모아 두었다가 확정"""

    def __init__(self, mode=EN):
        self.mode, self.text, self.comp = mode, '', []

    def commit(self):
        self.text += eng_to_hangul(ime_keys(''.join(self.comp)))
        self.comp = []

    @property
    def screen(self):
        return self.text + eng_to_hangul(ime_keys(''.join(self.comp)))

    def press(self, vk, shift=False):
        if 0x41 <= vk <= 0x5A:
            ch = chr(vk) if shift else chr(vk).lower()
            if self.mode == EN:
                self.text += ch
            else:
                self.comp.append(ch)
        elif vk == 0x08:
            if self.comp:
                self.comp.pop()
            else:
                self.text = self.text[:-1]
        elif vk == 0x15:
            self.commit()
            self.mode = KO if self.mode == EN else EN
        else:
            self.commit()
            self.text += {0x20: ' ', 0x0D: '\n', 0xBC: ',', 0xBE: '.', 0x31: '!' if shift else '1', 0xBD: '-'}[vk]


class FakePlatform(Platform):
    def __init__(self, ime, toggle_works=True):
        self.ime, self.toggle_works, self.later, self.engine = ime, toggle_works, [], None
        self.mode_known = True

    def get_mode(self):
        return self.ime.mode if self.mode_known else None

    def send_backspace(self, n):
        for _ in range(n):
            self.ime.press(0x08)

    def send_toggle(self):
        if self.toggle_works:
            self.ime.press(0x15)
        else:
            self.ime.commit()

    def send_keys(self, keys):
        for k in keys:
            self.ime.press(k.vk, k.shift)

    def replay(self, events):
        for ev in events:
            ev.source = 'replay'
            if not self.engine.handle(ev) and ev.down:
                self.ime.press(ev.vk, ev.shift)

    def run_later(self, fn):
        self.later.append(fn)


class Harness:
    def __init__(self, mode=EN, toggle_works=True, **settings):
        self.ime = FakeIME(mode)
        self.p = FakePlatform(self.ime, toggle_works)
        self.notes = []
        self.engine = Engine(self.p, Dictionary(DICT_FILES.sorted, DICT_FILES.common), Settings(**settings),
                             notify=lambda b, a, m=None: self.notes.append((b, a, m)))
        self.p.engine = self.engine
        self.app = 'notepad.exe'
        self.window = 1

    def key(self, vk, shift=False, ctrl=False, run=True):
        ev = KeyEvent(vk, True, shift=shift, ctrl=ctrl, app=self.app, window=self.window)
        if not self.engine.handle(ev):
            self.ime.press(vk, shift)
        self.engine.handle(KeyEvent(vk, False, shift=shift, app=self.app, window=self.window))
        if run:
            self.run()

    def run(self):
        while self.p.later:
            self.p.later.pop(0)()

    def type(self, s, run=True):
        """s: 누를 키 (영문자는 물리 키, 대문자는 Shift)"""
        for ch in s:
            if ch.isascii() and ch.isalpha():
                self.key(ord(ch.upper()), shift=ch.isupper(), run=run)
            elif ch == '!':
                self.key(0x31, shift=True, run=run)
            else:
                self.key(CHAR2VK[ch], run=run)


class EngineTest(unittest.TestCase):
    def test_english_mode_hangul_fixed_at_space(self):
        h = Harness(EN, check_length=30)
        h.type('gksrmf ')
        self.assertEqual(h.ime.screen, '한글 ')
        self.assertEqual(h.ime.mode, KO)

    def test_mid_word_at_6_and_continue_typing(self):
        h = Harness(EN)
        h.type('dkssud')
        self.assertEqual(h.ime.screen, '안녕')
        self.assertEqual(h.ime.mode, KO)
        h.type('gktpdy ')
        self.assertEqual(h.ime.screen, '안녕하세요 ')

    def test_fast_typing_during_fix_is_replayed_in_order(self):
        h = Harness(EN)
        h.type('dkssudgktpdy ', run=False)   # 교정이 끝나기 전에 계속 침
        h.run()
        self.assertEqual(h.ime.screen, '안녕하세요 ')

    def test_korean_mode_english_fixed(self):
        h = Harness(KO)
        h.type('hello world ')
        self.assertEqual(h.ime.screen, 'hello world ')
        self.assertEqual(h.ime.mode, EN)

    def test_real_words_untouched(self):
        h = Harness(EN)
        h.type('hello abandoned internationalization strongly ')
        self.assertEqual(h.ime.screen, 'hello abandoned internationalization strongly ')
        h2 = Harness(KO)
        h2.type('dkssudgktpdy zzz ahem ')   # 안녕하세요 ㅋㅋㅋ 모드
        self.assertEqual(h2.ime.screen, '안녕하세요 ㅋㅋㅋ 모드 ')

    def test_enter_and_punctuation(self):
        h = Harness(EN, check_length=30)
        h.type('dkssud, tkfkdgo!\n')
        self.assertEqual(h.ime.screen, '안녕, 사랑해!\n')

    def test_backspace_inside_word(self):
        h = Harness(EN, check_length=30)
        h.type('gksrmx')
        h.key(0x08)
        h.type('f ')
        self.assertEqual(h.ime.screen, '한글 ')

    def test_digits_block_word(self):
        h = Harness(EN)
        h.type('abc1dkssud ')
        self.assertEqual(h.ime.screen, 'abc1dkssud ')

    def test_undo_restores_and_learns(self):
        h = Harness(EN, check_length=30)
        h.type('rkawk ')
        self.assertEqual(h.ime.screen, '감자 ')
        h.key(0x5A, ctrl=True)
        self.assertEqual(h.ime.screen, 'rkawk ')
        self.assertEqual(h.ime.mode, EN)
        self.assertIn('rkawk', h.engine.settings.user_words)
        h.type('rkawk ')
        self.assertEqual(h.ime.screen, 'rkawk rkawk ')

    def test_undo_korean_to_english(self):
        h = Harness(KO)
        h.type('hello ')
        h.key(0x5A, ctrl=True)
        self.assertEqual(h.ime.screen, 'ㅗ디ㅣㅐ ')
        self.assertEqual(h.ime.mode, KO)

    def test_ctrl_z_after_typing_is_normal_undo(self):
        h = Harness(EN, check_length=30)
        h.type('rkawk a')
        ev = KeyEvent(0x5A, ctrl=True, app=h.app, window=1)
        self.assertFalse(h.engine.handle(ev))   # 앱의 원래 Ctrl+Z로 전달

    def test_toggle_failure_leaves_text_unchanged(self):
        h = Harness(EN, toggle_works=False, check_length=30)
        h.type('dkssud ')
        self.assertEqual(h.ime.screen, 'dkssud ')

    def test_unknown_mode_does_nothing(self):
        h = Harness(EN, check_length=30)
        h.p.mode_known = False
        h.type('dkssud ')
        self.assertEqual(h.ime.screen, 'dkssud ')

    def test_excluded_app_and_disabled(self):
        h = Harness(EN)
        h.app = 'chrome.exe'
        h.type('dkssud ')
        self.assertEqual(h.ime.screen, 'dkssud ')
        h2 = Harness(EN, enabled=False)
        h2.type('dkssud ')
        self.assertEqual(h2.ime.screen, 'dkssud ')

    def test_hotkey_toggles(self):
        h = Harness(EN)
        self.assertTrue(h.engine.handle(KeyEvent(0x48, ctrl=True, alt=True, window=1)))
        self.assertFalse(h.engine.settings.enabled)

    def test_shift_double_consonant(self):
        h = Harness(EN, check_length=30)
        h.type('Rhc ')
        self.assertEqual(h.ime.screen, '꽃 ')

    def test_toast(self):
        h = Harness(EN, check_length=30)
        h.type('dkssud ')
        self.assertEqual(h.notes[0][:2], ('dkssud', '안녕'))


class ContextTest(unittest.TestCase):
    """문맥 교정: 뒤 단어가 교정될 때 혼자서는 건너뛴 앞의 짧은 단어도 함께"""

    def test_short_english_words_fixed_with_next_word(self):
        h = Harness(KO)
        h.type('go to job ')
        self.assertEqual(h.ime.screen, 'go to job ')
        self.assertEqual(h.ime.mode, EN)
        self.assertEqual(h.notes[0][:2], ('해 새 ㅓㅐㅠ', 'go to job'))

    def test_short_words_alone_untouched(self):
        h = Harness(KO)
        h.type('go to ')
        self.assertEqual(h.ime.screen, '해 새 ')

    def test_only_adjacent_words_that_qualify(self):
        h = Harness(KO)
        h.type('dkssud go job ')   # 안녕(진짜 한글)은 그대로, go만 함께
        self.assertEqual(h.ime.screen, '안녕 go job ')

    def test_context_stops_at_punctuation_or_enter(self):
        h = Harness(KO)
        h.type('go. job ')
        self.assertEqual(h.ime.screen, '해. job ')

    def test_english_mode_short_korean_with_next_word(self):
        h = Harness(EN, check_length=30)
        h.type('sk dkssud ')
        self.assertEqual(h.ime.screen, '나 안녕 ')
        self.assertEqual(h.ime.mode, KO)

    def test_context_with_mid_word_fix(self):
        h = Harness(EN)                # 기본 6글자 중간 교정에서도 앞 단어를 함께
        h.type('sk dkssud')
        self.assertEqual(h.ime.screen, '나 안녕')
        h.type('gktpdy ')
        self.assertEqual(h.ime.screen, '나 안녕하세요 ')

    def test_undo_context_fix(self):
        h = Harness(KO)
        h.type('go to job ')
        h.key(0x5A, ctrl=True)
        self.assertEqual(h.ime.screen, '해 새 ㅓㅐㅠ ')
        self.assertEqual(h.ime.mode, KO)
        self.assertIn('ㅓㅐㅠ', h.engine.settings.user_words)


class RetypeTest(unittest.TestCase):
    """고친 단어를 지우고 원래 모드로 다시 쓰면 일부러 쓴 것으로 보고 그대로 둠"""

    def _kept_hello(self):
        """한글 모드로 hello → 교정 → 지우고 그 자리에 다시 씀 → 그대로"""
        h = Harness(KO)
        t = [0.0]
        h.engine.clock = lambda: t[0]
        h.type('hello ')
        self.assertEqual(h.ime.screen, 'hello ')
        for _ in range(6):
            h.key(0x08)
        h.key(0x15)                    # 한/영을 원래대로
        h.type('hello ')
        self.assertEqual(h.ime.screen, 'ㅗ디ㅣㅐ ')
        self.assertEqual(h.engine.settings.user_words, [])   # 영구히 배우지는 않음
        return h, t                    # 지금은 한글 모드

    def test_kept_word_stays_in_same_window_for_10_minutes(self):
        h, t = self._kept_hello()
        t[0] = 300.0                   # 5분 뒤 같은 창
        h.type('hello ')
        self.assertEqual(h.ime.screen, 'ㅗ디ㅣㅐ ㅗ디ㅣㅐ ')
        t[0] = 300.0 + 601            # 마지막으로 쓴 뒤 10분 넘게 지남
        h.type('hello ')
        self.assertEqual(h.ime.screen, 'ㅗ디ㅣㅐ ㅗ디ㅣㅐ hello ')

    def test_kept_word_in_other_window_only_1_minute(self):
        h, t = self._kept_hello()
        h.window = 2                   # 다른 창
        h.ime.text, h.ime.comp = '', []
        t[0] = 30.0
        h.type('hello ')
        self.assertEqual(h.ime.screen, 'ㅗ디ㅣㅐ ')     # 1분 안: 그대로
        h.window = 3
        h.ime.text, h.ime.comp = '', []
        t[0] = 120.0
        h.type('hello ')
        self.assertEqual(h.ime.screen, 'hello ')       # 1분 지남: 고침

    def test_retype_elsewhere_after_other_word_is_fixed(self):
        h = Harness(KO)
        h.type('hello ')
        for _ in range(6):
            h.key(0x08)
        h.type('dkssud ')              # 다른 단어(안녕)를 먼저 씀 → 그 자리가 아님
        h.key(0x15)
        h.type('hello ')
        self.assertEqual(h.ime.screen, '안녕 hello ')

    def test_repeating_same_mistake_without_erasing_is_fixed(self):
        h = Harness(KO)
        h.type('hello ')
        h.key(0x15)
        h.type('hello ')
        self.assertEqual(h.ime.screen, 'hello hello ')
        self.assertEqual(h.engine.settings.user_words, [])

    def test_retype_long_word_skips_mid_word_fix(self):
        h = Harness(EN)
        h.type('dkssudgktpdy ')
        self.assertEqual(h.ime.screen, '안녕하세요 ')
        for _ in range(6):
            h.key(0x08)
        h.key(0x15)
        h.type('dkssudgktpdy ')
        self.assertEqual(h.ime.screen, 'dkssudgktpdy ')

    def test_retype_after_window_expires_is_fixed(self):
        h = Harness(KO)
        t = [0.0]
        h.engine.clock = lambda: t[0]
        h.type('hello ')
        for _ in range(6):
            h.key(0x08)
        h.key(0x15)
        t[0] = 120.0
        h.type('hello ')
        self.assertEqual(h.ime.screen, 'hello ')

    def test_retyped_word_not_used_as_context(self):
        h = Harness(KO)
        h.type('go to job ')
        for _ in range(10):
            h.key(0x08)
        h.key(0x15)
        h.type('go to job ')           # 전체를 다시 씀 → 모두 그대로
        self.assertEqual(h.ime.screen, '해 새 ㅓㅐㅠ ')


if __name__ == '__main__':
    unittest.main()
