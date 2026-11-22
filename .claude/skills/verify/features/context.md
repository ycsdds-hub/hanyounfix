# 문맥 교정

짧은 단어 뒤의 단어가 영어로 고쳐지면, 앞의 짧은 단어도 영어였을 가능성이 높으므로 함께 고친다. `해 새 ㅓㅐㅠ`(한글 모드로 친 `go to job`)를 한꺼번에 `go to job`으로 바꾼다.

## Sub-features

- `context-en` 뒤 단어 교정 때 앞의 짧은 한글 단어들도 영어로 함께 바꿈.

## How to get to it (user POV)

- 한글 모드인 줄 모르고 짧은 영어 단어 여러 개를 이어서 친다.

## Driving it with drive.py

Preconditions:

- `doctor.py` `OK`.

- **문맥 교정.** `drive.py context`. `OK   context [ko] 'go to job ' -> 'go to job '`. 화면 변화가 `'해 새 ㅓㅐㅠ'` → 하나씩 지워 `''` → `'go to job '`.
- **증명.** `recent.json`에 `"before": "해 새 ㅓㅐㅠ", "after": "go to job"` 한 건.

## Gotchas

- `해`, `새`는 실제 한글 단어라 혼자서는 안 고친다. 앞 단어만 친 상태(`해 새 `)에서 멈추면 그대로인 것이 정상이다.
