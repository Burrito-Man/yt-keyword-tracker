# YouTube 키워드 트래커

`#世界樹計畫` 같은 캠페인/키워드의 영상 수, 조회수, Top5 영상을 검색·집계하는 팀 공용 웹앱입니다.
Streamlit Cloud에 올리면 링크 하나로 팀원 모두가 브라우저에서 바로 사용할 수 있습니다.

## 기능
- 키워드 2개 이상 AND / OR 검색
- 검색 기간 + 시간대(대만/한국/UTC) 설정
- 검색 모드 2가지
  - **전체 검색 (Search API)**: 키워드로 유튜브 전체 검색 (쿼터 소모 큼)
  - **채널 지정 검색 (Playlist 방식)**: 캠페인 참여 채널 목록만 훑어서 쿼터 대폭 절약
    - 채널 프리셋 제공: `TW 세계수 S2`, `TW 세계수 S3` (선택 후 직접 추가·삭제 가능)
- 결과: 전체 / 롱폼 / 쇼츠 / 라이브 다시보기 별 영상 수 · 조회수 합계 · Top5
- CSV 다운로드 (엑셀에서 바로 열림)
- **다국어 지원**: 사이드바 상단에서 한국어 / 繁體中文(번체 중국어) 전환 가능
- **특집 리포트** (사이드바 모드 전환): 키워드 그룹 2개 + 고정 채널 프리셋 + 기준일 전후 여러 주차를 한 번에 비교하는 사전 구성 리포트
  - 현재 등록된 리포트: `TW 세계수 S3 — 經典版 출시 전후 비교` (2026-07-29 기준 W-6~W+6, 총 12주)
  - 두 게임 키워드를 **상호배제 3분류**(A 전용 / B 전용 / 혼합)로 집계해 중복 집계 없이 정확하게 비교
  - 구간별 비교 표, 영상 수/조회수 추이 그래프, 구간별 상세 영상 목록(드릴다운) 제공
  - 새 리포트를 추가하려면 `app.py`의 `SPECIAL_REPORTS` 딕셔너리에 항목을 추가하면 됩니다

## 배포 방법 (GitHub + Streamlit Cloud)

### 1. GitHub 저장소 만들기
1. github.com에서 새 저장소 생성 (예: `yt-keyword-tracker`), Public 또는 팀 계정 소유의 Private 모두 가능
   (Private으로 하려면 Streamlit Cloud와 GitHub 계정 연동 필요)
2. 이 폴더의 3개 파일(`app.py`, `requirements.txt`, `README.md`)을 저장소에 업로드
   ```bash
   git init
   git add app.py requirements.txt README.md
   git commit -m "Initial commit: YouTube keyword tracker"
   git branch -M main
   git remote add origin https://github.com/<본인계정>/yt-keyword-tracker.git
   git push -u origin main
   ```

### 2. Streamlit Cloud 배포
1. https://share.streamlit.io 접속 → GitHub 계정으로 로그인
2. "New app" 클릭
3. 방금 만든 저장소 / `main` 브랜치 / `app.py` 선택
4. Deploy 클릭 → 1~2분 후 `https://<앱이름>.streamlit.app` 형태의 공개 URL 생성됨

### 3. 팀원에게 공유
- 생성된 URL을 Slack 채널 / Notion 페이지 / Confluence 문서에 링크로 공유하면 됩니다.
- 팀원은 별도 설치 없이 브라우저에서 접속 → 본인 YouTube Data API Key 입력 → 바로 사용 가능합니다.

## API Key 안내 (팀원 배포 시 함께 공유)
- 각자 Google Cloud Console(console.cloud.google.com)에서 프로젝트 생성 후 "YouTube Data API v3" 활성화 → 사용자 인증 정보에서 API 키 발급
- 이 앱은 입력된 API Key를 서버에 저장하지 않고, 해당 세션에서만 사용합니다. 새로고침하면 다시 입력해야 합니다.
- 일일 쿼터는 기본 10,000 units/day (프로젝트당). `search.list` 1회당 100 units 소모되므로, 검색 범위가 넓거나 자주 돌릴 경우 "채널 지정 검색(Playlist 방식)" 모드 사용을 권장합니다 (`playlistItems.list`는 1 unit).

## 로컬에서 먼저 테스트하고 싶다면
```bash
pip install -r requirements.txt
streamlit run app.py
```
브라우저에서 `http://localhost:8501` 접속.

## 참고
- 기존 로컬 스크립트(`yt_python.py`, `yt_weekly_stats.py`, `yt_playlist_search_s3.py`)의 검색/분류/집계 로직을 그대로 이식했습니다.
- 주차별 추이(주간 리포트)가 추가로 필요하면 알려주시면 옵션으로 추가해 드릴 수 있습니다.
