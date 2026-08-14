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
st.caption("Build v0.1 — 로그인 화면 + 대시보드 뼈대만 있는 스켈레톤 버전")
