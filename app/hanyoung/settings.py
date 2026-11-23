"""설정 저장과 시작 시 자동 실행

- Windows: %APPDATA%\\HanYoungFix\\settings.json, 레지스트리 Run 키
- macOS: ~/Library/Application Support/HanYoungFix/settings.json, ~/Library/LaunchAgents
"""
from __future__ import annotations

import json
import os
import sys
import threading
from dataclasses import asdict, fields

from .engine import Settings

APP_NAME = 'HanYoungFix'
RUN_KEY = r'Software\Microsoft\Windows\CurrentVersion\Run'


IS_MAC = sys.platform == 'darwin'
OLD_DEFAULT_EXCLUDED = {'chrome.exe', 'google chrome'}  # 예전 기본 제외 앱 (한 번만 지움)
# 한/영 키를 누르기 전부터 믿는 프로그램 (Windows). 주소창에서 한/영 상태를 바로(20ms 안) 알려 주고
# 교정이 되는 것을 실측한 Chromium 계열 브라우저 (2026-11-23, .claude/skills/verify/scripts/browsers.py).
# Firefox는 측정하지 못해 넣지 않음. 사용자가 확인 못 함(False)으로 배운 값이 있으면 그 값이 우선
DEFAULT_TRUSTED = ('chrome.exe', 'msedge.exe', 'whale.exe', 'brave.exe', 'opera.exe', 'vivaldi.exe',
                   'comet.exe', 'ego.exe', 'aside.exe', 'nortonbrowser.exe')
MAC_AGENT_ID = 'com.hanyoungfix.app'


def config_dir() -> str:
    if IS_MAC:
        base = os.path.expanduser('~/Library/Application Support')
    else:
        base = os.environ.get('APPDATA') or os.path.expanduser('~')
    path = os.path.join(base, APP_NAME)
    os.makedirs(path, exist_ok=True)
    return path


class Store:
    def __init__(self, path: str | None = None):
        self.path = path or os.path.join(config_dir(), 'settings.json')
        self.lock = threading.Lock()
        self.settings = Settings()
        self.trusted_apps: dict[str, bool] = {}
        self.load()
        for app in DEFAULT_TRUSTED:
            self.trusted_apps.setdefault(app, True)
        if self._migrated:
            self.save()  # 바뀐 기본값을 설정 파일에도 바로 반영

    def load(self):
        self._migrated = False
        try:
            with open(self.path, encoding='utf-8') as f:
                data = json.load(f)
        except (OSError, ValueError):
            return
        names = {f.name for f in fields(Settings)}
        for k, v in data.items():
            if k in names:
                setattr(self.settings, k, v)
        self.trusted_apps = {k.lower(): bool(v) for k, v in data.get('trusted_apps', {}).items()}
        s = self.settings
        if not data.get('browser_by_app'):
            # 예전 기본값(Chrome은 확장이 맡음)이면 지움: 확장은 주소창을 못 고치므로 이제 앱이 맡음
            s.excluded_apps = [a for a in s.excluded_apps if a.lower() not in OLD_DEFAULT_EXCLUDED]
            self._migrated = True
        s.check_length = max(4, min(30, int(s.check_length)))
        s.excluded_apps = [a.lower() for a in s.excluded_apps]

    def save(self):
        with self.lock:
            data = asdict(self.settings)
            data['trusted_apps'] = self.trusted_apps
            data['browser_by_app'] = True
            tmp = self.path + '.tmp'
            with open(tmp, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(tmp, self.path)


def launch_command() -> str:
    if getattr(sys, 'frozen', False):
        return f'"{sys.executable}"'
    pyw = os.path.join(os.path.dirname(sys.executable), 'pythonw.exe')
    main = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'main.py'))
    return f'"{pyw if os.path.exists(pyw) else sys.executable}" "{main}"'


def _mac_app_path() -> str | None:
    """실행 중인 .app 번들 경로 (.../HanYoungFix.app). 소스로 실행 중이면 None"""
    exe = os.path.realpath(sys.executable)
    marker = '.app/Contents/MacOS/'
    return exe[:exe.index(marker) + 4] if marker in exe else None


def _set_autostart_mac(on: bool):
    import plistlib
    path = os.path.expanduser(f'~/Library/LaunchAgents/{MAC_AGENT_ID}.plist')
    if not on:
        if os.path.exists(path):
            os.remove(path)
        return
    app = _mac_app_path()
    if app:
        args = ['/usr/bin/open', '-a', app]
    else:
        main = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'main.py'))
        args = [sys.executable, main]
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'wb') as f:
        plistlib.dump({'Label': MAC_AGENT_ID, 'ProgramArguments': args, 'RunAtLoad': True}, f)


def set_autostart(on: bool):
    if IS_MAC:
        _set_autostart_mac(on)
        return
    import winreg
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
        if on:
            winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, launch_command())
        else:
            try:
                winreg.DeleteValue(key, APP_NAME)
            except FileNotFoundError:
                pass


def sync_autostart(settings) -> bool:
    """설정에서 자동 실행이 켜져 있으면 지금 실행 중인 exe/app 위치로 다시 등록 (파일을 옮겨도 따라감).
    소스로 실행할 때(개발 중)는 등록하지 않음. 등록했으면 True"""
    if not settings.autostart or not getattr(sys, 'frozen', False):
        return False
    try:
        set_autostart(True)
        return True
    except OSError as e:
        print('자동 실행 등록 실패:', e)
        return False
