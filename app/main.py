"""한영 오타 자동 교정 - Windows / macOS 앱

실행: pythonw main.py (Windows) / python3 main.py (macOS)
      또는 빌드된 HanYoungFix.exe / HanYoungFix.app
Windows는 작업 표시줄 오른쪽 아이콘, macOS는 메뉴 막대 아이콘에서 켜기/끄기, 설정, 종료를 할 수 있습니다.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from hanyoung.core import Dictionary  # noqa: E402
from hanyoung.engine import Engine  # noqa: E402
from hanyoung.settings import Store, config_dir  # noqa: E402


def _log_to_file(always=False):
    # 콘솔이 없는 exe/app에서는 오류를 파일로 남김
    if always or sys.stdout is None or sys.stderr is None:
        log = open(os.path.join(config_dir(), 'log.txt'), 'a', encoding='utf-8', buffering=1)
        sys.stdout = sys.stderr = log


def main_windows():
    from hanyoung import win32
    from hanyoung.ui import App

    _log_to_file()
    if not win32.single_instance():
        win32.user32.MessageBoxW(None, '이미 실행 중이에요. 작업 표시줄 오른쪽 아이콘을 확인하세요.', '한영 오타 자동 교정', 0x40)
        return

    store = Store()
    dictionary = Dictionary.load()
    app = App(store)

    def on_trust(name, ok):
        store.trusted_apps[name] = ok
        app.post(store.save)

    platform = win32.WindowsPlatform(store.trusted_apps, on_trust=on_trust)
    engine = Engine(
        platform, dictionary, store.settings,
        notify=app.notify,
        on_learn=lambda word: app.post(store.save),
        on_toggle=lambda enabled: app.post(lambda: app.on_toggled(enabled)),
    )
    platform.engine = engine
    app.engine, app.platform = engine, platform

    hooks = win32.Hooks(engine, platform)
    hooks.start()
    if not store.trusted_apps:
        app.notify(None, None, '한영 자동 교정 시작! 쓰는 프로그램에서 한/영 키를 한 번 눌러 주세요')
    try:
        app.run()
    finally:
        hooks.stop()


def main_mac():
    from hanyoung import mac
    from hanyoung.ui_mac import MacApp

    _log_to_file(always=getattr(sys, 'frozen', False))
    if not mac.single_instance(os.path.join(config_dir(), 'app.lock')):
        print('이미 실행 중이에요. 메뉴 막대 아이콘을 확인하세요.')
        return

    store = Store()
    dictionary = Dictionary.load()
    app = MacApp(store)
    platform = mac.MacPlatform()  # 메인 스레드에서 만들어야 입력 소스 알림을 받음
    engine = Engine(
        platform, dictionary, store.settings,
        notify=app.notify,
        on_learn=lambda word: app.post(store.save),
        on_toggle=lambda enabled: app.post(lambda: app.on_toggled(enabled)),
    )
    platform.engine = engine
    app.engine, app.platform = engine, platform

    hooks = mac.Hooks(engine, platform)
    app.hooks = hooks
    perms = mac.has_permissions(prompt=True)
    if not hooks.start():
        print('키보드 감시를 시작하지 못함 (권한 필요):', perms)
        app.need_permission()
    try:
        app.run()
    finally:
        hooks.stop()


def main():
    if sys.platform == 'win32':
        main_windows()
    elif sys.platform == 'darwin':
        main_mac()
    else:
        sys.exit('Windows와 macOS에서만 동작해요. 다른 환경에서는 extension 폴더의 Chrome 확장을 쓰세요.')


if __name__ == '__main__':
    main()
