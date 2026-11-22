"""launch.py가 띄운 앱만 끄고(pid 파일 기준, 이름으로 죽이지 않음) 임시 인스턴스 폴더를 지움.
증거 폴더(verify-evidence/)는 지우지 않음.

사용: python .claude/skills/verify/scripts/cleanup.py
"""
import os
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402

pid = common.read_pid()
if pid and common.pid_alive(pid):
    subprocess.run(['taskkill', '/PID', str(pid), '/T', '/F'], capture_output=True)
    print('killed', pid, 'alive after:', common.pid_alive(pid))
else:
    print('no verify app running')
shutil.rmtree(common.INSTANCE, ignore_errors=True)
print('removed', common.INSTANCE, '| evidence kept in', common.EVIDENCE)
