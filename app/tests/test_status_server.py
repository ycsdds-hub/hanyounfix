"""Chrome 확장이 앱 상태를 묻는 로컬 서버"""
import json
import os
import sys
import unittest
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'app'))
from hanyoung import status_server  # noqa: E402
from hanyoung.settings import Store  # noqa: E402


class StatusServerTest(unittest.TestCase):
    def test_status_and_no_cors(self):
        state = {'on': True}
        srv = status_server.start(lambda: state['on'], port=0)
        port = srv.server_address[1]
        try:
            with urllib.request.urlopen(f'http://127.0.0.1:{port}/status', timeout=2) as r:
                self.assertEqual(json.loads(r.read()), {'app': 'HanYoungFix', 'enabled': True})
                self.assertIsNone(r.headers.get('Access-Control-Allow-Origin'))  # 웹사이트는 못 읽음
            state['on'] = False
            with urllib.request.urlopen(f'http://127.0.0.1:{port}/status', timeout=2) as r:
                self.assertFalse(json.loads(r.read())['enabled'])
        finally:
            srv.shutdown()

    def test_port_in_use_returns_none(self):
        srv = status_server.start(lambda: True, port=0)
        try:
            self.assertIsNone(status_server.start(lambda: True, port=srv.server_address[1]))
        finally:
            srv.shutdown()


class BrowserDefaultTest(unittest.TestCase):
    def test_old_chrome_exclusion_removed_once(self):
        import tempfile
        p = os.path.join(tempfile.mkdtemp(), 'settings.json')
        json.dump({'excluded_apps': ['chrome.exe', 'kakaotalk.exe']}, open(p, 'w'))
        s = Store(p)
        self.assertEqual(s.settings.excluded_apps, ['kakaotalk.exe'])
        self.assertEqual(json.load(open(p))['excluded_apps'], ['kakaotalk.exe'])  # 파일에도 바로 반영
        s.settings.excluded_apps.append('chrome.exe')   # 사용자가 다시 넣으면 그대로 둠
        s.save()
        self.assertEqual(Store(p).settings.excluded_apps, ['kakaotalk.exe', 'chrome.exe'])

    def test_new_install_excludes_nothing(self):
        import tempfile
        self.assertEqual(Store(os.path.join(tempfile.mkdtemp(), 'settings.json')).settings.excluded_apps, [])


if __name__ == '__main__':
    unittest.main()
