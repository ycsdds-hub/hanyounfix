"""작업 표시줄 아이콘(트레이), 설정 창, 교정 알림"""
from __future__ import annotations

import os
import queue
import tkinter as tk
from tkinter import ttk

from . import win32
from .core import default_data_dir
from .settings import set_autostart

FONT = ('Malgun Gothic', 10)
BG, FG, MUTED, ACCENT = '#1f2328', '#f6f8fa', '#9aa4ae', '#7ee2a8'


def icon_path() -> str:
    d = default_data_dir()
    for p in (os.path.join(d, 'icon.png'), os.path.join(d, 'icons', 'icon128.png')):
        if os.path.exists(p):
            return p
    return ''


class Toast:
    """오른쪽 아래 알림. 포커스를 가져가지 않습니다."""

    def __init__(self, root: tk.Tk):
        self.win = tk.Toplevel(root)
        self.win.overrideredirect(True)
        self.win.configure(bg=BG)
        self.win.withdraw()
        self.title = tk.Label(self.win, bg=BG, fg=FG, font=('Malgun Gothic', 11), anchor='w', justify='left')
        self.title.pack(fill='x', padx=14, pady=(10, 0))
        self.hint = tk.Label(self.win, bg=BG, fg=MUTED, font=('Malgun Gothic', 9), anchor='w')
        self.hint.pack(fill='x', padx=14, pady=(2, 10))
        self.win.update_idletasks()
        self.hwnd = int(self.win.wm_frame(), 16)
        win32.make_noactivate(self.hwnd)
        self.timer = None

    def show(self, before, after, message=None):
        if message:
            self.title.config(text=message, fg=FG)
            self.hint.config(text='')
        else:
            self.title.config(text=f'{before}  →  {after}', fg=ACCENT)
            self.hint.config(text='한/영을 바꿔 다시 입력했어요 · 잘못 고쳤으면 Ctrl+Z')
        self.win.update_idletasks()
        w = max(260, self.win.winfo_reqwidth())
        h = self.win.winfo_reqheight()
        left, top, right, bottom = win32.work_area()
        win32.show_noactivate(self.hwnd, right - w - 16, bottom - h - 16, w, h)
        if self.timer:
            self.win.after_cancel(self.timer)
        self.timer = self.win.after(2600, lambda: win32.hide(self.hwnd))


class SettingsWindow:
    def __init__(self, app: 'App'):
        self.app = app
        s = app.store.settings
        self.win = tk.Toplevel(app.root)
        self.win.title('한영 오타 자동 교정 설정')
        self.win.resizable(False, False)
        if app.icon_img:
            self.win.iconphoto(False, app.icon_img)
        self.win.protocol('WM_DELETE_WINDOW', self.close)
        f = ttk.Frame(self.win, padding=16)
        f.pack(fill='both')

        self.enabled = tk.BooleanVar(value=s.enabled)
        ttk.Checkbutton(f, text='자동 교정 켜기  (Ctrl+Alt+H)', variable=self.enabled).grid(row=0, column=0, columnspan=2, sticky='w')
        self.toast = tk.BooleanVar(value=s.show_toast)
        ttk.Checkbutton(f, text='교정할 때 알림 표시', variable=self.toast).grid(row=1, column=0, columnspan=2, sticky='w', pady=(4, 0))
        self.autostart = tk.BooleanVar(value=s.autostart)
        ttk.Checkbutton(f, text='윈도우 시작 시 자동 실행', variable=self.autostart).grid(row=2, column=0, columnspan=2, sticky='w', pady=(4, 0))

        ttk.Label(f, text='띄어쓰기 전에도 검사할 글자 수').grid(row=3, column=0, sticky='w', pady=(10, 0))
        self.length = tk.IntVar(value=s.check_length)
        ttk.Spinbox(f, from_=4, to=30, width=5, textvariable=self.length).grid(row=3, column=1, sticky='e', pady=(10, 0))

        ttk.Label(f, text='교정하지 않을 프로그램 (실행 파일 이름, 한 줄에 하나)').grid(row=4, column=0, columnspan=2, sticky='w', pady=(12, 2))
        ttk.Label(f, text='브라우저(주소창 포함)도 이 앱이 고쳐요. 앱이 켜져 있으면 Chrome 확장은 쉬어요.', foreground='#656d76').grid(row=5, column=0, columnspan=2, sticky='w')
        self.apps = tk.Text(f, width=46, height=4, font=('Consolas', 10))
        self.apps.insert('1.0', '\n'.join(s.excluded_apps))
        self.apps.grid(row=6, column=0, columnspan=2, sticky='we')

        ttk.Label(f, text='고치지 않을 단어 (한 줄에 하나)').grid(row=7, column=0, columnspan=2, sticky='w', pady=(12, 2))
        self.words = tk.Text(f, width=46, height=5, font=('Consolas', 10))
        self.words.insert('1.0', '\n'.join(s.user_words))
        self.words.grid(row=8, column=0, columnspan=2, sticky='we')

        ttk.Label(f, text='지금 앞에 있는 프로그램').grid(row=9, column=0, columnspan=2, sticky='w', pady=(12, 2))
        self.status = ttk.Label(f, text='다른 창을 클릭하면 여기에 표시돼요', foreground='#1a7f37')
        self.status.grid(row=10, column=0, columnspan=2, sticky='w')
        ttk.Label(f, text='처음 쓰는 프로그램에서는 한/영 키를 한 번 눌러야 교정이 시작돼요.', foreground='#656d76').grid(row=11, column=0, columnspan=2, sticky='w')

        btns = ttk.Frame(f)
        btns.grid(row=12, column=0, columnspan=2, sticky='e', pady=(14, 0))
        ttk.Button(btns, text='저장', command=self.save).pack(side='left', padx=4)
        ttk.Button(btns, text='닫기', command=self.close).pack(side='left')
        self.own = os.getpid()
        self._tick()
        self.win.lift()
        self.win.focus_force()

    def _tick(self):
        if not self.win.winfo_exists():
            return
        hwnd = win32.foreground()
        pid = win32.wintypes.DWORD()
        win32.user32.GetWindowThreadProcessId(hwnd, win32.ctypes.byref(pid))
        if hwnd and pid.value != self.own:
            app = win32.app_name(hwnd)
            mode = win32.ime_mode(hwnd)
            mode_txt = {'ko': '한글 모드', 'en': '영어 모드', None: '한/영 상태를 알 수 없음'}[mode]
            trusted = self.app.platform.trusted.get(app)
            if app in self.app.store.settings.excluded_apps:
                state = '제외된 프로그램'
            elif trusted is True:
                state = '교정 중'
            elif trusted is False:
                state = '이 프로그램은 한/영 상태를 알려 주지 않아 교정할 수 없어요'
            else:
                state = '한/영 키를 한 번 누르면 교정 시작'
            self.status.config(text=f'{app or "?"} · {mode_txt} · {state}')
        self.win.after(500, self._tick)

    def save(self):
        s = self.app.store.settings
        s.enabled = self.enabled.get()
        s.show_toast = self.toast.get()
        try:
            s.check_length = max(4, min(30, int(self.length.get())))
        except (tk.TclError, ValueError):
            pass
        s.excluded_apps = [a.strip().lower() for a in self.apps.get('1.0', 'end').splitlines() if a.strip()]
        s.user_words = list(dict.fromkeys(w.strip() for w in self.words.get('1.0', 'end').splitlines() if w.strip()))
        if self.autostart.get() != s.autostart:
            s.autostart = self.autostart.get()
            try:
                set_autostart(s.autostart)
            except OSError as e:
                print('자동 실행 설정 실패:', e)
        self.app.engine.sync_user_words()
        self.app.store.save()
        self.app.refresh_tray()
        self.close()

    def close(self):
        self.app.settings_window = None
        self.win.destroy()


class App:
    def __init__(self, store, engine=None, platform=None):
        self.store, self.engine, self.platform = store, engine, platform
        self.root = tk.Tk()
        self.root.withdraw()
        self.jobs: queue.Queue = queue.Queue()
        self.settings_window = None
        path = icon_path()
        self.icon_img = tk.PhotoImage(file=path) if path else None
        self.toast_box = Toast(self.root)
        self.tray = None
        self.root.after(50, self._poll)

    # 다른 스레드에서 호출해도 안전하게
    def post(self, fn):
        self.jobs.put(fn)

    def _poll(self):
        try:
            while True:
                self.jobs.get_nowait()()
        except queue.Empty:
            pass
        self.root.after(50, self._poll)

    def notify(self, before, after, message=None):
        self.post(lambda: self.toast_box.show(before, after, message))

    def open_settings(self):
        if self.settings_window:
            self.settings_window.win.lift()
        else:
            self.settings_window = SettingsWindow(self)

    def toggle(self):
        s = self.store.settings
        s.enabled = not s.enabled
        self.engine.reset()
        self.on_toggled(s.enabled)

    def toggle_autostart(self):
        """오른쪽 아래 아이콘 메뉴에서 '윈도우 시작 시 자동 실행' 켜기/끄기"""
        s = self.store.settings
        try:
            set_autostart(not s.autostart)
        except OSError as e:
            self.notify(None, None, f'자동 실행을 바꾸지 못했어요: {e}')
            return
        s.autostart = not s.autostart
        if self.settings_window:  # 설정 창이 열려 있으면 그 체크 표시도 맞춤
            self.settings_window.autostart.set(s.autostart)
        self.store.save()
        self.refresh_tray()
        self.notify(None, None, '윈도우 시작 시 자동으로 실행해요' if s.autostart else '윈도우 시작 시 자동 실행을 껐어요')

    def on_toggled(self, enabled):
        self.store.save()
        self.refresh_tray()
        self.notify(None, None, '자동 교정을 켰어요' if enabled else '자동 교정을 껐어요')

    def refresh_tray(self):
        if self.tray:
            self.tray.icon = self._tray_image()
            self.tray.title = '한영 오타 자동 교정' + ('' if self.store.settings.enabled else ' (꺼짐)')
            self.tray.update_menu()

    def _tray_image(self):
        from PIL import Image
        path = icon_path()
        img = Image.open(path).convert('RGBA') if path else Image.new('RGBA', (64, 64), BG)
        if not self.store.settings.enabled:
            alpha = img.getchannel('A')
            img = img.convert('L').convert('RGBA')
            img.putalpha(alpha.point(lambda a: a // 2))
        return img

    def start_tray(self):
        import pystray
        item = pystray.MenuItem
        menu = pystray.Menu(
            item('자동 교정', lambda: self.post(self.toggle), checked=lambda _: self.store.settings.enabled),
            item('설정 열기', lambda: self.post(self.open_settings), default=True),
            item('윈도우 시작 시 자동 실행', lambda: self.post(self.toggle_autostart),
                 checked=lambda _: self.store.settings.autostart),
            pystray.Menu.SEPARATOR,
            item('종료', lambda: self.post(self.quit)),
        )
        self.tray = pystray.Icon('HanYoungFix', self._tray_image(), '한영 오타 자동 교정', menu)
        self.tray.run_detached()

    def quit(self):
        if self.tray:
            self.tray.stop()
        self.root.quit()

    def run(self):
        self.start_tray()
        self.root.mainloop()
