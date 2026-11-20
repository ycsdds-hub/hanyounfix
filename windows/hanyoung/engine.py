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

from .core import Dictionary, decide, decide_context, eng_to_hangul, ime_keys

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
CONTEXT_WORDS = 3   # 문맥 교정 때 함께 볼 앞 단어 수
RETYPE_WINDOW = 60.0  # 초: 고친 단어를 이 시간 안에 같은 모드로 다시 치면 일부러 쓴 것으로 보고 그대로 둠
KEEP_SAME_WINDOW = 600.0   # 초: 일부러 다시 쓴 단어를 같은 창에서는 10분 동안 그대로 둠 (쓸 때마다 연장)
KEEP_OTHER_WINDOW = 60.0   # 초: 다른 창에서는 1분 동안만


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
    learn: str = ''      # 되돌렸을 때 '고치지 않을 단어'로 배울 단어 (문맥 교정이면 마지막 단어만)


@dataclass
class _Word:
    """띄어쓰기로 끝났지만 교정하지 않은 단어 (문맥 교정용)"""
    keys: list[Key]
    mode: str


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
        self.word_kept = False     # 이번 단어는 고쳤던 단어를 다시 친 것: 그대로 둠
        self.history: list[_Word] = []  # 바로 앞에 띄어쓰기로 이어 친 단어들 (오래된 순)
        self.recent: list[tuple[str, str, float]] = []  # 최근에 고친 (키, 원래 모드, 시각)
        self.kept: list[list] = []  # 일부러 다시 쓴 단어 [키, 모드, 창, 시각]
        self.erased = False        # 마지막 교정 뒤에 백스페이스로 지운 적이 있는지
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
        self.word_kept = False

    def _keystr(self) -> str:
        return ''.join(k.char for k in self.keys)

    @staticmethod
    def _show(keys: list[Key], mode: str) -> str:
        """keys를 mode로 쳤을 때 화면에 보이는 단어"""
        s = ''.join(k.char for k in keys)
        return s if mode == EN else eng_to_hangul(ime_keys(s))

    def _displayed(self, mode: str) -> str:
        """지금 화면에 보이는 단어"""
        return self._show(self.keys, mode)

    # ---------- 다시 쓰면 그대로 두기 ----------
    def _retype_index(self, keys: list[Key], mode: str, prefix: bool = False) -> int | None:
        """방금 고친 단어를 지우고 그 자리에 원래 모드 그대로 다시 쳤으면 그 기록의 위치 (prefix: 치는 중인 앞부분)"""
        if not self.erased:
            return None  # 지우지 않고 또 친 것은 같은 실수를 반복한 것으로 봄
        now = self.clock()
        self.recent = [r for r in self.recent if now - r[2] < RETYPE_WINDOW]
        s = ''.join(k.char for k in keys).lower()
        for i, (k, m, _) in enumerate(self.recent):
            if m == mode and (k == s or (prefix and (k.startswith(s) or s.startswith(k)))):
                return i
        return None

    def _retyped(self, keys: list[Key], mode: str, prefix: bool = False) -> bool:
        return self._retype_index(keys, mode, prefix) is not None

    def _keep(self, word: str, keys: list[Key], mode: str):
        """일부러 다시 쓴 단어: 같은 창에서 10분, 다른 창에서 1분 동안 그대로 둠 (영구히 배우지는 않음)"""
        s = ''.join(k.char for k in keys).lower()
        self.kept = [k for k in self.kept if not (k[0] == s and k[1] == mode and k[2] == self.window)]
        self.kept.append([s, mode, self.window, self.clock()])
        if self.settings.show_toast:
            self.notify(None, None, f"다시 쓰셔서 '{word}'은(는) 이 창에서 10분 동안 그대로 둘게요")

    def _exempt(self, keys: list[Key], mode: str, prefix: bool = False) -> bool:
        """일부러 다시 쓴 단어라 아직 그대로 둘 기간인지 (같은 창 10분, 다른 창 1분)"""
        now = self.clock()
        self.kept = [k for k in self.kept if now - k[3] < KEEP_SAME_WINDOW]
        s = ''.join(k.char for k in keys).lower()
        for k in self.kept:
            if k[1] != mode or not (k[0] == s or (prefix and k[0].startswith(s))):
                continue
            same = k[2] == self.window
            if now - k[3] < (KEEP_SAME_WINDOW if same else KEEP_OTHER_WINDOW):
                if same and k[0] == s:
                    k[3] = now  # 같은 창에서 또 쓰면 10분 연장
                return True
        return False

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
                self.history = []
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
            self.history = []
            return False
        if ev.window != self.window:
            self.window = ev.window
            self.reset()
            self.history = []
            self.recent = []
            self.last_fix = None

        if ev.ctrl and not ev.alt and not ev.win and ev.vk == VK_Z and self._can_undo():
            self._start(self._undo)
            return True
        if ev.ctrl or ev.alt or ev.win:
            if ev.ctrl and ev.vk == VK_BACK:
                self.erased = True
            self.reset()
            self.history = []
            return False
        if ev.vk in (VK_HANGUL, VK_HANJA):
            self.reset()
            self.history = []
            self.last_fix = None
            return False

        if 0x41 <= ev.vk <= 0x5A:
            if ev.caps:
                self.reset()
                self.history = []
                return False
            self.keys.append(Key(ev.vk, ev.shift))
            self.keys_since_fix += 1
            if not self.blocked and not self.word_fixed and not self.word_kept and len(self.keys) >= s.check_length:
                self._check_mid_word()
            return False  # 글자는 그대로 전달 (교정은 전달된 뒤에 실행)
        if ev.vk == VK_BACK:
            if self.keys:
                self.keys.pop()
            else:
                self.history = []  # 앞 단어와의 띄어쓰기를 지웠을 수 있음
            self.erased = True
            self.keys_since_fix += 1
            return False
        if ev.vk in BOUNDARY_VKS or (ev.shift and ev.vk == VK_1):
            return self._check_boundary(ev)
        if ev.vk in WORD_BLOCKING_VKS:
            self.keys = []
            self.blocked = True
            self.history = []
            return False
        # 방향키, Tab, Esc, Delete, F키 등: 단어가 끊김
        self.reset()
        self.history = []
        self.last_fix = None
        return False

    # ---------- 판단 ----------
    def _check_mid_word(self):
        """영어 모드로 한글을 길게 치는 중이면 띄어쓰기 전에 고침"""
        mode = self.p.get_mode()
        if mode != EN:
            return
        if self._retyped(self.keys, mode, prefix=True):
            self.word_kept = True
            return
        if self._exempt(self.keys, mode, prefix=True):
            return  # 일부러 쓴 단어일 수 있음: 띄어쓰기에서 판단
        fixed = decide(self._keystr(), self.dict, mid_word=True)
        if fixed:
            keys = list(self.keys)
            context = self._context(mode)  # 앞의 짧은 단어도 함께 (예: sk dkssud → 나 안녕)
            self.history = []
            self._start(lambda: self._fix(EN, keys, fixed, None, mid=True, context=context))

    def _check_boundary(self, ev: KeyEvent) -> bool:
        keys = list(self.keys)
        plain_space = ev.vk == VK_SPACE and not ev.shift
        if not keys or self.blocked or self.word_fixed:
            self.reset()
            self.history = []
            return False
        mode = self.p.get_mode()
        if mode is None:
            self.reset()
            self.history = []
            return False
        token = self._displayed(mode)
        idx = self._retype_index(keys, mode, prefix=self.word_kept)
        if self.word_kept or idx is not None:
            # 고친 단어를 지우고 그 자리에 같은 모드로 다시 침 → 이번만 그대로 (그 기록은 다 씀)
            if idx is not None:
                del self.recent[idx]
            self._keep(token, keys, mode)
            self.reset()
            self.history = []
            return False
        # 다른 단어를 끝까지 쳤으면 '그 자리에 다시 쓰기'는 끝남
        self.recent = []
        if self._exempt(keys, mode):
            # 일부러 다시 썼던 단어: 같은 창 10분, 다른 창 1분 동안 그대로
            self.reset()
            self.history = []
            return False
        fixed = decide(token, self.dict)
        if not fixed:
            self.reset()
            if plain_space:
                self.history = (self.history + [_Word(keys, mode)])[-CONTEXT_WORDS:]
            else:
                self.history = []
            return False
        context = self._context(mode)
        self.history = []
        boundary = Key(ev.vk, ev.shift)
        self._start(lambda: self._fix(mode, keys, fixed, boundary, mid=False, boundary_ev=ev, context=context))
        return True  # 띄어쓰기/Enter는 교정 뒤에 보냄

    def _context(self, mode: str) -> list:
        """이번 단어와 같은 모드로 바로 앞에 친 단어 중 함께 고칠 단어들 (가까운 것부터 끊김 없이)"""
        out = []
        for w in reversed(self.history):
            if w.mode != mode or self._retyped(w.keys, mode) or self._exempt(w.keys, mode):
                break
            shown = self._show(w.keys, mode)
            if decide(shown, self.dict):
                break  # 혼자서도 고쳐질 단어가 남아 있다면 일부러 둔 것 → 문맥으로 끌어오지 않음
            fixed = decide_context(shown, self.dict, to_english=(mode == KO))
            if not fixed:
                break
            out.append((w, fixed))
        out.reverse()
        return out

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

    def _fix(self, mode, keys, fixed, boundary, mid, boundary_ev=None, context=()):
        p = self.p
        word_before = self._show(keys, mode)
        # 문맥 교정: 앞 단어들과 띄어쓰기까지 한꺼번에 지우고 다시 침
        space = Key(VK_SPACE)
        all_keys, befores, afters = [], [], []
        for w, w_fixed in context:
            all_keys += w.keys + [space]
            befores.append(self._show(w.keys, mode))
            afters.append(w_fixed)
        all_keys += keys
        before = ' '.join(befores + [word_before])
        after = ' '.join(afters + [fixed])
        if mode == EN:
            # 화면: 영문 그대로 → 지우고, 한글로 바꾸고, 같은 키를 다시 누름 (IME가 조합)
            p.send_backspace(len(before))
            p.send_toggle()
            p.send_keys(all_keys)
        else:
            # 화면: 조합 중인 한글 → 전환하면 조합이 확정되므로 먼저 전환한 뒤 지움
            p.send_toggle()
            p.send_backspace(len(before))
            p.send_keys(all_keys)
        with self.lock:
            # Enter로 이미 보냈을 수 있는 글은 되돌리지 않음
            undoable = not (boundary and boundary.vk == VK_RETURN)
            self.last_fix = (_Fix(mode, all_keys, before, after, boundary, self.clock(), learn=word_before)
                             if undoable else None)
            now = self.clock()
            for w, _ in context:
                self.recent.append((''.join(k.char for k in w.keys).lower(), mode, now))
            self.recent.append((''.join(k.char for k in keys).lower(), mode, now))
            self.erased = False
            self.keys_since_fix = 0
            if mid:
                self.word_fixed = True   # 이어서 치는 글자는 새 모드로 그대로
            else:
                self.reset()
            if boundary_ev is not None:
                self.queue.insert(0, KeyEvent(**{**boundary_ev.__dict__, 'source': 'user'}))
        if self.settings.show_toast:
            self.notify(before, after)

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
        word = (f.learn or f.before).lower()
        with self.lock:
            self.last_fix = None
            self.reset()
            if word not in self.dict.user_words:
                self.settings.user_words.append(word)
                self.dict.user_words.add(word)
        self.on_learn(word)
        if self.settings.show_toast:
            self.notify(None, None, f"'{f.learn or f.before}'은(는) 앞으로 고치지 않을게요")
