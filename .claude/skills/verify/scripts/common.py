"""verify 스크립트들이 같이 쓰는 경로와 상수"""
import os
import sys
import tempfile

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..'))
APP_DIR = os.path.join(REPO, 'app')
sys.path.insert(0, APP_DIR)
for _s in (sys.stdout, sys.stderr):
    if _s and hasattr(_s, 'reconfigure'):
        _s.reconfigure(encoding='utf-8', errors='replace')  # 한국어 Windows 콘솔(cp949)에서도 깨지지 않게

# 검증용 인스턴스 상태 (지워도 되는 것): 격리된 APPDATA, pid, 로그
INSTANCE = os.path.join(tempfile.gettempdir(), 'hanyoung-verify')
APPDATA = os.path.join(INSTANCE, 'appdata')
CONFIG = os.path.join(APPDATA, 'HanYoungFix')   # settings.json, recent.json
PID_FILE = os.path.join(INSTANCE, 'app.pid')
LOG_FILE = os.path.join(INSTANCE, 'app.log')

# 증거 (cleanup이 지우지 않음, .gitignore 대상)
EVIDENCE = os.path.join(REPO, 'verify-evidence')

PORT = 47322                      # 사용자 앱(47321)과 겹치지 않는 상태 서버 포트
MUTEX = 'Local\\HanYoungFix-verify'  # 사용자 앱의 Local\\HanYoungFix 와 다른 이름
USER_PORT = 47321


def get_status(port, timeout=1.0):
    import json
    import urllib.request
    try:
        with urllib.request.urlopen(f'http://127.0.0.1:{port}/status', timeout=timeout) as r:
            return json.loads(r.read())
    except Exception:  # noqa: BLE001
        return None


def pid_alive(pid):
    import ctypes
    k = ctypes.windll.kernel32
    h = k.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not h:
        return False
    code = ctypes.c_ulong()
    k.GetExitCodeProcess(h, ctypes.byref(code))
    k.CloseHandle(h)
    return code.value == 259  # STILL_ACTIVE


def read_pid():
    try:
        with open(PID_FILE) as f:
            return int(f.read().strip())
    except (OSError, ValueError):
        return None
