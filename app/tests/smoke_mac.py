"""macOS에서만: 모듈 불러오기, 입력 소스 읽기, 플랫폼 만들기, 권한 확인이 오류 없이 되는지 (키 입력은 하지 않음)"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from hanyoung import mac, ui_mac  # noqa: E402,F401
from hanyoung.core import Dictionary  # noqa: E402
from hanyoung.keymap_mac import mode_of_source  # noqa: E402
from hanyoung.settings import Store, config_dir  # noqa: E402

assert 'Application Support' in config_dir(), config_dir()
sid = mac.current_source_id()
ids = mac.source_ids()
print('현재 입력 소스:', sid, '→', mode_of_source(sid))
print('켜 둔 입력 소스:', ids)
assert sid, '입력 소스를 읽지 못함'
assert ids, '입력 소스 목록이 비어 있음'
d = Dictionary.load()
assert d.is_word('hello') and not d.is_word('dkssud')
s = Store(os.path.join(tempfile.mkdtemp(), 'settings.json'))
assert s.settings.excluded_apps == ['google chrome'], s.settings.excluded_apps
p = mac.MacPlatform()
print('앞에 있는 앱:', p.front.name, '창:', p.front.window(), '모드:', p.get_mode())
print('권한:', mac.has_permissions(prompt=False))
print('smoke ok')
