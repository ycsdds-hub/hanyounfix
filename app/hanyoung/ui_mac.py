"""macOS 메뉴 막대 아이콘과 설정 (rumps)

Windows의 ui.py(트레이 + 설정 창 + 알림)와 같은 역할입니다.
- 교정하면 메뉴 막대 아이콘 옆에 'dkssud → 안녕'을 잠깐 보여 줍니다 (알림 센터보다 덜 방해됨)
- 단어·앱 목록은 메뉴에서 간단한 입력 창으로 고칩니다
"""
from __future__ import annotations

import os
import queue
import time

import rumps

from . import mac
from .core import default_data_dir
from .settings import set_autostart

TITLE = '한영 오타 자동 교정'


def icon_path() -> str:
    d = default_data_dir()
    for p in (os.path.join(d, 'icon.png'), os.path.join(d, 'icons', 'icon32.png'), os.path.join(d, 'icons', 'icon128.png')):
        if os.path.exists(p):
            return p
    return ''


class MacApp(rumps.App):
    def __init__(self, store):
        super().__init__(TITLE, icon=icon_path() or None, template=False, quit_button=None)
        self.store = store
        self.engine = None
        self.platform = None
        self.hooks = None
        self.history = None  # main.py에서 연결 (최근 교정 기록)
        self.jobs: queue.Queue = queue.Queue()
        self._flash_until = 0.0
        self._ticks = 0
        s = store.settings

        self.m_enabled = rumps.MenuItem('자동 교정  (⌃⌥H)', callback=self.toggle)
        self.m_toast = rumps.MenuItem('교정한 단어를 메뉴 막대에 표시', callback=self.toggle_toast)
        self.m_auto = rumps.MenuItem('로그인할 때 자동 실행', callback=self.toggle_autostart)
        self.m_status = rumps.MenuItem('상태 확인 중…')
        self.m_perm = rumps.MenuItem('권한 설정 열기…', callback=self.open_permissions)
        self.menu = [
            self.m_enabled, self.m_toast, self.m_auto, None,
            rumps.MenuItem('최근 교정 기록…', callback=self.show_history),
            rumps.MenuItem('고치지 않을 단어…', callback=self.edit_words),
            rumps.MenuItem('교정하지 않을 앱…', callback=self.edit_apps),
            rumps.MenuItem('띄어쓰기 전 검사 글자 수…', callback=self.edit_length),
            None, self.m_status, self.m_perm, None,
            rumps.MenuItem('종료', callback=self.quit_app),
        ]
        self.m_enabled.state = s.enabled
        self.m_toast.state = s.show_toast
        self.m_auto.state = s.autostart
        rumps.Timer(self._poll, 0.05).start()
        rumps.Timer(self._tick, 0.5).start()

    # ---------- 다른 스레드에서 안전하게 ----------
    def post(self, fn):
        self.jobs.put(fn)

    def _poll(self, _timer):
        try:
            while True:
                self.jobs.get_nowait()()
        except queue.Empty:
            pass

    # ---------- 알림 ----------
    def notify(self, before, after, message=None):
        self.post(lambda: self._show(before, after, message))

    def _show(self, before, after, message):
        if message:
            try:
                rumps.notification(TITLE, '', message)
            except Exception:  # noqa: BLE001  소스로 실행하면 알림 센터를 못 쓸 수 있음
                print(message)
            return
        if not self.store.settings.show_toast:
            return
        self.title = f'{before} → {after}'
        self._flash_until = time.monotonic() + 2.6

    def _tick(self, _timer):
        self._ticks += 1
        if self._flash_until and time.monotonic() > self._flash_until:
            self.title = None
            self._flash_until = 0.0
        if self.platform is not None:
            self.platform.refresh_mode()  # 입력 소스 알림을 놓쳐도 0.5초마다 맞춤
            if not self.platform.toggling:
                self.platform.front.update()
        self._update_status()

    def _update_status(self):
        s = self.store.settings
        if self.hooks is not None and not self.hooks.tap:
            self.m_status.title = '⚠️ 권한이 필요해요: 손쉬운 사용, 입력 모니터링'
            if self._ticks % 6 == 0:
                self.hooks.start()  # 3초마다 다시 시도: 권한을 주면 저절로 켜짐
            return
        if self.platform is None:
            return
        name = self.platform.front.name or '?'
        mode = {'ko': '한글', 'en': '영어', None: '지원하지 않는 입력 소스'}[self.platform.mode]
        if not s.enabled:
            state = '꺼짐'
        elif name in s.excluded_apps:
            state = '제외된 앱'
        else:
            state = '교정 중'
        self.m_status.title = f'{name} · {mode} · {state}'

    # ---------- 메뉴 ----------
    def toggle(self, _sender=None):
        s = self.store.settings
        s.enabled = not s.enabled
        if self.engine:
            self.engine.reset()
        self.on_toggled(s.enabled)

    def on_toggled(self, enabled):
        self.store.save()
        self.m_enabled.state = enabled
        self.title = None if enabled else '꺼짐'
        self.notify(None, None, '자동 교정을 켰어요' if enabled else '자동 교정을 껐어요')

    def toggle_toast(self, sender):
        s = self.store.settings
        s.show_toast = not s.show_toast
        sender.state = s.show_toast
        self.store.save()

    def toggle_autostart(self, sender):
        s = self.store.settings
        try:
            set_autostart(not s.autostart)
        except OSError as e:
            rumps.alert(TITLE, f'자동 실행을 설정하지 못했어요: {e}')
            return
        s.autostart = not s.autostart
        sender.state = s.autostart
        self.store.save()

    def _edit_list(self, title, message, items):
        w = rumps.Window(message=message, title=title, default_text='\n'.join(items),
                         ok='저장', cancel='취소', dimensions=(340, 160))
        r = w.run()
        if r.clicked != 1:
            return None
        return [x.strip() for x in r.text.splitlines() if x.strip()]

    def show_history(self, _sender=None):
        lines = self.history.lines() if self.history else []
        rumps.alert(title='최근 교정 기록',
                    message=('\n'.join(lines) if lines else '아직 교정한 기록이 없어요.')
                    + '\n\n맞게 쓴 글자를 잘못 고쳤다면: 고치지 않을 단어… 에 그 단어를 넣으세요.')

    def edit_words(self, _sender):
        s = self.store.settings
        words = self._edit_list('고치지 않을 단어', '한 줄에 하나씩 적어 주세요 (이름, 약어, 아이디 등)', s.user_words)
        if words is not None:
            s.user_words = list(dict.fromkeys(words))
            if self.engine:
                self.engine.sync_user_words()
            self.store.save()

    def edit_apps(self, _sender):
        s = self.store.settings
        apps = self._edit_list('교정하지 않을 앱',
                               '앱 실행 파일 이름, 한 줄에 하나 (메뉴의 상태 줄에 보이는 이름)\n'
                               '브라우저(주소창 포함)도 이 앱이 고쳐요. 앱이 켜져 있으면 Chrome 확장은 쉬어요.', s.excluded_apps)
        if apps is not None:
            s.excluded_apps = [a.lower() for a in apps]
            self.store.save()

    def edit_length(self, _sender):
        s = self.store.settings
        w = rumps.Window(message='띄어쓰기 전에도 검사할 글자 수 (4~30)', title=TITLE,
                         default_text=str(s.check_length), ok='저장', cancel='취소', dimensions=(120, 24))
        r = w.run()
        if r.clicked == 1:
            try:
                s.check_length = max(4, min(30, int(r.text.strip())))
                self.store.save()
            except ValueError:
                pass

    def open_permissions(self, _sender=None):
        mac.has_permissions(prompt=True)
        mac.open_privacy_settings('Accessibility')

    def need_permission(self):
        """처음 실행: 권한 안내 (메뉴 막대가 뜬 뒤에 한 번)"""
        def show(timer):
            timer.stop()
            r = rumps.alert(
                TITLE,
                '한영 오타를 고치려면 키보드 입력을 읽고 보낼 권한이 필요해요.\n\n'
                '시스템 설정 → 개인정보 보호 및 보안에서\n'
                '· 손쉬운 사용\n· 입력 모니터링\n'
                '목록에 HanYoungFix를 켜 주세요. 켜면 자동으로 시작돼요.',
                ok='설정 열기', cancel='나중에')
            if r == 1:
                self.open_permissions()
        rumps.Timer(show, 1.0).start()

    def quit_app(self, _sender=None):
        if self.hooks:
            self.hooks.stop()
        rumps.quit_application()
