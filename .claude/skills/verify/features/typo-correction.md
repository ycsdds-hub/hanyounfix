# 오타 교정

한/영을 잘못 둔 채 친 단어를 지우고, 한/영을 바꾼 뒤, 같은 키를 다시 쳐서 맞는 글자로 고친다. 진짜 영어 단어는 그대로 둔다.

## Sub-features

- `typo-ko-early` 영어 모드로 친 한글이 6글자가 되면 띄어쓰기 전에 미리 고치고 한/영을 한글로 바꿈 (`dkssud` → `안녕`).
- `typo-ko-space` 짧은 단어는 띄어쓰기에서 고침 (`rkawk ` → `감자 `).
- `typo-en` 한글 모드로 친 영어를 띄어쓰기에서 고치고 한/영을 영어로 바꿈 (`ㅗ디ㅣㅐ` → `hello`).
- `keep-en` 사전에 있는 영어는 그대로 (`hello world`).
- `shift-boundary` Shift를 누른 채 친 경계 키는 교정 뒤에도 Shift가 유지됨 (`rkawk?` → `감자?`, 한글 모드 `apple`+Shift+Enter → 줄바꿈, 보내기 아님).

## How to get to it (user POV)

- 신뢰한 프로그램에서 그냥 타이핑한다. 별도 조작 없음.

## Driving it with drive.py

Preconditions:

- `doctor.py` `OK`, 사용자에게 자동 입력 예고.

- **미리 교정.** `drive.py typo-ko`. `OK   typo-ko [en] 'dkssud ' -> '안녕 '`, 화면 변화가 `'dkssud' → … → '' → '안' → '안녕 '` 처럼 지우고 다시 친다.
- **띄어쓰기 교정.** `drive.py typo-ko-space`. `-> '감자 '`.
- **영어로.** `drive.py ko-to-en`. `-> 'hello '`, 화면 변화에 `'ㅗ디ㅣㅐ'`가 보인 뒤 `'hello '`.
- **그대로.** `drive.py keep-en`. `-> 'hello world '`, 화면 변화에 지우는 단계가 없다.
- **Shift 경계 키.** `drive.py shift-question shift-enter`. `-> '감자?'`, `-> 'apple
'`. 실패하면 `'감자/'`, `'apple[send]'` (Claude·카카오톡 같은 채팅 앱에서는 메시지가 전송됨).
- **증명.** `recent.json`에 `dkssud→안녕`, `rkawk→감자`, `ㅗ디ㅣㅐ→hello` 기록이 있고 `hello world` 기록은 없다. `result.json`의 `mode_after`가 교정 뒤 한/영(`ko`/`en`).

## Gotchas

- 결과 글자만 보면 "앱이 아무것도 안 했는데 우연히 맞음"과 구분이 안 되는 사례가 있다 (`keep-en`). trace와 recent.json으로 판단한다.
- 키 간격(0.09초)을 너무 줄이면 Tk가 키를 처리하기 전에 앱이 지우기 시작해 `d안녕` 같은 잔여가 생길 수 있다. 실제 메모장(TSF)은 Tk보다 더 느리다 — 메모장 고유 문제는 이 드라이버로 재현되지 않을 수 있다.
