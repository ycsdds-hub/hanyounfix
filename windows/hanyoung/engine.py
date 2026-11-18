"""키 입력을 받아 한영 오타를 판단하고 고치는 엔진 (OS와 무관)

Windows 쪽(win32.py)은 키보드 후킹 이벤트를 KeyEvent로 바꿔 Engine.handle()에 넘기고,
Engine은 Platform 인터페이스(백스페이스, 한/영 전환, 키 다시 누르기)로 교정합니다.

교정 방식
- 지운 뒤 한/영을 바꾸고, 사용자가 눌렀던 '같은 물리 키'를 다시 누릅니다.
  IME가 직접 글자를 조합하므로 자연스럽고, 전환이 실패해도 원래 글자가 그대로 다시 입력될 뿐입니다.
- 교정하는 동안 사용자가 친 키는 막아 두었다가 교정이 끝나면 순서대로 다시 보냅니다.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field

from .core import Dictionary, decide, eng_to_hangul, ime_keys

KO, EN = 'ko', 'en'

VK_BACK, VK_TAB, VK_RETURN, VK_SPACE = 0x08, 0x09, 0x0D, 0x20
VK_HANGUL, VK_HANJA, VK_ESCAPE, VK_CAPITAL = 0x15, 0x19, 0x1B, 0x14
VK_SHIFTS = {0x10, 0xA0, 0xA1}
VK_CTRLS = {0x11, 0xA2, 0xA3}
VK_ALTS = {0x12, 0xA4, 0xA5}
VK_WINS = {0x5B, 0x5C}
MODIFIERS = VK_SHIFTS | VK_CTRLS | VK_ALTS | VK_WINS
VK_Z, VK_H = 0x5A, 0x48
# 단어를 끝내는 키: Space, Enter, , . ; / ' (Shift 포함 → ! ? : " 등)
BOUNDARY_VKS = {VK_SPACE, VK_RETURN, 0xBC, 0xBE, 0xBA, 0xBF, 0xDE}
VK_1 = 0x31  # Shift+1 = !
# 단어 중간에 오면 그 단어는 검사하지 않는 글자 키 (숫자, - = [ ] \ `)
WORD_BLOCKING_VKS = set(range(0x30, 0x3A)) | set(range(0x60, 0x70)) | {0xBD, 0xBB, 0xDB, 0xDD, 0xDC, 0xC0}

UNDO_WINDOW = 6.0  # 초


@dataclass(frozen=True)
class Key:
    """다시 누를 물리 키 하나"""
    vk: int
    shift: bool = False

    @property
    def char(self) -> str:
        c = chr(self.vk)  # 0x41~0x5A는 A~Z
        return c if self.shift else c.lower()


@dataclass
class KeyEvent:
    vk: int
    down: bool = True
    shift: bool = False
    ctrl: bool = False
    alt: bool = False
    win: bool = False
    caps: bool = False
    source: str = 'user'     # user | action(우리가 보낸 교정 키) | replay(막아 두었다 다시 보낸 키) | other
    app: str = ''            # 앞에 있는 프로그램 실행 파일 이름 (소문자)
    window: int = 0          # 앞에 있는 창
    password: bool = False   # 비밀번호 입력칸
    raw: object = None       # 다시 보낼 때 쓰는 원래 이벤트 정보


class Platform:
    """Engine이 쓰는 OS 기능. win32.py와 테스트용 가짜가 구현합니다."""

    def get_mode(self) -> str | None:   # 'ko', 'en', 모르면 None
        raise NotImplementedError

    def send_backspace(self, n: int) -> None:
        raise NotImplementedError

    def send_toggle(self) -> None:
        raise NotImplementedError

    def send_keys(self, keys: list[Key]) -> None:
        raise NotImplementedError

    def replay(self, events: list[KeyEvent]) -> None:
        """막아 둔 사용자 이벤트를 source='replay'로 다시 보냄 (그 이벤트는 다시 handle()을 거침)"""
        raise NotImplementedError

    def run_later(self, fn) -> None:
        """방금 키가 프로그램에 전달된 뒤에 fn을 실행"""
        raise NotImplementedError


@dataclass
class Settings:
    enabled: bool = True
    check_length: int = 6
    show_toast: bool = True
    user_words: list[str] = field(default_factory=list)
    excluded_apps: list[str] = field(default_factory=lambda: ['chrome.exe'])
    autostart: bool = False


@dataclass
class _Fix:
    orig_mode: str
    keys: list[Key]
    before: str          # 고치기 전 화면에 보이던 단어
    after: str           # 고친 단어
    boundary: Key | None
    time: float


class Engine:
    def __init__(self, platform: Platform, dictionary: Dictionary, settings: Settings,
                 notify=None, on_learn=None, on_toggle=None, clock=time.monotonic):
        self.p = platform
        self.dict = dictionary
        self.settings = settings
        self.notify = notify or (lambda before, after, message=None: None)
        self.on_learn = on_learn or (lambda word: None)
        self.on_toggle = on_toggle or (lambda enabled: None)
        self.clock = clock
        self.lock = threading.RLock()
        self.busy = False
        self.queue: list[KeyEvent] = []
        self.keys: list[Key] = []
        self.blocked = False       # 숫자 등이 섞여 이번 단어는 검사하지 않음
        self.word_fixed = False    # 이번 단어는 이미 고쳤음 (이어서 치는 중)
        self.window = None
        self.last_fix: _Fix | None = None
        self.keys_since_fix = 0
        self.sync_user_words()

    # ---------- 상태 ----------
    def sync_user_words(self):
        self.dict.user_words = {w.lower() for w in self.settings.user_words}

    def reset(self):
        self.keys = []
        self.blocked = False
        self.word_fixed = False

    def _keystr(self) -> str:
        return ''.join(k.char for k in self.keys)

    def _displayed(self, mode: str) -> str:
        """지금 화면에 보이는 단어"""
        s = self._keystr()
        return s if mode == EN else eng_to_hangul(ime_keys(s))

    # ---------- 이벤트 ----------
    def handle(self, ev: KeyEvent) -> bool:
        """True를 반환하면 이 키를 막습니다(프로그램에 전달하지 않음)."""
        with self.lock:
            if ev.source == 'action':
                return False
            if ev.source == 'other':
                if ev.down:
                    self.reset()
                return False
            if self.busy and ev.source == 'user':
                self.queue.append(ev)
                return True
            if not ev.down:
                return False
            return self._key_down(ev)

    def mouse_click(self):
        with self.lock:
            if not self.busy:
                self.reset()
                self.last_fix = None

    def _key_down(self, ev: KeyEvent) -> bool:
        s = self.settings
        if ev.ctrl and ev.alt and ev.vk == VK_H:
            s.enabled = not s.enabled
            self.reset()
            self.on_toggle(s.enabled)
            return True
        if ev.vk in MODIFIERS:
            return False
        if not s.enabled or ev.password or ev.app in s.excluded_apps:
            self.reset()
            return False
        if ev.window != self.window:
            self.window = ev.window
            self.reset()
            self.last_fix = None

        if ev.ctrl and not ev.alt and not ev.win and ev.vk == VK_Z and self._can_undo():
            self._start(self._undo)
            return True
        if ev.ctrl or ev.alt or ev.win:
            self.reset()
            return False
        if ev.vk in (VK_HANGUL, VK_HANJA):
            self.reset()
            self.last_fix = None
            return False

        if 0x41 <= ev.vk <= 0x5A:
            if ev.caps:
                self.reset()
                return False
            self.keys.append(Key(ev.vk, ev.shift))
            self.keys_since_fix += 1
            if not self.blocked and not self.word_fixed and len(self.keys) >= s.check_length:
                self._check_mid_word()
            return False  # 글자는 그대로 전달 (교정은 전달된 뒤에 실행)
        if ev.vk == VK_BACK:
            if self.keys:
                self.keys.pop()
            self.keys_since_fix += 1
            return False
        if ev.vk in BOUNDARY_VKS or (ev.shift and ev.vk == VK_1):
            return self._check_boundary(ev)
        if ev.vk in WORD_BLOCKING_VKS:
            self.keys = []
            self.blocked = True
            return False
        # 방향키, Tab, Esc, Delete, F키 등: 단어가 끊김
        self.reset()
        self.last_fix = None
        return False

    # ---------- 판단 ----------
    def _check_mid_word(self):
        """영어 모드로 한글을 길게 치는 중이면 띄어쓰기 전에 고침"""
        mode = self.p.get_mode()
        if mode != EN:
            return
        fixed = decide(self._keystr(), self.dict, mid_word=True)
        if fixed:
            keys = list(self.keys)
            self._start(lambda: self._fix(EN, keys, fixed, None, mid=True))

    def _check_boundary(self, ev: KeyEvent) -> bool:
        keys = list(self.keys)
        if not keys or self.blocked or self.word_fixed:
            self.reset()
            return False
        mode = self.p.get_mode()
        if mode is None:
            self.reset()
            return False
        token = self._displayed(mode)
        fixed = decide(token, self.dict)
        if not fixed:
            self.reset()
            return False
        boundary = Key(ev.vk, ev.shift)
        self._start(lambda: self._fix(mode, keys, fixed, boundary, mid=False, boundary_ev=ev))
        return True  # 띄어쓰기/Enter는 교정 뒤에 보냄

    # ---------- 실행 ----------
    def _can_undo(self) -> bool:
        f = self.last_fix
        return bool(f) and self.keys_since_fix == 0 and self.clock() - f.time < UNDO_WINDOW

    def _start(self, action):
        self.busy = True
        self.p.run_later(lambda: self._run(action))

    def _run(self, action):
        try:
            action()
        finally:
            self._drain()

    def _drain(self):
        """막아 두었던 키를 차례로 다시 보내고, 다 보내면 busy 해제"""
        while True:
            with self.lock:
                pending, self.queue = self.queue, []
                if not pending:
                    self.busy = False
                    return
            self.p.replay(pending)

    def _fix(self, mode, keys, fixed, boundary, mid, boundary_ev=None):
        p = self.p
        before = ''.join(k.char for k in keys)
        if mode == EN:
            # 화면: 영문 그대로 → 지우고, 한글로 바꾸고, 같은 키를 다시 누름 (IME가 조합)
            p.send_backspace(len(keys))
            p.send_toggle()
            p.send_keys(keys)
        else:
            before = eng_to_hangul(ime_keys(before))
            # 화면: 조합 중인 한글 → 전환하면 조합이 확정되므로 먼저 전환한 뒤 지움
            p.send_toggle()
            p.send_backspace(len(before))
            p.send_keys(keys)
        with self.lock:
            # Enter로 이미 보냈을 수 있는 글은 되돌리지 않음
            undoable = not (boundary and boundary.vk == VK_RETURN)
            self.last_fix = _Fix(mode, keys, before, fixed, boundary, self.clock()) if undoable else None
            self.keys_since_fix = 0
            if mid:
                self.word_fixed = True   # 이어서 치는 글자는 새 모드로 그대로
            else:
                self.reset()
            if boundary_ev is not None:
                self.queue.insert(0, KeyEvent(**{**boundary_ev.__dict__, 'source': 'user'}))
        if self.settings.show_toast:
            self.notify(before, fixed)

    def _undo(self):
        f = self.last_fix
        p = self.p
        extra = [f.boundary] if f.boundary else []
        if f.orig_mode == EN:
            # 지금 화면: 고친 한글(+띄어쓰기), 모드는 한글
            p.send_toggle()
            p.send_backspace(len(f.after) + len(extra))
            p.send_keys(f.keys + extra)
        else:
            # 지금 화면: 고친 영문(+띄어쓰기), 모드는 영어
            p.send_backspace(len(f.keys) + len(extra))
            p.send_toggle()
            p.send_keys(f.keys + extra)
        word = f.before.lower()
        with self.lock:
            self.last_fix = None
            self.reset()
            if word not in self.dict.user_words:
                self.settings.user_words.append(word)
                self.dict.user_words.add(word)
        self.on_learn(word)
        if self.settings.show_toast:
            self.notify(None, None, f"'{f.before}'은(는) 앞으로 고치지 않을게요")
