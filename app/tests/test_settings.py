"""시작 시 자동 실행 설정 (Windows 레지스트리·Mac LaunchAgent는 가짜로 바꿔 어느 OS에서나 실행)"""
import os
import plistlib
import sys
import tempfile
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'app'))
from hanyoung import settings as S  # noqa: E402
from hanyoung.engine import Settings  # noqa: E402


class AutostartTest(unittest.TestCase):
    def test_default_on(self):
        self.assertTrue(Settings().autostart)

    def test_mac_launch_agent_written_and_removed(self):
        home = tempfile.mkdtemp()
        with mock.patch.object(S.os.path, 'expanduser', lambda p: p.replace('~', home, 1)), \
                mock.patch.object(S, '_mac_app_path', lambda: '/Applications/HanYoungFix.app'):
            S._set_autostart_mac(True)
            path = os.path.join(home, 'Library', 'LaunchAgents', f'{S.MAC_AGENT_ID}.plist')
            with open(path, 'rb') as f:
                data = plistlib.load(f)
            self.assertEqual(data['ProgramArguments'], ['/usr/bin/open', '-a', '/Applications/HanYoungFix.app'])
            self.assertTrue(data['RunAtLoad'])
            S._set_autostart_mac(False)
            self.assertFalse(os.path.exists(path))

    def test_mac_app_path_from_bundle(self):
        exe = '/Applications/HanYoungFix.app/Contents/MacOS/HanYoungFix'
        with mock.patch.object(S.sys, 'executable', exe), mock.patch.object(S.os.path, 'realpath', lambda p: p):
            self.assertEqual(S._mac_app_path(), '/Applications/HanYoungFix.app')

    def test_sync_registers_only_packaged_app(self):
        calls = []
        with mock.patch.object(S, 'set_autostart', lambda on: calls.append(on)):
            with mock.patch.object(S.sys, 'frozen', False, create=True):
                self.assertFalse(S.sync_autostart(Settings()))           # 소스 실행: 등록 안 함
            with mock.patch.object(S.sys, 'frozen', True, create=True):
                self.assertFalse(S.sync_autostart(Settings(autostart=False)))  # 꺼 둠: 등록 안 함
                self.assertTrue(S.sync_autostart(Settings()))            # exe/app: 지금 위치로 등록
        self.assertEqual(calls, [True])

    def test_windows_command_is_exe_path(self):
        with mock.patch.object(S.sys, 'frozen', True, create=True), \
                mock.patch.object(S.sys, 'executable', r'C:\Users\me\Desktop\HanYoungFix.exe'):
            self.assertEqual(S.launch_command(), r'"C:\Users\me\Desktop\HanYoungFix.exe"')


if __name__ == '__main__':
    unittest.main()


class DefaultTrustTest(unittest.TestCase):
    """한/영 상태를 제대로 알려 주는 것을 확인한 브라우저는 한/영 키를 누르기 전에도 교정"""

    def test_new_install_trusts_browsers(self):
        store = S.Store(os.path.join(tempfile.mkdtemp(), 'settings.json'))
        # 2026-11-23 실측: 주소창에서 한/영 상태를 바로 알려 주고 교정이 되는 브라우저
        for exe in ('chrome.exe', 'msedge.exe', 'whale.exe', 'brave.exe', 'opera.exe', 'vivaldi.exe',
                    'comet.exe', 'ego.exe', 'aside.exe', 'nortonbrowser.exe', 'firefox.exe'):
            self.assertIs(store.trusted_apps.get(exe), True, exe)

    def test_existing_settings_gain_edge_but_keep_learned_false(self):
        path = os.path.join(tempfile.mkdtemp(), 'settings.json')
        with open(path, 'w', encoding='utf-8') as f:
            f.write('{"browser_by_app": true, "trusted_apps": {"chrome.exe": false, "notepad.exe": true}}')
        store = S.Store(path)
        self.assertIs(store.trusted_apps['msedge.exe'], True)
        self.assertIs(store.trusted_apps['chrome.exe'], False)  # 사용자 환경에서 확인한 결과가 우선
        self.assertIs(store.trusted_apps['notepad.exe'], True)
