"""한영 오타 자동 교정 - Windows 앱

실행: pythonw main.py   (또는 빌드된 HanYoungFix.exe)
작업 표시줄 오른쪽 아이콘에서 켜기/끄기, 설정, 종료를 할 수 있습니다.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

if sys.platform != 'win32':
    sys.exit('이 앱은 Windows 전용이에요. Chrome에서는 extension 폴더의 확장 프로그램을 쓰세요.')

from hanyoung import win32  # noqa: E402
from hanyoung.core import Dictionary  # noqa: E402
from hanyoung.engine import Engine  # noqa: E402
from hanyoung.settings import Store, config_dir  # noqa: E402
from hanyoung.ui import App  # noqa: E402


def main():
    # pythonw/exe에는 콘솔이 없으므로 오류는 파일로 남김
    if sys.stdout is None or sys.stderr is None:
        log = open(os.path.join(config_dir(), 'log.txt'), 'a', encoding='utf-8', buffering=1)
        sys.stdout = sys.stderr = log

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


if __name__ == '__main__':
    main()
