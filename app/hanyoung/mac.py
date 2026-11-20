"""macOS: 키보드 감시(이벤트 탭), 입력 소스(한/영) 읽기·바꾸기, 키 보내기

Windows의 win32.py와 같은 역할입니다. 판단과 교정 순서는 engine.py가 하고, 여기서는
- 키 이벤트를 KeyEvent(엔진이 쓰는 Windows 키 번호)로 바꿔 넘기고
- 엔진이 막은 키(교정 중 친 키)는 나중에 다시 보내며
- 백스페이스, 한/영 전환, 같은 키 다시 누르기를 실제로 수행합니다.

필요한 권한: 손쉬운 사용(Accessibility), 입력 모니터링(Input Monitoring)
입력 소스(TIS) API는 메인 스레드에서만 부르고, 다른 스레드는 캐시된 값을 읽습니다.
"""
from __future__ import annotations

import ctypes
import os
import threading
import time

import objc
import Quartz
from AppKit import NSWorkspace
from Foundation import NSDistributedNotificationCenter, NSObject
from PyObjCTools import AppHelper

from .engine import EN, KO, Key, KeyEvent, Platform
from .keymap_mac import mode_of_source, pick_source, to_mac, to_vk

MAGIC_ACTION = 0x48594601  # 우리가 보낸 교정 키
MAGIC_REPLAY = 0x48594602  # 막아 두었다가 다시 보낸 사용자 키
VK_HANGUL, VK_BACK = 0x15, 0x08

# ---------- 입력 소스 (Carbon TIS, ctypes) ----------
_carbon = ctypes.cdll.LoadLibrary('/System/Library/Frameworks/Carbon.framework/Carbon')
_cf = ctypes.cdll.LoadLibrary('/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation')
_vp = ctypes.c_void_p
_carbon.TISCopyCurrentKeyboardInputSource.restype = _vp
_carbon.TISGetInputSourceProperty.restype = _vp
_carbon.TISGetInputSourceProperty.argtypes = [_vp, _vp]
_carbon.TISCreateInputSourceList.restype = _vp
_carbon.TISCreateInputSourceList.argtypes = [_vp, ctypes.c_bool]
_carbon.TISSelectInputSource.restype = ctypes.c_int32
_carbon.TISSelectInputSource.argtypes = [_vp]
_cf.CFArrayGetCount.restype = ctypes.c_long
_cf.CFArrayGetCount.argtypes = [_vp]
_cf.CFArrayGetValueAtIndex.restype = _vp
_cf.CFArrayGetValueAtIndex.argtypes = [_vp, ctypes.c_long]
_cf.CFRelease.argtypes = [_vp]
_cf.CFStringGetCString.restype = ctypes.c_bool
_cf.CFStringGetCString.argtypes = [_vp, ctypes.c_char_p, ctypes.c_long, ctypes.c_uint32]
_PROP_ID = _vp.in_dll(_carbon, 'kTISPropertyInputSourceID')
_PROP_SELECTABLE = _vp.in_dll(_carbon, 'kTISPropertyInputSourceIsSelectCapable')
_CF_TRUE = _vp.in_dll(_cf, 'kCFBooleanTrue')
_UTF8 = 0x08000100


def _cfstr(ref) -> str:
    if not ref:
        return ''
    buf = ctypes.create_string_buffer(512)
    return buf.value.decode('utf-8') if _cf.CFStringGetCString(ref, buf, 512, _UTF8) else ''


def current_source_id() -> str:
    """지금 선택된 입력 소스 ID (메인 스레드에서 호출)"""
    src = _carbon.TISCopyCurrentKeyboardInputSource()
    try:
        return _cfstr(_carbon.TISGetInputSourceProperty(src, _PROP_ID))
    finally:
        if src:
            _cf.CFRelease(src)


def _sources():
    """선택할 수 있는(켜 둔) 키보드 입력 소스 {ID: 포인터}. 포인터는 목록이 살아 있는 동안만 유효"""
    arr = _carbon.TISCreateInputSourceList(None, False)
    out = {}
    if arr:
        for i in range(_cf.CFArrayGetCount(arr)):
            src = _cf.CFArrayGetValueAtIndex(arr, i)
            if _carbon.TISGetInputSourceProperty(src, _PROP_SELECTABLE) == _CF_TRUE.value:
                out[_cfstr(_carbon.TISGetInputSourceProperty(src, _PROP_ID))] = src
    return out, arr


def source_ids() -> list[str]:
    srcs, arr = _sources()
    try:
        return list(srcs)
    finally:
        if arr:
            _cf.CFRelease(arr)


def select_source(source_id: str) -> bool:
    srcs, arr = _sources()
    try:
        src = srcs.get(source_id)
        return bool(src) and _carbon.TISSelectInputSource(src) == 0
    finally:
        if arr:
            _cf.CFRelease(arr)


def on_main(fn, timeout=1.0):
    """메인 스레드에서 fn을 실행하고 결과를 돌려줌 (이미 메인이면 바로)"""
    if threading.current_thread() is threading.main_thread():
        return fn()
    box, done = {}, threading.Event()

    def run():
        try:
            box['v'] = fn()
        except Exception as e:  # noqa: BLE001
            box['e'] = e
        done.set()
    AppHelper.callAfter(run)
    if not done.wait(timeout):
        return None
    if 'e' in box:
        raise box['e']
    return box.get('v')


# ---------- 권한 ----------
def has_permissions(prompt=False) -> dict[str, bool]:
    """손쉬운 사용 / 입력 모니터링 / 키 보내기 권한. prompt=True면 처음 한 번 시스템 창을 띄움"""
    from HIServices import AXIsProcessTrustedWithOptions, kAXTrustedCheckOptionPrompt
    ax = bool(AXIsProcessTrustedWithOptions({kAXTrustedCheckOptionPrompt: bool(prompt)}))
    listen = bool(Quartz.CGPreflightListenEventAccess())
    post = bool(Quartz.CGPreflightPostEventAccess())
    if prompt:
        if not listen:
            Quartz.CGRequestListenEventAccess()
        if not post:
            Quartz.CGRequestPostEventAccess()
    return {'accessibility': ax, 'input_monitoring': listen, 'post': post}


# ---------- 입력 소스 바꾼 뒤 앞 창에 반영시키기 ----------
# macOS는 프로그램이 한국어 같은 입력기로 입력 소스를 바꾸면, 지금 쓰는 창에는 바로 반영되지 않을 때가 있음
# (CI 실측: 입력 소스는 '한국어'인데 앞 창은 영어로 입력됨). 잠깐 보이지 않는 창으로 포커스를 옮겼다가
# 되돌리면 앞 창이 입력 소스를 다시 읽어 반영됨 (macism 등에서 쓰는 방법)
_nudge_win = None


def focus_nudge_begin():
    """메인 스레드: 우리 앱의 보이지 않는 창을 잠깐 앞으로. 원래 앞에 있던 앱을 돌려줌"""
    global _nudge_win
    from AppKit import (NSApplication, NSBackingStoreBuffered, NSMakeRect, NSWindow,
                        NSWindowStyleMaskTitled)
    prev = NSWorkspace.sharedWorkspace().frontmostApplication()
    if _nudge_win is None:
        w = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(-10000, -10000, 1, 1), NSWindowStyleMaskTitled, NSBackingStoreBuffered, False)
        w.setAlphaValue_(0.0)
        w.setReleasedWhenClosed_(False)
        _nudge_win = w
    NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
    _nudge_win.makeKeyAndOrderFront_(None)
    return prev


def focus_nudge_end(prev):
    """메인 스레드: 보이지 않는 창을 치우고 원래 앱을 다시 앞으로"""
    if _nudge_win is not None:
        _nudge_win.orderOut_(None)
    if prev is not None:
        prev.activateWithOptions_(1 << 1)  # NSApplicationActivateIgnoringOtherApps


def open_privacy_settings(pane='Accessibility'):
    os.system(f'open "x-apple.systempreferences:com.apple.preference.security?Privacy_{pane}"')


# ---------- 앞에 있는 앱과 창 ----------
class Front:
    """앞에 있는 앱 이름과 창 번호. 앱 이름은 메인 스레드 알림으로 갱신, 창 번호는 잠깐 캐시"""

    def __init__(self):
        self.pid = 0
        self.name = ''
        self._win = (0.0, 0)
        self.update()

    def update(self):
        app = NSWorkspace.sharedWorkspace().frontmostApplication()
        if app is not None:
            self.pid = int(app.processIdentifier())
            url = app.executableURL()
            self.name = (url.lastPathComponent() if url else (app.localizedName() or '')).lower()

    def window(self) -> int:
        now = time.monotonic()
        if now - self._win[0] < 0.3:
            return self._win[1]
        num = 0
        info = Quartz.CGWindowListCopyWindowInfo(
            Quartz.kCGWindowListOptionOnScreenOnly | Quartz.kCGWindowListExcludeDesktopElements, Quartz.kCGNullWindowID)
        for w in info or []:
            if w.get('kCGWindowOwnerPID') == self.pid and w.get('kCGWindowLayer', 0) == 0:
                num = int(w.get('kCGWindowNumber', 0))
                break
        self._win = (now, num or self.pid)
        return self._win[1]


class _Observer(NSObject):
    """입력 소스가 바뀌거나 앞 앱이 바뀌면 메인 스레드에서 호출됨"""

    def initWithPlatform_(self, platform):
        self = objc.super(_Observer, self).init()
        if self is None:
            return None
        self.platform = platform
        return self

    def sourceChanged_(self, _note):
        self.platform.refresh_mode()

    def appActivated_(self, _note):
        if not self.platform.toggling:  # 한/영 반영용으로 잠깐 포커스를 옮길 때는 앞 앱으로 치지 않음
            self.platform.front.update()


# ---------- 플랫폼 ----------
class MacPlatform(Platform):
    STEP = 0.012
    ACT_DELAY = 0.12        # 교정 시작 전, 방금 누른 키를 앱이 먼저 처리하도록
    KEY_GAP = 0.012         # 보내는 키 사이 간격
    TOGGLE_MAX_WAIT = 0.4   # 한/영 전환이 실제로 반영될 때까지 기다리는 최대 시간
    FOCUS_NUDGE = True      # 입력 소스를 바꾼 뒤 포커스를 잠깐 옮겨 앞 창에 반영

    def __init__(self):
        import queue
        self.engine = None
        self.jobs = queue.Queue()
        self.front = Front()
        self.mode = mode_of_source(current_source_id())
        self.last_en_source = None
        self.toggling = False
        self._remember_source(current_source_id())
        self._observer = _Observer.alloc().initWithPlatform_(self)
        NSDistributedNotificationCenter.defaultCenter().addObserver_selector_name_object_(
            self._observer, 'sourceChanged:', 'com.apple.Carbon.TISNotifySelectedKeyboardInputSourceChanged', None)
        NSWorkspace.sharedWorkspace().notificationCenter().addObserver_selector_name_object_(
            self._observer, 'appActivated:', 'NSWorkspaceDidActivateApplicationNotification', None)
        threading.Thread(target=self._worker, daemon=True, name='hanyoung-worker').start()

    # ----- 한/영 상태 -----
    def _remember_source(self, sid):
        if mode_of_source(sid) == EN:
            self.last_en_source = sid

    def refresh_mode(self):
        """메인 스레드: 입력 소스를 다시 읽고, 사용자가 바꿨으면 엔진에 한/영 키처럼 알림"""
        sid = current_source_id()
        self._remember_source(sid)
        new = mode_of_source(sid)
        old, self.mode = self.mode, new
        if new != old and not self.toggling and self.engine is not None:
            ev = KeyEvent(VK_HANGUL, True, source='user', app=self.front.name, window=self.front.window())
            try:
                self.engine.handle(ev)
            except Exception as e:  # noqa: BLE001
                print('한/영 전환 처리 오류:', e)

    def get_mode(self):
        return self.mode

    # ----- 교정 실행 -----
    def _worker(self):
        while True:
            fn = self.jobs.get()
            time.sleep(self.ACT_DELAY)
            try:
                fn()
            except Exception as e:  # noqa: BLE001
                print('교정 중 오류:', e)

    def run_later(self, fn):
        self.jobs.put(fn)

    @staticmethod
    def _post(mac_code, down, shift=False, magic=MAGIC_ACTION):
        ev = Quartz.CGEventCreateKeyboardEvent(None, mac_code, down)
        Quartz.CGEventSetFlags(ev, Quartz.kCGEventFlagMaskShift if shift else 0)
        Quartz.CGEventSetIntegerValueField(ev, Quartz.kCGEventSourceUserData, magic)
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, ev)

    def _tap(self, vk, shift=False):
        code = to_mac(vk)
        if code is None:
            return
        self._post(code, True, shift)
        self._post(code, False, shift)
        if self.KEY_GAP:
            time.sleep(self.KEY_GAP)

    def send_backspace(self, n):
        for _ in range(n):
            self._tap(VK_BACK)
        time.sleep(self.STEP)

    def send_toggle(self):
        before = self.mode
        target = EN if before == KO else KO
        self.toggling = True
        try:
            if before == KO:
                # 조합 중인 글자를 먼저 확정: 입력 소스만 바꾸면 Mac 한국어 입력기가 조합 중인 글자를
                # 기억해 두었다가 다음에 한국어로 바꿀 때 다시 넣음 (CI 실측: 'ㅐgo to job')
                # 띄어쓰기로 확정한 뒤 그 띄어쓰기를 바로 지우면 화면은 그대로
                self._tap(0x20)
                self._tap(VK_BACK)
            def select():
                sid = pick_source(source_ids(), target, self.last_en_source)
                return bool(sid) and select_source(sid)
            on_main(select)
            if self.FOCUS_NUDGE:
                prev = on_main(focus_nudge_begin)
                time.sleep(0.06)
                on_main(lambda: focus_nudge_end(prev))
                time.sleep(0.08)
            end = time.monotonic() + self.TOGGLE_MAX_WAIT
            while time.monotonic() < end:
                on_main(self.refresh_mode)
                if self.mode == target:
                    break
                time.sleep(0.01)
            time.sleep(self.KEY_GAP)
        finally:
            self.toggling = False

    def send_keys(self, keys: list[Key]):
        for k in keys:
            self._tap(k.vk, k.shift)
        time.sleep(self.STEP)

    def replay(self, events: list[KeyEvent]):
        for ev in events:
            if not ev.raw:
                continue
            code, flags = ev.raw
            e = Quartz.CGEventCreateKeyboardEvent(None, code, ev.down)
            Quartz.CGEventSetFlags(e, flags)
            Quartz.CGEventSetIntegerValueField(e, Quartz.kCGEventSourceUserData, MAGIC_REPLAY)
            Quartz.CGEventPost(Quartz.kCGHIDEventTap, e)
        time.sleep(self.STEP)


# ---------- 키보드 감시 ----------
_KEY_TYPES = (Quartz.kCGEventKeyDown, Quartz.kCGEventKeyUp)
_MOUSE_TYPES = (Quartz.kCGEventLeftMouseDown, Quartz.kCGEventRightMouseDown, Quartz.kCGEventOtherMouseDown)


def make_event(etype, event, platform: MacPlatform) -> KeyEvent:
    code = Quartz.CGEventGetIntegerValueField(event, Quartz.kCGKeyboardEventKeycode)
    flags = Quartz.CGEventGetFlags(event)
    magic = Quartz.CGEventGetIntegerValueField(event, Quartz.kCGEventSourceUserData)
    if magic == MAGIC_ACTION:
        source = 'action'
    elif magic == MAGIC_REPLAY:
        source = 'replay'
    else:
        source = 'user'  # 키보드에서 온 키 (다른 프로그램이 보낸 키도 사용자 입력처럼 다룸)
    down = etype == Quartz.kCGEventKeyDown
    ev = KeyEvent(
        vk=to_vk(code), down=down, source=source, raw=(code, flags),
        shift=bool(flags & Quartz.kCGEventFlagMaskShift),
        # 엔진의 Ctrl 단축키(Ctrl+Z 되돌리기, Ctrl+Alt+H 켜고 끄기)는 Mac에서 ⌘ 또는 Control
        ctrl=bool(flags & (Quartz.kCGEventFlagMaskCommand | Quartz.kCGEventFlagMaskControl)),
        alt=bool(flags & Quartz.kCGEventFlagMaskAlternate),
        caps=bool(flags & Quartz.kCGEventFlagMaskAlphaShift),
    )
    if down and source in ('user', 'replay'):
        ev.app = platform.front.name
        ev.window = platform.front.window()
    return ev


class Hooks:
    """이벤트 탭을 자체 스레드의 런루프에서 돌립니다."""

    def __init__(self, engine, platform: MacPlatform):
        self.engine, self.platform = engine, platform
        self.tap = None
        self.loop = None
        self.ready = threading.Event()

    def _callback(self, proxy, etype, event, refcon):
        if etype in (Quartz.kCGEventTapDisabledByTimeout, Quartz.kCGEventTapDisabledByUserInput):
            if self.tap:
                Quartz.CGEventTapEnable(self.tap, True)  # 시스템이 꺼 버린 탭을 다시 켬
            return event
        try:
            if etype in _MOUSE_TYPES:
                self.engine.mouse_click()
                return event
            if etype in _KEY_TYPES:
                if self.engine.handle(make_event(etype, event, self.platform)):
                    return None  # 이 키를 막음 (교정 뒤 다시 보냄)
        except Exception as e:  # noqa: BLE001
            print('키 처리 오류:', e)
        return event

    def _run(self):
        mask = 0
        for t in _KEY_TYPES + _MOUSE_TYPES:
            mask |= Quartz.CGEventMaskBit(t)
        self.tap = Quartz.CGEventTapCreate(
            Quartz.kCGSessionEventTap, Quartz.kCGHeadInsertEventTap, Quartz.kCGEventTapOptionDefault,
            mask, self._callback, None)
        if not self.tap:
            self.ready.set()
            return
        source = Quartz.CFMachPortCreateRunLoopSource(None, self.tap, 0)
        self.loop = Quartz.CFRunLoopGetCurrent()
        Quartz.CFRunLoopAddSource(self.loop, source, Quartz.kCFRunLoopCommonModes)
        Quartz.CGEventTapEnable(self.tap, True)
        self.ready.set()
        Quartz.CFRunLoopRun()

    def start(self) -> bool:
        """이벤트 탭을 켬. 권한이 없으면 False (권한을 준 뒤 다시 부르면 켜짐)"""
        if self.tap:
            return True
        self.ready = threading.Event()
        threading.Thread(target=self._run, daemon=True, name='hanyoung-tap').start()
        self.ready.wait(3)
        return bool(self.tap)

    def stop(self):
        if self.loop:
            Quartz.CFRunLoopStop(self.loop)


def single_instance(path: str) -> bool:
    import fcntl
    global _lock_file
    _lock_file = open(path, 'w')
    try:
        fcntl.flock(_lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return True
    except OSError:
        return False


_lock_file = None
