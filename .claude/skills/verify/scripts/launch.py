"""검증용 HanYoungFix(Windows)를 소스로 띄움. 실제 main_windows()를 그대로 실행하되 네 가지만 바꿈:

1. APPDATA를 임시 폴더로 → 사용자 설정·기록(%APPDATA%\\HanYoungFix)을 건드리지 않음
2. 단일 실행 이름(mutex)과 상태 서버 포트(47322)를 따로 → 사용자 앱이 켜져 있어도 같이 뜸
3. 주입된 키(LLKHF_INJECTED)도 사용자 키로 취급 → drive.py가 SendInput으로 친 키를 앱이 처리
   (실제 키보드만 받는 판단 'user' vs 'other' 자체는 단위 테스트로만 확인됨)
4. 소스 실행이라 자동 실행(레지스트리)은 원래부터 등록하지 않음 (settings.sync_autostart)

사용: python .claude/skills/verify/scripts/launch.py   (백그라운드로 띄우고 준비되면 종료)
"""
import functools
import json
import os
import shutil
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402


def child():
    os.environ['APPDATA'] = common.APPDATA
    from hanyoung import win32, status_server
    import main as app_main
    orig_single = win32.single_instance
    win32.single_instance = lambda: orig_single(common.MUTEX)
    win32.LLKHF_INJECTED = 0  # make_event가 실행 시점에 이 값을 읽음
    status_server.start = functools.partial(status_server.start, port=common.PORT)
    app_main.main_windows()


def parent():
    pid = common.read_pid()
    if pid and common.pid_alive(pid):
        sys.exit(f'already running pid {pid} (cleanup.py 먼저)')
    if common.get_status(common.PORT):
        sys.exit(f'port {common.PORT} already answers; something else is running')
    shutil.rmtree(common.INSTANCE, ignore_errors=True)
    os.makedirs(common.CONFIG)
    # 빈 설정에서 시작 (trusted_apps 없음 → 한/영 키를 한 번 눌러야 그 프로그램에서 고침)
    with open(os.path.join(common.CONFIG, 'settings.json'), 'w', encoding='utf-8') as f:
        json.dump({'browser_by_app': True}, f)
    log = open(common.LOG_FILE, 'w', encoding='utf-8')
    env = dict(os.environ, PYTHONIOENCODING='utf-8', PYTHONUNBUFFERED='1')
    p = subprocess.Popen([sys.executable, os.path.abspath(__file__), '--child'], cwd=common.REPO,
                         stdout=log, stderr=subprocess.STDOUT, env=env,
                         creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
    with open(common.PID_FILE, 'w') as f:
        f.write(str(p.pid))
    end = time.time() + 20
    while time.time() < end:
        if p.poll() is not None:
            sys.exit(f'app exited code {p.returncode}; see {common.LOG_FILE}')
        st = common.get_status(common.PORT)
        if st and st.get('app') == 'HanYoungFix':
            print(f'READY pid {p.pid} status {st} config {common.CONFIG}')
            return
        time.sleep(0.3)
    sys.exit(f'not ready in 20s; see {common.LOG_FILE}')


if __name__ == '__main__':
    child() if '--child' in sys.argv else parent()
