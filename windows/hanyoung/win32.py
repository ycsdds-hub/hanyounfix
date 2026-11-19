"""Windows 구현: 키보드 후킹, IME 상태 조회, 키 보내기 (ctypes만 사용)"""
from __future__ import annotations

import ctypes
import os
import queue
import threading
import time
from ctypes import wintypes

from .engine import KO, EN, Key, KeyEvent, Platform

user32 = ctypes.WinDLL('user32', use_last_error=True)
imm32 = ctypes.WinDLL('imm32', use_last_error=True)
kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)

ULONG_PTR = ctypes.c_size_t
MAGIC_ACTION = 0x48594601  # 우리가 보낸 교정 키
MAGIC_REPLAY = 0x48594602  # 막아 두었다가 다시 보낸 사용자 키

INPUT_KEYBOARD = 1
KEYEVENTF_EXTENDEDKEY, KEYEVENTF_KEYUP = 0x0001, 0x0002
LLKHF_EXTENDED, LLKHF_INJECTED = 0x01, 0x10
WM_KEYDOWN, WM_KEYUP, WM_SYSKEYDOWN, WM_SYSKEYUP = 0x100, 0x101, 0x104, 0x105
WM_IME_CONTROL, IMC_GETCONVERSIONMODE, IMC_GETOPENSTATUS = 0x283, 0x001, 0x005
IME_CMODE_NATIVE = 0x1
SMTO_ABORTIFHUNG = 0x2
VK_SHIFT, VK_CONTROL, VK_MENU, VK_LWIN, VK_RWIN, VK_CAPITAL = 0x10, 0x11, 0x12, 0x5B, 0x5C, 0x14
VK_LSHIFT, VK_RSHIFT, VK_BACK, VK_HANGUL = 0xA0, 0xA1, 0x08, 0x15
LANG_KOREAN = 0x0412
ES_PASSWORD, GWL_STYLE = 0x0020, -16
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [('wVk', wintypes.WORD), ('wScan', wintypes.WORD), ('dwFlags', wintypes.DWORD),
                ('time', wintypes.DWORD), ('dwExtraInfo', ULONG_PTR)]


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [('dx', wintypes.LONG), ('dy', wintypes.LONG), ('mouseData', wintypes.DWORD),
                ('dwFlags', wintypes.DWORD), ('time', wintypes.DWORD), ('dwExtraInfo', ULONG_PTR)]


class _INPUTUNION(ctypes.Union):
    _fields_ = [('ki', KEYBDINPUT), ('mi', MOUSEINPUT)]


class INPUT(ctypes.Structure):
    _anonymous_ = ('u',)
    _fields_ = [('type', wintypes.DWORD), ('u', _INPUTUNION)]


class GUITHREADINFO(ctypes.Structure):
    _fields_ = [('cbSize', wintypes.DWORD), ('flags', wintypes.DWORD), ('hwndActive', wintypes.HWND),
                ('hwndFocus', wintypes.HWND), ('hwndCapture', wintypes.HWND), ('hwndMenuOwner', wintypes.HWND),
                ('hwndMoveSize', wintypes.HWND), ('hwndCaret', wintypes.HWND), ('rcCaret', wintypes.RECT)]


user32.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int]
user32.GetForegroundWindow.restype = wintypes.HWND
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
user32.GetKeyboardLayout.restype = ctypes.c_void_p
user32.GetKeyboardLayout.argtypes = [wintypes.DWORD]
user32.SendMessageTimeoutW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM,
                                       wintypes.UINT, wintypes.UINT, ctypes.POINTER(ULONG_PTR)]
user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetGUIThreadInfo.argtypes = [wintypes.DWORD, ctypes.POINTER(GUITHREADINFO)]
user32.MapVirtualKeyW.argtypes = [wintypes.UINT, wintypes.UINT]
imm32.ImmGetDefaultIMEWnd.argtypes = [wintypes.HWND]
imm32.ImmGetDefaultIMEWnd.restype = wintypes.HWND
kernel32.OpenProcess.restype = wintypes.HANDLE
kernel32.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR,
                                                ctypes.POINTER(wintypes.DWORD)]


def key_down(vk: int) -> bool:
    return bool(user32.GetAsyncKeyState(vk) & 0x8000)


def caps_on() -> bool:
    return bool(user32.GetKeyState(VK_CAPITAL) & 1)


def foreground() -> int:
    return user32.GetForegroundWindow() or 0


_app_cache: dict[int, tuple[float, str]] = {}


def app_name(hwnd: int) -> str:
    """창을 가진 프로그램의 실행 파일 이름 (소문자, 예: notepad.exe)"""
    now = time.monotonic()
    hit = _app_cache.get(hwnd)
    if hit and now - hit[0] < 2:
        return hit[1]
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    name = ''
    h = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value)
    if h:
        buf = ctypes.create_unicode_buffer(520)
        size = wintypes.DWORD(len(buf))
        if kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
            name = os.path.basename(buf.value).lower()
        kernel32.CloseHandle(h)
    _app_cache[hwnd] = (now, name)
    return name


def is_password_field(hwnd: int) -> bool:
    """일반 Windows 입력칸(Edit)이 비밀번호 칸인지"""
    tid = user32.GetWindowThreadProcessId(hwnd, None)
    info = GUITHREADINFO(cbSize=ctypes.sizeof(GUITHREADINFO))
    if not user32.GetGUIThreadInfo(tid, ctypes.byref(info)) or not info.hwndFocus:
        return False
    cls = ctypes.create_unicode_buffer(64)
    user32.GetClassNameW(info.hwndFocus, cls, 64)
    if 'edit' not in cls.value.lower():
        return False
    return bool(user32.GetWindowLongW(info.hwndFocus, GWL_STYLE) & ES_PASSWORD)


def ime_mode(hwnd: int | None = None) -> str | None:
    """앞 창의 한/영 상태. 한국어 키보드가 아니거나 알 수 없으면 None"""
    hwnd = hwnd or foreground()
    if not hwnd:
        return None
    tid = user32.GetWindowThreadProcessId(hwnd, None)
    layout = user32.GetKeyboardLayout(tid) or 0
    if (layout & 0xFFFF) != LANG_KOREAN:
        return None
    # 바깥 창이 아니라 실제 입력 중인 칸에 물어봐야 함. Windows 11 메모장(TSF)처럼
    # 바깥 창의 IME는 한/영을 바꿔도 그대로인 프로그램이 있음
    info = GUITHREADINFO(cbSize=ctypes.sizeof(GUITHREADINFO))
    if user32.GetGUIThreadInfo(tid, ctypes.byref(info)) and info.hwndFocus:
        hwnd = info.hwndFocus
    ime = imm32.ImmGetDefaultIMEWnd(hwnd)
    if not ime:
        return None
    res = ULONG_PTR()
    ok = user32.SendMessageTimeoutW(ime, WM_IME_CONTROL, IMC_GETOPENSTATUS, 0, SMTO_ABORTIFHUNG, 80, ctypes.byref(res))
    if not ok:
        return None
    if not res.value:
        return EN  # IME가 닫혀 있으면 영문
    ok = user32.SendMessageTimeoutW(ime, WM_IME_CONTROL, IMC_GETCONVERSIONMODE, 0, SMTO_ABORTIFHUNG, 80,
                                    ctypes.byref(res))
    if not ok:
        return None
    return KO if res.value & IME_CMODE_NATIVE else EN


def _kbd(vk: int, up: bool = False, extra: int = MAGIC_ACTION, scan: int | None = None, extended=False) -> INPUT:
    flags = (KEYEVENTF_KEYUP if up else 0) | (KEYEVENTF_EXTENDEDKEY if extended else 0)
    if scan is None:
        scan = user32.MapVirtualKeyW(vk, 0)
    return INPUT(type=INPUT_KEYBOARD, ki=KEYBDINPUT(vk, scan, flags, 0, extra))


def _send(inputs: list[INPUT]):
    if not inputs:
        return
    arr = (INPUT * len(inputs))(*inputs)
    user32.SendInput(len(inputs), arr, ctypes.sizeof(INPUT))


class WindowsPlatform(Platform):
    STEP = 0.012       # 키 묶음 사이 쉬는 시간
    TOGGLE_WAIT = 0.04  # 한/영 전환 뒤 IME가 바뀔 때까지

    def __init__(self, trusted_apps=None, on_trust=None):
        self.engine = None
        self.jobs: queue.Queue = queue.Queue()
        # 한/영 상태를 제대로 알려 주는지 확인된 프로그램 {exe: True/False}
        self.trusted: dict[str, bool] = dict(trusted_apps or {})
        self.on_trust = on_trust or (lambda app, ok: None)
        threading.Thread(target=self._worker, daemon=True, name='hanyoung-worker').start()

    def observe_toggle(self, hwnd: int, app: str):
        """사용자가 한/영 키를 누를 때 상태가 실제로 바뀌는지 보고 그 프로그램을 신뢰할지 정함"""
        before = ime_mode(hwnd)

        def check():
            after = ime_mode(hwnd)
            if before is None or after is None:
                return
            ok = before != after
            if self.trusted.get(app) != ok:
                self.trusted[app] = ok
                self.on_trust(app, ok)

        threading.Timer(0.15, check).start()

    def _worker(self):
        while True:
            fn = self.jobs.get()
            time.sleep(0.02)  # 방금 누른 키가 프로그램에 먼저 전달되도록
            try:
                fn()
            except Exception as e:  # 교정 실패가 앱 전체를 멈추지 않도록
                print('교정 중 오류:', e)

    def run_later(self, fn):
        self.jobs.put(fn)

    def get_mode(self):
        hwnd = foreground()
        if not self.trusted.get(app_name(hwnd)):
            return None  # 아직 확인 안 된 프로그램에서는 고치지 않음
        return ime_mode(hwnd)

    def _release_modifiers(self):
        ups = [_kbd(vk, up=True) for vk in (VK_LSHIFT, VK_RSHIFT, VK_SHIFT) if key_down(vk)]
        _send(ups)

    def send_backspace(self, n):
        self._release_modifiers()
        for _ in range(n):
            _send([_kbd(VK_BACK), _kbd(VK_BACK, up=True)])
        time.sleep(self.STEP)

    def send_toggle(self):
        self._release_modifiers()
        _send([_kbd(VK_HANGUL), _kbd(VK_HANGUL, up=True)])
        time.sleep(self.TOGGLE_WAIT)

    def send_keys(self, keys: list[Key]):
        shift = key_down(VK_SHIFT)
        for k in keys:
            seq = []
            if k.shift and not shift:
                seq.append(_kbd(VK_LSHIFT))
                shift = True
            elif not k.shift and shift:
                seq += [_kbd(VK_LSHIFT, up=True), _kbd(VK_RSHIFT, up=True)]
                shift = False
            seq += [_kbd(k.vk), _kbd(k.vk, up=True)]
            _send(seq)
        if shift:
            _send([_kbd(VK_LSHIFT, up=True)])
        time.sleep(self.STEP)

    def replay(self, events: list[KeyEvent]):
        for ev in events:
            vk, scan, flags = ev.raw
            _send([_kbd(vk, up=not ev.down, extra=MAGIC_REPLAY, scan=scan, extended=bool(flags & LLKHF_EXTENDED))])
        time.sleep(self.STEP)


class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [('vkCode', wintypes.DWORD), ('scanCode', wintypes.DWORD), ('flags', wintypes.DWORD),
                ('time', wintypes.DWORD), ('dwExtraInfo', ULONG_PTR)]


LRESULT = ctypes.c_ssize_t
HOOKPROC = ctypes.WINFUNCTYPE(LRESULT, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)
user32.SetWindowsHookExW.argtypes = [ctypes.c_int, HOOKPROC, wintypes.HINSTANCE, wintypes.DWORD]
user32.SetWindowsHookExW.restype = wintypes.HHOOK
user32.CallNextHookEx.argtypes = [wintypes.HHOOK, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM]
user32.CallNextHookEx.restype = LRESULT
user32.UnhookWindowsHookEx.argtypes = [wintypes.HHOOK]
kernel32.GetModuleHandleW.restype = wintypes.HMODULE
WH_KEYBOARD_LL, WH_MOUSE_LL = 13, 14
WM_LBUTTONDOWN, WM_RBUTTONDOWN, WM_MBUTTONDOWN, WM_QUIT = 0x201, 0x204, 0x207, 0x12
VK_RMENU = 0xA5


def make_event(msg: int, data: KBDLLHOOKSTRUCT) -> KeyEvent:
    down = msg in (WM_KEYDOWN, WM_SYSKEYDOWN)
    extra = data.dwExtraInfo or 0
    if extra == MAGIC_ACTION:
        source = 'action'
    elif extra == MAGIC_REPLAY:
        source = 'replay'
    elif data.flags & LLKHF_INJECTED:
        source = 'other'
    else:
        source = 'user'
    hwnd = foreground()
    ev = KeyEvent(
        vk=data.vkCode, down=down, source=source, raw=(data.vkCode, data.scanCode, data.flags),
        shift=key_down(VK_SHIFT), ctrl=key_down(VK_CONTROL), alt=key_down(VK_MENU),
        win=key_down(VK_LWIN) or key_down(VK_RWIN), caps=caps_on(), window=hwnd,
    )
    if down and source in ('user', 'replay'):
        ev.app = app_name(hwnd)
        ev.password = is_password_field(hwnd)
    return ev


class Hooks:
    """전역 키보드/마우스 후킹. 자체 스레드에서 메시지 루프를 돌립니다."""

    def __init__(self, engine, platform: WindowsPlatform):
        self.engine, self.platform = engine, platform
        self.thread_id = None
        self._kb = HOOKPROC(self._on_key)      # 참조를 잡아 두어야 GC되지 않음
        self._mouse = HOOKPROC(self._on_mouse)
        self.ready = threading.Event()

    def _on_key(self, code, wparam, lparam):
        if code == 0:
            try:
                data = ctypes.cast(lparam, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
                ev = make_event(wparam, data)
                if ev.down and ev.source == 'user' and ev.vk in (VK_HANGUL, VK_RMENU):
                    self.platform.observe_toggle(ev.window, ev.app or app_name(ev.window))
                if self.engine.handle(ev):
                    return 1  # 이 키를 막음
            except Exception as e:
                print('키 처리 오류:', e)
        return user32.CallNextHookEx(None, code, wparam, lparam)

    def _on_mouse(self, code, wparam, lparam):
        if code == 0 and wparam in (WM_LBUTTONDOWN, WM_RBUTTONDOWN, WM_MBUTTONDOWN):
            try:
                self.engine.mouse_click()
            except Exception:
                pass
        return user32.CallNextHookEx(None, code, wparam, lparam)

    def _loop(self):
        self.thread_id = kernel32.GetCurrentThreadId()
        mod = kernel32.GetModuleHandleW(None)
        kb = user32.SetWindowsHookExW(WH_KEYBOARD_LL, self._kb, mod, 0)
        ms = user32.SetWindowsHookExW(WH_MOUSE_LL, self._mouse, mod, 0)
        self.ready.set()
        if not kb:
            print('키보드 후킹 실패:', ctypes.get_last_error())
            return
        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))
        user32.UnhookWindowsHookEx(kb)
        if ms:
            user32.UnhookWindowsHookEx(ms)

    def start(self):
        threading.Thread(target=self._loop, daemon=True, name='hanyoung-hook').start()
        self.ready.wait(3)

    def stop(self):
        if self.thread_id:
            user32.PostThreadMessageW(self.thread_id, WM_QUIT, 0, 0)


def single_instance(name='Local\\HanYoungFix') -> bool:
    kernel32.CreateMutexW.restype = wintypes.HANDLE
    single_instance.handle = kernel32.CreateMutexW(None, False, name)
    return ctypes.get_last_error() != 183  # ERROR_ALREADY_EXISTS


def work_area():
    rect = wintypes.RECT()
    user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(rect), 0)  # SPI_GETWORKAREA
    return rect.left, rect.top, rect.right, rect.bottom


def make_noactivate(hwnd: int):
    """알림 창이 포커스를 빼앗지 않도록 (교정 중인 창에 키가 가야 하므로)"""
    GWL_EXSTYLE = -20
    WS_EX_NOACTIVATE, WS_EX_TOOLWINDOW, WS_EX_TOPMOST, WS_EX_TRANSPARENT = 0x08000000, 0x80, 0x8, 0x20
    get = user32.GetWindowLongW
    user32.SetWindowLongW(hwnd, GWL_EXSTYLE,
                          get(hwnd, GWL_EXSTYLE) | WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW | WS_EX_TOPMOST | WS_EX_TRANSPARENT)


def show_noactivate(hwnd: int, x: int, y: int, w: int, h: int):
    HWND_TOPMOST, SWP_NOACTIVATE, SWP_SHOWWINDOW = -1, 0x0010, 0x0040
    user32.SetWindowPos(hwnd, HWND_TOPMOST, x, y, w, h, SWP_NOACTIVATE | SWP_SHOWWINDOW)


def hide(hwnd: int):
    user32.ShowWindow(hwnd, 0)
