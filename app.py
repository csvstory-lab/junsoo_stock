import streamlit as st

st.set_page_config(
    page_title="나의 주식 정보 대시보드",
    page_icon="📈",
    layout="wide",
)


def check_password() -> bool:
    """비밀번호를 맞게 입력해야 True를 반환. 로그인창 역할을 하는 함수."""

    def password_entered():
        if st.session_state.get("password") == st.secrets["APP_PASSWORD"]:
            st.session_state["password_correct"] = True
            del st.session_state["password"]
        else:
            st.session_state["password_correct"] = False

    # 아직 로그인 시도 전
    if "password_correct" not in st.session_state:
        st.markdown("## 🔒 로그인")
        st.text_input(
            "비밀번호를 입력하세요",
            type="password",
            on_change=password_entered,
            key="password",
        )
        return False

    # 로그인 실패
    elif not st.session_state["password_correct"]:
        st.markdown("## 🔒 로그인")
        st.text_input(
            "비밀번호를 입력하세요",
            type="password",
            on_change=password_entered,
            key="password",
        )
        st.error("비밀번호가 틀렸습니다. 다시 시도해주세요.")
        return False

    # 로그인 성공
    else:
        return True


# ---------------------------------------------------------
# 로그인 게이트: 통과 못하면 여기서 화면이 멈춤
# ---------------------------------------------------------
if not check_password():
    st.stop()


# ---------------------------------------------------------
# 로그인 성공 후에만 보이는 실제 대시보드 화면
# ---------------------------------------------------------
st.title("📈 나의 주식 정보 대시보드")
st.caption("개인용 · 나만 볼 수 있는 페이지입니다")

with st.sidebar:
    st.subheader("메뉴")
    st.page_link if False else None  # (추후 멀티페이지 확장 시 사용)
    if st.button("로그아웃"):
        st.session_state["password_correct"] = False
        st.rerun()

col1, col2 = st.columns(2)

with col1:
    st.subheader("🏛 오늘의 가치투자 후보 (자리표시)")
    st.info(
        "여기에 DART 공시 + GP/A·F-Score·PBR 재무필터 결과가 표시될 예정입니다.\n\n"
        "다음 단계에서 DART OpenAPI 연동 모듈을 이 자리에 붙입니다."
    )

with col2:
    st.subheader("⚡ 오늘의 단기 후보 (자리표시)")
    st.info(
        "여기에 수급/모멘텀 + 뉴스 영향력 지수 결과가 표시될 예정입니다.\n\n"
        "다음 단계에서 GDELT/네이버 뉴스 연동 모듈을 이 자리에 붙입니다."
    )

st.divider()

# ---------------------------------------------------------
# 국내 공시(DART) 모듈 — v0.2에서 새로 추가된 실제 동작 기능
# ---------------------------------------------------------
import pandas as pd
from datetime import datetime, timedelta

try:
    from opendartreader import OpenDartReader  # 최신 버전 (패키지명이 소문자로 변경됨)
except ImportError:
    import OpenDartReader  # 예전 버전 호환용

st.header("🏛 관심종목 최근 공시")
st.caption("DART 전자공시시스템에서 최근 14일간 공시를 가져와 유형별로 1차 점수를 매깁니다")


@st.cache_resource
def get_dart_client():
    return OpenDartReader(st.secrets["DART_API_KEY"])


# 공시 유형별 사전 가중치 (지난 가이드 3-1 표와 동일한 개념)
WEIGHT_TABLE = {
    "자기주식취득": 0.6,
    "자기주식처분": -0.3,
    "무상증자": 0.5,
    "유상증자": -0.4,
    "횡령": -0.9,
    "배임": -0.9,
    "소송": -0.5,
    "최대주주": 0.0,
    "주식매수선택권": 0.1,
    "감자": -0.6,
}


def score_report(report_name: str):
    for keyword, weight in WEIGHT_TABLE.items():
        if keyword in report_name:
            return weight, keyword
    return 0.0, None


@st.cache_data(ttl=1800, show_spinner=False)
def fetch_disclosures(names: tuple, start_date: str):
    dart = get_dart_client()
    rows = []
    for name in names:
        try:
            df = dart.list(name, start=start_date)
        except Exception as e:
            rows.append({"종목": name, "공시일": "-", "제목": f"조회 실패: {e}", "감지 키워드": "-", "영향력 점수": None})
            continue
        if df is None or len(df) == 0:
            continue
        for _, r in df.iterrows():
            weight, keyword = score_report(r["report_nm"])
            rows.append(
                {
                    "종목": name,
                    "공시일": r["rcept_dt"],
                    "제목": r["report_nm"],
                    "감지 키워드": keyword or "-",
                    "영향력 점수": weight,
                }
            )
    return rows


watchlist_input = st.text_input(
    "관심 종목 (쉼표로 구분)", value="삼성전자, 카카오", key="watchlist"
)
tickers = tuple(t.strip() for t in watchlist_input.split(",") if t.strip())

if st.button("공시 불러오기"):
    if "DART_API_KEY" not in st.secrets:
        st.error("DART_API_KEY가 아직 Secrets에 등록되지 않았습니다. Settings → Secrets에서 추가해주세요.")
    else:
        start = (datetime.today() - timedelta(days=14)).strftime("%Y-%m-%d")
        with st.spinner("DART에서 공시 가져오는 중..."):
            rows = fetch_disclosures(tickers, start)
        if rows:
            result_df = pd.DataFrame(rows).sort_values("영향력 점수", na_position="last")
            st.dataframe(result_df, use_container_width=True, hide_index=True)
        else:
            st.info("최근 14일간 공시가 없습니다.")

st.divider()
st.caption("Build v0.2 — 로그인 화면 + DART 공시 모듈 (규칙 기반 1차 스코어링)")

# ---------------------------------------------------------
# 재무 필터 (GP/A) 모듈 — v0.3에서 새로 추가
# ---------------------------------------------------------
st.divider()
st.header("💰 재무 필터 (GP/A)")
st.caption("총자산 대비 매출총이익 비율 — 높을수록 자산 대비 수익창출력이 좋은 '알짜' 기업입니다")


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_gpa(names: tuple, year: int):
    dart = get_dart_client()
    rows = []
    for name in names:
        df = None
        used_fs_div = None
        for fs_div in ("CFS", "OFS"):  # 연결재무제표 먼저 시도, 없으면 별도재무제표
            try:
                candidate = dart.finstate_all(name, year, fs_div=fs_div)
            except Exception:
                candidate = None
            if candidate is not None and len(candidate) > 0:
                df = candidate
                used_fs_div = fs_div
                break

        if df is None or len(df) == 0:
            rows.append({"종목": name, "GP/A": None, "비고": "해당 연도 재무제표 데이터 없음"})
            continue

        try:
            df["account_nm"] = df["account_nm"].astype(str).str.strip()

            def get_amount(account_name):
                matched = df[df["account_nm"] == account_name]["thstrm_amount"].values
                if len(matched) == 0:
                    return None
                return float(str(matched[0]).replace(",", ""))

            total_assets = get_amount("자산총계")
            gross_profit = get_amount("매출총이익")
            if gross_profit is None:
                revenue = get_amount("매출액")
                if revenue is None:
                    revenue = get_amount("수익(매출액)")
                cogs = get_amount("매출원가")
                gross_profit = (revenue - cogs) if (revenue is not None and cogs is not None) else None

            gpa = (gross_profit / total_assets) if (gross_profit is not None and total_assets) else None
            rows.append(
                {
                    "종목": name,
                    "재무제표": "연결" if used_fs_div == "CFS" else "별도",
                    "매출총이익(억원)": round(gross_profit / 1e8, 1) if gross_profit is not None else None,
                    "총자산(억원)": round(total_assets / 1e8, 1) if total_assets else None,
                    "GP/A": round(gpa, 3) if gpa is not None else None,
                    "비고": "-" if gpa is not None else "매출총이익 계정 없음 (성격별 손익계산서 채택 기업일 수 있음)",
                }
            )
        except Exception as e:
            rows.append({"종목": name, "GP/A": None, "비고": f"계산 오류: {e}"})
    return rows


col_a, col_b = st.columns([3, 1])
with col_a:
    gpa_watchlist = st.text_input(
        "GP/A 조회할 종목 (쉼표로 구분)", value="삼성전자, 카카오", key="gpa_watchlist"
    )
with col_b:
    gpa_year = st.number_input("기준 연도", min_value=2015, max_value=2026, value=2025, step=1)

if st.button("GP/A 계산하기"):
    if "DART_API_KEY" not in st.secrets:
        st.error("DART_API_KEY가 아직 Secrets에 등록되지 않았습니다.")
    else:
        gpa_tickers = tuple(t.strip() for t in gpa_watchlist.split(",") if t.strip())
        with st.spinner("재무제표 조회 중..."):
            gpa_rows = fetch_gpa(gpa_tickers, int(gpa_year))
        gpa_df = pd.DataFrame(gpa_rows).sort_values("GP/A", ascending=False, na_position="last")
        st.dataframe(gpa_df, use_container_width=True, hide_index=True)
        st.caption(
            "GP/A는 대략 0.3 이상이면 수익성이 우수한 편으로 봅니다. 참고용 수치이며 투자 조언이 아닙니다. "
            "일부 종목은 업종별 계정과목 표기 차이로 '데이터 없음'이 나올 수 있어요."
        )

st.divider()
st.caption("Build v0.3 — 로그인 + DART 공시 모듈 + GP/A 재무 필터")
