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

st.set_page_config(page_title="YouTube 키워드 트래커", page_icon="📊", layout="wide")

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


def keyword_match(v, keywords, mode):
    title = v["snippet"].get("title", "")
    desc = v["snippet"].get("description", "")
    tags = " ".join(v["snippet"].get("tags", []))
    text = title + " " + desc + " " + tags
    if mode == "AND (모두 포함)":
        return all(kw in text for kw in keywords)
    return any(kw in text for kw in keywords)


def classify(v):
    if is_shorts(v):
        return "쇼츠"
    if v.get("liveStreamingDetails"):
        return "라이브 다시보기"
    return "롱폼"


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


def collect_videos_search_mode(youtube, keywords, after, before, progress_cb=None):
    seen, all_videos = set(), []
    for i, kw in enumerate(keywords):
        if progress_cb:
            progress_cb(i, len(keywords), kw)
        for v in fetch_by_search(youtube, kw, after, before):
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
            st.warning(f"채널 {ch_id} 조회 중 오류: {e}")
    return all_videos


# ----------------------------------------------------------------------------
# UI
# ----------------------------------------------------------------------------

st.title("📊 YouTube 키워드 트래커")
st.caption("특정 키워드/캠페인의 영상 수·조회수를 검색·집계합니다. (예: #世界樹計畫)")

with st.sidebar:
    st.header("🔑 API Key")
    api_key = st.text_input(
        "YouTube Data API Key",
        type="password",
        help="본인의 Google Cloud 프로젝트에서 발급받은 YouTube Data API v3 키를 입력하세요. "
        "이 값은 서버에 저장되지 않고 현재 세션에서만 사용됩니다.",
    )

    st.header("🔍 검색 조건")
    keywords_raw = st.text_area(
        "검색 키워드 (한 줄에 하나씩 입력, 2개 이상 가능)",
        value="#世界樹計畫",
        height=80,
    )
    keywords = [k.strip() for k in keywords_raw.splitlines() if k.strip()]

    match_mode = st.radio(
        "다중 키워드 매칭 방식",
        ["OR (하나라도 포함)", "AND (모두 포함)"],
        index=0,
        help="OR: 검색 결과 후보를 넓게 모은 뒤, 제목/설명/태그 중 하나라도 키워드를 포함하면 채택.\n"
        "AND: 제목/설명/태그 전체 텍스트에 모든 키워드가 포함되어야 채택.",
    )

    st.header("📅 검색 기간")
    col1, col2 = st.columns(2)
    with col1:
        date_start = st.date_input("시작일", value=datetime(2026, 1, 1))
    with col2:
        date_end = st.date_input("종료일", value=datetime.today())

    utc_offset = st.selectbox(
        "기준 시간대", options=[("대만 (UTC+8)", 8), ("한국 (UTC+9)", 9), ("UTC+0", 0)], format_func=lambda x: x[0]
    )[1]

    st.header("⚙️ 검색 모드")
    search_mode = st.radio(
        "모드 선택",
        ["전체 검색 (Search API)", "채널 지정 검색 (Playlist 방식, 쿼터 절약)"],
        help="전체 검색: 키워드로 유튜브 전체를 검색 (쿼터 소모 큼).\n"
        "채널 지정 검색: 지정한 채널들의 업로드 목록만 훑어서 쿼터를 크게 절약합니다. "
        "캠페인 참여 채널이 고정되어 있을 때 추천합니다.",
    )

    channel_ids = []
    if search_mode.startswith("채널"):
        channel_ids_raw = st.text_area(
            "채널 ID 목록 (한 줄에 하나씩, 'UC...' 형태)",
            height=150,
            help="예: UCBHyZqX3kt4AiAzgK0Qrcag",
        )
        channel_ids = [c.strip() for c in channel_ids_raw.splitlines() if c.strip()]

    run_btn = st.button("🚀 검색 실행", type="primary", use_container_width=True)

# ----------------------------------------------------------------------------
# 실행
# ----------------------------------------------------------------------------

if run_btn:
    if not api_key:
        st.error("API Key를 입력해주세요.")
        st.stop()
    if not keywords:
        st.error("검색 키워드를 최소 1개 입력해주세요.")
        st.stop()
    if search_mode.startswith("채널") and not channel_ids:
        st.error("채널 지정 검색 모드에서는 채널 ID를 최소 1개 입력해주세요.")
        st.stop()
    if date_start > date_end:
        st.error("시작일이 종료일보다 늦을 수 없습니다.")
        st.stop()

    after = to_utc(date_start, utc_offset, end_of_day=False)
    before = to_utc(date_end, utc_offset, end_of_day=True)

    try:
        youtube = build("youtube", "v3", developerKey=api_key)

        progress = st.progress(0.0, text="검색 준비 중...")

        def progress_cb(i, total, label):
            progress.progress((i + 1) / total, text=f"조회 중: {label} ({i + 1}/{total})")

        with st.spinner("영상 데이터를 수집하는 중입니다..."):
            if search_mode.startswith("전체"):
                raw_videos = collect_videos_search_mode(youtube, keywords, after, before, progress_cb)
            else:
                raw_videos = collect_videos_playlist_mode(youtube, channel_ids, after, before, progress_cb)

        progress.empty()

        videos = [v for v in raw_videos if keyword_match(v, keywords, match_mode)]

        if not videos:
            st.warning("조건에 맞는 영상을 찾지 못했습니다.")
            st.stop()

        rows = []
        for v in videos:
            rows.append(
                {
                    "분류": classify(v),
                    "제목": v["snippet"].get("title", ""),
                    "채널": v["snippet"].get("channelTitle", ""),
                    "게시일": v["snippet"].get("publishedAt", ""),
                    "조회수": int(v["statistics"].get("viewCount", 0)),
                    "URL": f"https://www.youtube.com/watch?v={v['id']}",
                }
            )
        df = pd.DataFrame(rows)

        # ------------------------------------------------------------------
        # 요약 지표
        # ------------------------------------------------------------------
        st.subheader("📈 요약")
        categories = ["롱폼", "쇼츠", "라이브 다시보기"]
        counts = {c: int((df["분류"] == c).sum()) for c in categories}
        views_sum = {c: int(df.loc[df["분류"] == c, "조회수"].sum()) for c in categories}

        m0, m1, m2, m3 = st.columns(4)
        m0.metric("전체 영상 수", f"{len(df):,}개", help=f"조회수 합계 {df['조회수'].sum():,}회")
        m1.metric("롱폼", f"{counts['롱폼']:,}개", help=f"조회수 합계 {views_sum['롱폼']:,}회")
        m2.metric("쇼츠", f"{counts['쇼츠']:,}개", help=f"조회수 합계 {views_sum['쇼츠']:,}회")
        m3.metric("라이브 다시보기", f"{counts['라이브 다시보기']:,}개", help=f"조회수 합계 {views_sum['라이브 다시보기']:,}회")

        st.markdown("**항목별 조회수 합계**")
        summary_df = pd.DataFrame(
            {
                "항목": ["전체"] + categories,
                "영상 수": [len(df)] + [counts[c] for c in categories],
                "조회수 합계": [int(df["조회수"].sum())] + [views_sum[c] for c in categories],
            }
        )
        st.dataframe(summary_df, use_container_width=True, hide_index=True)

        # ------------------------------------------------------------------
        # Top 5
        # ------------------------------------------------------------------
        st.subheader("🏆 조회수 Top 5")

        def show_top5(sub_df, label):
            top5 = sub_df.sort_values("조회수", ascending=False).head(5)
            if top5.empty:
                st.caption(f"{label}: 해당 영상 없음")
                return
            st.markdown(f"**{label}**")
            st.dataframe(
                top5[["제목", "채널", "조회수", "URL"]].reset_index(drop=True),
                use_container_width=True,
                hide_index=True,
                column_config={"URL": st.column_config.LinkColumn("링크")},
            )

        show_top5(df, "전체")
        for c in categories:
            show_top5(df[df["분류"] == c], c)

        # ------------------------------------------------------------------
        # 전체 목록 + 다운로드
        # ------------------------------------------------------------------
        st.subheader("📋 전체 영상 목록")
        st.dataframe(
            df.sort_values("조회수", ascending=False).reset_index(drop=True),
            use_container_width=True,
            hide_index=True,
            column_config={"URL": st.column_config.LinkColumn("링크")},
        )

        csv = df.to_csv(index=False).encode("utf-8-sig")
        st.download_button(
            "⬇️ CSV 다운로드 (Excel에서 열기 가능)",
            data=csv,
            file_name=f"youtube_stats_{date_start}_{date_end}.csv",
            mime="text/csv",
        )

    except HttpError as e:
        st.error(f"YouTube API 오류가 발생했습니다: {e}")
    except Exception as e:
        st.error(f"오류가 발생했습니다: {e}")
else:
    st.info("왼쪽 사이드바에서 조건을 설정하고 '검색 실행' 버튼을 눌러주세요.")
