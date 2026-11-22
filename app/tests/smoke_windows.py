"""Windows에서만: 모듈 불러오기, 구조체 크기, 설정 저장, IME 조회가 오류 없이 되는지"""
import ctypes
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from hanyoung import win32, ui  # noqa: E402,F401
from hanyoung.core import Dictionary  # noqa: E402
from hanyoung.settings import Store  # noqa: E402

assert ctypes.sizeof(win32.INPUT) == (40 if ctypes.sizeof(ctypes.c_void_p) == 8 else 28), ctypes.sizeof(win32.INPUT)
assert ctypes.sizeof(win32.KBDLLHOOKSTRUCT) == (24 if ctypes.sizeof(ctypes.c_void_p) == 8 else 20)
d = Dictionary.load()
assert d.is_word('hello') and not d.is_word('dkssud')
s = Store(os.path.join(tempfile.mkdtemp(), 'settings.json'))
s.settings.user_words.append('test')
s.trusted_apps['notepad.exe'] = True
s.save()
s2 = Store(s.path)
assert s2.settings.user_words == ['test'] and s2.trusted_apps == {'notepad.exe': True}
print('foreground:', win32.app_name(win32.foreground()), 'mode:', win32.ime_mode())
# 오른쪽 아래 아이콘 메뉴의 '윈도우 시작 시 자동 실행' 켜기/끄기 (레지스트리는 가짜로)
from unittest import mock  # noqa: E402
from hanyoung import ui as ui_mod  # noqa: E402
calls = []
with mock.patch.object(ui_mod, 'set_autostart', lambda on: calls.append(on)):
    store = Store(os.path.join(tempfile.mkdtemp(), 'settings.json'))
    app = ui_mod.App(store)
    assert store.settings.autostart is True           # 기본 켜짐
    app.toggle_autostart()
    assert store.settings.autostart is False and calls == [False]
    assert Store(store.path).settings.autostart is False  # 저장됨
    app.toggle_autostart()
    assert store.settings.autostart is True and calls == [False, True]
    # 최근 교정 기록 창
    from hanyoung.history import History  # noqa: E402
    app.history = History(os.path.join(tempfile.mkdtemp(), 'recent.json'))
    app.history.add({'kind': 'fix', 'before': 'dkssud', 'after': '안녕', 'mode': 'en', 'app': 'notepad.exe'})
    w = app.open_history()
    w.update()
    text = w.winfo_children()[0].winfo_children()[0].get('1.0', 'end')
    assert 'dkssud → 안녕' in text and 'notepad.exe' in text, text
    w.destroy()
    app.root.destroy()
print('smoke ok')
