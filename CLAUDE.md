# 프로젝트 안내 (Claude용)

- **작업을 이어서 할 때:** `PROGRESS.md`에 "진행 중" 항목이 있으면 먼저 읽고, 적힌 브랜치로 바꾼 뒤 체크되지 않은 단계부터 이어서 한다.
- **작업 중단 대비:** 여러 단계짜리 작업은 단계마다 `PROGRESS.md`를 갱신하고, 작업 브랜치에 커밋·푸시해 둔다 (main은 다 끝난 뒤에 합침).
- 구조: `extension/` Chrome 확장, `app/` Windows·Mac 앱 (공통 로직 `app/hanyoung/core.py`, `engine.py`), `test/cases.json` 은 확장과 앱이 같이 쓰는 판단 사례.
- 테스트: `npm test`, `python -m unittest discover -s app/tests`
- 작업 기록은 Obsidian 볼트 `C:\Users\Chan\Desktop\obvault\A folder\Claude\` 에 남긴다.
