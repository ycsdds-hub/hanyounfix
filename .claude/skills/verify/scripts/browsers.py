"""설치된 브라우저마다 주소창에서 교정이 되는지 확인. launch.py로 검증 앱을 띄운 뒤 실행.
브라우저마다 새 창을 열고(about:blank) → 주소창(Ctrl+L) → 한/영 상태 조회와 전환 시간 측정 →
한/영 키 두 번(신뢰 학습) → 영어 모드로 dkssud + 띄어쓰기 → 주소창 글자를 클립보드로 읽음 → 연 창만 닫음.
키보드·포커스·클립보드를 브라우저당 약 10초 쓴다 (클립보드는 끝나면 되돌림).

사용: python .claude/skills/verify/scripts/browsers.py [--no-trust] [exe이름 ...]   (없으면 등록된 브라우저 전부)
      --no-trust: 한/영 키를 누르지 않고 침 (기본 신뢰 목록만으로 고치는지 확인)
증거: verify-evidence/<시각>-browsers/result.json, transcript.txt
"""
import ctypes
import datetime
import json
import os
import subprocess
import sys
import time
import tkinter as tk
import winreg
from ctypes import wintypes

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402
from hanyoung import win32  # noqa: E402

u = ctypes.windll.user32
lines = []
NO_TRUST = '--no-trust' in sys.argv


def log(*a):
    s = ' '.join(str(x) for x in a)
    print(s, flush=True)
    lines.append(s)


def k(vk, up=False):
    return win32._kbd(vk, up=up, extra=0)  # extra=0: 사용자 키처럼


def press(vk):
    win32._send([k(vk), k(vk, True)])


def combo(mod, vk):
    win32._send([k(mod), k(vk), k(vk, True), k(mod, True)])


def registered_browsers():
    found = {}
    for root, sub in ((winreg.HKEY_LOCAL_MACHINE, r'SOFTWARE\Clients\StartMenuInternet'),
                      (winreg.HKEY_CURRENT_USER, r'SOFTWARE\Clients\StartMenuInternet'),
                      (winreg.HKEY_LOCAL_MACHINE, r'SOFTWARE\WOW6432Node\Clients\StartMenuInternet')):
        try:
            key = winreg.OpenKey(root, sub)
        except OSError:
            continue
        for i in range(winreg.QueryInfoKey(key)[0]):
            name = winreg.EnumKey(key, i)
            try:
                cmd = winreg.QueryValue(key, name + r'\shell\open\command').strip().strip('"')
            except OSError:
                continue
            if cmd.lower().endswith('.exe') and os.path.exists(cmd):
                found[cmd.lower()] = (name, cmd)
    return sorted(found.values(), key=lambda x: x[0].lower())


def windows_of(exe):
    out = []

    def cb(h, _):
        if u.IsWindowVisible(h) and u.GetWindowTextLengthW(h) and win32.app_name(h) == exe:
            out.append(h)
        return True
    u.EnumWindows(ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)(cb), 0)
    return out


class Clip:
    def __init__(self):
        self.root = tk.Tk()
        self.root.withdraw()
        try:
            self.saved = self.root.clipboard_get()
        except tk.TclError:
            self.saved = None

    def address_text(self):
        for _ in range(3):  # 복사가 가끔 비어서 몇 번 다시 읽음
            text = self._read()
            if text not in (None, '<<none>>'):
                return text
        return text

    def _read(self):
        self.root.clipboard_clear()
        self.root.clipboard_append('<<none>>')
        self.root.update()
        combo(win32.VK_CONTROL, ord('L'))
        time.sleep(0.3)
        combo(win32.VK_CONTROL, ord('C'))
        time.sleep(0.5)
        self.root.update()  # 클립보드 주인이 바뀐 것을 Tk가 알아야 새 내용을 읽음
        try:
            return self.root.clipboard_get()
        except tk.TclError:
            return None

    def restore(self):
        self.root.clipboard_clear()
        if self.saved is not None:
            self.root.clipboard_append(self.saved)
        self.root.update()
        self.root.destroy()


def fixes_for(exe):
    try:
        with open(os.path.join(common.CONFIG, 'recent.json'), encoding='utf-8') as f:
            return sum(1 for e in json.load(f) if e.get('app') == exe and e.get('kind') == 'fix')
    except (OSError, ValueError):
        return 0


def toggle_ms():
    before = win32.ime_mode()
    press(win32.VK_HANGUL)
    t = time.perf_counter()
    while time.perf_counter() - t < 1.0:
        if win32.ime_mode() != before:
            return before, round((time.perf_counter() - t) * 1000)
        time.sleep(0.005)
    return before, None


def check(name, path, clip):
    exe = os.path.basename(path).lower()
    r = {'browser': name, 'exe': exe}
    old = set(windows_of(exe))
    if exe == 'firefox.exe':
        # 프로필이 여러 개면 '프로필 선택' 창에서 멈추므로, 사용자 프로필 대신 임시 프로필로 띄움
        profile = os.path.join(common.INSTANCE, 'firefox-profile')
        os.makedirs(profile, exist_ok=True)
        args = [path, '-no-remote', '-new-instance', '-profile', profile, 'about:blank']
    else:
        args = [path, '--new-window', 'about:blank']
    proc = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)  # 브라우저 자체 로그는 버림
    new = None
    end = time.time() + 45  # 꺼져 있던 브라우저는 처음 뜨는 데 오래 걸림
    while time.time() < end and not new:
        time.sleep(0.5)
        fresh = [h for h in windows_of(exe) if h not in old]
        new = fresh[0] if fresh else None
    if not new:
        r['error'] = 'new window did not appear in 45s'
        return r
    try:
        return drive(r, new, clip)
    finally:
        press(0x1B)
        time.sleep(0.2)
        u.PostMessageW(new, 0x0010, 0, 0)  # WM_CLOSE: 이 스크립트가 연 창만
        time.sleep(1)
        if exe == 'firefox.exe':  # 임시 프로필 인스턴스는 이 스크립트 것: 끝날 때까지 기다리고 안 끝나면 끔
            try:
                proc.wait(15)
            except subprocess.TimeoutExpired:
                subprocess.run(['taskkill', '/PID', str(proc.pid), '/T', '/F'], capture_output=True)


def drive(r, new, clip):
    end = time.time() + 60  # 처음 켠 프로필은 한동안 응답 없음(Ghost 창)
    while time.time() < end and u.IsHungAppWindow(new):
        time.sleep(0.5)
    r['hung'] = bool(u.IsHungAppWindow(new))
    time.sleep(3)  # 첫 실행 화면·세션 복원이 자리 잡을 시간
    press(0x87)  # F24: SetForegroundWindow 허용용 (아무 동작 없음)
    u.SetForegroundWindow(new)
    time.sleep(0.6)
    r['focused'] = win32.foreground() == new
    combo(win32.VK_CONTROL, ord('L'))
    time.sleep(0.4)
    r['mode_read'] = win32.ime_mode()
    if NO_TRUST:  # 한/영 키를 한 번도 누르지 않음: 기본 신뢰만으로 고치는지
        r['toggle_ms'] = 'skipped'
    else:
        lat = []
        for _ in range(4):
            lat.append(toggle_ms())
            time.sleep(0.3)  # 앱의 한/영 확인(0.15초 뒤)이 다음 키와 겹치지 않게
        r['toggle_ms'] = [ms for _, ms in lat]
        for _ in range(2):
            if win32.ime_mode() == 'en':
                break
            press(win32.VK_HANGUL)
            time.sleep(0.4)
    r['mode_before_typing'] = win32.ime_mode()
    before_fixes = fixes_for(r['exe'])
    combo(win32.VK_CONTROL, ord('L'))
    press(win32.VK_BACK)
    time.sleep(0.3)
    keys, want = ('dkssud ', '안녕') if win32.ime_mode() != 'ko' else ('hello ', 'hello')
    r['keys'] = keys
    for ch in keys:
        press(0x20 if ch == ' ' else ord(ch.upper()))
        time.sleep(0.09)
    time.sleep(1.5)
    r['typed'] = clip.address_text()
    r['recorded'] = fixes_for(r['exe']) - before_fixes
    r['mode_after'] = win32.ime_mode()
    # 교정 기록이 있어야 하고, 읽은 글자가 있으면 안녕이어야 함 (클립보드 읽기는 가끔 실패)
    text = r['typed'] if r['typed'] not in (None, '<<none>>') else None
    r['ok'] = r['recorded'] == 1 and (text is None or text.strip() == want)
    return r


def main():
    if not (common.get_status(common.PORT) or {}).get('enabled'):
        sys.exit('verify app not ready (launch.py)')
    if u.GetKeyState(0x14) & 1:
        sys.exit('Caps Lock is on: 앱은 Caps Lock이 켜져 있으면 고치지 않음. 끄고 다시 실행')
    want = {a.lower() for a in sys.argv[1:] if not a.startswith('--')}
    targets = [(n, p) for n, p in registered_browsers() if not want or os.path.basename(p).lower() in want]
    log('browsers:', ', '.join(f'{n} ({os.path.basename(p)})' for n, p in targets))
    clip = Clip()
    results = []
    try:
        clip.address_text()  # 첫 복사는 가끔 비어서 한 번 버림
        for name, path in targets:
            r = check(name, path, clip)
            results.append(r)
            log(f'{"OK  " if r.get("ok") else "FAIL"} {name} ({r["exe"]}) mode={r.get("mode_read")} '
                f'toggle_ms={r.get("toggle_ms")} typed={r.get("typed")!r} recorded={r.get("recorded")} after={r.get("mode_after")} '
                f'{r.get("error", "")}')
    finally:
        clip.restore()
    trusted = {}
    try:
        with open(os.path.join(common.CONFIG, 'settings.json'), encoding='utf-8') as f:
            trusted = json.load(f).get('trusted_apps', {})
    except (OSError, ValueError):
        pass
    log('verify trusted_apps:', trusted)
    out = os.path.join(common.EVIDENCE, datetime.datetime.now().strftime('%Y%m%d-%H%M%S') + '-browsers')
    os.makedirs(out)
    with open(os.path.join(out, 'result.json'), 'w', encoding='utf-8') as f:
        json.dump({'results': results, 'trusted_apps': trusted}, f, ensure_ascii=False, indent=2)
    fails = sum(not r.get('ok') for r in results)
    log('모두 통과' if not fails else f'실패 {fails}', '| evidence:', out)
    with open(os.path.join(out, 'transcript.txt'), 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines) + '\n')
    sys.exit(1 if fails else 0)


if __name__ == '__main__':
    main()
