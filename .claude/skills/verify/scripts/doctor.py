"""읽기만 하는 상태 점검: 검증용 인스턴스를 몰아도 되는지. 마지막 줄이 OK 또는 NOT OK.

사용: python .claude/skills/verify/scripts/doctor.py
"""
import ctypes
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402

problems = []
pid = common.read_pid()
alive = bool(pid and common.pid_alive(pid))
print('verify app pid:', pid, 'alive' if alive else 'NOT running')
if not alive:
    problems.append('verify app not running (launch.py)')
st = common.get_status(common.PORT)
print(f'status :{common.PORT}:', st)
if not (st and st.get('app') == 'HanYoungFix'):
    problems.append('status server not answering')
elif not st.get('enabled'):
    problems.append('correction disabled in verify instance')
layout = ctypes.windll.user32.GetKeyboardLayout(0) & 0xFFFF
print('keyboard layout:', hex(layout), '(Korean)' if layout == 0x412 else '(NOT Korean: ime_mode는 None, 교정 안 됨)')
if layout != 0x412:
    problems.append('Korean keyboard layout not active')
print('config dir:', common.CONFIG, 'exists' if os.path.isdir(common.CONFIG) else 'missing')
print(f'user app :{common.USER_PORT}:', common.get_status(common.USER_PORT),
      '(사용자 앱. 주입 키는 무시하므로 같이 켜져 있어도 됨)')
if os.path.exists(common.LOG_FILE):
    with open(common.LOG_FILE, encoding='utf-8', errors='replace') as f:
        tail = f.read()[-800:].strip()
    if tail:
        print('log tail:\n' + tail)
print('OK' if not problems else 'NOT OK: ' + '; '.join(problems))
sys.exit(1 if problems else 0)
