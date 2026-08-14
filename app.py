import streamlit as st
import json
import base64
import pandas as pd
import requests
import FinanceDataReader as fdr
from datetime import datetime, timedelta

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

# ---------------------------------------------------------
# 매크로 시장 날씨 — v0.6에서 새로 추가 (원본 설계 3-① 매크로 가중치 매트릭스)
# ---------------------------------------------------------
st.subheader("🌤️ 오늘의 시장 날씨")


@st.cache_data(ttl=3600, show_spinner=False)
def get_macro_snapshot():
    result = {}
    start = (datetime.today() - timedelta(days=10)).strftime("%Y-%m-%d")
    for key, symbol in [("환율", "USD/KRW"), ("미국채10년물", "US10YT"), ("VIX", "VIX")]:
        try:
            df = fdr.DataReader(symbol, start)
            if df is not None and len(df) >= 2:
                latest = float(df["Close"].iloc[-1])
                prev = float(df["Close"].iloc[-2])
                result[key] = {
                    "value": latest,
                    "change_pct": (latest - prev) / prev * 100,
                    "date": str(df.index[-1].date()),
                }
            elif df is not None and len(df) == 1:
                result[key] = {"value": float(df["Close"].iloc[-1]), "change_pct": None, "date": str(df.index[-1].date())}
            else:
                result[key] = {"value": None, "change_pct": None, "date": None}
        except Exception:
            result[key] = {"value": None, "change_pct": None, "date": None}
    return result


macro = get_macro_snapshot()

mcol1, mcol2, mcol3, mcol4 = st.columns(4)

with mcol1:
    d = macro.get("환율", {})
    if d.get("value") is not None:
        st.metric("💵 원/달러 환율", f"{d['value']:,.1f}원",
                   f"{d['change_pct']:+.2f}%" if d.get("change_pct") is not None else None)
    else:
        st.metric("💵 원/달러 환율", "조회 실패")

with mcol2:
    d = macro.get("미국채10년물", {})
    if d.get("value") is not None:
        st.metric("🏦 美 국채 10년물", f"{d['value']:.2f}%",
                   f"{d['change_pct']:+.2f}%" if d.get("change_pct") is not None else None)
    else:
        st.metric("🏦 美 국채 10년물", "조회 실패")

with mcol3:
    d = macro.get("VIX", {})
    if d.get("value") is not None:
        st.metric("😨 VIX 공포지수", f"{d['value']:.1f}",
                   f"{d['change_pct']:+.2f}%" if d.get("change_pct") is not None else None)
    else:
        st.metric("😨 VIX 공포지수", "조회 실패")

with mcol4:
    vix_val = macro.get("VIX", {}).get("value")
    if vix_val is not None:
        if vix_val >= 30:
            risk_label = "🔴 위험"
        elif vix_val >= 20:
            risk_label = "🟡 주의"
        else:
            risk_label = "🟢 안정"
        st.metric("🚦 종합 시장 심리", risk_label)
    else:
        st.metric("🚦 종합 시장 심리", "N/A")

if vix_val is not None and vix_val >= 30:
    st.warning("VIX가 30을 넘었습니다 — 시장 변동성이 큰 구간입니다. 단기 매매 진입은 더 신중하게 판단하세요.")

st.caption("환율·금리·VIX는 1시간마다 갱신됩니다 (Yahoo Finance 기준). 참고용 정보이며 투자 조언이 아닙니다.")

col1, col2 = st.columns(2)

with col1:
    st.subheader("🏛 오늘의 가치투자 후보 (GP/A + PBR)")
    try:
        with open("data/gpa_ranking.json", "r", encoding="utf-8") as f:
            gpa_data = json.load(f)
        filter_note = gpa_data.get("filter_note", "")
        st.caption(
            f"업데이트: {gpa_data['updated_at']} · {gpa_data['scan_year']}년 재무제표 기준 · "
            f"{gpa_data['total_success']}/{gpa_data['total_scanned']}개 종목 계산 성공"
            + (f" · 선정 기준: {filter_note}" if filter_note else "")
        )
        if not gpa_data.get("complete", True):
            st.warning("이 결과는 스캔이 끝까지 완료되지 않은 중간 저장본입니다. 다음 자동 실행 때 갱신됩니다.")
        rank_df = pd.DataFrame(gpa_data["ranking"])
        st.dataframe(rank_df, use_container_width=True, hide_index=True, height=400)
        st.caption(
            "GP/A 상위권(수익성 좋은 기업) 중에서 PBR이 낮은(싸게 거래되는) 순으로 뽑은 결과입니다. "
            "참고용 수치이며 투자 조언이 아닙니다. F-Score 필터는 다음 단계에서 추가 예정입니다."
        )
    except FileNotFoundError:
        st.info(
            "아직 자동 스캔 결과가 없습니다. GitHub Actions에서 'daily_scan' 워크플로를 "
            "한 번 수동 실행하면 이 자리에 순위표가 나타납니다."
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
try:
    from opendartreader import OpenDartReader  # 최신 버전 (패키지명이 소문자로 변경됨)
except ImportError:
    import OpenDartReader  # 예전 버전 호환용

st.header("🏛 관심종목 최근 공시")
st.caption("DART 전자공시시스템에서 최근 14일간 공시를 가져와 유형별로 1차 점수를 매깁니다")


@st.cache_resource
def get_dart_client():
    return OpenDartReader(st.secrets["DART_API_KEY"])


def resolve_corp_code(dart, corp: str):
    """6자리 종목코드 또는 회사명(정확/부분 일치)으로 DART 고유번호를 찾는다.
    반환값: (corp_code, 매칭된 정식 회사명) 또는 못 찾으면 (None, None)"""
    corp = str(corp).strip()
    codes = dart.corp_codes.copy()
    codes["stock_code"] = codes["stock_code"].astype(str).str.strip()
    codes["corp_name"] = codes["corp_name"].astype(str).str.strip()

    if corp.isdigit() and len(corp) == 6:
        matched = codes[codes["stock_code"] == corp]
    else:
        matched = codes[codes["corp_name"] == corp]  # 1) 정확히 일치
        if matched.empty:
            matched = codes[codes["corp_name"].str.contains(corp, na=False, regex=False)]  # 2) 부분 일치
            listed = matched[matched["stock_code"].notna() & (matched["stock_code"] != "")]
            if len(listed) > 0:
                matched = listed  # 상장기업 우선

    if matched.empty:
        return None, None
    row = matched.iloc[0]
    return row["corp_code"], row["corp_name"]


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
        corp_code, resolved_name = resolve_corp_code(dart, name)
        if not corp_code:
            rows.append({"종목": name, "공시일": "-", "제목": "종목을 찾을 수 없음 (이름 또는 종목코드 확인)", "감지 키워드": "-", "영향력 점수": None})
            continue
        try:
            df = dart.list(corp_code, start=start_date)
        except Exception as e:
            rows.append({"종목": resolved_name, "공시일": "-", "제목": f"조회 실패: {e}", "감지 키워드": "-", "영향력 점수": None})
            continue
        if df is None or len(df) == 0:
            continue
        for _, r in df.iterrows():
            weight, keyword = score_report(r["report_nm"])
            rows.append(
                {
                    "종목": resolved_name,
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
st.header("💰 개별 종목 GP/A 직접 조회 (수동)")
st.caption("특정 종목만 빠르게 확인하고 싶을 때 사용하세요. 위쪽 자동 랭킹과 별개로 그 자리에서 바로 계산합니다.")


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_gpa(names: tuple, year: int):
    dart = get_dart_client()
    rows = []
    for name in names:
        corp_code, resolved_name = resolve_corp_code(dart, name)
        if not corp_code:
            rows.append({"종목": name, "GP/A": None, "비고": "종목을 찾을 수 없음 (이름 또는 종목코드 확인)"})
            continue

        df = None
        used_fs_div = None
        last_error = None
        for fs_div in ("CFS", "OFS"):  # 연결재무제표 먼저 시도, 없으면 별도재무제표
            try:
                candidate = dart.finstate_all(corp_code, year, fs_div=fs_div)
            except Exception as e:
                last_error = str(e)
                candidate = None
            if candidate is not None and len(candidate) > 0:
                df = candidate
                used_fs_div = fs_div
                break

        if df is None or len(df) == 0:
            note = f"조회 실패: {last_error}" if last_error else "해당 연도 재무제표 데이터 없음"
            rows.append({"종목": resolved_name, "GP/A": None, "비고": note})
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
                    "종목": resolved_name,
                    "재무제표": "연결" if used_fs_div == "CFS" else "별도",
                    "매출총이익(억원)": round(gross_profit / 1e8, 1) if gross_profit is not None else None,
                    "총자산(억원)": round(total_assets / 1e8, 1) if total_assets else None,
                    "GP/A": round(gpa, 3) if gpa is not None else None,
                    "비고": "-" if gpa is not None else "매출총이익 계정 없음 (성격별 손익계산서 채택 기업일 수 있음)",
                }
            )
        except Exception as e:
            rows.append({"종목": resolved_name, "GP/A": None, "비고": f"계산 오류: {e}"})
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
st.caption("Build v0.4 — 로그인 + 매일 자동 GP/A 전체 스캔 + 공시 모듈 + 개별 종목 수동 조회")

# ---------------------------------------------------------
# 리스크 관리 (MDD Guard) 모듈 — v0.5에서 새로 추가
# 보유 종목을 GitHub 저장소(data/holdings.json)에 저장해서 재접속해도 유지되게 합니다.
# ---------------------------------------------------------
st.divider()
st.header("🚨 내 보유 종목 리스크 관리")
st.caption("매수 단가 대비 낙폭이 기준을 넘으면 경고를 표시합니다 (단기 -3% / 장기 -15%)")

GITHUB_REPO = st.secrets.get("GITHUB_REPO", "")
HOLDINGS_PATH = "data/holdings.json"


def github_headers():
    return {
        "Authorization": f"token {st.secrets['GH_PAT']}",
        "Accept": "application/vnd.github+json",
    }


def load_holdings():
    """raw.githubusercontent.com은 몇 분간 캐시가 걸려 방금 저장한 내용이 바로 안 보일 수 있어서,
    캐시가 덜 걸리는 GitHub API(api.github.com)로 직접 읽어옵니다."""
    api_url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{HOLDINGS_PATH}"
    try:
        r = requests.get(api_url, headers=github_headers(), timeout=10)
        if r.status_code == 200:
            content_b64 = r.json()["content"]
            content_str = base64.b64decode(content_b64).decode("utf-8")
            return json.loads(content_str)
    except Exception:
        pass
    return []


def save_holdings(holdings):
    api_url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{HOLDINGS_PATH}"
    sha = None
    try:
        r = requests.get(api_url, headers=github_headers(), timeout=10)
        if r.status_code == 200:
            sha = r.json().get("sha")
    except Exception:
        pass

    content_str = json.dumps(holdings, ensure_ascii=False, indent=2)
    content_b64 = base64.b64encode(content_str.encode("utf-8")).decode("utf-8")
    payload = {"message": "보유 종목 업데이트", "content": content_b64, "branch": "main"}
    if sha:
        payload["sha"] = sha

    try:
        resp = requests.put(api_url, headers=github_headers(), json=payload, timeout=10)
        return resp.status_code in (200, 201)
    except Exception:
        return False


if "GH_PAT" not in st.secrets or not GITHUB_REPO:
    st.info(
        "보유 종목을 저장하려면 GH_PAT(GitHub 개인 액세스 토큰)와 GITHUB_REPO를 "
        "Secrets에 등록해야 합니다. 등록 방법은 안내를 참고해주세요."
    )
else:
    # 세션 안에서는 GitHub을 다시 읽지 않고 이미 가진 목록을 그대로 씁니다.
    # (저장 직후 바로 다시 읽으면 캐시 때문에 방금 추가한 게 안 보일 수 있어서)
    if "holdings" not in st.session_state:
        st.session_state["holdings"] = load_holdings()
    holdings = st.session_state["holdings"]

    @st.cache_resource
    def get_krx_listing():
        return fdr.StockListing("KRX")

    with st.expander("➕ 보유 종목 추가"):
        with st.form("add_holding"):
            h_code = st.text_input("종목코드 (6자리)")
            h_qty = st.number_input("매수 수량(주)", min_value=0, step=1, value=0)
            h_price = st.number_input("매수 단가(원)", min_value=0, step=100)
            h_type = st.radio("매매 유형", ["장기", "단기"], horizontal=True)
            submitted = st.form_submit_button("추가")
            if submitted:
                if h_code.strip() and h_price > 0:
                    code_clean = h_code.strip().zfill(6)
                    resolved_name = code_clean
                    try:
                        listing = get_krx_listing()
                        matched = listing[listing["Code"].astype(str).str.zfill(6) == code_clean]
                        if len(matched) > 0:
                            resolved_name = matched.iloc[0]["Name"]
                    except Exception:
                        pass
                    holdings.append(
                        {
                            "종목코드": code_clean,
                            "종목명": resolved_name,
                            "매수수량": int(h_qty),
                            "매수단가": h_price,
                            "유형": h_type,
                        }
                    )
                    if save_holdings(holdings):
                        st.success(f"{resolved_name} 추가되었습니다.")
                        st.rerun()
                    else:
                        st.error("저장에 실패했습니다. GH_PAT 권한 설정을 확인해주세요.")
                else:
                    st.warning("종목코드와 매수 단가를 입력해주세요.")

    if holdings:
        @st.cache_data(ttl=300, show_spinner=False)
        def get_current_price(code: str):
            """반환값: (현재가, 그 가격의 기준일자) — 며칠자 가격인지 화면에 그대로 보여줘서
            캐시나 데이터 지연으로 인한 혼동을 막습니다."""
            try:
                recent_start = (datetime.today() - timedelta(days=10)).strftime("%Y-%m-%d")
                df = fdr.DataReader(code, recent_start)
                if df is not None and len(df) > 0:
                    price = float(df["Close"].iloc[-1])
                    price_date = str(df.index[-1].date())
                    return price, price_date
            except Exception:
                pass
            return None, None

        if st.button("🔄 현재가 새로고침"):
            get_current_price.clear()

        rows = []
        for h in holdings:
            cur, price_date = get_current_price(h["종목코드"])
            qty = h.get("매수수량", 0)
            display_name = h.get("종목명", h["종목코드"])
            if cur is None:
                rows.append(
                    {"종목명": display_name, "종목코드": h["종목코드"], "현재가": None, "기준일": None,
                     "수익률(%)": None, "평가손익(원)": None, "상태": "가격 조회 실패"}
                )
                continue
            change_pct = (cur - h["매수단가"]) / h["매수단가"] * 100
            profit = (cur - h["매수단가"]) * qty if qty else None
            threshold = -3 if h["유형"] == "단기" else -15
            if change_pct <= threshold:
                status = "🔴 손절 검토"
            elif change_pct <= threshold / 2:
                status = "🟡 주의"
            else:
                status = "🟢 정상"
            rows.append(
                {
                    "종목명": display_name,
                    "종목코드": h["종목코드"],
                    "매수수량": qty,
                    "매수단가": h["매수단가"],
                    "현재가": cur,
                    "기준일": price_date,
                    "수익률(%)": round(change_pct, 1),
                    "평가손익(원)": round(profit) if profit is not None else None,
                    "상태": status,
                }
            )

        holdings_df = pd.DataFrame(rows)
        st.dataframe(holdings_df, use_container_width=True, hide_index=True)

        del_options = [
            f"{h.get('종목명', h['종목코드'])} ({h['종목코드']}, 매수단가 {h['매수단가']:,}원)" for h in holdings
        ]
        to_delete = st.selectbox("삭제할 종목 선택", ["선택 안 함"] + del_options)
        if st.button("선택한 종목 삭제") and to_delete != "선택 안 함":
            idx = del_options.index(to_delete)
            holdings.pop(idx)
            if save_holdings(holdings):
                st.success("삭제되었습니다.")
                st.rerun()

        st.caption(
            "🔴 손절 검토 = 기준 낙폭 초과 · 🟡 주의 = 기준의 절반 이상 하락 · "
            "현재가는 KRX 정규장(09:00~15:30) 종가 기준이며, 넥스트레이드(NXT) 연장거래(~20:00) 가격과는 다를 수 있습니다. "
            "'기준일'이 오늘 날짜가 아니면 아직 최신 시세가 반영되기 전일 수 있습니다. "
            "이 표는 참고용이며 투자 조언이 아닙니다."
        )
    else:
        st.info("아직 등록된 보유 종목이 없습니다. 위에서 추가해보세요.")

st.divider()

# ---------------------------------------------------------
# 뉴스 감성 분석 모듈 — v0.7에서 새로 추가
# 네이버 뉴스(NAVER API HUB) + Groq(무료 LLM)로 호재/악재를 -1.0~+1.0로 판단합니다.
# ---------------------------------------------------------
import re

st.header("📰 뉴스 감성 분석")
st.caption("네이버 뉴스에서 최근 기사를 가져와 AI(Groq)로 호재/악재를 판단합니다 (-1.0 ~ +1.0)")

NAVER_NEWS_URL = "https://naverapihub.apigw.ntruss.com/search/v1/news"
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"


def naver_headers():
    return {
        "X-NCP-APIGW-API-KEY-ID": st.secrets["NAVER_CLIENT_ID"],
        "X-NCP-APIGW-API-KEY": st.secrets["NAVER_CLIENT_SECRET"],
    }


@st.cache_data(ttl=1800, show_spinner=False)
def fetch_news(query: str, display: int = 5):
    try:
        params = {"query": query, "display": display, "sort": "date"}
        r = requests.get(NAVER_NEWS_URL, headers=naver_headers(), params=params, timeout=10)
        if r.status_code != 200:
            return []
        items = r.json().get("items", [])
        cleaned = []
        for it in items:
            title = re.sub(r"</?b>", "", it.get("title", ""))
            desc = re.sub(r"</?b>", "", it.get("description", ""))
            cleaned.append({"title": title, "description": desc, "pubDate": it.get("pubDate", "")})
        return cleaned
    except Exception:
        return []


def score_news_with_groq(stock_name: str, headlines: list):
    if not headlines:
        return None
    joined = "\n".join(f"- {h['title']}" for h in headlines)
    prompt = (
        f"다음은 '{stock_name}' 관련 최근 뉴스 제목들이다.\n\n{joined}\n\n"
        f"이 뉴스들이 종합적으로 '{stock_name}' 주가에 미칠 영향을 "
        f"-1.0(매우 부정적)부터 +1.0(매우 긍정적) 사이의 숫자 하나로 평가해라. "
        f"단순 일상 뉴스면 0에 가깝게 평가해라.\n\n"
        f"반드시 아래 형식으로만 답하고 다른 말은 하지 마라:\n"
        f"점수: [숫자]\n이유: [한 문장]"
    )
    try:
        headers = {"Authorization": f"Bearer {st.secrets['GROQ_API_KEY']}", "Content-Type": "application/json"}
        payload = {
            "model": "llama-3.3-70b-versatile",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.2,
        }
        r = requests.post(GROQ_URL, headers=headers, json=payload, timeout=20)
        if r.status_code == 200:
            return r.json()["choices"][0]["message"]["content"]
        return f"조회 실패 (상태코드 {r.status_code})"
    except Exception as e:
        return f"오류: {e}"


def parse_score(text: str):
    if not text:
        return None, None
    m = re.search(r"점수\s*[:：]\s*([+-]?\d*\.?\d+)", text)
    score = float(m.group(1)) if m else None
    m2 = re.search(r"이유\s*[:：]\s*(.+)", text)
    reason = m2.group(1).strip() if m2 else text.strip()
    return score, reason


required_secrets = ["NAVER_CLIENT_ID", "NAVER_CLIENT_SECRET", "GROQ_API_KEY"]
missing = [s for s in required_secrets if s not in st.secrets]

if missing:
    st.info(f"뉴스 감성 분석을 쓰려면 Secrets에 {', '.join(missing)} 등록이 필요합니다.")
else:
    news_watchlist = st.text_input(
        "뉴스 분석할 종목 (쉼표로 구분)", value="삼성전자, 카카오", key="news_watchlist"
    )

    if st.button("뉴스 감성 분석 실행"):
        names = [n.strip() for n in news_watchlist.split(",") if n.strip()]
        rows = []
        for name in names:
            with st.spinner(f"{name} 뉴스 분석 중..."):
                news_items = fetch_news(name, display=5)
                if not news_items:
                    rows.append({"종목": name, "점수": None, "이유": "관련 뉴스를 찾지 못했습니다", "최근 기사": "-"})
                    continue
                llm_result = score_news_with_groq(name, news_items)
                score, reason = parse_score(llm_result)
                rows.append(
                    {"종목": name, "점수": score, "이유": reason, "최근 기사": news_items[0]["title"]}
                )

        news_df = pd.DataFrame(rows)
        st.table(news_df.set_index("종목"))

        for r in rows:
            if r["점수"] is not None and r["점수"] <= -0.7:
                st.error(f"🚨 {r['종목']}: 강한 악재 감지 (점수 {r['점수']}) — {r['이유']}")

        st.caption(
            "AI가 뉴스 제목만 보고 판단한 참고용 점수이며, 오탐(잘못 판단)이 있을 수 있습니다. "
            "투자 조언이 아니며, 중요한 판단 전엔 반드시 원문 기사를 직접 확인하세요."
        )

st.divider()
st.caption("Build v0.7 — 로그인 + 매크로 날씨 + 매일 자동 GP/A·PBR 스캔 + 공시 모듈 + 개별 조회 + 리스크 관리 + 뉴스 감성 분석")
