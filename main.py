import streamlit as st
import pandas as pd
import requests

from datetime import datetime, timedelta, date
from zoneinfo import ZoneInfo


# --------------------------------------------------
# 1. 페이지 기본 설정
# --------------------------------------------------
st.set_page_config(
    page_title="일별 박스오피스",
    page_icon="🎬",
    layout="wide"
)

st.title("🎬 일별 박스오피스")
st.caption("KOBIS 영화관입장권통합전산망 일별 박스오피스")


# --------------------------------------------------
# 2. 한국 시간 기준 날짜 계산
# --------------------------------------------------
# Streamlit Cloud 서버의 시간대가 한국이 아닐 수 있으므로
# 반드시 Asia/Seoul 시간대를 사용합니다.
korea_now = datetime.now(ZoneInfo("Asia/Seoul"))

today = korea_now.date()
yesterday = today - timedelta(days=1)


# --------------------------------------------------
# 3. 조회 날짜 선택
# --------------------------------------------------
st.subheader("📅 날짜 선택")

selected_date = st.date_input(
    "박스오피스를 조회할 날짜를 선택하세요.",
    value=yesterday,

    # KOBIS 일별 박스오피스 서비스의 오래된 데이터까지
    # 조회할 수 있도록 충분히 이전 날짜로 설정
    min_value=date(2004, 1, 1),

    # 오늘 데이터는 아직 집계 전일 수 있으므로
    # 최대 선택 가능 날짜를 어제로 제한
    max_value=yesterday
)

# API에서 사용하는 yyyymmdd 형식
target_date = selected_date.strftime("%Y%m%d")

# 화면에 표시할 날짜
display_date = selected_date.strftime("%Y년 %m월 %d일")

st.info(f"현재 조회 날짜: **{display_date}**")


# --------------------------------------------------
# 4. KOBIS API에서 데이터 가져오기
# --------------------------------------------------
# 같은 날짜를 다시 조회하면
# 약 1시간 동안 저장된 데이터를 사용합니다.
@st.cache_data(ttl=3600)
def load_boxoffice(target_dt):

    # ----------------------------------------------
    # 인증키 가져오기
    # ----------------------------------------------
    try:
        api_key = st.secrets["KOBIS_KEY"]

    except KeyError:
        return None, (
            "KOBIS_KEY가 설정되어 있지 않습니다.\n\n"
            "Streamlit Cloud의 **Settings → Secrets**에서 "
            "`KOBIS_KEY`를 등록해 주세요."
        )


    # ----------------------------------------------
    # API 주소
    # ----------------------------------------------
    url = (
        "https://www.kobis.or.kr/kobisopenapi/webservice/rest/"
        "boxoffice/searchDailyBoxOfficeList.json"
    )

    params = {
        "key": api_key,
        "targetDt": target_dt
    }


    # ----------------------------------------------
    # API 요청
    # ----------------------------------------------
    try:

        response = requests.get(
            url,
            params=params,
            timeout=10
        )

        response.raise_for_status()

    except requests.exceptions.Timeout:

        return None, (
            "KOBIS 서버의 응답 시간이 너무 오래 걸리고 있습니다.\n\n"
            "잠시 후 다시 시도해 주세요."
        )

    except requests.exceptions.RequestException as e:

        return None, (
            "KOBIS API에 연결하지 못했습니다.\n\n"
            "인터넷 연결이나 KOBIS 서버 상태를 확인해 주세요.\n\n"
            f"오류 내용: {e}"
        )


    # ----------------------------------------------
    # JSON 변환
    # ----------------------------------------------
    try:
        data = response.json()

    except ValueError:

        return None, (
            "KOBIS 서버에서 정상적인 데이터를 받지 못했습니다.\n\n"
            "잠시 후 다시 시도해 주세요."
        )


    # ----------------------------------------------
    # faultInfo 확인
    # ----------------------------------------------
    # KOBIS는 인증키가 잘못되어도
    # HTTP 상태코드 200이 오는 경우가 있기 때문에
    # faultInfo를 따로 확인해야 합니다.
    if "faultInfo" in data:

        fault = data.get("faultInfo", {})

        message = fault.get(
            "message",
            "KOBIS API에서 오류가 발생했습니다."
        )

        return None, (
            "KOBIS API에서 오류가 반환되었습니다.\n\n"
            f"오류 메시지: {message}\n\n"
            "Streamlit Secrets의 `KOBIS_KEY`가 올바른지 확인해 주세요."
        )


    # ----------------------------------------------
    # boxOfficeResult 확인
    # ----------------------------------------------
    boxoffice_result = data.get("boxOfficeResult")

    if not boxoffice_result:

        return None, (
            "박스오피스 결과를 찾을 수 없습니다.\n\n"
            "API 응답 형식이나 인증키를 확인해 주세요."
        )


    # ----------------------------------------------
    # 영화 목록 가져오기
    # ----------------------------------------------
    movie_list = boxoffice_result.get(
        "dailyBoxOfficeList",
        []
    )


    # 영화 목록이 비어 있는 경우
    if not movie_list:

        return None, "EMPTY"


    # DataFrame으로 변환
    df = pd.DataFrame(movie_list)

    return df, None


# --------------------------------------------------
# 5. 데이터 불러오기
# --------------------------------------------------
df, error_message = load_boxoffice(target_date)


# --------------------------------------------------
# 영화 목록이 비어 있는 경우
# --------------------------------------------------
if error_message == "EMPTY":

    st.warning("그날은 아직 집계 전입니다.")

    st.caption(
        "KOBIS에 해당 날짜의 일별 박스오피스 자료가 "
        "아직 등록되지 않았을 수 있습니다."
    )

    st.stop()


# --------------------------------------------------
# 일반 오류가 발생한 경우
# --------------------------------------------------
if error_message:

    st.error(error_message)

    st.stop()


# --------------------------------------------------
# 6. 문자열 숫자를 실제 숫자로 변환
# --------------------------------------------------
# KOBIS API에서는 숫자도 문자열로 전달됩니다.
#
# 예:
# "100"
# "250000"
#
# 문자열 상태에서는 정렬이 이상해질 수 있으므로
# 숫자로 변환합니다.
numeric_columns = [
    "rank",
    "rankInten",
    "audiCnt",
    "audiAcc",
    "scrnCnt",
    "showCnt"
]

for column in numeric_columns:

    if column in df.columns:

        df[column] = pd.to_numeric(
            df[column],
            errors="coerce"
        ).fillna(0).astype(int)


# --------------------------------------------------
# 7. 순위 기준 정렬
# --------------------------------------------------
df = (
    df
    .sort_values(
        by="rank",
        ascending=True
    )
    .reset_index(drop=True)
)


# --------------------------------------------------
# 8. 누적관객 100만 명 이상 영화 표시
# --------------------------------------------------
# 원래 영화명은 유지하고
# 화면 표시용 영화명을 따로 만듭니다.
df["영화명표시"] = df.apply(
    lambda row:
        f"{row['movieNm']} 🏆"
        if row["audiAcc"] >= 1_000_000
        else row["movieNm"],
    axis=1
)


# --------------------------------------------------
# 9. 순위 변동 표시 만들기
# --------------------------------------------------
# rankInten
#
# 양수 : 순위 상승
# 음수 : 순위 하락
# 0    : 변동 없음
def make_rank_change(value):

    if value > 0:
        return f"↑ {value}"

    elif value < 0:
        return f"↓ {abs(value)}"

    else:
        return "-"


df["순위변동"] = df["rankInten"].apply(
    make_rank_change
)


# --------------------------------------------------
# 10. 1위 영화 크게 보여주기
# --------------------------------------------------
first_movie = df.iloc[0]

st.markdown("---")

st.subheader(
    f"🥇 1위 · {first_movie['영화명표시']}"
)

col1, col2, col3 = st.columns(3)


with col1:

    st.metric(
        label="👥 관객수",
        value=f"{first_movie['audiCnt']:,}명"
    )


with col2:

    st.metric(
        label="🎟️ 누적 관객수",
        value=f"{first_movie['audiAcc']:,}명"
    )


with col3:

    st.metric(
        label="🎞️ 스크린수",
        value=f"{first_movie['scrnCnt']:,}개"
    )


# --------------------------------------------------
# 11. 관객수 상위 5편 막대그래프
# --------------------------------------------------
st.markdown("---")

st.subheader("📊 관객수 상위 5편")


# 관객수 기준으로 숫자 정렬
top5 = (
    df
    .sort_values(
        by="audiCnt",
        ascending=False
    )
    .head(5)
    .copy()
)


# 그래프에는 영화명을 표시
chart_data = (
    top5[
        [
            "영화명표시",
            "audiCnt"
        ]
    ]
    .set_index("영화명표시")
)


st.bar_chart(
    chart_data,
    horizontal=True
)


# --------------------------------------------------
# 12. 전체 박스오피스 표
# --------------------------------------------------
st.markdown("---")

st.subheader("🎞️ 전체 박스오피스")


table_df = df[
    [
        "rank",
        "순위변동",
        "영화명표시",
        "openDt",
        "audiCnt",
        "audiAcc",
        "scrnCnt"
    ]
].copy()


# 화면에 표시되는 열 이름
table_df.columns = [
    "순위",
    "순위 변동",
    "영화명",
    "개봉일",
    "관객수",
    "누적관객",
    "스크린수"
]


# --------------------------------------------------
# 13. 숫자 표시 형식 변경
# --------------------------------------------------
table_df["관객수"] = table_df["관객수"].map(
    lambda x: f"{x:,}"
)

table_df["누적관객"] = table_df["누적관객"].map(
    lambda x: f"{x:,}"
)

table_df["스크린수"] = table_df["스크린수"].map(
    lambda x: f"{x:,}"
)


# --------------------------------------------------
# 14. 순위 변동 글자 색 지정
# --------------------------------------------------
# 양수 : 빨간색 위 화살표
# 음수 : 파란색 아래 화살표
#
# pandas Styler를 이용하면
# Streamlit 표에서도 글자색을 적용할 수 있습니다.
def rank_change_color(value):

    if str(value).startswith("↑"):

        return (
            "color: #e53935; "
            "font-weight: bold;"
        )

    elif str(value).startswith("↓"):

        return (
            "color: #1976d2; "
            "font-weight: bold;"
        )

    return "color: #888888;"


styled_table = (
    table_df
    .style
    .map(
        rank_change_color,
        subset=["순위 변동"]
    )
)


st.dataframe(
    styled_table,
    use_container_width=True,
    hide_index=True,
    height=420
)


# --------------------------------------------------
# 15. 표 읽는 방법
# --------------------------------------------------
st.caption(
    "🔴 ↑ 순위 상승 · "
    "🔵 ↓ 순위 하락 · "
    "🏆 누적관객 100만 명 이상"
)


# --------------------------------------------------
# 16. 데이터 출처
# --------------------------------------------------
st.caption(
    f"조회 기준일: {display_date} · "
    "자료 출처: 영화진흥위원회 KOBIS 영화관입장권통합전산망"
)
