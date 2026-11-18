import json
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'windows'))
from hanyoung.core import Dictionary, decide, eng_to_hangul, hangul_to_eng  # noqa: E402

CASES = json.load(open(os.path.join(ROOT, 'test', 'cases.json'), encoding='utf-8'))
DICT = Dictionary.load(os.path.join(ROOT, 'extension'))


class CoreTest(unittest.TestCase):
    def test_convert(self):
        for keys, hangul in CASES['convert']:
            self.assertEqual(eng_to_hangul(keys), hangul, keys)
            self.assertEqual(eng_to_hangul(hangul_to_eng(hangul)), hangul)

    def test_decide_shared_cases(self):
        for token, mid, expect in CASES['decide']:
            self.assertEqual(decide(token, DICT, mid_word=mid), expect, f'{token} mid={mid}')

    def test_mid_word_never_breaks_long_english(self):
        bad = [w for w in DICT.sorted if len(w) >= 7 and decide(w[:6], DICT, mid_word=True)]
        self.assertEqual(bad[:10], [])

    def test_user_words(self):
        d = Dictionary(DICT.sorted, DICT.common, {'dkssud'})
        self.assertIsNone(decide('dkssud', d))


if __name__ == '__main__':
    unittest.main()
