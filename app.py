"""
YouTube 키워드 트래커
====================
팀 공용 웹앱 버전. #世界樹計畫 등 특정 캠페인/키워드의
영상 수 · 조회수 · Top5 영상을 검색/집계합니다.

- 사용자가 본인 API Key를 직접 입력 (서버에 저장되지 않음, 세션에서만 사용)
- 키워드 2개 이상 AND/OR 검색 지원
- 날짜 범위 + 타임존 오프셋 설정
- 검색 모드: (1) 전체 검색(Search API)  (2) 채널 지정 검색(Playlist 방식, 쿼터 절약)
- 결과: 전체/롱폼/쇼츠/라이브 영상 수, 항목별 조회수 합계, 항목별 조회수 Top5
"""

import re
from datetime import date, datetime, timedelta

import pandas as pd
import streamlit as st
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# ----------------------------------------------------------------------------
# 다국어 지원 (한국어 / 繁體中文)
# 새 문구를 추가할 때는 아래 TEXT 딕셔너리에 "ko"와 "zh" 두 언어 모두 채워주세요.
# ----------------------------------------------------------------------------

if "lang" not in st.session_state:
    st.session_state["lang"] = "ko"

TEXT = {
    "ko": {
        "page_title": "YouTube 키워드 트래커",
        "lang_label": "🌐 언어 / Language",
        "app_title": "📊 YouTube 키워드 트래커",
        "app_caption": "특정 키워드/캠페인의 영상 수·조회수를 검색·집계합니다. (예: #世界樹計畫)",
        "api_key_header": "🔑 API Key",
        "api_key_label": "YouTube Data API Key",
        "api_key_help": "본인의 Google Cloud 프로젝트에서 발급받은 YouTube Data API v3 키를 입력하세요. "
        "이 값은 서버에 저장되지 않고 현재 세션에서만 사용됩니다.",
        "search_cond_header": "🔍 검색 조건",
        "keywords_label": "검색 키워드 (한 줄에 하나씩 입력, 2개 이상 가능)",
        "match_mode_label": "다중 키워드 매칭 방식",
        "match_mode_or": "OR (하나라도 포함)",
        "match_mode_and": "AND (모두 포함)",
        "match_mode_help": "OR: 검색 결과 후보를 넓게 모은 뒤, 제목/설명/태그 중 하나라도 키워드를 포함하면 채택.\n"
        "AND: 제목/설명/태그 전체 텍스트에 모든 키워드가 포함되어야 채택.",
        "match_scope_label": "키워드 검색 범위",
        "match_scope_all": "제목 + 설명 + 태그 (기본, 권장)",
        "match_scope_title": "제목만",
        "match_scope_help": "이 설정은 검색된 영상 후보를 우리 쪽에서 최종적으로 채택할지 걸러내는 기준입니다 "
        "(YouTube 자체 검색 대상 범위와는 별개).\n"
        "제목+설명+태그: 설명란에만 키워드가 있는 영상도 채택 (더 많이 잡히지만, 관련 없는 영상이 섞일 가능성도 약간 있음).\n"
        "제목만: 제목에 키워드가 명시된 영상만 채택 (더 정확하지만, 설명란에만 언급된 영상은 누락될 수 있음).",
        "period_header": "📅 검색 기간",
        "date_start_label": "시작일",
        "date_end_label": "종료일",
        "timezone_label": "기준 시간대",
        "tz_taiwan": "대만 (UTC+8)",
        "tz_korea": "한국 (UTC+9)",
        "tz_utc": "UTC+0",
        "mode_header": "⚙️ 검색 모드",
        "mode_label": "모드 선택",
        "mode_search": "전체 검색 (Search API)",
        "mode_playlist": "채널 지정 검색 (Playlist 방식, 쿼터 절약)",
        "mode_help": "전체 검색: 키워드로 유튜브 전체를 검색 (쿼터 소모 큼). '#' 포함/미포함 버전을 자동으로 함께 검색합니다.\n"
        "채널 지정 검색: 지정한 채널들의 업로드 목록만 훑어서 쿼터를 크게 절약합니다. "
        "캠페인 참여 채널이 고정되어 있을 때 추천합니다.",
        "mode_search_caption": "ℹ️ '#'이 붙은 키워드는 '#' 없는 버전도 함께 검색해서 누락을 줄입니다. "
        "다만 YouTube Search API 자체가 관련도 기반이라, 채널 지정 검색보다는 결과가 적게 잡힐 수 있습니다.",
        "preset_label": "채널 프리셋",
        "preset_custom": "직접 입력",
        "preset_help": "자주 쓰는 채널 목록을 선택하면 아래 입력창에 자동으로 채워집니다. "
        "선택 후에도 직접 추가/삭제해서 수정할 수 있습니다.",
        "channel_ids_label": "채널 ID 목록 (한 줄에 하나씩, 'UC...' 형태)",
        "channel_ids_help": "예: UCBHyZqX3kt4AiAzgK0Qrcag / 프리셋 선택 후 직접 추가·삭제 가능",
        "channel_count_caption": "현재 채널 {n}개 지정됨",
        "run_button": "🚀 검색 실행",
        "err_need_api_key": "API Key를 입력해주세요.",
        "err_need_keyword": "검색 키워드를 최소 1개 입력해주세요.",
        "err_need_channel": "채널 지정 검색 모드에서는 채널 ID를 최소 1개 입력해주세요.",
        "err_date_order": "시작일이 종료일보다 늦을 수 없습니다.",
        "progress_prepare": "검색 준비 중...",
        "progress_fetching": "조회 중: {label} ({i}/{total})",
        "spinner_collecting": "영상 데이터를 수집하는 중입니다...",
        "warn_no_results": "조건에 맞는 영상을 찾지 못했습니다.",
        "warn_channel_error": "채널 {ch} 조회 중 오류: {e}",
        "summary_header": "📈 요약",
        "cat_all": "전체",
        "cat_longform": "롱폼",
        "cat_shorts": "쇼츠",
        "cat_live": "라이브 다시보기",
        "metric_help_views_sum": "조회수 합계 {n}회",
        "metric_total_label": "전체 영상 수",
        "unit_count": "개",
        "summary_table_title": "**항목별 조회수 합계**",
        "table_col_category": "분류",
        "table_col_title": "제목",
        "table_col_channel": "채널",
        "table_col_date": "게시일",
        "table_col_views": "조회수",
        "link_col_label": "링크",
        "summary_col_item": "항목",
        "summary_col_count": "영상 수",
        "summary_col_views_sum": "조회수 합계",
        "top5_header": "🏆 조회수 Top 5",
        "top5_none": "{label}: 해당 영상 없음",
        "all_list_header": "📋 전체 영상 목록",
        "csv_button_label": "⬇️ CSV 다운로드 (Excel에서 열기 가능)",
        "api_error_prefix": "YouTube API 오류가 발생했습니다: {e}",
        "generic_error_prefix": "오류가 발생했습니다: {e}",
        "idle_info": "왼쪽 사이드바에서 조건을 설정하고 '검색 실행' 버튼을 눌러주세요.",
        "app_mode_label": "🧭 모드 선택",
        "app_mode_normal": "🔍 일반 검색",
        "app_mode_report": "📊 특집 리포트",
        "app_mode_snapshot": "📋 채널 스냅샷",
        "report_header": "📊 특집 리포트",
        "report_select_label": "리포트 선택",
        "report_config_title": "**리포트 구성**",
        "report_channel_count": "채널 {n}개 (프리셋: {preset})",
        "report_window_count": "총 {n}개 구간 (W{start} ~ W{end}, 기준일 전후 각 {half}주)",
        "report_run_button": "🚀 특집 리포트 실행",
        "report_progress": "구간 처리 중: {label} ({i}/{total})",
        "report_spinner": "{n}개 구간을 순차 조회하는 중입니다...",
        "report_summary_header": "📋 구간별 비교 표",
        "report_col_window": "구간",
        "report_col_period": "기간",
        "report_col_count_suffix": " 영상 수",
        "report_col_views_suffix": " 조회수",
        "report_chart_count_header": "📈 영상 발행 수 추이",
        "report_chart_views_header": "👁 조회수 합계 추이",
        "report_drilldown_header": "🔎 구간별 상세 영상 목록",
        "report_drilldown_group_none": "{group}: 해당 영상 없음",
        "report_idle_info": "왼쪽에서 리포트를 선택하고 '특집 리포트 실행' 버튼을 눌러주세요.",
        "report_csv_filename_note": "특집 리포트 요약",
        "snapshot_header": "📋 채널 스냅샷",
        "snapshot_desc": "키워드·날짜 필터 없이, 채널별 최신 업로드를 그대로 훑어봅니다.",
        "snapshot_preset_label": "채널 프리셋",
        "snapshot_n_label": "채널당 최근 영상 수",
        "snapshot_n_help": "각 채널에서 가장 최근에 올라온 영상을 몇 개씩 가져올지 정합니다.",
        "snapshot_run_button": "🚀 채널 스냅샷 실행",
        "snapshot_progress": "채널 조회 중: {label} ({i}/{total})",
        "snapshot_spinner": "채널 {n}개의 최신 영상을 조회하는 중입니다...",
        "snapshot_idle_info": "왼쪽에서 채널 프리셋과 개수를 정하고 '채널 스냅샷 실행' 버튼을 눌러주세요.",
        "snapshot_result_header": "📋 채널별 최신 영상",
        "snapshot_col_channel": "채널",
        "snapshot_empty_note": "이 채널에서는 영상을 찾지 못했습니다.",
        "snapshot_total_caption": "채널 {n}개, 영상 {m}개 조회 완료",
        "report_cat_pure_suffix": " 전용",
        "report_cat_mixed": "혼합 (두 게임 모두 언급)",
        "report_mutual_exclusion_note": "ℹ️ 제목에 두 게임 키워드가 모두 있으면 '혼합'으로 분류하고, 하나만 있으면 각 게임 전용으로 분류합니다 (중복 집계 방지).",
        "guide_header": "📘 API Key 발급 가이드 & 사용 유의사항 (처음이시면 펼쳐보세요)",
        "guide_body": """
### 1. YouTube API Key 발급 방법
1. [Google Cloud Console](https://console.cloud.google.com/)에 접속해 구글 계정으로 로그인 (무료)
2. 새 프로젝트 생성 (또는 기존 프로젝트 선택)
3. 좌측 메뉴 **API 및 서비스 → 라이브러리**에서 "YouTube Data API v3" 검색 후 **사용 설정**
4. **API 및 서비스 → 사용자 인증 정보 → 사용자 인증 정보 만들기 → API 키** 클릭 시 즉시 발급
5. (권장) 발급된 키의 "API 제한사항"에서 YouTube Data API v3만 사용하도록 제한 설정

📎 공식 가이드: https://developers.google.com/youtube/v3/getting-started

---
### 2. 일일 무료 Quota에 따른 예상 실행 가능 횟수
- Google 프로젝트당 하루 기본 **10,000 units** 무료 제공 (매일 태평양 표준시 자정 초기화 — 한국/대만 기준 대략 오후 4~5시경)
- API 호출당 소모량: `search.list` **100 units**, `videos.list` / `playlistItems.list` 각 **1 unit**
- **전체 검색 모드**: '#' 포함/미포함 버전을 자동으로 함께 검색하므로, 결과가 적은 키워드 기준 1회 실행당 약 200~600 units 소모 → **하루 약 15~50회** 실행 가능 (검색 결과가 많아 페이지가 늘어날수록 소모량 증가·실행 가능 횟수 감소)
- **채널 지정 검색 모드**: 채널 1개당 약 2~3 units 소모 → 채널 28개 기준 1회 실행당 약 60~90 units → **하루 100회 이상** 여유롭게 실행 가능
- ⚠️ 팀원 각자 API Key를 발급받아도, **같은 Google Cloud 프로젝트에서 여러 키를 만들면 quota를 서로 공유**합니다. 팀원별로 quota를 독립적으로 쓰려면 각자 별도 프로젝트에서 키를 발급받아야 합니다.

---
### 3. 검색 결과 관련 제약사항 · 주의사항
- 한 검색 조건당 최대 **약 500개** 결과까지만 조회 가능 (그 이상은 API가 다음 페이지를 제공하지 않음)
- `전체 검색`은 관련도(relevance) 기반 랭킹이라 **"완전 일치 검색"이 아님** — 제목/설명/태그에 키워드가 있어도 관련도 점수가 낮으면 결과에서 누락될 수 있음
- 검색 대상은 **제목/설명/태그**뿐이며, 자막·댓글·커뮤니티 게시물 내용은 검색 대상이 아님
- 업로드 직후 영상은 검색 인덱스 반영까지 시간이 걸려 **일시적으로 누락**될 수 있음
- 비공개·한정공개·삭제된 영상은 두 모드 모두 조회 불가
- `채널 지정 검색`은 관련도 알고리즘을 거치지 않고 채널의 전체 업로드를 직접 필터링하므로 위 문제들에서 비교적 자유롭습니다. 참여 채널이 고정되어 있다면 이 모드를 우선 사용하시길 권장합니다.
""",
    },
    "zh": {
        "page_title": "YouTube 關鍵字追蹤器",
        "lang_label": "🌐 語言 / Language",
        "app_title": "📊 YouTube 關鍵字追蹤器",
        "app_caption": "搜尋並統計特定關鍵字／活動的影片數量與觀看次數。（例如：#世界樹計畫）",
        "api_key_header": "🔑 API金鑰",
        "api_key_label": "YouTube Data API 金鑰",
        "api_key_help": "請輸入您在 Google Cloud 專案中申請的 YouTube Data API v3 金鑰。"
        "此金鑰不會儲存在伺服器上，僅在目前的瀏覽階段中使用。",
        "search_cond_header": "🔍 搜尋條件",
        "keywords_label": "搜尋關鍵字（每行輸入一個，可輸入2個以上）",
        "match_mode_label": "多重關鍵字比對方式",
        "match_mode_or": "OR（包含任一即可）",
        "match_mode_and": "AND（須全部包含）",
        "match_mode_help": "OR：先廣泛蒐集候選影片，只要標題／說明／標籤中有一項符合關鍵字即採用。\n"
        "AND：標題／說明／標籤的全部文字中必須包含所有關鍵字才會採用。",
        "match_scope_label": "關鍵字搜尋範圍",
        "match_scope_all": "標題＋說明＋標籤（預設，建議）",
        "match_scope_title": "僅標題",
        "match_scope_help": "此設定是我們對搜尋到的候選影片進行最終篩選的標準"
        "（與YouTube本身的搜尋範圍無關）。\n"
        "標題＋說明＋標籤：只要說明欄有出現關鍵字的影片也會被採用（涵蓋範圍較廣，但可能混入少量不相關影片）。\n"
        "僅標題：只有標題中明確出現關鍵字的影片才會被採用（較精準，但可能遺漏僅在說明欄提及的影片）。",
        "period_header": "📅 搜尋期間",
        "date_start_label": "開始日期",
        "date_end_label": "結束日期",
        "timezone_label": "時區基準",
        "tz_taiwan": "台灣 (UTC+8)",
        "tz_korea": "韓國 (UTC+9)",
        "tz_utc": "UTC+0",
        "mode_header": "⚙️ 搜尋模式",
        "mode_label": "選擇模式",
        "mode_search": "全站搜尋 (Search API)",
        "mode_playlist": "指定頻道搜尋（播放清單模式，節省配額）",
        "mode_help": "全站搜尋：以關鍵字搜尋整個YouTube（消耗配額較多）。會自動一併搜尋含「#」與不含「#」的版本。\n"
        "指定頻道搜尋：只掃描指定頻道的上傳清單，可大幅節省配額。"
        "適合活動參與頻道已固定的情況。",
        "mode_search_caption": "ℹ️ 含「#」的關鍵字會自動一併搜尋不含「#」的版本以減少遺漏。"
        "不過由於 YouTube Search API 本身以相關性為基礎排序，結果可能會比指定頻道搜尋少。",
        "preset_label": "頻道預設清單",
        "preset_custom": "手動輸入",
        "preset_help": "選擇常用的頻道清單後，會自動填入下方輸入框。"
        "選擇後仍可自行新增／刪除進行修改。",
        "channel_ids_label": "頻道ID清單（每行一個，格式為「UC...」）",
        "channel_ids_help": "例如：UCBHyZqX3kt4AiAzgK0Qrcag／選擇預設清單後仍可自行新增、刪除",
        "channel_count_caption": "目前已指定 {n} 個頻道",
        "run_button": "🚀 開始搜尋",
        "err_need_api_key": "請輸入API金鑰。",
        "err_need_keyword": "請至少輸入1個搜尋關鍵字。",
        "err_need_channel": "在指定頻道搜尋模式下，請至少輸入1個頻道ID。",
        "err_date_order": "開始日期不能晚於結束日期。",
        "progress_prepare": "正在準備搜尋...",
        "progress_fetching": "查詢中：{label} ({i}/{total})",
        "spinner_collecting": "正在收集影片資料...",
        "warn_no_results": "找不到符合條件的影片。",
        "warn_channel_error": "查詢頻道 {ch} 時發生錯誤：{e}",
        "summary_header": "📈 摘要",
        "cat_all": "全部",
        "cat_longform": "長影片",
        "cat_shorts": "Shorts短片",
        "cat_live": "直播回放",
        "metric_help_views_sum": "觀看次數合計 {n} 次",
        "metric_total_label": "總影片數",
        "unit_count": "部",
        "summary_table_title": "**各項目觀看次數合計**",
        "table_col_category": "分類",
        "table_col_title": "標題",
        "table_col_channel": "頻道",
        "table_col_date": "發布日期",
        "table_col_views": "觀看次數",
        "link_col_label": "連結",
        "summary_col_item": "項目",
        "summary_col_count": "影片數",
        "summary_col_views_sum": "觀看次數合計",
        "top5_header": "🏆 觀看次數 Top 5",
        "top5_none": "{label}：無符合影片",
        "all_list_header": "📋 全部影片清單",
        "csv_button_label": "⬇️ 下載CSV（可用Excel開啟）",
        "api_error_prefix": "發生YouTube API錯誤：{e}",
        "generic_error_prefix": "發生錯誤：{e}",
        "idle_info": "請在左側側邊欄設定條件後，點擊「開始搜尋」按鈕。",
        "app_mode_label": "🧭 選擇模式",
        "app_mode_normal": "🔍 一般搜尋",
        "app_mode_report": "📊 專題報告",
        "app_mode_snapshot": "📋 頻道快照",
        "report_header": "📊 專題報告",
        "report_select_label": "選擇報告",
        "report_config_title": "**報告設定**",
        "report_channel_count": "頻道 {n} 個（預設清單：{preset}）",
        "report_window_count": "共 {n} 個區間（W{start} ~ W{end}，基準日前後各 {half} 週）",
        "report_run_button": "🚀 執行專題報告",
        "report_progress": "處理區間中：{label} ({i}/{total})",
        "report_spinner": "正在依序查詢 {n} 個區間...",
        "report_summary_header": "📋 各區間比較表",
        "report_col_window": "區間",
        "report_col_period": "期間",
        "report_col_count_suffix": " 影片數",
        "report_col_views_suffix": " 觀看次數",
        "report_chart_count_header": "📈 影片發布數趨勢",
        "report_chart_views_header": "👁 觀看次數合計趨勢",
        "report_drilldown_header": "🔎 各區間詳細影片清單",
        "report_drilldown_group_none": "{group}：無符合影片",
        "report_idle_info": "請在左側選擇報告後，點擊「執行專題報告」按鈕。",
        "report_csv_filename_note": "專題報告摘要",
        "snapshot_header": "📋 頻道快照",
        "snapshot_desc": "不套用關鍵字或日期篩選，直接瀏覽各頻道最新上傳的影片。",
        "snapshot_preset_label": "頻道預設清單",
        "snapshot_n_label": "每個頻道要看的最新影片數",
        "snapshot_n_help": "設定要從每個頻道抓取幾部最新上傳的影片。",
        "snapshot_run_button": "🚀 執行頻道快照",
        "snapshot_progress": "查詢頻道中：{label} ({i}/{total})",
        "snapshot_spinner": "正在查詢 {n} 個頻道的最新影片...",
        "snapshot_idle_info": "請在左側選擇頻道預設清單與數量，點擊「執行頻道快照」按鈕。",
        "snapshot_result_header": "📋 各頻道最新影片",
        "snapshot_col_channel": "頻道",
        "snapshot_empty_note": "此頻道找不到影片。",
        "snapshot_total_caption": "已查詢 {n} 個頻道、共 {m} 部影片",
        "report_cat_pure_suffix": "專屬",
        "report_cat_mixed": "混合（同時提及兩款遊戲）",
        "report_mutual_exclusion_note": "ℹ️ 標題中若同時出現兩款遊戲的關鍵字，會歸類為「混合」；只出現一個則歸類為該遊戲專屬（避免重複計算）。",
        "guide_header": "📘 API金鑰申請指南與使用須知（第一次使用請展開查看）",
        "guide_body": """
### 1. 如何申請 YouTube API金鑰
1. 前往 [Google Cloud Console](https://console.cloud.google.com/) 並用Google帳號登入（免費）
2. 建立新專案（或選擇既有專案）
3. 於左側選單「API和服務 → 程式庫」搜尋「YouTube Data API v3」並點擊**啟用**
4. 「API和服務 → 憑證 → 建立憑證 → API金鑰」，點擊後即可立即取得金鑰
5.（建議）點擊金鑰進行「API限制」設定，僅允許使用 YouTube Data API v3

📎 官方指南：https://developers.google.com/youtube/v3/getting-started

---
### 2. 每日免費配額下的預估可執行次數
- 每個 Google 專案預設每日提供 **10,000 units** 免費配額（每天太平洋標準時間午夜重置，約為台灣/韓國時間下午4~5點左右）
- 各API呼叫消耗量：`search.list` **100 units**，`videos.list`／`playlistItems.list` 各 **1 unit**
- **全站搜尋模式**：會自動一併搜尋含「#」與不含「#」的版本，結果較少的關鍵字每次執行約消耗200~600 units → **每日約可執行15~50次**（結果越多、分頁越多，消耗越大、可執行次數越少）
- **指定頻道搜尋模式**：每個頻道約消耗2~3 units → 以28個頻道估算，每次約消耗60~90 units → **每日可寬鬆執行100次以上**
- ⚠️ 即使團隊成員各自申請了API金鑰，若都建立在**同一個 Google Cloud 專案**下，配額仍是共用的。若希望每位成員的配額互相獨立，請各自在不同專案中申請金鑰。

---
### 3. 搜尋結果相關限制與注意事項
- 每個搜尋條件最多只能取得約 **500筆** 結果（超過此數量後API本身就不會再提供下一頁）
- 「全站搜尋」是以相關性（relevance）排序，**並非「完全比對搜尋」**——標題／說明／標籤中即使包含關鍵字，若相關性分數偏低仍可能被遺漏
- 搜尋範圍僅限於**標題／說明／標籤**，不包含字幕、留言或社群貼文內容
- 剛上傳的影片可能因搜尋索引尚未更新而**暫時查詢不到**
- 非公開、不公開分享或已刪除的影片，無論用哪種模式都無法查詢到
- 「指定頻道搜尋」不經過相關性演算法，而是直接掃描頻道全部上傳影片後再過濾，因此較不受上述問題影響。若活動參與頻道已固定，建議優先使用此模式以獲得更準確的結果。
""",
    },
}


CURRENT_LANG = st.session_state["lang"]


def t(key, **kwargs):
    text = TEXT[CURRENT_LANG][key]
    return text.format(**kwargs) if kwargs else text


st.set_page_config(page_title=t("page_title"), page_icon="📊", layout="wide")

# ----------------------------------------------------------------------------
# 채널 ID 프리셋
# 새 프리셋을 추가하려면 아래 딕셔너리에 "이름": [채널ID, ...] 형태로 추가하면 됩니다.
# ----------------------------------------------------------------------------

CHANNEL_PRESETS = {
    "TW 세계수 S2": [
        "UCBHyZqX3kt4AiAzgK0Qrcag",
        "UCLlE4endO2rIcWqUqc76xDA",
        "UCGKL5LoNqNAR8yCj8wiWScA",
        "UCMQ9Az4Ob6caXuK0TQnTPqw",
        "UCPuQUetajpqyPTFto2Uz-JA",
        "UCQ7SNp-izmqQasmP3Oc2t5w",
        "UCFaLDiwNtMTxbQcyzRynJQQ",
        "UCK1ejENR4sra6wiCJgOuUOg",
        "UC2WUQg_3PoToFOsppiQJ06Q",
        "UCBao4tw7MoTfx3GZD3uj6jA",
        "UCcumJaVU2oiUDMWU17T3rQg",
        "UCIL5FSFDYMHthsURIQjkqpQ",
        "UC2Y_OnxCHnbzvxkNgcG8sTw",
        "UCL92rdEZGj2jTkKSAWAOh6Q",
        "UCDyibt-oI2zJDPYxY542ddQ",
        "UCQfiZ8zMUXuaThA2qYof1Rg",
        "UC0MU_D3rKovbFfvprFJotOA",
        "UChT2RpVSgR-a9goIyAhBU3Q",
        "UC6drD8RH_SZg1Xj23YOkjUA",
        "UC6JrwAxp3GAczaZCFhzjk_g",
        "UCNJIm-sIiAzJHmzIaa6LybQ",
        "UCa_u-cwdS0btZIbB6nxLxng",
        "UC5nY3KM8Rv4Tm6lR8I0TP2Q",
        "UCTyQHiHUcm5rZhaDCYIrrEQ",
        "UCOd6CxXco94NNvVWRlKI95Q",
        "UCWEJJnxptIYTz3blcibLZsA",
        "UCY-6y_uo51dSCMrIFPAsDFw",
        "UCWEyZxN5O3VO29SgaehNQkw",
    ],
    "TW 세계수 S3": [
        "UCBHyZqX3kt4AiAzgK0Qrcag",
        "UCLlE4endO2rIcWqUqc76xDA",
        "UCGKL5LoNqNAR8yCj8wiWScA",
        "UCMQ9Az4Ob6caXuK0TQnTPqw",
        "UCPuQUetajpqyPTFto2Uz-JA",
        "UCQ7SNp-izmqQasmP3Oc2t5w",
        "UCFaLDiwNtMTxbQcyzRynJQQ",
        "UC5QuEzJtaQa2oO8kekD0NyA",
        "UC2WUQg_3PoToFOsppiQJ06Q",
        "UCBao4tw7MoTfx3GZD3uj6jA",
        "UCcumJaVU2oiUDMWU17T3rQg",
        "UCIL5FSFDYMHthsURIQjkqpQ",
        "UC2Y_OnxCHnbzvxkNgcG8sTw",
        "UCL92rdEZGj2jTkKSAWAOh6Q",
        "UCDyibt-oI2zJDPYxY542ddQ",
        "UCQfiZ8zMUXuaThA2qYof1Rg",
        "UC0MU_D3rKovbFfvprFJotOA",
        "UChT2RpVSgR-a9goIyAhBU3Q",
        "UC6drD8RH_SZg1Xj23YOkjUA",
        "UC6JrwAxp3GAczaZCFhzjk_g",
        "UCNJIm-sIiAzJHmzIaa6LybQ",
        "UC6bxkFe4AQ_DoLhhQFKcKzw",
        "UC5nY3KM8Rv4Tm6lR8I0TP2Q",
        "UCGeo7SiITw9uNHbtkLYjBXQ",
        "UCWEJJnxptIYTz3blcibLZsA",
        "UCY-6y_uo51dSCMrIFPAsDFw",
        "UCWEyZxN5O3VO29SgaehNQkw",
    ],
}

# ----------------------------------------------------------------------------
# 특집 리포트 설정
# 여러 키워드 그룹 + 고정 채널 프리셋 + 기준일 전후 여러 주차를 한 번에 비교하는
# 사전 구성 리포트. 새 리포트를 추가하려면 아래 딕셔너리에 항목을 추가하면 됩니다.
# ----------------------------------------------------------------------------

SPECIAL_REPORTS = {
    "s3_classic_vs_worldtree": {
        "name_ko": "TW 세계수 S3 — 經典版 출시 전후 비교",
        "name_zh": "TW 世界樹 S3 — 經典版上線前後比較",
        "channel_preset": "TW 세계수 S3",
        "pivot_date": date(2026, 7, 29),
        "utc_offset": 8,
        "window_start": -6,
        "window_end": 6,
        "groups": [
            {
                "key": "A",
                "label_ko": "世界樹計畫 계열",
                "label_zh": "世界樹計畫系列",
                "keywords": ["世界樹計畫", "#世界樹計畫"],
                "match_mode": "OR",
                "match_scope": "TITLE_ONLY",
            },
            {
                "key": "B",
                "label_ko": "經典版 계열",
                "label_zh": "經典版系列",
                "keywords": ["新楓之谷經典版", "經典版"],
                "match_mode": "OR",
                "match_scope": "ALL",
            },
        ],
    },
}

# ----------------------------------------------------------------------------
# 유틸 함수
# ----------------------------------------------------------------------------

def to_utc(date_obj, utc_offset, end_of_day=False):
    dt = datetime.combine(date_obj, datetime.min.time())
    if end_of_day:
        dt = dt.replace(hour=23, minute=59, second=59)
    dt = dt - timedelta(hours=utc_offset)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def is_shorts(v):
    title = v["snippet"].get("title", "").lower()
    desc = v["snippet"].get("description", "").lower()
    if "#shorts" in title or "#shorts" in desc:
        return True
    dur = v["contentDetails"].get("duration", "")
    m = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", dur)
    if not m:
        return False
    h, mins, s = int(m.group(1) or 0), int(m.group(2) or 0), int(m.group(3) or 0)
    return h * 3600 + mins * 60 + s <= 60


def keyword_match(v, keywords, mode_code, scope_code="ALL"):
    title = v["snippet"].get("title", "")
    if scope_code == "TITLE_ONLY":
        text = title
    else:
        desc = v["snippet"].get("description", "")
        tags = " ".join(v["snippet"].get("tags", []))
        text = title + " " + desc + " " + tags
    if mode_code == "AND":
        return all(kw in text for kw in keywords)
    return any(kw in text for kw in keywords)


def classify(v):
    """내부 분류 코드(LONGFORM/SHORTS/LIVE)를 반환. 화면 표시용 문구는 t()로 별도 변환."""
    if is_shorts(v):
        return "SHORTS"
    if v.get("liveStreamingDetails"):
        return "LIVE"
    return "LONGFORM"


def video_row(v):
    """영상 하나를 결과 테이블용 표준 dict로 변환 (일반 검색·특집 리포트 공용)."""
    return {
        "category": classify(v),
        "title": v["snippet"].get("title", ""),
        "channel": v["snippet"].get("channelTitle", ""),
        "published_at": v["snippet"].get("publishedAt", ""),
        "views": int(v["statistics"].get("viewCount", 0)),
        "url": f"https://www.youtube.com/watch?v={v['id']}",
    }


def compute_report_windows(pivot, start_n, end_n):
    """기준일(pivot) 전후로 7일 단위 구간(W-n ~ W+n)을 계산. n=0(기준일 당일 단독)은 사용하지 않음:
    음수는 기준일 이전으로 끝나는 7일, 양수는 기준일을 포함해 시작하는 7일."""
    windows = []
    for n in range(start_n, end_n + 1):
        if n == 0:
            continue
        if n < 0:
            s = pivot + timedelta(days=7 * n)
            e = pivot + timedelta(days=7 * (n + 1) - 1)
        else:
            s = pivot + timedelta(days=7 * (n - 1))
            e = pivot + timedelta(days=7 * n - 1)
        windows.append({"n": n, "label": f"W{n:+d}", "start": s, "end": e})
    return windows


def classify_crossover(v, group_a, group_b):
    """두 키워드 그룹(A/B) 매칭 결과를 조합해 상호배제 3분류로 반환.
    PURE_A: A만 해당, PURE_B: B만 해당, MIXED: 둘 다 해당(제목에 두 게임 모두 언급), None: 둘 다 미해당."""
    is_a = keyword_match(v, group_a["keywords"], group_a["match_mode"], group_a["match_scope"])
    is_b = keyword_match(v, group_b["keywords"], group_b["match_mode"], group_b["match_scope"])
    if is_a and is_b:
        return "MIXED"
    if is_a:
        return "PURE_A"
    if is_b:
        return "PURE_B"
    return None


# ----------------------------------------------------------------------------
# 검색 모드 1: Search API 기반 (전체 검색)
# ----------------------------------------------------------------------------

def fetch_by_search(youtube, query, after, before):
    videos = []
    page_token = None
    while True:
        res = (
            youtube.search()
            .list(
                part="snippet",
                q=query,
                type="video",
                publishedAfter=after,
                publishedBefore=before,
                maxResults=50,
                order="date",
                pageToken=page_token,
            )
            .execute()
        )
        ids = [i["id"]["videoId"] for i in res.get("items", [])]
        if ids:
            detail = (
                youtube.videos()
                .list(part="snippet,statistics,contentDetails,liveStreamingDetails", id=",".join(ids))
                .execute()
            )
            videos.extend(detail.get("items", []))
        page_token = res.get("nextPageToken")
        if not page_token:
            break
    return videos


def build_query_variants(keywords):
    """'#' 있는 버전 / 없는 버전을 모두 만들어 검색 누락을 줄인다.
    (YouTube Search API는 '#'이 포함된 q 값에서 relevance 매칭 범위가 좁아지는 경향이 있음)
    """
    variants = []
    seen = set()
    for kw in keywords:
        candidates = [kw, kw.lstrip("#")] if kw.startswith("#") else [kw, "#" + kw]
        for c in candidates:
            if c and c not in seen:
                seen.add(c)
                variants.append(c)
    return variants


def collect_videos_search_mode(youtube, keywords, after, before, progress_cb=None):
    seen, all_videos = set(), []
    queries = build_query_variants(keywords)
    for i, q in enumerate(queries):
        if progress_cb:
            progress_cb(i, len(queries), q)
        for v in fetch_by_search(youtube, q, after, before):
            if v["id"] not in seen:
                seen.add(v["id"])
                all_videos.append(v)
    return all_videos


# ----------------------------------------------------------------------------
# 검색 모드 2: 채널 지정 Playlist 기반 (쿼터 절약)
# ----------------------------------------------------------------------------

def ch_to_playlist_id(channel_id):
    return "UU" + channel_id[2:]


def fetch_by_playlist(youtube, playlist_id, after, before, stale_limit=10):
    videos = []
    page_token = None
    while True:
        res = (
            youtube.playlistItems()
            .list(part="snippet,contentDetails", playlistId=playlist_id, maxResults=50, pageToken=page_token)
            .execute()
        )
        ids = []
        old_count = 0
        for item in res.get("items", []):
            published = item["contentDetails"].get("videoPublishedAt", "")
            if not published:
                continue
            if published > before:
                continue
            if published <= after:
                old_count += 1
                if old_count >= stale_limit:
                    break
                continue
            old_count = 0
            ids.append(item["contentDetails"]["videoId"])

        if ids:
            detail = (
                youtube.videos()
                .list(part="snippet,statistics,contentDetails,liveStreamingDetails", id=",".join(ids))
                .execute()
            )
            videos.extend(detail.get("items", []))

        page_token = res.get("nextPageToken")
        if not page_token or old_count >= stale_limit:
            break
    return videos


def collect_videos_playlist_mode(youtube, channel_ids, after, before, progress_cb=None):
    seen, all_videos = set(), []
    for i, ch_id in enumerate(channel_ids):
        if progress_cb:
            progress_cb(i, len(channel_ids), ch_id)
        pl_id = ch_to_playlist_id(ch_id.strip())
        try:
            for v in fetch_by_playlist(youtube, pl_id, after, before):
                if v["id"] not in seen:
                    seen.add(v["id"])
                    all_videos.append(v)
        except HttpError as e:
            st.warning(t("warn_channel_error", ch=ch_id, e=e))
    return all_videos


def fetch_latest_playlist_video_ids(youtube, playlist_id, n):
    """업로드 재생목록에서 최신순으로 영상 ID를 최대 n개 가져온다 (날짜 필터 없음)."""
    ids = []
    page_token = None
    while len(ids) < n:
        res = (
            youtube.playlistItems()
            .list(
                part="contentDetails",
                playlistId=playlist_id,
                maxResults=min(50, n - len(ids)),
                pageToken=page_token,
            )
            .execute()
        )
        items = res.get("items", [])
        if not items:
            break
        ids.extend(item["contentDetails"]["videoId"] for item in items if item.get("contentDetails", {}).get("videoId"))
        page_token = res.get("nextPageToken")
        if not page_token:
            break
    return ids[:n]


def collect_channel_snapshot(youtube, channel_ids, n, progress_cb=None):
    """채널별 최신 영상 n개를 (채널ID -> 영상 상세 리스트, 최신순) 딕셔너리로 반환. 키워드/날짜 필터 없음."""
    results = {}
    for i, ch_id in enumerate(channel_ids):
        if progress_cb:
            progress_cb(i, len(channel_ids), ch_id)
        ch_id = ch_id.strip()
        pl_id = ch_to_playlist_id(ch_id)
        try:
            ids = fetch_latest_playlist_video_ids(youtube, pl_id, n)
            videos = []
            for chunk_start in range(0, len(ids), 50):
                chunk = ids[chunk_start : chunk_start + 50]
                detail = (
                    youtube.videos()
                    .list(part="snippet,statistics,contentDetails,liveStreamingDetails", id=",".join(chunk))
                    .execute()
                )
                videos.extend(detail.get("items", []))
            video_map = {v["id"]: v for v in videos}
            results[ch_id] = [video_map[vid] for vid in ids if vid in video_map]
        except HttpError as e:
            st.warning(t("warn_channel_error", ch=ch_id, e=e))
            results[ch_id] = []
    return results


# ----------------------------------------------------------------------------
# UI
# ----------------------------------------------------------------------------

st.title(t("app_title"))
st.caption(t("app_caption"))

with st.expander(t("guide_header"), expanded=False):
    st.markdown(t("guide_body"))

with st.sidebar:
    lang_choice = st.selectbox(
        t("lang_label"),
        options=["ko", "zh"],
        format_func=lambda c: "한국어" if c == "ko" else "繁體中文",
        key="lang",
    )

    st.header(t("api_key_header"))
    api_key = st.text_input(
        t("api_key_label"),
        type="password",
        help=t("api_key_help"),
    )

    app_mode = st.radio(
        t("app_mode_label"),
        [("app_mode_normal", "NORMAL"), ("app_mode_report", "REPORT"), ("app_mode_snapshot", "SNAPSHOT")],
        format_func=lambda x: t(x[0]),
        horizontal=True,
    )[1]
    st.divider()

    if app_mode == "NORMAL":
        st.header(t("search_cond_header"))
        keywords_raw = st.text_area(
            t("keywords_label"),
            value="#世界樹計畫",
            height=80,
        )
        keywords = [k.strip() for k in keywords_raw.splitlines() if k.strip()]

        match_mode = st.radio(
            t("match_mode_label"),
            [("match_mode_or", "OR"), ("match_mode_and", "AND")],
            format_func=lambda x: t(x[0]),
            index=0,
            help=t("match_mode_help"),
        )[1]

        match_scope = st.radio(
            t("match_scope_label"),
            [("match_scope_all", "ALL"), ("match_scope_title", "TITLE_ONLY")],
            format_func=lambda x: t(x[0]),
            index=0,
            help=t("match_scope_help"),
        )[1]

        st.header(t("period_header"))
        col1, col2 = st.columns(2)
        with col1:
            date_start = st.date_input(t("date_start_label"), value=datetime(2026, 1, 1))
        with col2:
            date_end = st.date_input(t("date_end_label"), value=datetime.today())

        utc_offset = st.selectbox(
            t("timezone_label"),
            options=[("tz_taiwan", 8), ("tz_korea", 9), ("tz_utc", 0)],
            format_func=lambda x: t(x[0]),
        )[1]

        st.header(t("mode_header"))
        search_mode = st.radio(
            t("mode_label"),
            [("mode_search", "SEARCH"), ("mode_playlist", "PLAYLIST")],
            format_func=lambda x: t(x[0]),
            help=t("mode_help"),
        )[1]
        if search_mode == "SEARCH":
            st.caption(t("mode_search_caption"))

        channel_ids = []
        if search_mode == "PLAYLIST":

            def _apply_preset():
                preset_name = st.session_state["channel_preset_select"]
                if preset_name == "CUSTOM":
                    st.session_state["channel_ids_text"] = ""
                else:
                    st.session_state["channel_ids_text"] = "\n".join(CHANNEL_PRESETS[preset_name])

            preset_choice = st.selectbox(
                t("preset_label"),
                ["CUSTOM"] + list(CHANNEL_PRESETS.keys()),
                key="channel_preset_select",
                format_func=lambda x: t("preset_custom") if x == "CUSTOM" else x,
                on_change=_apply_preset,
                help=t("preset_help"),
            )

            if "channel_ids_text" not in st.session_state:
                st.session_state["channel_ids_text"] = (
                    "\n".join(CHANNEL_PRESETS[preset_choice]) if preset_choice != "CUSTOM" else ""
                )

            channel_ids_raw = st.text_area(
                t("channel_ids_label"),
                height=150,
                key="channel_ids_text",
                help=t("channel_ids_help"),
            )
            channel_ids = [c.strip() for c in channel_ids_raw.splitlines() if c.strip()]
            if channel_ids:
                st.caption(t("channel_count_caption", n=len(channel_ids)))

        run_btn = st.button(t("run_button"), type="primary", use_container_width=True)

    elif app_mode == "REPORT":
        st.header(t("report_header"))
        report_key = st.selectbox(
            t("report_select_label"),
            list(SPECIAL_REPORTS.keys()),
            format_func=lambda k: SPECIAL_REPORTS[k]["name_ko" if CURRENT_LANG == "ko" else "name_zh"],
        )
        report = SPECIAL_REPORTS[report_key]

        st.markdown(t("report_config_title"))
        for g in report["groups"]:
            glabel = g["label_ko"] if CURRENT_LANG == "ko" else g["label_zh"]
            scope_label = t("match_scope_title") if g["match_scope"] == "TITLE_ONLY" else t("match_scope_all")
            mode_label = t("match_mode_and") if g["match_mode"] == "AND" else t("match_mode_or")
            st.caption(f"· **{glabel}**: {' / '.join(g['keywords'])} ({mode_label}, {scope_label})")
        st.caption(
            t("report_channel_count", n=len(CHANNEL_PRESETS[report["channel_preset"]]), preset=report["channel_preset"])
        )
        st.caption(
            t(
                "report_window_count",
                n=report["window_end"] - report["window_start"],
                start=report["window_start"],
                end=report["window_end"],
                half=report["window_end"],
            )
        )
        st.caption(t("report_mutual_exclusion_note"))

        run_report_btn = st.button(t("report_run_button"), type="primary", use_container_width=True)

    else:  # SNAPSHOT
        st.header(t("snapshot_header"))
        st.caption(t("snapshot_desc"))

        snapshot_preset = st.selectbox(t("snapshot_preset_label"), list(CHANNEL_PRESETS.keys()))
        snapshot_channel_ids = CHANNEL_PRESETS[snapshot_preset]
        snapshot_n = st.number_input(
            t("snapshot_n_label"), min_value=1, max_value=50, value=10, step=1, help=t("snapshot_n_help")
        )
        st.caption(t("report_channel_count", n=len(snapshot_channel_ids), preset=snapshot_preset))

        run_snapshot_btn = st.button(t("snapshot_run_button"), type="primary", use_container_width=True)

# ----------------------------------------------------------------------------
# 실행
# ----------------------------------------------------------------------------

if app_mode == "NORMAL" and run_btn:
    if not api_key:
        st.error(t("err_need_api_key"))
        st.stop()
    if not keywords:
        st.error(t("err_need_keyword"))
        st.stop()
    if search_mode == "PLAYLIST" and not channel_ids:
        st.error(t("err_need_channel"))
        st.stop()
    if date_start > date_end:
        st.error(t("err_date_order"))
        st.stop()

    after = to_utc(date_start, utc_offset, end_of_day=False)
    before = to_utc(date_end, utc_offset, end_of_day=True)

    try:
        youtube = build("youtube", "v3", developerKey=api_key)

        progress = st.progress(0.0, text=t("progress_prepare"))

        def progress_cb(i, total, label):
            progress.progress((i + 1) / total, text=t("progress_fetching", label=label, i=i + 1, total=total))

        with st.spinner(t("spinner_collecting")):
            if search_mode == "SEARCH":
                raw_videos = collect_videos_search_mode(youtube, keywords, after, before, progress_cb)
            else:
                raw_videos = collect_videos_playlist_mode(youtube, channel_ids, after, before, progress_cb)

        progress.empty()

        videos = [v for v in raw_videos if keyword_match(v, keywords, match_mode, match_scope)]

        if not videos:
            st.warning(t("warn_no_results"))
            st.stop()

        rows = []
        for v in videos:
            rows.append(video_row(v))
        df = pd.DataFrame(rows)

        CATEGORY_LABEL_KEY = {"LONGFORM": "cat_longform", "SHORTS": "cat_shorts", "LIVE": "cat_live"}
        categories = ["LONGFORM", "SHORTS", "LIVE"]

        col_labels = {
            "category": t("table_col_category"),
            "title": t("table_col_title"),
            "channel": t("table_col_channel"),
            "published_at": t("table_col_date"),
            "views": t("table_col_views"),
            "url": t("link_col_label"),
        }

        def col_config():
            return {
                "category": st.column_config.TextColumn(col_labels["category"]),
                "title": st.column_config.TextColumn(col_labels["title"]),
                "channel": st.column_config.TextColumn(col_labels["channel"]),
                "published_at": st.column_config.TextColumn(col_labels["published_at"]),
                "views": st.column_config.NumberColumn(col_labels["views"], format="%d"),
                "url": st.column_config.LinkColumn(col_labels["url"]),
            }

        def localize_category(sub_df):
            out = sub_df.copy()
            out["category"] = out["category"].map(lambda c: t(CATEGORY_LABEL_KEY[c]))
            return out

        # ------------------------------------------------------------------
        # 요약 지표
        # ------------------------------------------------------------------
        st.subheader(t("summary_header"))
        counts = {c: int((df["category"] == c).sum()) for c in categories}
        views_sum = {c: int(df.loc[df["category"] == c, "views"].sum()) for c in categories}

        m0, m1, m2, m3 = st.columns(4)
        m0.metric(
            t("metric_total_label"),
            f"{len(df):,}{t('unit_count')}",
            help=t("metric_help_views_sum", n=f"{df['views'].sum():,}"),
        )
        for col, cat in zip([m1, m2, m3], categories):
            col.metric(
                t(CATEGORY_LABEL_KEY[cat]),
                f"{counts[cat]:,}{t('unit_count')}",
                help=t("metric_help_views_sum", n=f"{views_sum[cat]:,}"),
            )

        st.markdown(t("summary_table_title"))
        summary_df = pd.DataFrame(
            {
                "item": [t("cat_all")] + [t(CATEGORY_LABEL_KEY[c]) for c in categories],
                "count": [len(df)] + [counts[c] for c in categories],
                "views_sum": [int(df["views"].sum())] + [views_sum[c] for c in categories],
            }
        )
        st.dataframe(
            summary_df,
            use_container_width=True,
            hide_index=True,
            column_config={
                "item": st.column_config.TextColumn(t("summary_col_item")),
                "count": st.column_config.NumberColumn(t("summary_col_count"), format="%d"),
                "views_sum": st.column_config.NumberColumn(t("summary_col_views_sum"), format="%d"),
            },
        )

        # ------------------------------------------------------------------
        # Top 5
        # ------------------------------------------------------------------
        st.subheader(t("top5_header"))

        def show_top5(sub_df, label):
            top5 = sub_df.sort_values("views", ascending=False).head(5)
            if top5.empty:
                st.caption(t("top5_none", label=label))
                return
            st.markdown(f"**{label}**")
            st.dataframe(
                top5[["title", "channel", "views", "url"]].reset_index(drop=True),
                use_container_width=True,
                hide_index=True,
                column_config={
                    "title": st.column_config.TextColumn(col_labels["title"]),
                    "channel": st.column_config.TextColumn(col_labels["channel"]),
                    "views": st.column_config.NumberColumn(col_labels["views"], format="%d"),
                    "url": st.column_config.LinkColumn(col_labels["url"]),
                },
            )

        show_top5(df, t("cat_all"))
        for c in categories:
            show_top5(df[df["category"] == c], t(CATEGORY_LABEL_KEY[c]))

        # ------------------------------------------------------------------
        # 전체 목록 + 다운로드
        # ------------------------------------------------------------------
        st.subheader(t("all_list_header"))
        st.dataframe(
            localize_category(df).sort_values("views", ascending=False).reset_index(drop=True),
            use_container_width=True,
            hide_index=True,
            column_config=col_config(),
        )

        export_df = localize_category(df).sort_values("views", ascending=False).rename(columns=col_labels)
        csv = export_df.to_csv(index=False).encode("utf-8-sig")
        st.download_button(
            t("csv_button_label"),
            data=csv,
            file_name=f"youtube_stats_{date_start}_{date_end}.csv",
            mime="text/csv",
        )

    except HttpError as e:
        st.error(t("api_error_prefix", e=e))
    except Exception as e:
        st.error(t("generic_error_prefix", e=e))

elif app_mode == "REPORT" and run_report_btn:
    if not api_key:
        st.error(t("err_need_api_key"))
        st.stop()

    report_channel_ids = CHANNEL_PRESETS[report["channel_preset"]]
    windows = compute_report_windows(report["pivot_date"], report["window_start"], report["window_end"])
    group_a, group_b = report["groups"][0], report["groups"][1]
    group_labels = {g["key"]: (g["label_ko"] if CURRENT_LANG == "ko" else g["label_zh"]) for g in report["groups"]}

    BUCKET_ORDER = ["PURE_A", "PURE_B", "MIXED"]
    bucket_labels = {
        "PURE_A": f"{group_labels[group_a['key']]}{t('report_cat_pure_suffix')}",
        "PURE_B": f"{group_labels[group_b['key']]}{t('report_cat_pure_suffix')}",
        "MIXED": t("report_cat_mixed"),
    }

    try:
        youtube = build("youtube", "v3", developerKey=api_key)

        progress = st.progress(0.0, text=t("report_progress", label=windows[0]["label"], i=1, total=len(windows)))
        window_results = []

        with st.spinner(t("report_spinner", n=len(windows))):
            for idx, w in enumerate(windows):
                progress.progress(
                    (idx + 1) / len(windows),
                    text=t("report_progress", label=w["label"], i=idx + 1, total=len(windows)),
                )
                after = to_utc(w["start"], report["utc_offset"], end_of_day=False)
                before = to_utc(w["end"], report["utc_offset"], end_of_day=True)
                raw_videos = collect_videos_playlist_mode(youtube, report_channel_ids, after, before)

                bucket_videos = {b: [] for b in BUCKET_ORDER}
                for v in raw_videos:
                    b = classify_crossover(v, group_a, group_b)
                    if b:
                        bucket_videos[b].append(v)

                bucket_data = {
                    b: {
                        "count": len(vids),
                        "views": sum(int(v["statistics"].get("viewCount", 0)) for v in vids),
                        "videos": vids,
                    }
                    for b, vids in bucket_videos.items()
                }
                window_results.append({"window": w, "buckets": bucket_data})

        progress.empty()

        # ------------------------------------------------------------------
        # 구간별 비교 표
        # ------------------------------------------------------------------
        st.subheader(t("report_summary_header"))
        summary_rows = []
        for wr in window_results:
            row = {
                t("report_col_window"): wr["window"]["label"],
                t("report_col_period"): f"{wr['window']['start']} ~ {wr['window']['end']}",
            }
            for b in BUCKET_ORDER:
                bl = bucket_labels[b]
                row[f"{bl}{t('report_col_count_suffix')}"] = wr["buckets"][b]["count"]
                row[f"{bl}{t('report_col_views_suffix')}"] = wr["buckets"][b]["views"]
            summary_rows.append(row)
        summary_df = pd.DataFrame(summary_rows)
        st.dataframe(summary_df, use_container_width=True, hide_index=True)

        # ------------------------------------------------------------------
        # 추이 그래프
        # ------------------------------------------------------------------
        window_labels = [wr["window"]["label"] for wr in window_results]

        st.subheader(t("report_chart_count_header"))
        count_chart_df = pd.DataFrame(
            {bucket_labels[b]: [wr["buckets"][b]["count"] for wr in window_results] for b in BUCKET_ORDER},
            index=window_labels,
        )
        st.line_chart(count_chart_df)

        st.subheader(t("report_chart_views_header"))
        views_chart_df = pd.DataFrame(
            {bucket_labels[b]: [wr["buckets"][b]["views"] for wr in window_results] for b in BUCKET_ORDER},
            index=window_labels,
        )
        st.line_chart(views_chart_df)

        # ------------------------------------------------------------------
        # 구간별 상세 영상 목록 (드릴다운)
        # ------------------------------------------------------------------
        st.subheader(t("report_drilldown_header"))
        for wr in window_results:
            w = wr["window"]
            with st.expander(f"{w['label']}  ({w['start']} ~ {w['end']})"):
                for b in BUCKET_ORDER:
                    bl = bucket_labels[b]
                    vids = wr["buckets"][b]["videos"]
                    st.markdown(f"**{bl}**")
                    if not vids:
                        st.caption(t("report_drilldown_group_none", group=bl))
                        continue
                    vdf = pd.DataFrame([video_row(v) for v in vids]).sort_values("views", ascending=False)
                    st.dataframe(
                        vdf[["title", "channel", "views", "url"]].reset_index(drop=True),
                        use_container_width=True,
                        hide_index=True,
                        column_config={
                            "title": st.column_config.TextColumn(t("table_col_title")),
                            "channel": st.column_config.TextColumn(t("table_col_channel")),
                            "views": st.column_config.NumberColumn(t("table_col_views"), format="%d"),
                            "url": st.column_config.LinkColumn(t("link_col_label")),
                        },
                    )

        csv = summary_df.to_csv(index=False).encode("utf-8-sig")
        st.download_button(
            t("csv_button_label"),
            data=csv,
            file_name=f"special_report_{report_key}.csv",
            mime="text/csv",
        )

    except HttpError as e:
        st.error(t("api_error_prefix", e=e))
    except Exception as e:
        st.error(t("generic_error_prefix", e=e))

elif app_mode == "SNAPSHOT" and run_snapshot_btn:
    if not api_key:
        st.error(t("err_need_api_key"))
        st.stop()

    try:
        youtube = build("youtube", "v3", developerKey=api_key)

        progress = st.progress(
            0.0, text=t("snapshot_progress", label=snapshot_channel_ids[0], i=1, total=len(snapshot_channel_ids))
        )

        def snapshot_progress_cb(i, total, label):
            progress.progress((i + 1) / total, text=t("snapshot_progress", label=label, i=i + 1, total=total))

        with st.spinner(t("snapshot_spinner", n=len(snapshot_channel_ids))):
            snapshot_results = collect_channel_snapshot(
                youtube, snapshot_channel_ids, int(snapshot_n), snapshot_progress_cb
            )

        progress.empty()

        st.subheader(t("snapshot_result_header"))

        rows = []
        for ch_id in snapshot_channel_ids:
            for v in snapshot_results.get(ch_id.strip(), []):
                rows.append(video_row(v))

        empty_channels = [ch for ch in snapshot_channel_ids if not snapshot_results.get(ch.strip())]

        if not rows:
            st.warning(t("warn_no_results"))
        else:
            SNAP_CATEGORY_LABEL_KEY = {"LONGFORM": "cat_longform", "SHORTS": "cat_shorts", "LIVE": "cat_live"}
            df = pd.DataFrame(rows)
            df["category"] = df["category"].map(lambda c: t(SNAP_CATEGORY_LABEL_KEY[c]))

            st.dataframe(
                df,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "category": st.column_config.TextColumn(t("table_col_category")),
                    "title": st.column_config.TextColumn(t("table_col_title")),
                    "channel": st.column_config.TextColumn(t("table_col_channel")),
                    "published_at": st.column_config.TextColumn(t("table_col_date")),
                    "views": st.column_config.NumberColumn(t("table_col_views"), format="%d"),
                    "url": st.column_config.LinkColumn(t("link_col_label")),
                },
            )
            st.caption(t("snapshot_total_caption", n=len(snapshot_channel_ids), m=len(rows)))

            if empty_channels:
                st.caption(f"ℹ️ {t('snapshot_empty_note')} ({', '.join(empty_channels)})")

            export_df = df.rename(
                columns={
                    "category": t("table_col_category"),
                    "title": t("table_col_title"),
                    "channel": t("table_col_channel"),
                    "published_at": t("table_col_date"),
                    "views": t("table_col_views"),
                    "url": t("link_col_label"),
                }
            )
            csv = export_df.to_csv(index=False).encode("utf-8-sig")
            st.download_button(
                t("csv_button_label"),
                data=csv,
                file_name=f"channel_snapshot_{snapshot_preset}.csv",
                mime="text/csv",
            )

    except HttpError as e:
        st.error(t("api_error_prefix", e=e))
    except Exception as e:
        st.error(t("generic_error_prefix", e=e))

else:
    if app_mode == "NORMAL":
        st.info(t("idle_info"))
    elif app_mode == "REPORT":
        st.info(t("report_idle_info"))
    else:
        st.info(t("snapshot_idle_info"))
