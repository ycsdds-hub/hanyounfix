# 진행 상황 (작업 중단 대비)

> 작업이 중간에 끊겨도 여기서 이어서 하기 위한 기록입니다. 여러 단계짜리 작업을 시작하면 아래 "진행 중"에 적고,
> 단계마다 갱신해 작업 브랜치에 커밋·푸시합니다. 다 끝나면 main에 합치고 "진행 중"을 비웁니다.

## 진행 중: 시작 시 자동 실행 기본 켜기 (2026-11-21)

**브랜치:** `autostart`
- [x] `Settings.autostart` 기본값 True, `sync_autostart()`: exe/app으로 실행될 때마다 지금 위치로 다시 등록 (소스 실행은 제외)
- [x] 테스트 `app/tests/test_settings.py` (Mac LaunchAgent, 등록 조건, Windows 명령) → 전체 47개 통과
- [x] exe 다시 빌드해 바탕화면 교체, 이 PC 설정 켬 → Run 키에 바탕화면 HanYoungFix.exe 등록 확인
- [ ] (사용자 질문) 켜고 끄는 방법 안내: Windows 트레이 아이콘 → 설정 → '윈도우 시작 시 자동 실행', Mac 메뉴 막대 → '로그인할 때 자동 실행'
- [ ] CI(Windows·Mac) 확인 → main에 합치기, Obsidian 기록

## 최근 끝난 작업

- **Mac 앱 (2026-11-20 ~ 21, 브랜치 `mac-app` → main):** `app/hanyoung/mac.py`, `ui_mac.py`, `keymap_mac.py`, `build_mac.sh`.
  GitHub macOS 러너에서 실제 타이핑 5가지 두 번 연속 통과 (`app/tests/e2e_mac.py`).
  간헐적 한/영 전환 실패는 입력 소스를 바꾼 뒤 포커스를 잠깐 옮겨 해결 (CI 5번 연속 5/5, 첫 교정 포함).
  남은 확인: 사용자 Mac에서 직접 사용 (권한 2개 켜기).
