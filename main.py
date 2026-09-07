import streamlit as st
import pandas as pd
import requests
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo


# ---------------------------------------------------------
# 1. Streamlit 페이지 기본 설정
# ---------------------------------------------------------
st.set_page_config(
    page_title="어제의 박스오피스",
    page_icon="🎬",
    layout="wide"
)

st.title("🎬 어제의 박스오피스")
st.caption("KOBIS 영화관입장권통합전산망 일별 박스오피스")


# ---------------------------------------------------------
# 2. 한국 시간 기준으로 '어제' 날짜 계산
# ---------------------------------------------------------
# Streamlit Cloud 서버는 한국 시간이 아닐 수 있으므로
# 반드시 Asia/Seoul 시간대를 직접 지정합니다.
korea_now = datetime.now(ZoneInfo("Asia/Seoul"))
yesterday = korea_now.date() - timedelta(days=1)

# KOBIS API가 요구하는 형식: yyyymmdd
target_date = yesterday.strftime("%Y%m%d")

# 화면에 보여 줄 날짜 형식
display_date = yesterday.strftime("%Y년 %m월 %d일")

st.subheader(f"📅 {display_date} 박스오피스")


# ---------------------------------------------------------
# 3. KOBIS API 호출 함수
# ---------------------------------------------------------
# ttl=3600 → 같은 날짜를 다시 조회할 때
# 약 1시간 동안 기존 결과를 기억하여 API를 다시 호출하지 않습니다.
@st.cache_data(ttl=3600)
def load_boxoffice(target_dt):
    # Streamlit의 비밀값 저장소에서 인증키를 불러옵니다.
    # 코드에 실제 인증키를 직접 적으면 안 됩니다.
    try:
        api_key = st.secrets["KOBIS_KEY"]
    except Exception:
        return None, (
            "KOBIS 인증키를 찾을 수 없습니다.\n\n"
            "Streamlit의 **Secrets**에 다음과 같이 등록했는지 확인해 주세요.\n\n"
            '`KOBIS_KEY = "발급받은_인증키"`'
        )

    url = (
        "https://www.kobis.or.kr/kobisopenapi/webservice/rest/"
        "boxoffice/searchDailyBoxOfficeList.json"
    )

    params = {
        "key": api_key,
        "targetDt": target_dt
    }

    try:
        # 서버가 너무 오래 응답하지 않는 경우를 대비해
        # 최대 10초까지만 기다립니다.
        response = requests.get(
            url,
            params=params,
            timeout=10
        )

        # HTTP 상태코드가 200번대가 아니면 오류 발생
        response.raise_for_status()

        data = response.json()

    except requests.exceptions.Timeout:
        return None, (
            "KOBIS 서버 응답 시간이 너무 오래 걸렸습니다.\n\n"
            "잠시 후 다시 접속해 주세요."
        )

    except requests.exceptions.RequestException as e:
        return None, (
            "KOBIS API 요청에 실패했습니다.\n\n"
            "인터넷 연결 상태 또는 KOBIS 서버 상태를 확인해 주세요.\n\n"
            f"오류 내용: {e}"
        )

    except ValueError:
        return None, (
            "KOBIS 서버에서 정상적인 JSON 데이터를 받지 못했습니다.\n\n"
            "잠시 후 다시 시도해 주세요."
        )


    # -----------------------------------------------------
    # 4. KOBIS의 faultInfo 확인
    # -----------------------------------------------------
    # KOBIS는 인증키가 잘못되어도 HTTP 200을 반환할 수 있습니다.
    # 이 경우 응답 안에 faultInfo가 들어옵니다.
    if "faultInfo" in data:
        fault_info = data["faultInfo"]

        message = fault_info.get(
            "message",
            "KOBIS에서 오류 정보를 반환했습니다."
        )

        return None, (
            "KOBIS API에서 오류가 발생했습니다.\n\n"
            f"**오류 메시지:** {message}\n\n"
            "다음 내용을 확인해 주세요.\n\n"
            "- Streamlit Secrets의 `KOBIS_KEY`가 올바른지\n"
            "- KOBIS에서 발급받은 인증키가 정상적으로 사용 가능한지\n"
            "- 인증키 앞뒤에 불필요한 공백이 들어가 있지 않은지"
        )


    # -----------------------------------------------------
    # 5. 영화 목록 가져오기
    # -----------------------------------------------------
    try:
        movie_list = data["boxOfficeResult"]["dailyBoxOfficeList"]
    except (KeyError, TypeError):
        return None, (
            "KOBIS 응답에서 박스오피스 목록을 찾을 수 없습니다.\n\n"
            "KOBIS 서버의 응답 구조가 정상인지 확인해 주세요."
        )


    # 영화 목록이 빈 경우
    if not movie_list:
        return None, (
            f"{target_dt} 날짜의 박스오피스 데이터가 없습니다.\n\n"
            "다음 내용을 확인해 주세요.\n\n"
            "- 조회 날짜의 집계가 아직 완료되지 않았는지\n"
            "- KOBIS 서비스가 정상 운영 중인지\n"
            "- 인증키가 정상인지"
        )


    # -----------------------------------------------------
    # 6. DataFrame으로 변환
    # -----------------------------------------------------
    df = pd.DataFrame(movie_list)


    # 필요한 열만 선택
    required_columns = [
        "rank",
        "movieNm",
        "openDt",
        "audiCnt",
        "audiAcc",
        "scrnCnt"
    ]

    # 혹시 응답에 필요한 열이 빠진 경우 확인
    missing_columns = [
        col for col in required_columns
        if col not in df.columns
    ]

    if missing_columns:
        return None, (
            "KOBIS 응답에 필요한 데이터가 일부 없습니다.\n\n"
            f"누락된 항목: {', '.join(missing_columns)}"
        )

    df = df[required_columns].copy()


    # -----------------------------------------------------
    # 7. 문자열로 온 숫자를 실제 숫자로 변환
    # -----------------------------------------------------
    number_columns = [
        "rank",
        "audiCnt",
        "audiAcc",
        "scrnCnt"
    ]

    for col in number_columns:
        df[col] = pd.to_numeric(
            df[col],
            errors="coerce"
        )

    # 숫자 변환에 실패한 행은 제거
    df = df.dropna(
        subset=["rank", "audiCnt", "audiAcc", "scrnCnt"]
    )

    if df.empty:
        return None, (
            "박스오피스 숫자 데이터를 정상적으로 변환하지 못했습니다.\n\n"
            "KOBIS 응답 데이터를 확인해 주세요."
        )


    # 정수형으로 변환
    for col in number_columns:
        df[col] = df[col].astype(int)


    # 순위 기준 정렬
    df = df.sort_values("rank").reset_index(drop=True)

    return df, None


# ---------------------------------------------------------
# 8. API 데이터 불러오기
# ---------------------------------------------------------
df, error_message = load_boxoffice(target_date)


# ---------------------------------------------------------
# 9. 오류가 발생한 경우 안내
# ---------------------------------------------------------
if error_message:
    st.error(error_message)
    st.stop()


# ---------------------------------------------------------
# 10. 1위 영화 표시
# ---------------------------------------------------------
first_movie = df.iloc[0]

st.markdown("### 🏆 박스오피스 1위")

st.markdown(
    f"## 🎞️ {first_movie['movieNm']}"
)

# 지표 카드 3개를 가로로 배치
col1, col2, col3 = st.columns(3)

with col1:
    st.metric(
        label="👥 어제 관객수",
        value=f"{first_movie['audiCnt']:,}명"
    )

with col2:
    st.metric(
        label="🎟️ 누적 관객수",
        value=f"{first_movie['audiAcc']:,}명"
    )

with col3:
    st.metric(
        label="🖥️ 스크린수",
        value=f"{first_movie['scrnCnt']:,}개"
    )


st.divider()


# ---------------------------------------------------------
# 11. 관객수 상위 5편 막대그래프
# ---------------------------------------------------------
st.markdown("### 📊 관객수 상위 5편")

# 관객수를 기준으로 큰 순서대로 정렬
top5 = (
    df.sort_values(
        "audiCnt",
        ascending=False
    )
    .head(5)
    [["movieNm", "audiCnt"]]
    .set_index("movieNm")
)

# Streamlit 기본 막대그래프
st.bar_chart(
    top5,
    y="audiCnt"
)


st.divider()


# ---------------------------------------------------------
# 12. 전체 박스오피스 표
# ---------------------------------------------------------
st.markdown("### 📋 일별 박스오피스 순위")

# 화면에 표시하기 좋은 한글 이름으로 변경
display_df = df.rename(
    columns={
        "rank": "순위",
        "movieNm": "영화명",
        "openDt": "개봉일",
        "audiCnt": "관객수",
        "audiAcc": "누적관객",
        "scrnCnt": "스크린수"
    }
)

# 숫자를 1,234 형식으로 표시하면서
# 내부 데이터는 숫자형으로 유지합니다.
st.dataframe(
    display_df,
    use_container_width=True,
    hide_index=True,
    column_config={
        "순위": st.column_config.NumberColumn(
            "순위",
            format="%d위"
        ),
        "영화명": st.column_config.TextColumn(
            "영화명"
        ),
        "개봉일": st.column_config.TextColumn(
            "개봉일"
        ),
        "관객수": st.column_config.NumberColumn(
            "관객수",
            format="localized"
        ),
        "누적관객": st.column_config.NumberColumn(
            "누적관객",
            format="localized"
        ),
        "스크린수": st.column_config.NumberColumn(
            "스크린수",
            format="localized"
        )
    }
)


# ---------------------------------------------------------
# 13. 하단 안내
# ---------------------------------------------------------
st.caption(
    "※ 데이터 출처: 영화진흥위원회 KOBIS 영화관입장권통합전산망"
)
