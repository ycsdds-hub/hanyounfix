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
