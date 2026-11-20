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
print('smoke ok')
