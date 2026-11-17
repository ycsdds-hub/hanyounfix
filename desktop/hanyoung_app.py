"""한영전환 실시간 자동 교정 앱 (Windows / macOS)

실행:   python hanyoung_app.py
점검:   python hanyoung_app.py --check    (현재 한영 상태가 제대로 감지되는지 5초간 출력)
일시정지/재개: Ctrl+Alt+H   (비밀번호 입력 등에서 잠깐 끄고 싶을 때)

필요: pip install pynput      (hanyoung_fix.py 와 같은 폴더에 두세요)
"""
import os
import re
import subprocess
import sys
import threading
import time

try:
    from pynput import keyboard, mouse
except Exception:  # 미설치 또는 디스플레이 없음
    keyboard = mouse = None

from hanyoung_fix import JAMO2KEY, WORDS, eng_to_hangul, hangul_to_eng

# ---------- 설정 ----------
CHECK_LEN = 10      # 이 글자 수에 도달하면 (띄어쓰기 전이라도) 한 번 검사
MIN_LEN = 3         # 이보다 짧은 단어는 오탐 방지를 위해 검사하지 않음
KO, EN = "ko", "en"
SHIFT_JAMO_KEYS = set("QWERTOP")  # 두벌식에서 Shift가 의미 있는 키
USER_WORDS = os.path.expanduser("~/.hanyoung_words.txt")  # 교정하지 말아야 할 단어(한 줄에 하나)

if os.path.exists(USER_WORDS):
    with open(USER_WORDS, encoding="utf-8") as f:
        WORDS.update(w.strip().lower() for w in f if w.strip())


# ---------- 순수 로직 (OS 무관) ----------
def norm(keys):
    """한글 IME에서는 Shift가 의미 없는 키(예: A)를 소문자로 취급."""
    return ''.join(c if c in SHIFT_JAMO_KEYS else c.lower() for c in keys)


def decide(keys, mode):
    """현재 모드(mode)와 입력 의도가 다르면 교정할 텍스트를, 아니면 None을 반환."""
    hangul = eng_to_hangul(norm(keys))
    clean = all('가' <= c <= '힣' for c in hangul)
    if keys.lower() in WORDS:
        intent = EN
    elif clean:
        intent = KO
    else:
        intent = EN
    if intent == mode:
        return None
    return keys if intent == EN else hangul


def backspaces_needed(keys, mode, composing):
    """화면에 보이는 글자를 지우는 데 필요한 백스페이스 수.
    조합 중인 마지막 글자는 자모 단위로 지워지므로 키 수만큼 필요."""
    if mode == EN:
        return len(keys)
    shown = eng_to_hangul(norm(keys))
    if not composing:
        return len(shown)
    return len(shown) - 1 + len(hangul_to_eng(shown[-1]))


# ---------- 플랫폼별 구현 ----------
class WindowsPlatform:
    name = "Windows"
    hint = "관리자 권한으로 실행 중인 프로그램에서 쓰려면 이 스크립트도 관리자 권한으로 실행하세요."

    def __init__(self):
        import ctypes
        from ctypes import wintypes
        self.user32, self.imm32 = ctypes.windll.user32, ctypes.windll.imm32
        self.user32.GetForegroundWindow.restype = wintypes.HWND
        self.imm32.ImmGetDefaultIMEWnd.argtypes = [wintypes.HWND]
        self.imm32.ImmGetDefaultIMEWnd.restype = wintypes.HWND
        self.user32.SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
        self.user32.SendMessageW.restype = ctypes.c_ssize_t

    def get_mode(self):
        ime = self.imm32.ImmGetDefaultIMEWnd(self.user32.GetForegroundWindow())
        if not ime:
            return None
        conv = self.user32.SendMessageW(ime, 0x283, 0x001, 0)  # WM_IME_CONTROL, IMC_GETCONVERSIONMODE
        return KO if conv & 1 else EN                          # IME_CMODE_NATIVE = 한글

    def toggle_mode(self, kb):
        key = keyboard.KeyCode.from_vk(0x15)  # VK_HANGUL (한/영 키)
        kb.press(key)
        kb.release(key)

    def key_letter(self, key, shift):
        vk = getattr(key, "vk", None)
        if vk and 0x41 <= vk <= 0x5A:
            c = chr(vk)
            return c if shift else c.lower()
        return None


class MacPlatform:
    name = "macOS"
    hint = ("시스템 설정 > 개인정보 보호 및 보안 > '손쉬운 사용'과 '입력 모니터링'에 "
            "터미널(또는 실행한 앱)을 허용해야 해요. 입력 소스 전환 단축키는 기본값 Control+Space여야 합니다.")

    def get_mode(self):
        try:
            out = subprocess.run(
                ["defaults", "read", "com.apple.HIToolbox", "AppleSelectedInputSources"],
                capture_output=True, text=True, timeout=2).stdout
        except Exception:
            return None
        if not out:
            return None
        return KO if re.search(r"Korean|Hangul|2SetKorean", out, re.I) else EN

    def toggle_mode(self, kb):
        with kb.pressed(keyboard.Key.ctrl):
            kb.tap(keyboard.Key.space)

    def key_letter(self, key, shift):
        return None  # char 기반 처리 사용


def make_platform():
    if sys.platform.startswith("win"):
        return WindowsPlatform()
    if sys.platform == "darwin":
        return MacPlatform()
    sys.exit("지원하지 않는 OS예요. Windows와 macOS만 지원합니다.")


# ---------- 실시간 교정기 ----------
class Fixer:
    SHIFT = {"shift", "shift_l", "shift_r"}
    CTRL = {"ctrl", "ctrl_l", "ctrl_r"}
    ALT = {"alt", "alt_l", "alt_r", "alt_gr"}
    CMD = {"cmd", "cmd_l", "cmd_r"}

    def __init__(self, platform):
        self.plat = platform
        self.kb = keyboard.Controller()
        self.buf = []
        self.checked = False
        self.busy = False
        self.ignore_until = 0.0
        self.enabled = True
        self.mods = {"shift": False, "ctrl": False, "alt": False, "cmd": False}

    # -- 상태 --
    def reset(self):
        self.buf.clear()
        self.checked = False

    def _mod_name(self, key):
        name = getattr(key, "name", None)
        for label, group in (("shift", self.SHIFT), ("ctrl", self.CTRL),
                             ("alt", self.ALT), ("cmd", self.CMD)):
            if name in group:
                return label
        return None

    def _letter(self, key):
        c = self.plat.key_letter(key, self.mods["shift"])
        if c is None and isinstance(key, keyboard.KeyCode) and key.char:
            c = JAMO2KEY.get(key.char, key.char)
        return c if c and c.isascii() and c.isalpha() else None

    # -- 이벤트 --
    def on_press(self, key):
        if self.busy or time.time() < self.ignore_until:
            return
        mod = self._mod_name(key)
        if mod:
            self.mods[mod] = True
            return
        c = self._letter(key)
        if self.mods["ctrl"] and self.mods["alt"] and c and c.lower() == "h":
            self.enabled = not self.enabled
            print("교정 켜짐" if self.enabled else "교정 일시정지")
            self.reset()
            return
        if not self.enabled:
            return
        if self.mods["ctrl"] or self.mods["alt"] or self.mods["cmd"]:
            self.reset()
            return
        if c:
            self.buf.append(c)
            if len(self.buf) == CHECK_LEN and not self.checked:
                self.check(boundary=None)
        elif key == keyboard.Key.space:
            if not self.checked:
                self.check(boundary=" ")
            self.reset()
        elif key == keyboard.Key.backspace:
            if self.buf:
                self.buf.pop()
        else:
            self.reset()

    def on_release(self, key):
        mod = self._mod_name(key)
        if mod:
            self.mods[mod] = False

    def on_click(self, *_):
        self.reset()

    # -- 검사 / 교정 --
    def check(self, boundary):
        keys = ''.join(self.buf)
        self.checked = True
        if len(keys) < MIN_LEN:
            return
        mode = self.plat.get_mode()
        if mode is None:
            return
        target = decide(keys, mode)
        if target is None:
            return
        n = backspaces_needed(keys, mode, composing=boundary is None)
        if boundary:
            n += 1  # 이미 입력된 띄어쓰기
        self.busy = True
        self.reset()
        threading.Timer(0.06, self._apply, args=(n, target, boundary)).start()

    def _apply(self, n, target, boundary):
        try:
            for _ in range(n):
                self.kb.tap(keyboard.Key.backspace)
                time.sleep(0.004)
            self.plat.toggle_mode(self.kb)
            time.sleep(0.08)
            self.kb.type(target + (boundary or ""))
            time.sleep(0.05)
        finally:
            self.ignore_until = time.time() + 0.3
            self.busy = False


def main():
    if keyboard is None:
        sys.exit("pynput를 불러오지 못했어요.  pip install pynput  후 다시 실행해 주세요.")
    plat = make_platform()
    print(f"[{plat.name}] 한영 자동 교정 시작  (일시정지/재개: Ctrl+Alt+H, 종료: Ctrl+C)")
    print(plat.hint)

    if "--check" in sys.argv:
        for _ in range(5):
            print("현재 모드:", plat.get_mode())
            time.sleep(1)
        return

    fixer = Fixer(plat)
    with keyboard.Listener(on_press=fixer.on_press, on_release=fixer.on_release) as kl, \
            mouse.Listener(on_click=fixer.on_click) as ml:
        try:
            kl.join()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
