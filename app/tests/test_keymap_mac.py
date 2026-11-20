"""macOS 키 코드 표와 입력 소스 판별 (macOS 없이도 실행)"""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'app'))
from hanyoung.engine import BOUNDARY_VKS, VK_BACK, VK_HANGUL, VK_SPACE, VK_RETURN  # noqa: E402
from hanyoung.keymap_mac import OTHER_VK, mode_of_source, pick_source, to_mac, to_vk  # noqa: E402


class KeymapTest(unittest.TestCase):
    def test_all_letters_round_trip(self):
        for c in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ':
            vk = ord(c)
            self.assertIsNotNone(to_mac(vk), c)
            self.assertEqual(to_vk(to_mac(vk)), vk, c)

    def test_known_mac_codes(self):
        self.assertEqual(to_vk(0x00), ord('A'))
        self.assertEqual(to_vk(0x02), ord('D'))   # dkssud 의 d
        self.assertEqual(to_vk(0x28), ord('K'))
        self.assertEqual(to_vk(0x31), VK_SPACE)
        self.assertEqual(to_vk(0x24), VK_RETURN)
        self.assertEqual(to_vk(0x33), VK_BACK)

    def test_engine_keys_can_be_sent(self):
        # 엔진이 보내는 키(글자, 백스페이스, 띄어쓰기 등 경계 키)는 모두 Mac 키로 바꿀 수 있어야 함
        for vk in [VK_BACK, *BOUNDARY_VKS]:
            self.assertIsNotNone(to_mac(vk), hex(vk))

    def test_unknown_key_breaks_word_not_toggle(self):
        self.assertEqual(to_vk(0x7A), OTHER_VK)          # F1
        self.assertNotIn(VK_HANGUL, [to_vk(c) for c in range(0x80)])  # 어떤 키도 한/영으로 오인하지 않음


class SourceTest(unittest.TestCase):
    def test_modes(self):
        self.assertEqual(mode_of_source('com.apple.inputmethod.Korean.2SetKorean'), 'ko')
        self.assertEqual(mode_of_source('com.apple.inputmethod.Korean.2SetKoreanStandard'), 'ko')
        self.assertIsNone(mode_of_source('com.apple.inputmethod.Korean.390Sebulshik'))   # 세벌식: 키 배치가 달라 교정 안 함
        self.assertEqual(mode_of_source('com.apple.inputmethod.Korean.Roman'), 'en')
        self.assertEqual(mode_of_source('com.apple.keylayout.ABC'), 'en')
        self.assertEqual(mode_of_source('com.apple.keylayout.US'), 'en')
        self.assertIsNone(mode_of_source('com.apple.keylayout.Dvorak'))
        self.assertIsNone(mode_of_source('com.apple.inputmethod.Kotoeri.RomajiTyping.Japanese'))
        self.assertIsNone(mode_of_source(''))

    def test_pick(self):
        ids = ['com.apple.keylayout.ABC', 'com.apple.inputmethod.Korean.2SetKorean']
        self.assertEqual(pick_source(ids, 'ko'), 'com.apple.inputmethod.Korean.2SetKorean')
        self.assertEqual(pick_source(ids, 'en'), 'com.apple.keylayout.ABC')
        ids2 = ['com.apple.keylayout.US', 'com.apple.keylayout.British', 'com.apple.inputmethod.Korean.2SetKorean']
        self.assertEqual(pick_source(ids2, 'en', preferred_en='com.apple.keylayout.British'), 'com.apple.keylayout.British')
        self.assertIsNone(pick_source(['com.apple.keylayout.ABC'], 'ko'))   # 한국어 입력기가 없음


if __name__ == '__main__':
    unittest.main()
