"""macOS 실제 타이핑 확인 (CI용)

한국어 두벌식 입력 소스를 켜고, 이 스크립트가 직접 띄운 텍스트 창에 사람처럼 키를 쳐서
실행 중인 HanYoungFix 앱이 고친 결과를 읽습니다. (다른 앱을 AppleScript로 조종하면 자동화 권한
창에 막히므로, 창을 직접 만들어 그 내용을 바로 읽음)

전제: HanYoungFix 앱이 이미 실행 중이고 손쉬운 사용·입력 모니터링 권한이 있음 (GitHub macOS 러너는 허용됨)
사용: python -u app/tests/e2e_mac.py
"""
import ctypes
import os
import sys
import threading
import time

import AppKit
import Quartz
from PyObjCTools import AppHelper

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from hanyoung import mac  # noqa: E402
from hanyoung.keymap_mac import mode_of_source, pick_source, to_mac  # noqa: E402

KOREAN = 'com.apple.inputmethod.Korean.2SetKorean'
mac._carbon.TISEnableInputSource.restype = ctypes.c_int32
mac._carbon.TISEnableInputSource.argtypes = [ctypes.c_void_p]

CASES = [
    ('en', 'rkawk ', None),                   # 준비 운동: 앱이 새로 켠 한국어 입력 소스를 알아차리게 (채점 안 함)
    ('en', 'dkssud ', '안녕 '),               # 6글자 중간 교정 + 한/영 전환
    ('en', 'rkawk ', '감자 '),                # 띄어쓰기에서 교정
    ('ko', 'hello ', 'hello '),               # 한글 모드로 친 영어
    ('ko', 'go to job ', 'go to job '),       # 문맥 교정
    ('en', 'hello world ', 'hello world '),   # 진짜 영어는 그대로
]


def enable_korean():
    """설치된 입력 소스 중 한국어(두벌식)를 켬 (메인 스레드)"""
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


def make_window():
    app = AppKit.NSApplication.sharedApplication()
    app.setActivationPolicy_(AppKit.NSApplicationActivationPolicyRegular)
    rect = AppKit.NSMakeRect(200, 200, 520, 200)
    style = AppKit.NSWindowStyleMaskTitled | AppKit.NSWindowStyleMaskClosable
    win = AppKit.NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
        rect, style, AppKit.NSBackingStoreBuffered, False)
    win.setTitle_('hanyoung e2e')
    tv = AppKit.NSTextView.alloc().initWithFrame_(AppKit.NSMakeRect(0, 0, 520, 200))
    for setter in ('setAutomaticQuoteSubstitutionEnabled_', 'setAutomaticSpellingCorrectionEnabled_',
                   'setAutomaticTextReplacementEnabled_', 'setContinuousSpellCheckingEnabled_',
                   'setAutomaticDashSubstitutionEnabled_', 'setAutomaticTextCompletionEnabled_'):
        if hasattr(tv, setter):
            getattr(tv, setter)(False)
    win.setContentView_(tv)
    win.makeKeyAndOrderFront_(None)
    win.makeFirstResponder_(tv)
    app.activateIgnoringOtherApps_(True)
    return app, win, tv


def type_keys(s, gap=0.09):
    for ch in s:
        vk = 0x20 if ch == ' ' else ord(ch.upper())
        code = to_mac(vk)
        for down in (True, False):
            ev = Quartz.CGEventCreateKeyboardEvent(None, code, down)
            Quartz.CGEventSetFlags(ev, 0)
            Quartz.CGEventPost(Quartz.kCGHIDEventTap, ev)
        time.sleep(gap)


def run_cases(app, win, tv):
    fails = 0
    try:
        time.sleep(2)
        print('켜 둔 입력 소스:', mac.on_main(mac.source_ids))
        for mode, keys, want in CASES:
            def prepare():
                tv.setString_('')
                app.activateIgnoringOtherApps_(True)
                win.makeKeyAndOrderFront_(None)
                win.makeFirstResponder_(tv)
                sid = pick_source(mac.source_ids(), mode)
                if sid:
                    mac.select_source(sid)
            mac.on_main(prepare)
            time.sleep(0.8)  # 앱이 입력 소스 변경을 알아차릴 시간
            sid = mac.on_main(mac.current_source_id)
            if mode_of_source(sid) != mode:
                print(f'FAIL 입력 소스를 {mode}로 못 바꿈: {sid}')
                fails += 1
                continue
            # 교정 중 화면이 어떻게 바뀌는지 0.03초마다 기록 (실패 원인 분석용)
            trace, stop = [], threading.Event()

            def sample():
                last = None
                while not stop.is_set():
                    cur = str(mac.on_main(lambda: tv.string(), timeout=0.2) or '')
                    if cur != last:
                        trace.append(cur)
                        last = cur
                    time.sleep(0.03)
            th = threading.Thread(target=sample, daemon=True)
            th.start()
            type_keys(keys)
            time.sleep(1.5)
            stop.set()
            th.join(1)
            got = str(mac.on_main(lambda: tv.string()) or '')
            if want is None:
                print(f'준비 [{mode}] {keys!r} -> {got!r}')
                continue
            ok = got == want
            if not ok:
                print('   화면 변화:', ' → '.join(repr(t) for t in trace))
            fails += not ok
            print(f'{"OK  " if ok else "FAIL"} [{mode}] {keys!r} -> {got!r} (기대 {want!r})')
    except Exception as e:  # noqa: BLE001
        print('FAIL 오류:', repr(e))
        fails += 1
    print('모두 통과' if not fails else f'실패 {fails}')
    sys.stdout.flush()
    os._exit(1 if fails else 0)


def main():
    if '--enable-only' in sys.argv:
        # 실제 Mac처럼 앱을 켜기 전에 한국어 입력기를 미리 켜 둠 (CI에서 앱보다 먼저 실행)
        print('한국어 입력 소스 켜기:', enable_korean())
        for mode in ('ko', 'en'):
            sid = pick_source(mac.source_ids(), mode)
            print(mode, '선택:', sid, bool(sid) and mac.select_source(sid))
            time.sleep(1)
        print('현재:', mac.current_source_id())
        return
    print('한국어 입력 소스 켜기:', enable_korean())
    app, win, tv = make_window()
    threading.Thread(target=run_cases, args=(app, win, tv), daemon=True).start()
    AppHelper.runEventLoop(installInterrupt=True)


if __name__ == '__main__':
    main()
