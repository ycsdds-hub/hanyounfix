"""설정 저장(%APPDATA%\\HanYoungFix\\settings.json)과 윈도우 시작 시 자동 실행"""
from __future__ import annotations

import json
import os
import sys
import threading
from dataclasses import asdict, fields

from .engine import Settings

APP_NAME = 'HanYoungFix'
RUN_KEY = r'Software\Microsoft\Windows\CurrentVersion\Run'


def config_dir() -> str:
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

    def load(self):
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
        s.check_length = max(4, min(30, int(s.check_length)))
        s.excluded_apps = [a.lower() for a in s.excluded_apps]

    def save(self):
        with self.lock:
            data = asdict(self.settings)
            data['trusted_apps'] = self.trusted_apps
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


def set_autostart(on: bool):
    import winreg
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
        if on:
            winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, launch_command())
        else:
            try:
                winreg.DeleteValue(key, APP_NAME)
            except FileNotFoundError:
                pass
