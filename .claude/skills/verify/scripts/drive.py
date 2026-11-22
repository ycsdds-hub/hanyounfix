"""검증용 앱이 켜진 상태에서, 이 스크립트가 직접 띄운 텍스트 창(Tk)에 키를 쳐서 앱이 고친 결과를 읽음.
키보드와 포커스를 잠깐(약 30초) 빼앗으므로 사용자가 타이핑하지 않을 때만 실행.

사용: python .claude/skills/verify/scripts/drive.py [journey ...]
      journey: trust, typo-ko, typo-ko-space, ko-to-en, keep-en, context  (없으면 전부, trust는 항상 먼저)
증거: verify-evidence/<시각>/result.json, transcript.txt, settings.json, recent.json
종료 코드: 0 모두 통과, 1 실패
"""
import ctypes
import datetime
import json
import os
import shutil
import sys
import time
import tkinter as tk

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402
from hanyoung import win32  # noqa: E402

JOURNEYS = {  # 이름: (시작 한/영, 칠 키, 기대 결과)
    'typo-ko': ('en', 'dkssud ', '안녕 '),          # 영어 모드로 친 한글: 6글자에서 미리 교정 + 한/영 전환
    'typo-ko-space': ('en', 'rkawk ', '감자 '),     # 띄어쓰기에서 교정
    'ko-to-en': ('ko', 'hello ', 'hello '),         # 한글 모드로 친 영어
    'keep-en': ('en', 'hello world ', 'hello world '),  # 진짜 영어는 그대로
    'context': ('ko', 'go to job ', 'go to job '),  # 문맥 교정: 짧은 앞 단어도 같이
}
VK = {' ': 0x20}
user32 = ctypes.windll.user32
lines = []


def log(*a):
    s = ' '.join(str(x) for x in a)
    print(s, flush=True)
    lines.append(s)


def press(vk):
    win32._send([win32._kbd(vk, extra=0), win32._kbd(vk, up=True, extra=0)])  # extra=0: '사용자' 키처럼


class Window:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title('hanyoung verify')
        self.root.geometry('520x200+200+200')
        self.root.attributes('-topmost', True)
        self.text = tk.Text(self.root, font=('Malgun Gothic', 14))
        self.text.pack(fill='both', expand=True)
        self.pump(0.5)
        self.hwnd = int(self.root.wm_frame(), 16)

    def pump(self, sec):
        end = time.time() + sec
        while time.time() < end:
            self.root.update()
            time.sleep(0.01)

    def value(self):
        return self.text.get('1.0', 'end-1c')

    def focus(self):
        # 뒤에 있는 프로세스가 SetForegroundWindow를 쓰려면 직전 입력이 필요. Alt를 쓰면 Tk 창이
        # 메뉴 모드에 들어가 update()가 멈추므로, 아무 동작 없는 F24를 씀
        press(0x87)
        user32.SetForegroundWindow(self.hwnd)
        self.text.focus_force()
        self.pump(0.3)
        return win32.foreground() == self.hwnd

    def set_mode(self, mode):
        for _ in range(2):
            if win32.ime_mode() == mode:
                return True
            press(win32.VK_HANGUL)
            self.pump(0.4)
        return win32.ime_mode() == mode

    def type_traced(self, keys, gap=0.09, settle=1.5):
        trace, last = [], None
        for ch in keys:
            press(VK.get(ch, ord(ch.upper())))
            end = time.time() + gap
            while time.time() < end:
                self.root.update()
                cur = self.value()
                if cur != last:
                    trace.append(cur)
                    last = cur
                time.sleep(0.01)
        end = time.time() + settle
        while time.time() < end:
            self.root.update()
            cur = self.value()
            if cur != last:
                trace.append(cur)
                last = cur
            time.sleep(0.02)
        return self.value(), trace


def read_json(name):
    try:
        with open(os.path.join(common.CONFIG, name), encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def main():
    names = [a for a in sys.argv[1:] if a in JOURNEYS] or list(JOURNEYS)
    bad = [a for a in sys.argv[1:] if a not in JOURNEYS and a != 'trust']
    if bad:
        sys.exit(f'unknown journey {bad}; choose from trust, {", ".join(JOURNEYS)}')
    st = common.get_status(common.PORT)
    if not (st and st.get('enabled')):
        sys.exit('verify app not ready (launch.py, doctor.py)')
    out = os.path.join(common.EVIDENCE, datetime.datetime.now().strftime('%Y%m%d-%H%M%S'))
    results, fails = [], 0
    w = Window()
    exe = win32.app_name(w.hwnd)
    log('window exe:', exe, 'focused:', w.focus())

    # trust: 새 프로그램에서는 한/영 키를 한 번 눌러야 앱이 그 프로그램의 한/영 상태를 믿고 고침
    before = win32.ime_mode()
    press(win32.VK_HANGUL)
    w.pump(0.6)
    press(win32.VK_HANGUL)
    w.pump(0.6)
    trusted = (read_json('settings.json') or {}).get('trusted_apps', {})
    ok = trusted.get(exe) is True
    fails += not ok
    results.append({'journey': 'trust', 'ok': ok, 'mode_before': before, 'trusted_apps': trusted})
    log(f'{"OK  " if ok else "FAIL"} trust: settings.json trusted_apps = {trusted} (기대 {exe}: true)')

    for name in names:
        mode, keys, want = JOURNEYS[name]
        w.text.delete('1.0', 'end')
        focused = w.focus()
        mode_ok = w.set_mode(mode)
        if not (focused and mode_ok):
            fails += 1
            results.append({'journey': name, 'ok': False, 'error': f'focus={focused} mode={win32.ime_mode()}'})
            log(f'FAIL {name}: 준비 실패 focus={focused} 한/영={win32.ime_mode()} (기대 {mode})')
            continue
        got, trace = w.type_traced(keys)
        ok = got == want
        fails += not ok
        results.append({'journey': name, 'ok': ok, 'mode': mode, 'keys': keys, 'want': want, 'got': got,
                        'mode_after': win32.ime_mode(), 'trace': trace})
        log(f'{"OK  " if ok else "FAIL"} {name} [{mode}] {keys!r} -> {got!r} (기대 {want!r})')
        log('     화면 변화:', ' → '.join(repr(t) for t in trace))

    w.root.destroy()
    recent = read_json('recent.json')
    log('recent.json:', json.dumps(recent, ensure_ascii=False))
    os.makedirs(out)
    for name in ('settings.json', 'recent.json'):
        src = os.path.join(common.CONFIG, name)
        if os.path.exists(src):
            shutil.copy(src, out)
    with open(os.path.join(out, 'result.json'), 'w', encoding='utf-8') as f:
        json.dump({'fails': fails, 'results': results}, f, ensure_ascii=False, indent=2)
    log('모두 통과' if not fails else f'실패 {fails}', '| evidence:', out)
    with open(os.path.join(out, 'transcript.txt'), 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines) + '\n')
    sys.exit(1 if fails else 0)


if __name__ == '__main__':
    main()
