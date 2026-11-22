"""최근 교정 기록 (최근 20개, 이 PC의 설정 폴더 recent.json 에만 저장)

맞게 쓴 글자를 잘못 고친 경우를 나중에 확인하고 예외로 넣기 위한 기록입니다.
"""
from __future__ import annotations

import json
import os
import threading
import time

MAX = 20
KIND_TEXT = {'fix': '고침', 'undo': '되돌림', 'keep': '다시 써서 그대로'}
MODE_TEXT = {'ko': '한글 모드', 'en': '영어 모드', None: ''}


class History:
    def __init__(self, path: str, max_items: int = MAX):
        self.path, self.max = path, max_items
        self.lock = threading.Lock()
        try:
            with open(path, encoding='utf-8') as f:
                self.items = list(json.load(f))[-max_items:]
        except (OSError, ValueError):
            self.items = []

    def add(self, entry: dict):
        e = {'time': time.strftime('%m-%d %H:%M:%S'), **entry}
        with self.lock:
            self.items = (self.items + [e])[-self.max:]
            tmp = self.path + '.tmp'
            with open(tmp, 'w', encoding='utf-8') as f:
                json.dump(self.items, f, ensure_ascii=False, indent=1)
            os.replace(tmp, self.path)

    def lines(self) -> list[str]:
        """최근 것부터 한 줄씩: '11-22 09:30:01  claude.exe  한글 모드  고침  ㅗ디ㅣㅐ → hello'"""
        out = []
        with self.lock:
            items = list(reversed(self.items))
        for e in items:
            kind = KIND_TEXT.get(e.get('kind'), e.get('kind', ''))
            words = e.get('before', '') + (f" → {e['after']}" if e.get('after') else '')
            parts = [e.get('time', ''), e.get('app') or '?', MODE_TEXT.get(e.get('mode'), ''), kind, words]
            out.append('  '.join(p for p in parts if p))
        return out
