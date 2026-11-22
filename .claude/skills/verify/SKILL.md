---
name: verify
description: HanYoungFix Windows 앱(한영 오타 자동 교정, app/)을 소스로 격리 실행하고, 직접 띄운 텍스트 창에 실제로 키를 쳐서 교정·한/영 전환·최근 기록이 되는지 증거와 함께 확인한다. app/hanyoung 의 engine/core/win32/ui 를 바꾼 뒤, 또는 "앱에서 실제로 되는지 확인", "verify", "실제 타이핑 테스트" 요청 때 쓴다.
---

# verify: HanYoungFix Windows 앱 실제 타이핑 확인

이 저장소의 주 화면은 **Windows 앱**이다. 전역 키보드 훅으로 모든 프로그램의 입력을 보고, 잘못 친 단어를 지우고 한/영을 바꿔 다시 친다. 이 스킬은 그 앱을 사용자 것과 분리해 띄우고, 스크립트가 만든 Tk 텍스트 창에 키를 보내 결과 글자를 읽는다.

다른 화면: Chrome 확장(`extension/`)은 이 스킬로 몰지 않는다 (판단 로직은 `npm test`, `test/cases.json`). Mac 앱은 CI의 `app/tests/e2e_mac.py`가 같은 방식으로 확인한다.

모든 명령은 저장소 루트에서 실행한다. Python 3.10+, `pip install -r app/requirements.txt` (pystray, pillow) 필요.

## 반드시 알아 둘 것

- **키보드와 포커스를 약 20초 빼앗는다.** drive 전에 사용자에게 "작은 'hanyoung verify' 창이 뜨고 자동 입력하니 그동안 타이핑하지 말라"고 알린다. 사용자가 치는 키도 검증 앱이 같이 처리한다.
- **사용자 앱과 같이 떠도 된다.** 검증 앱은 다른 mutex(`Local\HanYoungFix-verify`), 다른 포트(47322), 임시 APPDATA를 쓴다. 사용자 앱(`HanYoungFix.exe`, 포트 47321)은 주입된 키를 무시하므로 drive의 키에 반응하지 않는다. 사용자 앱이나 그 설정(`%APPDATA%\HanYoungFix`)을 끄거나 건드리지 않는다.
- **한 번에 하나만.** 키보드는 하나뿐이라 검증 인스턴스 두 개를 동시에 몰 수 없다. launch.py가 이미 떠 있으면 거부한다.
- **알려진 차이:** drive는 SendInput으로 키를 보내므로, launch.py가 `win32.LLKHF_INJECTED = 0` 으로 주입 키도 사용자 키로 받게 한다. 그 외(훅, 엔진, 백스페이스·한/영 전환 전송, IME 조회, 설정·기록 저장)는 실제 코드 그대로다. "진짜 키보드 vs 주입 키" 구분 자체는 이 스킬로 증명되지 않는다 (`app/tests/test_engine.py` 범위). 그 부분을 바꿨다면 사용자에게 직접 타이핑 확인을 부탁한다.
- 키보드 배열이 한국어(0x412)여야 한다. 아니면 `ime_mode()`가 None이라 아무것도 안 고친다.

## Launch

```
python .claude/skills/verify/scripts/launch.py
```

- 임시 폴더(`%TEMP%\hanyoung-verify\`)를 비우고 `appdata\HanYoungFix\settings.json`을 `{"browser_by_app": true}`로 만든 뒤(신뢰한 프로그램 없음) `app/main.py`의 `main_windows()`를 백그라운드로 띄운다.
- 준비되면 `READY pid <n> status {'app': 'HanYoungFix', 'enabled': True} config <경로>`를 찍고 끝난다. 상태 서버는 키보드 훅 시작 뒤에 열리므로 READY면 훅도 켜진 상태다.
- 실패하면 `app exited code N; see ...app.log` — 로그를 읽는다 (예: `No module named 'pystray'` → requirements 설치).
- 작업 표시줄 오른쪽에 아이콘이 하나 더 생기고 "한영 자동 교정 시작!" 알림이 뜨는 것은 정상.

## Doctor

```
python .claude/skills/verify/scripts/doctor.py
```

읽기만 한다. pid 생존, 47322 상태 응답과 `enabled`, 키보드 배열, 설정 폴더, 사용자 앱 상태, 앱 로그 끝부분을 보여 주고 마지막 줄이 `OK` 또는 `NOT OK: <이유>`. 이상하면 먼저 이걸 돌린다.

## Drive

```
python .claude/skills/verify/scripts/drive.py [journey ...]
```

- journey: `typo-ko`, `typo-ko-space`, `ko-to-en`, `keep-en`, `context`. 생략하면 전부. `trust`는 항상 먼저 돈다 (새 프로그램은 한/영 키를 한 번 눌러야 고치기 시작하므로).
- 각 journey: 창 비우기 → 앞으로 가져오기 → 한/영을 시작 상태로 → 키를 0.09초 간격으로 → 1.5초 기다림 → 창 글자 읽기. 0.01초마다 글자 변화(trace)를 기록한다.
- 출력 줄: `OK  ` / `FAIL` + journey + 친 키 + 결과 + 기대, 그 아래 `화면 변화:`. 마지막 줄 `모두 통과 | evidence: <폴더>` 또는 `실패 N`. 종료 코드 0/1.
- 새 사례를 넣으려면 `drive.py`의 `JOURNEYS`에 `(시작 한/영, 칠 키, 기대 결과)`를 추가하고 `features/`에도 적는다. 키는 영문 소문자와 띄어쓰기만 지원한다.
- 창을 못 가져오거나 한/영을 못 맞추면 `FAIL <journey>: 준비 실패 focus=... 한/영=...`. 사용자가 다른 창을 클릭했거나 전체 화면 앱이 떠 있는 경우가 많다.

## Evidence

`verify-evidence/<YYYYMMDD-HHMMSS>/` (git 무시 대상, cleanup이 지우지 않음):

- `result.json` — journey별 기대/결과/교정 뒤 한/영/trace
- `transcript.txt` — 콘솔 출력 그대로
- `settings.json` — 검증 앱이 저장한 설정 (`trusted_apps`에 `python.exe: true`가 있으면 trust 증명)
- `recent.json` — 앱이 남긴 최근 교정 기록 (화면 결과와 별개의 부수 효과 증명)

증명 기준: 최종 글자만이 아니라 trace(지우고 다시 치는 과정)와 recent.json 기록을 같이 본다. 교정하지 말아야 할 사례(`keep-en`)는 recent.json에 기록이 없어야 한다. 사용자에게 보고할 때 evidence 폴더 경로와 OK/FAIL 줄을 붙인다.

## Cleanup

```
python .claude/skills/verify/scripts/cleanup.py
```

pid 파일의 프로세스만 `taskkill /PID <pid> /T /F`로 끈다 (이름으로 죽이지 않음 — 사용자의 `HanYoungFix.exe`, `python.exe`가 같이 떠 있다). 그다음 `%TEMP%\hanyoung-verify\`를 지운다. `verify-evidence/`는 남는다. 실패한 시도 뒤에도 항상 돌린다.

## 순서 요약

1. 사용자에게 자동 입력 예고
2. `launch.py` → `READY`
3. `doctor.py` → `OK`
4. `drive.py [journey]` → `모두 통과`
5. `cleanup.py` → evidence 폴더가 남았는지 확인

기능별 레시피와 함정은 [features/README.md](features/README.md).
