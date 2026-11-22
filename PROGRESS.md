# 진행 상황 (작업 중단 대비)

> 작업이 중간에 끊겨도 여기서 이어서 하기 위한 기록입니다. 여러 단계짜리 작업을 시작하면 아래 "진행 중"에 적고,
> 단계마다 갱신해 작업 브랜치에 커밋·푸시합니다. 다 끝나면 main에 합치고 "진행 중"을 비웁니다.

## 진행 중: 브라우저 주소창도 고치기 (2026-11-22)

**브랜치:** `chrome-by-app`. 원인: 앱 설정에서 chrome.exe 제외, 확장은 주소창을 못 고침
- [x] 앱: 기본 제외 앱 없음, 예전 기본값(chrome.exe / google chrome)은 한 번 지움 (`browser_by_app` 표시)
- [x] 앱: `status_server.py` (127.0.0.1:47321/status), Windows·Mac 둘 다 시작, 테스트 → 51개 통과
- [ ] 확장: 앱이 켜져 있으면 쉬기 (background가 /status 확인, manifest host_permissions)
- [ ] exe 다시 빌드, 이 PC 설정에서 chrome.exe 빠졌는지·/status 응답 확인, 사용자에게 주소창·확장 새로고침 확인 요청
- [ ] CI, main 합치기, Obsidian 기록

## 최근 끝난 작업

- **시작 시 자동 실행 (2026-11-21, 브랜치 `autostart` → main):** 기본 켜짐, 실행할 때마다 exe/app 위치로 다시 등록, Windows 아이콘 메뉴에 켜기/끄기 추가. CI Windows·Mac 통과.
- **Mac 앱 (2026-11-20 ~ 21, 브랜치 `mac-app` → main):** `app/hanyoung/mac.py`, `ui_mac.py`, `keymap_mac.py`, `build_mac.sh`.
  GitHub macOS 러너에서 실제 타이핑 5가지 두 번 연속 통과 (`app/tests/e2e_mac.py`).
  간헐적 한/영 전환 실패는 입력 소스를 바꾼 뒤 포커스를 잠깐 옮겨 해결 (CI 5번 연속 5/5, 첫 교정 포함).
  남은 확인: 사용자 Mac에서 직접 사용 (권한 2개 켜기).
