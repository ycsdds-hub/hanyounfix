# 진행 상황 (작업 중단 대비)

> 작업이 중간에 끊겨도 여기서 이어서 하기 위한 기록입니다. 단계마다 갱신하고 `mac-app` 브랜치에 커밋·푸시합니다.
> 다 끝나면 main에 합치고 이 파일의 "진행 중" 부분을 비웁니다.

## 진행 중: Mac 앱 만들기 (2026-11-20 시작)

**요청:** "오늘 완성한 hanyoungfix app을 Mac에서도 사용할 수 있게 해줘"
**브랜치:** `mac-app` (main에서 갈라짐, main은 `e36082f`)

### 설계
- `windows/` → `app/`로 이름 변경. 공통 로직(`core.py`, `engine.py`, `settings.py`)은 Windows·Mac이 같이 씀
- `app/hanyoung/mac.py`: 이벤트 탭으로 키 감시·막기·다시 보내기, 입력 소스(TIS)로 한/영 읽기·바꾸기
  - 한/영 상태는 입력 소스 ID로 판별 (`com.apple.inputmethod.Korean.2SetKorean` → 한글, `com.apple.keylayout.ABC` → 영어). 모든 앱에서 읽히므로 Mac은 '한/영 한 번 눌러 확인' 단계가 필요 없음
  - TIS API는 메인 스레드에서만 호출 (`on_main`), 다른 스레드는 캐시(`platform.mode`) 사용
  - 사용자가 한/영을 바꾸면(입력 소스 변경 알림) 엔진에 한/영 키처럼 알려 줌
- `app/hanyoung/keymap_mac.py`: Mac 키 코드 ↔ 엔진 키 번호(Windows VK). 순수 파이썬이라 Windows에서도 테스트
- `app/hanyoung/ui_mac.py`: rumps 메뉴 막대 앱. 교정하면 아이콘 옆에 'dkssud → 안녕'을 잠깐 표시
- `app/main.py`: OS에 따라 `main_windows()` / `main_mac()`
- `settings.py`: Mac 설정 위치 `~/Library/Application Support/HanYoungFix`, 로그인 자동 실행은 LaunchAgent, 기본 제외 앱 `google chrome`
- 단축키: ⌘ 또는 Control을 엔진의 Ctrl로 취급 (⌘Z 되돌리기, ⌃⌥H 켜기/끄기)
- 권한: 손쉬운 사용 + 입력 모니터링. 없으면 메뉴에 표시하고 3초마다 다시 시도

### 단계
- [x] 폴더 이름 변경 `windows/` → `app/`, 테스트 경로·.gitignore 수정 (빈 `windows/` 폴더는 사용 중이라 로컬에 남음, git과 무관)
- [x] `keymap_mac.py` + 테스트 (`app/tests/test_keymap_mac.py`), 전체 42개 통과
- [x] `mac.py`, `ui_mac.py`, `main.py`, `settings.py` 작성
- [x] `requirements-mac.txt`, `tests/smoke_mac.py`, `build_mac.sh` 작성
- [x] `build.bat` 에 Mac 모듈 제외 옵션, CI 경로 `windows/` → `app/` 수정, CI에 macOS 작업 추가 (테스트·스모크·.app 빌드·8초 실행 확인·zip 업로드)
- [x] `gh workflow run CI --ref mac-app` 으로 Mac CI 확인 → 첫 실행에서 테스트·스모크·빌드·8초 실행 모두 통과 (러너는 권한이 이미 허용됨)
- [ ] CI에 실제 타이핑 확인 추가 (`app/tests/e2e_mac.py`: 한국어 두벌식 켜고 TextEdit에 dkssud 등 입력 후 결과 읽기) → 결과 확인, 실패하면 고치기
- [x] Windows exe 다시 빌드해 바탕화면 교체 (09:35, 정상 실행)
- [x] README에 Mac 설치·권한·한계 추가, 폴더 구조 app/ 반영
- [ ] main에 합치고 푸시, Obsidian 노트 기록 (`Claude/2026-11-20 ...`)

### 확인 방법
- Windows: `python -m unittest discover -s app/tests` (Mac 표 테스트 포함)
- Mac(CI): `.github/workflows/ci.yml` 의 `mac-app` 작업. 실제 타이핑은 사용자의 Mac에서 확인해야 함

### 알아 둘 것
- 이 PC는 Windows라 Mac 실제 동작은 직접 확인 못 함 → GitHub Mac 러너에서 빌드·실행 확인까지만
- 서명·공증 없는 앱이라 Mac에서 처음 열 때 "확인되지 않은 개발자" 경고 → 시스템 설정 > 개인정보 보호 및 보안 > "그래도 열기"
- 임시 서명이라 새로 빌드할 때마다 권한을 다시 줘야 할 수 있음
