# 처음 쓰는 프로그램 신뢰

앱은 한/영 상태를 제대로 알려 주는지 확인된 프로그램에서만 고친다. 처음 쓰는 프로그램에서 사용자가 한/영 키를 누르면 상태가 실제로 바뀌는지 보고 그 프로그램을 믿을지 정해 설정에 저장한다. 시작 알림이 "쓰는 프로그램에서 한/영 키를 한 번 눌러 주세요"라고 안내한다.

## Sub-features

- `trust-learn` 한/영 키로 상태가 바뀌면 그 프로그램을 신뢰하고 `settings.json`의 `trusted_apps`에 저장.
- `trust-block` 신뢰 전에는 같은 오타를 쳐도 고치지 않음.

## How to get to it (user POV)

- 앱을 켠 뒤 글을 쓸 프로그램에서 한/영 키를 한 번 누른다.

## Driving it with drive.py

Preconditions:

- `launch.py`로 새로 띄움 (`trusted_apps` 비어 있음), `doctor.py` `OK`.

- **신뢰 학습.** 창에서 한/영을 두 번 누른다. `python .claude/skills/verify/scripts/drive.py keep-en` (trust는 항상 먼저 돈다). `OK   trust: settings.json trusted_apps = {'python.exe': True}` 줄이 나온다.
- **증명.** evidence 폴더의 `settings.json`에 `"python.exe": true`.

## Gotchas

- `trust-block`은 drive가 trust를 항상 먼저 돌려서 지금은 몰 수 없다. 확인하려면 trust 없이 치는 journey를 추가해야 한다 (기대: 오타 그대로, recent.json 비어 있음).
- 한/영 키가 상태를 못 바꾸는 환경(한국어 배열 아님)이면 `ime_mode()`가 None이라 신뢰도 저장되지 않는다. doctor의 keyboard layout 줄을 본다.
- Chrome(`chrome.exe`)과 Edge(`msedge.exe`)는 처음부터 신뢰한다 (`settings.DEFAULT_TRUSTED`). 이 둘로는 `trust-learn`을 증명할 수 없으니 drive의 Tk 창(`python.exe`)으로 확인한다.
