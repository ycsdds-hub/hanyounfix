"""최근 교정 기록"""
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'app'))
sys.path.insert(0, os.path.join(ROOT, 'app', 'tests'))
from hanyoung.engine import EN, KO  # noqa: E402
from hanyoung.history import History  # noqa: E402
from test_engine import Harness  # noqa: E402


def harness_with_log(mode, **settings):
    h = Harness(mode, **settings)
    log = []
    h.engine.on_fix = log.append
    return h, log


class EngineRecordTest(unittest.TestCase):
    def test_fix_is_recorded_with_app_and_mode(self):
        h, log = harness_with_log(EN, check_length=30)
        h.type('dkssud ')
        self.assertEqual(log, [{'kind': 'fix', 'before': 'dkssud', 'after': '안녕', 'mode': EN, 'app': 'notepad.exe'}])

    def test_korean_mode_fix_and_undo(self):
        h, log = harness_with_log(KO)
        h.type('hello ')
        h.key(0x5A, ctrl=True)
        self.assertEqual([e['kind'] for e in log], ['fix', 'undo'])
        self.assertEqual((log[0]['before'], log[0]['after']), ('ㅗ디ㅣㅐ', 'hello'))
        self.assertEqual((log[1]['before'], log[1]['after']), ('hello', 'ㅗ디ㅣㅐ'))

    def test_keep_is_recorded(self):
        h, log = harness_with_log(KO)
        h.type('hello ')
        for _ in range(6):
            h.key(0x08)
        h.key(0x15)
        h.type('hello ')
        self.assertEqual(log[-1]['kind'], 'keep')
        self.assertEqual(log[-1]['before'], 'ㅗ디ㅣㅐ')

    def test_real_words_not_recorded(self):
        h, log = harness_with_log(EN)
        h.type('hello world ')
        self.assertEqual(log, [])


class HistoryFileTest(unittest.TestCase):
    def test_keeps_last_20_and_survives_restart(self):
        p = os.path.join(tempfile.mkdtemp(), 'recent.json')
        h = History(p)
        for i in range(25):
            h.add({'kind': 'fix', 'before': f'w{i}', 'after': f'x{i}', 'mode': 'en', 'app': 'notepad.exe'})
        h2 = History(p)
        self.assertEqual(len(h2.items), 20)
        lines = h2.lines()
        self.assertIn('w24 → x24', lines[0])     # 최근 것부터
        self.assertIn('notepad.exe', lines[0])
        self.assertIn('영어 모드', lines[0])
        self.assertIn('w5 → x5', lines[-1])


if __name__ == '__main__':
    unittest.main()
