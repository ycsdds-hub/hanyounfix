# 진행 상황 (작업 중단 대비)

> 작업이 중간에 끊겨도 여기서 이어서 하기 위한 기록입니다. 여러 단계짜리 작업을 시작하면 아래 "진행 중"에 적고,
> 단계마다 갱신해 작업 브랜치에 커밋·푸시합니다. 다 끝나면 main에 합치고 "진행 중"을 비웁니다.

## 진행 중

없음

## 최근 끝난 작업

- **확장: 한글 모드로 친 웹 주소 교정 (2026-11-27, 브랜치 `ext-address` → main):** `ㅈㅈㅈ.ㅇㄷㄹ둥` → `www.defend`. 띄어쓰기·Enter 때 띄어쓰기 없는 덩어리를 `HY.decideAddress`(시작 www./http(s)://, 끝 .com·.kr 등 표)로 판단해 통째로 바꿈. 확장만 해당, Windows·Mac 앱(core.py)과 ycsAutoFix 에는 아직 없음.
- **확장: 사전 조회가 늦을 때 교정 놓침·반만 고침 (2026-11-27, 브랜치 `ext-slow-lookup` → main):** 서비스 워커가 막 깨어나면 첫 사전 조회가 몇 초 걸리고, 늦게 온 중간 교정이 이미 더 친 단어의 앞부분만 바꿔 `안sudgktpdy`가 남던 문제. 중간 교정은 그 뒤로 더 친 글자가 없을 때만 적용, 입력칸에 들어가면 사전을 미리 읽음(`warm`). 확장 실제 동작 시험 `npm run test:ext`(격리 Chrome, CDP `Extensions.loadUnpacked`) 6번 연속 통과.
- **최근 교정 기록 (2026-11-22, 브랜치 `fix-history`):** 맞는 한글이 잠깐 영어로 바뀐 현상(원인 미확정)을 확인하려고 추가. 엔진 `on_fix`, `history.py`(recent.json, 20개), Windows 아이콘 메뉴·Mac 메뉴. 테스트 56개.
- **브라우저 주소창도 고치기 (2026-11-22, 브랜치 `chrome-by-app` → main):** 앱이 Chrome도 맡음, 앱이 켜져 있으면 확장은 쉼(`status_server.py`, 127.0.0.1:47321). 상태 서버의 getfqdn이 Mac 앱 시작을 막던 문제 고침. CI 통과, 사용자 주소창 확인.
- **시작 시 자동 실행 (2026-11-21, 브랜치 `autostart` → main):** 기본 켜짐, 실행할 때마다 exe/app 위치로 다시 등록, Windows 아이콘 메뉴에 켜기/끄기 추가. CI Windows·Mac 통과.
- **Mac 앱 (2026-11-20 ~ 21, 브랜치 `mac-app` → main):** `app/hanyoung/mac.py`, `ui_mac.py`, `keymap_mac.py`, `build_mac.sh`.
  GitHub macOS 러너에서 실제 타이핑 5가지 두 번 연속 통과 (`app/tests/e2e_mac.py`).
  간헐적 한/영 전환 실패는 입력 소스를 바꾼 뒤 포커스를 잠깐 옮겨 해결 (CI 5번 연속 5/5, 첫 교정 포함).
  남은 확인: 사용자 Mac에서 직접 사용 (권한 2개 켜기).
