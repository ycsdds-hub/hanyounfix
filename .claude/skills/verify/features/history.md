# 최근 교정 기록

앱이 고친 단어를 최근 20개까지 이 PC의 설정 폴더 `recent.json`에 남기고, 작업 표시줄 아이콘 메뉴에서 창으로 보여 준다. 잘못 고친 단어를 사용자가 찾아보는 용도.

## Sub-features

- `history-record` 교정할 때마다 시각, 종류, 전/후, 한/영, 프로그램을 기록.
- `history-view` 아이콘 메뉴 → 최근 교정 기록 창에 `전 → 후`와 프로그램 이름 표시.

## How to get to it (user POV)

- 기록: 그냥 타이핑하면 자동.
- 보기: 작업 표시줄 오른쪽 아이콘 메뉴의 최근 교정 기록.

## Driving it with drive.py

Preconditions:

- `doctor.py` `OK`.

- **기록.** 교정되는 journey 아무거나. `drive.py typo-ko`. 끝의 `recent.json:` 줄에 `{"kind": "fix", "before": "dkssud", "after": "안녕", "mode": "en", "app": "python.exe"}`.
- **증명.** evidence 폴더의 `recent.json`이 같은 내용. 교정 안 한 journey는 항목이 없다.

## Gotchas

- `history-view`(트레이 메뉴 창)는 drive.py로 못 연다. `app/tests/smoke_windows.py`가 창 내용을 모의 기록으로 확인하지만 실제 트레이 클릭은 확인 안 됨으로 보고한다.
- 기록은 `on_fix` 콜백이 Tk 스레드로 넘겨 저장하므로 교정 직후 바로 읽으면 비어 있을 수 있다. drive는 모든 journey 뒤에 읽는다.
