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
from datetime import datetime, timedelta

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


def keyword_match(v, keywords, mode_code):
    title = v["snippet"].get("title", "")
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


# ----------------------------------------------------------------------------
# UI
# ----------------------------------------------------------------------------

st.title(t("app_title"))
st.caption(t("app_caption"))

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

# ----------------------------------------------------------------------------
# 실행
# ----------------------------------------------------------------------------

if run_btn:
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

        videos = [v for v in raw_videos if keyword_match(v, keywords, match_mode)]

        if not videos:
            st.warning(t("warn_no_results"))
            st.stop()

        rows = []
        for v in videos:
            rows.append(
                {
                    "category": classify(v),
                    "title": v["snippet"].get("title", ""),
                    "channel": v["snippet"].get("channelTitle", ""),
                    "published_at": v["snippet"].get("publishedAt", ""),
                    "views": int(v["statistics"].get("viewCount", 0)),
                    "url": f"https://www.youtube.com/watch?v={v['id']}",
                }
            )
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
else:
    st.info(t("idle_info"))
