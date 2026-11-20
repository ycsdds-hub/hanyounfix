"""macOS 실제 타이핑 확인 (CI용): 한국어 두벌식을 켜고, TextEdit에 사람처럼 쳐서 교정 결과를 읽음

전제: HanYoungFix 앱이 이미 실행 중이고 손쉬운 사용·입력 모니터링 권한이 있음 (GitHub macOS 러너는 허용됨)
사용: python app/tests/e2e_mac.py
"""
import ctypes
import os
import subprocess
import sys
import time

import Quartz

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from hanyoung import mac  # noqa: E402
from hanyoung.keymap_mac import mode_of_source, pick_source, to_mac  # noqa: E402

KOREAN = 'com.apple.inputmethod.Korean.2SetKorean'
mac._carbon.TISEnableInputSource.restype = ctypes.c_int32
mac._carbon.TISEnableInputSource.argtypes = [ctypes.c_void_p]


def enable_korean():
    """설치된 입력 소스 중 한국어(두벌식)를 켬"""
    arr = mac._carbon.TISCreateInputSourceList(None, True)
    found = []
    for i in range(mac._cf.CFArrayGetCount(arr)):
        src = mac._cf.CFArrayGetValueAtIndex(arr, i)
        sid = mac._cfstr(mac._carbon.TISGetInputSourceProperty(src, mac._PROP_ID))
        if sid in ('com.apple.inputmethod.Korean', KOREAN):
            mac._carbon.TISEnableInputSource(src)
            found.append(sid)
    mac._cf.CFRelease(arr)
    return found


def select(mode):
    sid = pick_source(mac.source_ids(), mode)
    ok = bool(sid) and mac.select_source(sid)
    time.sleep(0.5)
    return ok, mac.current_source_id()


def osa(*lines):
    args = ['osascript']
    for ln in lines:
        args += ['-e', ln]
    return subprocess.run(args, capture_output=True, text=True).stdout.strip()


def text():
    return osa('tell application "TextEdit" to get text of document 1')


def clear():
    osa('tell application "TextEdit" to set text of document 1 to ""')
    time.sleep(0.3)


def type_keys(s, gap=0.09):
    for ch in s:
        vk = 0x20 if ch == ' ' else ord(ch.upper())
        code = to_mac(vk)
        for down in (True, False):
            ev = Quartz.CGEventCreateKeyboardEvent(None, code, down)
            Quartz.CGEventSetFlags(ev, 0)
            Quartz.CGEventPost(Quartz.kCGHIDEventTap, ev)
        time.sleep(gap)


print('한국어 입력 소스 켜기:', enable_korean())
time.sleep(1)
print('켜 둔 입력 소스:', mac.source_ids())
osa('tell application "TextEdit" to activate', 'tell application "TextEdit" to make new document')
time.sleep(2)

CASES = [
    ('en', 'dkssud ', '안녕 '),               # 6글자 중간 교정 + 한/영 전환
    ('en', 'rkawk ', '감자 '),                # 띄어쓰기에서 교정
    ('ko', 'hello ', 'hello '),               # 한글 모드로 친 영어
    ('ko', 'go to job ', 'go to job '),       # 문맥 교정
    ('en', 'hello world ', 'hello world '),   # 진짜 영어는 그대로
]
fails = 0
for mode, keys, want in CASES:
    clear()
    ok, sid = select(mode)
    if not ok or mode_of_source(sid) != mode:
        print(f'입력 소스를 {mode}로 못 바꿈: {sid}')
        fails += 1
        continue
    type_keys(keys)
    time.sleep(1.5)
    got = text()
    mark = 'OK ' if got == want else 'FAIL'
    fails += got != want
    print(f'{mark} [{mode}] {keys!r} -> {got!r} (기대 {want!r})')

print('실패' if fails else '모두 통과', fails)
sys.exit(1 if fails else 0)
