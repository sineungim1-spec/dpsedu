
from __future__ import annotations

import io
import uuid
from datetime import datetime

import pandas as pd
import streamlit as st
from PIL import Image

try:
    from lan_info import get_lan_ip
except ImportError:
    # lan_info.py가 누락되어도 Dashboard 자체는 실행되도록 fallback
    def get_lan_ip():
        import socket

        sock = None
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            # 실제 데이터 전송 없이 현재 PC의 LAN 인터페이스 주소만 확인
            sock.connect(("8.8.8.8", 80))
            return sock.getsockname()[0]
        except Exception:
            try:
                return socket.gethostbyname(socket.gethostname())
            except Exception:
                return "127.0.0.1"
        finally:
            if sock is not None:
                try:
                    sock.close()
                except Exception:
                    pass

from dashboard_core import (
    extract_bundle_bytes,
    load_bundle_contract,
    stage_image_bytes,
    run_efficientad_inference,
    anomaly_visuals,
    contract_public,
    RUNTIME_ROOT,
    get_workshop_inference_status,
)

st.set_page_config(
    page_title="AI Vision 품질검사 모니터",
    page_icon="◈",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ------------------------------------------------------------
# 강제 Dark UI
# OS/브라우저/Streamlit 설정이 Light여도 동일하게 보이도록 CSS로 재고정
# ------------------------------------------------------------
st.markdown(
    """
<style>
:root{
  --bg:#07101f;
  --bg2:#091426;
  --panel:#0f1b2e;
  --panel2:#13213a;
  --line:#253855;
  --text:#f4f7fb;
  --muted:#93a7c3;
  --blue:#4f8cff;
  --cyan:#39c8e8;
  --green:#35d07f;
  --red:#ff5c67;
  --amber:#f6b94b;
}

html, body, [class*="css"], .stApp{
  background:linear-gradient(180deg,var(--bg) 0%,var(--bg2) 100%) !important;
  color:var(--text) !important;
}
.stApp{
  min-height:100vh;
}
[data-testid="stHeader"]{
  background:#07101f !important;
  border-bottom:1px solid rgba(76,104,145,.18) !important;
}
[data-testid="stToolbar"], [data-testid="stDecoration"]{
  background:transparent !important;
}
[data-testid="stToolbar"] button,
[data-testid="stToolbar"] svg,
[data-testid="stHeader"] button,
[data-testid="stHeader"] svg{
  color:#dbe8fb !important;
  fill:#dbe8fb !important;
}
[data-testid="stSidebar"]{
  background:#081321 !important;
  border-right:1px solid var(--line) !important;
}
[data-testid="stSidebar"] *{
  color:var(--text);
}
[data-testid="stSidebarContent"]{
  padding-top:1.2rem;
}
.block-container{
  max-width:1640px !important;
  padding-top:1.35rem !important;
  padding-bottom:3rem !important;
}
h1,h2,h3,h4,p,span,label,div{
  color:inherit;
}

/* 입력 위젯을 Light mode에서도 어둡게 */
[data-testid="stFileUploader"] section{
  background:#0d192b !important;
  border:1px dashed #3a5276 !important;
  border-radius:12px !important;
}
[data-testid="stFileUploader"] section *{
  color:#dce8f8 !important;
}
[data-testid="stFileUploaderFile"]{
  background:#132039 !important;
  border:1px solid #2d4162 !important;
}
[data-testid="stTextInput"] input,
[data-baseweb="select"] > div,
[data-testid="stSelectbox"] > div > div,
textarea{
  background:#0d192b !important;
  color:#f4f7fb !important;
  border-color:#344966 !important;
}
[data-testid="stTextInput"] input::placeholder{
  color:#778da9 !important;
}
[data-testid="stRadio"] label{
  color:#d8e5f6 !important;
}

/* 버튼 */
.stButton > button,
[data-testid="stBaseButton-primary"],
[data-testid="stBaseButton-secondary"]{
  min-height:3rem !important;
  border-radius:10px !important;
  font-weight:800 !important;
  letter-spacing:-.01em !important;
}
.stButton > button[kind="primary"],
[data-testid="stBaseButton-primary"]{
  color:white !important;
  background:linear-gradient(90deg,#347cf4,#5b91ff) !important;
  border:1px solid #6da0ff !important;
  box-shadow:0 7px 22px rgba(47,117,238,.24) !important;
}
.stButton > button[kind="secondary"],
[data-testid="stBaseButton-secondary"]{
  color:#e5eefc !important;
  background:#132039 !important;
  border:1px solid #344a6d !important;
}
.stButton > button:hover{
  filter:brightness(1.08);
}

/* 탭 */
[data-baseweb="tab-list"]{
  gap:.45rem !important;
  border-bottom:1px solid #233650 !important;
}
[data-baseweb="tab"]{
  color:#9eb1cc !important;
  font-weight:800 !important;
  padding:.85rem 1rem !important;
}
[aria-selected="true"][data-baseweb="tab"]{
  color:#ffffff !important;
  background:#101d31 !important;
  border-radius:9px 9px 0 0 !important;
}
[data-baseweb="tab-highlight"]{
  background:#4f8cff !important;
}

/* Streamlit info/success/error */
[data-testid="stAlert"]{
  background:#0e1b2f !important;
  color:#e6eef9 !important;
  border:1px solid #2d4161 !important;
  border-radius:10px !important;
}
[data-testid="stAlert"] p,
[data-testid="stAlert"] div{
  color:#e6eef9 !important;
}
div[data-testid="stCode"]{
  background:#08111f !important;
  border:1px solid #2b3e5d !important;
}
code, pre{
  color:#e9f1ff !important;
}

/* 기본 metric도 어둡게 */
div[data-testid="stMetric"]{
  background:#0f1b2e !important;
  border:1px solid #283c5a !important;
  border-radius:12px !important;
  padding:.9rem 1rem !important;
}
div[data-testid="stMetric"] label{
  color:#91a6c2 !important;
}
div[data-testid="stMetricValue"]{
  color:#f5f8ff !important;
}

/* 커스텀 */
.hero{
  display:flex;
  align-items:flex-end;
  justify-content:space-between;
  gap:1rem;
  margin-bottom:1.15rem;
  padding:1.15rem 1.25rem;
  background:
    radial-gradient(circle at 85% 15%,rgba(79,140,255,.18),transparent 30%),
    linear-gradient(135deg,#0e1a2d,#0a1425);
  border:1px solid #283d5b;
  border-radius:16px;
  box-shadow:0 12px 32px rgba(0,0,0,.18);
}
.hero-kicker{
  color:#58c8e8 !important;
  font-size:.72rem;
  font-weight:900;
  letter-spacing:.14em;
  text-transform:uppercase;
}
.hero-title{
  color:white !important;
  font-size:1.65rem;
  font-weight:900;
  margin-top:.25rem;
  letter-spacing:-.04em;
}
.hero-sub{
  color:#98abc5 !important;
  font-size:.78rem;
  margin-top:.35rem;
}
.hero-pill{
  color:#cfe0fb !important;
  border:1px solid #395477;
  background:#102039;
  padding:.55rem .8rem;
  border-radius:999px;
  white-space:nowrap;
  font-size:.72rem;
  font-weight:800;
}
.status-row{
  display:grid;
  grid-template-columns:repeat(4,minmax(0,1fr));
  gap:.75rem;
  margin:.25rem 0 1rem;
}
.status-card{
  position:relative;
  overflow:hidden;
  min-height:116px;
  padding:1rem 1.05rem;
  border-radius:13px;
  border:1px solid #2a3e5d;
  background:linear-gradient(180deg,#121f34,#0d192b);
  box-shadow:0 9px 24px rgba(0,0,0,.14);
}
.status-card:after{
  content:"";
  position:absolute;
  inset:auto 0 0;
  height:3px;
  background:#33527c;
}
.status-card.ok-card:after{background:var(--green)}
.status-card.ng-card:after{background:var(--red)}
.status-card.review-card:after{background:var(--amber)}
.status-card.blue-card:after{background:var(--blue)}
.status-card.cyan-card:after{background:var(--cyan)}
.status-label{
  color:#91a6c1 !important;
  font-size:.72rem;
  font-weight:700;
}
.status-value{
  color:white !important;
  font-size:1.72rem;
  line-height:1.1;
  font-weight:900;
  margin-top:.55rem;
}
.status-value.ok{color:#49df8e !important}
.status-value.ng{color:#ff6b74 !important}
.status-value.review{color:#f6b94b !important}
.status-value.blue{color:#7caeff !important}
.status-sub{
  color:#7087a5 !important;
  font-size:.67rem;
  margin-top:.45rem;
}
.vtitle{
  display:flex;
  align-items:center;
  justify-content:space-between;
  color:#dce8f8 !important;
  font-size:.78rem;
  font-weight:900;
  margin:.15rem 0 .45rem;
}
.vtag{
  color:#8fa5c1 !important;
  border:1px solid #354a68;
  background:#0e192a;
  border-radius:6px;
  padding:.13rem .4rem;
  font-size:.57rem;
}
.visual-box{
  background:#07101d;
  border:1px solid #293d5a;
  border-radius:12px;
  padding:.6rem;
}
.edu-note{
  background:#0d1b30;
  border:1px solid #254363;
  border-left:4px solid #4f8cff;
  color:#aebfd4 !important;
  border-radius:9px;
  padding:.75rem .9rem;
  font-size:.77rem;
  line-height:1.55;
  margin:.7rem 0;
}
.section-title{
  color:white !important;
  font-weight:900;
  font-size:1rem;
  letter-spacing:-.025em;
  margin-top:.2rem;
}
.sidebar-brand{
  color:white !important;
  font-weight:900;
  font-size:1.15rem;
}
.sidebar-brand span{
  display:block;
  color:#89a0bd !important;
  font-size:.68rem;
  font-weight:600;
  margin-top:.2rem;
}
.sidebar-help{
  color:#7890ad !important;
  font-size:.66rem;
  line-height:1.5;
}
.bundle-ok{
  background:#0d2a25;
  border:1px solid #215746;
  color:#53df9a !important;
  padding:.7rem .8rem;
  border-radius:9px;
  font-weight:800;
  font-size:.76rem;
}
@media(max-width:1000px){
  .status-row{grid-template-columns:1fr 1fr}
  .hero{align-items:flex-start;flex-direction:column}
}
@media(max-width:650px){
  .status-row{grid-template-columns:1fr}
}

/* v4: prevent Streamlit header from covering the dashboard */
[data-testid="stHeader"],
header[data-testid="stHeader"],
[data-testid="stToolbar"],
[data-testid="stDecoration"],
.stApp > header{
  display:none !important;
  visibility:hidden !important;
  height:0 !important;
  min-height:0 !important;
}
.block-container{
  padding-top:1.25rem !important;
  margin-top:0 !important;
}
.hero{
  margin-top:.2rem !important;
  border-color:#31527a !important;
  box-shadow:0 14px 34px rgba(0,0,0,.22) !important;
}
.hero-title{
  line-height:1.28 !important;
  padding:.12rem 0 !important;
}
.hero-kicker{color:#5fe0ff !important}
.hero-sub{color:#b7cbe4 !important}
.hero-pill{
  background:#10284a !important;
  border-color:#416a98 !important;
  color:#e4efff !important;
}
[data-baseweb="tab"]{
  color:#b2c5dc !important;
  opacity:1 !important;
}
[aria-selected="true"][data-baseweb="tab"]{
  color:#ffffff !important;
}
[data-baseweb="tab-highlight"]{
  background:#4f8cff !important;
  height:3px !important;
}
[data-testid="stFileUploader"] section{
  background:#0b182b !important;
  border:1px dashed #4c6d98 !important;
}
[data-testid="stFileUploader"] button{
  background:#1b2c49 !important;
  color:#ffffff !important;
  border:1px solid #4c6d98 !important;
}
[data-testid="stFileUploaderFile"]{
  background:#101f35 !important;
  color:#f5f8ff !important;
}
[data-testid="stBaseButton-primary"]{
  background:linear-gradient(90deg,#2f78ef,#5f99ff) !important;
  color:#ffffff !important;
  border:1px solid #79aaff !important;
}
[data-testid="stBaseButton-primary"]:hover{
  filter:brightness(1.08) !important;
}
[data-testid="stSidebar"]{
  background:linear-gradient(180deg,#07111f,#091628) !important;
}
[data-testid="stAlert"]{
  color:#eef5ff !important;
  border-color:#365172 !important;
}

</style>
""",
    unsafe_allow_html=True,
)

# ------------------------------------------------------------
# state
# ------------------------------------------------------------
defaults = {
    "bundle_contract": None,
    "bundle_id": None,
    "result": None,
    "logs": [],
    "participant_session_id": uuid.uuid4().hex[:8],
}
for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ------------------------------------------------------------
# sidebar
# ------------------------------------------------------------
with st.sidebar:
    st.markdown(
        '<div class="sidebar-brand">◈ 모델 연결<span>EfficientAD model bundle → 범용 검사시스템</span></div>',
        unsafe_allow_html=True,
    )
    st.write("")
    bundle_file = st.file_uploader(
        "EfficientAD model bundle",
        type=["zip"],
        help="EfficientAD bundle ZIP을 업로드합니다. Legacy 2-ZONE, 3-ZONE 교육용/회사형, Candidate4/PF1 bundle을 자동 판별합니다.",
    )

    if bundle_file is not None:
        try:
            bid, bundle_root = extract_bundle_bytes(bundle_file.getvalue(), "streamlit")
            contract = load_bundle_contract(bundle_root)
            st.session_state.bundle_contract = contract
            st.session_state.bundle_id = bid
            st.markdown('<div class="bundle-ok">✓ bundle 연결 완료</div>', unsafe_allow_html=True)
            if contract.is_three_zone:
                c_low, c_high = st.columns(2)
                c_low.metric("Review Low", f"{contract.review_low:.6f}")
                c_high.metric("NG High", f"{contract.ng_high:.6f}")
            else:
                st.metric("현재 모델 Threshold", f"{contract.threshold:.6f}")
            st.caption("대시보드에 하드코딩한 값이 아니라, 업로드한 bundle에서 읽은 판정기준")
            st.markdown("**Project**")
            st.caption(contract.project_name)
            st.markdown("**Model**")
            st.caption(contract.model_name)
            if contract.warnings:
                with st.expander("bundle 호환 안내"):
                    for w in contract.warnings:
                        st.warning(w)
        except Exception as exc:
            st.session_state.bundle_contract = None
            st.session_state.bundle_id = None
            st.error("bundle 검증에 실패했습니다.")
            st.code(f"{type(exc).__name__}: {exc}")

    st.divider()
    lan_ip = get_lan_ip()
    st.markdown("### 🛜 강의장 공유 서버")
    st.code(f"http://{lan_ip}:8501")
    st.caption("연수생은 같은 Wi-Fi에서 위 주소로 접속합니다.")
    st.caption(f"현재 브라우저 세션: {st.session_state.participant_session_id}")
    st.info("각 브라우저의 bundle·검사결과·기록은 서로 분리됩니다.")

    st.divider()
    st.markdown(
        f"""
<div class="sidebar-help">
추론 파일은 한글 프로젝트 경로에서 직접 실행하지 않고<br>
<b>{RUNTIME_ROOT}</b><br>
아래의 영문 전용 런타임으로 자동 복사됩니다.<br><br>
<b>Anomaly Score는 불량 확률이 아닙니다.</b>
</div>
""",
        unsafe_allow_html=True,
    )

contract = st.session_state.bundle_contract

# ------------------------------------------------------------
# header
# ------------------------------------------------------------
st.markdown(
    """
<div class="hero">
  <div>
    <div class="hero-kicker">AI VISION · SESSION 05</div>
    <div class="hero-title">AI Vision 품질검사 · 판정지원 모니터</div>
    <div class="hero-sub">프로젝트별 EfficientAD model bundle 연결 · 실제 추론 · 전문지식 기반 최종 검증</div>
  </div>
  <div class="hero-pill">모델 → 검사 → 판정 → 기록 → 수업 연결</div>
</div>
""",
    unsafe_allow_html=True,
)

if contract is None:
    st.info("왼쪽에서 4차시에서 만든 EfficientAD model bundle 또는 제공된 회사 backup bundle을 업로드하세요.")
    st.stop()

meta = contract_public(contract)

st.markdown(
    f"""
<div class="edu-note">
<b>현재 연결 프로젝트</b> — {meta["project"]}<br>
<b>현재 모델</b> — {meta["model"]} · image_size {meta["image_size"]} · {('Review Low %.6f · NG High %.6f' % (meta['review_low'], meta['ng_high'])) if meta['threshold_mode']=='THREE_ZONE' else ('Threshold %.6f' % meta['threshold'])}
</div>
""",
    unsafe_allow_html=True,
)

tabs = st.tabs(["🟢 검사 모니터", "📊 품질 대시보드", "🧠 모델 정보", "🔗 프로젝트 연결"])

# ------------------------------------------------------------
# 1. 검사 모니터
# ------------------------------------------------------------
with tabs[0]:
    st.markdown(
        """
<div class="edu-note">
<b>강의장 공유 모드</b> — 이 화면은 강사 PC의 실제 EfficientAD 환경에서 동작합니다.
각 연수생은 자기 4차시 bundle과 자기 이미지를 올리며, 브라우저 세션별 결과는 서로 분리됩니다.
실제 EfficientAD 추론은 최대 3명이 동시에 실행되고, 4번째 요청부터 자동 대기합니다.
</div>
""",
        unsafe_allow_html=True,
    )

    @st.fragment(run_every="1s")
    def render_workshop_server_load():
        load = get_workshop_inference_status()
        active = load["active"]
        waiting = load["waiting"]
        limit = load["limit"]
        completed = load["completed"]

        if waiting > 0:
            queue_text = f"{waiting}명 대기 중"
            queue_class = "ng-card"
        elif active >= limit:
            queue_text = "3/3 사용 중"
            queue_class = "cyan-card"
        else:
            queue_text = "바로 검사 가능"
            queue_class = "blue-card"

        st.markdown(
            f"""
<div class="status-row">
  <div class="status-card cyan-card">
    <div class="status-label">현재 추론 중</div>
    <div class="status-value">{active}/{limit}</div>
    <div class="status-sub">실제 EfficientAD 동시 실행</div>
  </div>
  <div class="status-card {queue_class}">
    <div class="status-label">대기 중</div>
    <div class="status-value">{waiting}</div>
    <div class="status-sub">{queue_text}</div>
  </div>
  <div class="status-card blue-card">
    <div class="status-label">완료된 추론</div>
    <div class="status-value">{completed}</div>
    <div class="status-sub">현재 서버 실행 이후 누적</div>
  </div>
</div>
""",
            unsafe_allow_html=True,
        )

    render_workshop_server_load()

    st.caption(
        "접속·bundle 업로드·이미지 업로드는 모두 동시에 가능합니다. "
        "실제 모델 추론만 강사 PC에서 최대 3명까지 병렬 처리하며, 4번째부터 자동 대기합니다."
    )

    image_file = st.file_uploader(
        "검사 이미지",
        type=["png", "jpg", "jpeg", "bmp"],
        key="inspection_image",
        help="현재 bundle의 프로젝트와 같은 촬영조건·검사대상 이미지를 사용하세요.",
    )

    original = None
    if image_file is not None:
        try:
            original = Image.open(io.BytesIO(image_file.getvalue())).convert("RGB")
        except Exception as exc:
            st.error(f"이미지를 열 수 없습니다: {exc}")

    if st.button(
        "▶ 실제 EfficientAD 검사 시작",
        type="primary",
        use_container_width=True,
        disabled=original is None,
    ):
        pred = None

        try:
            staged = stage_image_bytes(
                image_file.getvalue(),
                image_file.name,
                "streamlit",
                st.session_state.bundle_id,
            )
            with st.spinner("강사 PC에서 실제 EfficientAD 추론 중입니다. 최대 3명까지 동시에 실행되며, 자리가 없으면 자동 대기합니다..."):
                pred = run_efficientad_inference(contract=contract, image_path=staged)
        except Exception as exc:
            st.session_state.result = None
            st.error("실제 EfficientAD 모델 추론 단계에서 실패했습니다.")
            st.code(f"{type(exc).__name__}: {exc}")

        if pred is not None:
            try:
                visuals = pred.get("visuals") or anomaly_visuals(original, pred["anomaly_map"])
                st.session_state.result = {
                    **pred,
                    **visuals,
                    "file": image_file.name,
                    "time": datetime.now().strftime("%H:%M:%S"),
                }
            except Exception as exc:
                st.session_state.result = None
                st.error("모델 추론은 성공했지만 결과 시각화 단계에서 실패했습니다.")
                st.code(f"{type(exc).__name__}: {exc}")
                st.info(
                    f"추론 자체는 완료되었습니다. "
                    f"Score={pred['score']:.6f}, "
                    + (f"Review Low={contract.review_low:.6f}, NG High={contract.ng_high:.6f}, " if contract.is_three_zone else f"Threshold={contract.threshold:.6f}, ")
                    + f"Decision={pred['decision']}"
                )

    result = st.session_state.result

    if result is None:
        st.markdown(
            """
<div class="edu-note">
검사 버튼을 누르면 <b>현재 업로드한 model.ckpt</b>로 실제 추론합니다.
가짜 Score·가짜 OK/NG를 생성하지 않습니다.
</div>
""",
            unsafe_allow_html=True,
        )
    else:
        decision = result["decision"]
        if decision == "OK":
            decision_class, card_class = "ok", "ok-card"
        elif decision == "REVIEW":
            decision_class, card_class = "review", "review-card"
        else:
            decision_class, card_class = "ng", "ng-card"

        threshold_value = (
            f"{contract.review_low:.3f} / {contract.ng_high:.3f}"
            if contract.is_three_zone else f"{contract.threshold:.4f}"
        )
        threshold_label = "Review Low / NG High" if contract.is_three_zone else "Threshold"
        threshold_sub = "bundle의 OK / REVIEW / NG 기준" if contract.is_three_zone else "bundle에서 읽은 모델별 판정기준"

        st.markdown(
            f"""
<div class="status-row">
  <div class="status-card {card_class}">
    <div class="status-label">판정 결과</div>
    <div class="status-value {decision_class}">{decision}</div>
    <div class="status-sub">Score와 현재 bundle 판정기준 비교</div>
  </div>
  <div class="status-card cyan-card">
    <div class="status-label">Anomaly Score</div>
    <div class="status-value">{result["score"]:.4f}</div>
    <div class="status-sub">불량 확률이 아닌 이상점수</div>
  </div>
  <div class="status-card blue-card">
    <div class="status-label">{threshold_label}</div>
    <div class="status-value blue" style="font-size:1.25rem">{threshold_value}</div>
    <div class="status-sub">{threshold_sub}</div>
  </div>
  <div class="status-card blue-card">
    <div class="status-label">검사 모델</div>
    <div class="status-value" style="font-size:1.05rem">{meta["model"]}</div>
    <div class="status-sub">{result["elapsed_sec"]:.2f} s · 대기 {result.get("queue_wait_sec", 0.0):.2f} s · 최대 3명 동시</div>
  </div>
</div>
""",
            unsafe_allow_html=True,
        )

        rule_text = (
            f"Score < {contract.review_low:.6f} → OK / "
            f"{contract.review_low:.6f} ≤ Score < {contract.ng_high:.6f} → REVIEW / "
            f"Score ≥ {contract.ng_high:.6f} → NG"
            if contract.is_three_zone else
            (f"Score ≥ {contract.threshold:.6f} → NG / 그보다 작으면 OK" if contract.above_is_ng
             else f"Score ≤ {contract.threshold:.6f} → NG / 그보다 크면 OK")
        )
        st.caption(
            f"이미지: {result['file']}  ·  검사 시각 {result['time']}  ·  {rule_text}"
        )
        guard = result.get("input_guard")
        guard_text = guard.get("status") if isinstance(guard, dict) else "미사용"
        roi_mode = result.get('roi_mode', 'NONE')
        roi_text = '적용' if roi_mode not in {'NONE', 'DECLARED_UNSUPPORTED'} else ('미지원 recipe' if roi_mode == 'DECLARED_UNSUPPORTED' else 'bundle 전용 ROI 없음')
        st.caption(
            f"Input Guard: {guard_text}  ·  Score mode: {result.get('score_mode','RAW_ANOMALIB')}  ·  "
            f"ROI/Preprocess: {roi_text}"
        )

        c1, c2 = st.columns(2, gap="medium")
        with c1:
            st.markdown('<div class="vtitle">모델 입력 이미지 <span class="vtag">INPUT</span></div>', unsafe_allow_html=True)
            st.image(result["original"], use_container_width=True)
        with c2:
            st.markdown('<div class="vtitle">원본 + 이상영역 <span class="vtag">OVERLAY</span></div>', unsafe_allow_html=True)
            st.image(result["overlay"], use_container_width=True)

        c3, c4 = st.columns(2, gap="medium")
        with c3:
            st.markdown('<div class="vtitle">이상도 <span class="vtag">HEATMAP</span></div>', unsafe_allow_html=True)
            st.image(result["heatmap"], use_container_width=True)
        with c4:
            st.markdown('<div class="vtitle">윤곽선 <span class="vtag">CONTOUR*</span></div>', unsafe_allow_html=True)
            st.image(result["contour"], use_container_width=True)

        if result.get("score_mode") == "PF1_DECISION":
            st.markdown(
                """
<div class="edu-note">
<b>* Candidate4/PF1 시각화</b> — bundle의 ROI/localization 기준을 적용하고 Heatmap·Overlay·Contour에 동일한 evidence mask를 사용합니다.
빨간 영역은 GT 결함마스크가 없는 경우 <b>결함 후보(evidence)</b>이며, 이미지 단위 판정은 PF1 Decision Score와 bundle의 판정기준으로 이루어집니다.
</div>
""", unsafe_allow_html=True)
        else:
            st.markdown(
                """
<div class="edu-note">
<b>* Contour 안내</b> — 실제 anomaly map에서 이상도가 높은 영역을 수업에서 보기 쉽게 윤곽으로 표시한 시각화입니다.
<b>판정에는 사용하지 않습니다.</b> 판정은 이미지 단위 Score와 bundle의 판정기준으로 이루어집니다.
</div>
""", unsafe_allow_html=True)

        st.markdown('<div class="section-title">사람의 전공지식 기반 최종 검증</div>', unsafe_allow_html=True)
        a, b = st.columns([0.28, 0.72])
        with a:
            human = st.radio("최종 판단", ["OK", "NG", "재검사 필요"], horizontal=True)
        with b:
            evidence = st.text_input(
                "판단 근거",
                placeholder="예: Heatmap에서 강조된 영역이 실제 결함·품질기준과 일치함",
            )

        if st.button("검사 기록 저장", type="secondary", use_container_width=True):
            human_ai = "REVIEW" if human == "재검사 필요" else human
            st.session_state.logs.append(
                {
                    "time": datetime.now().strftime("%H:%M:%S"),
                    "file": result["file"],
                    "score": result["score"],
                    "threshold": contract.threshold if not contract.is_three_zone else None,
                    "review_low": contract.review_low,
                    "ng_high": contract.ng_high,
                    "ai": result["decision"],
                    "human": human,
                    "match": "일치" if human_ai == result["decision"] else "불일치",
                    "input_guard": (result.get("input_guard") or {}).get("status") if isinstance(result.get("input_guard"), dict) else None,
                    "score_mode": result.get("score_mode"),
                    "evidence": evidence,
                }
            )
            st.success("현재 세션 검사 기록에 저장했습니다.")

# ------------------------------------------------------------
# 2. 품질 대시보드
# ------------------------------------------------------------
with tabs[1]:
    df = pd.DataFrame(st.session_state.logs)
    total = len(df)
    ai_ok = int((df["ai"] == "OK").sum()) if total else 0
    ai_review = int((df["ai"] == "REVIEW").sum()) if total else 0
    ai_ng = int((df["ai"] == "NG").sum()) if total else 0
    review_rate = ai_review / total * 100 if total else 0.0
    ng_rate = ai_ng / total * 100 if total else 0.0
    avg_score = float(df["score"].mean()) if total else 0.0

    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("총 검사", total)
    c2.metric("AI OK", ai_ok)
    c3.metric("AI REVIEW", ai_review)
    c4.metric("AI NG", ai_ng)
    c5.metric("REVIEW율", f"{review_rate:.1f}%")
    c6.metric("평균 Score", f"{avg_score:.4f}")

    st.markdown('<div class="section-title">검사 Score 추이</div>', unsafe_allow_html=True)
    if total:
        chart = df[["score"]].copy()
        chart.index = range(1, total + 1)
        st.line_chart(chart, height=280)

        st.markdown('<div class="section-title">최근 검사 이력</div>', unsafe_allow_html=True)
        st.dataframe(
            df.tail(15),
            use_container_width=True,
            hide_index=True,
        )
        st.download_button(
            "CSV 검사기록 다운로드",
            df.to_csv(index=False).encode("utf-8-sig"),
            file_name="inspection_log.csv",
            mime="text/csv",
            use_container_width=True,
        )
    else:
        st.info("검사 모니터에서 실제 검사 후 ‘검사 기록 저장’을 누르면 여기에 누적됩니다.")

# ------------------------------------------------------------
# 3. 모델 정보
# ------------------------------------------------------------
with tabs[2]:
    m = meta["metrics"]
    d = meta["dataset"]

    st.markdown(f"### {meta['project']}")
    st.caption(
        "bundle에 실제로 들어 있는 메타데이터만 표시합니다. "
        "없는 성능값이나 데이터 수는 임의로 만들어 표시하지 않습니다."
    )

    available_metrics = [
        ("AUROC", m["auroc"]),
        ("F1", m["f1"]),
        ("Accuracy", m["accuracy"]),
        ("Recall", m["recall"]),
        ("Precision", m["precision"]),
    ]
    available_metrics = [(name, value) for name, value in available_metrics if value is not None]

    if available_metrics:
        cols = st.columns(min(len(available_metrics), 5))
        for col, (name, value) in zip(cols, available_metrics):
            col.metric(name, f"{value*100:.1f}%")
    else:
        st.info("이 bundle에는 표시 가능한 AUROC/F1/Accuracy/Recall/Precision 메타데이터가 없습니다.")

    st.markdown('<div class="section-title">데이터 구성</div>', unsafe_allow_html=True)
    if d["cards"]:
        cols = st.columns(min(len(d["cards"]), 4))
        for i, (label, value) in enumerate(d["cards"]):
            cols[i % len(cols)].metric(label, value)
    else:
        st.info("dataset.json에 인식 가능한 데이터 개수 정보가 없습니다.")

    if d["source"]:
        st.caption(f"Dataset source: {d['source']}")
    if d["license_note"]:
        st.caption(f"License note: {d['license_note']}")

    cm_values = [m["tn"], m["fp"], m["fn"], m["tp"]]
    left, right = st.columns([0.45, 0.55], gap="large")

    with left:
        st.markdown('<div class="section-title">혼동행렬</div>', unsafe_allow_html=True)
        if all(v is not None for v in cm_values):
            if meta["threshold_mode"] == "THREE_ZONE" and m.get("review") is not None:
                # REVIEW total is shown separately because some bundle schemas do not split it by actual class.
                cm = pd.DataFrame(
                    [[m["tn"], m["fp"]], [m["fn"], m["tp"]]],
                    index=["실제 GOOD", "실제 BAD"],
                    columns=["AI OK", "AI NG"],
                )
                st.dataframe(cm, use_container_width=True)
                st.metric("AI REVIEW", m["review"])
                if m.get("review_rate") is not None:
                    st.caption(f"REVIEW rate: {m['review_rate']*100:.1f}%")
                st.caption("REVIEW는 자동 최종판정에서 제외 · GOOD+NG=FP / BAD+OK=FN")
            else:
                cm = pd.DataFrame(
                    [[m["tn"], m["fp"]], [m["fn"], m["tp"]]],
                    index=["실제 GOOD", "실제 BAD"],
                    columns=["AI OK", "AI NG"],
                )
                st.dataframe(cm, use_container_width=True)
                st.caption("GOOD + AI NG = FP / BAD + AI OK = FN")
        else:
            st.info("이 bundle에는 TN/FP/FN/TP 전체 정보가 없어 혼동행렬을 만들지 않습니다.")

    with right:
        st.markdown('<div class="section-title">현재 model bundle 설정</div>', unsafe_allow_html=True)
        st.json(meta["config"])

    with st.expander("bundle 원본 메타데이터 보기"):
        st.markdown("**model_info.json**")
        st.json(meta["raw"]["model_info"])
        st.markdown("**config.json**")
        st.json(meta["raw"]["config"])
        st.markdown("**threshold.json**")
        st.json(meta["raw"]["threshold"])
        st.markdown("**metrics.json**")
        st.json(meta["raw"]["metrics"])
        if meta["raw"].get("final_metrics"):
            st.markdown("**final_metrics.json**")
            st.json(meta["raw"]["final_metrics"])
        if meta["raw"].get("calibration_metrics"):
            st.markdown("**calibration_metrics.json**")
            st.json(meta["raw"]["calibration_metrics"])
        st.markdown("**dataset.json**")
        st.json(meta["raw"]["dataset"])

    st.markdown(
        """
<div class="edu-note">
<b>실행 성공 ≠ 좋은 검사모델</b><br>
checkpoint가 정상 생성되고 대시보드에서 추론된다는 것과 실제 품질검사 성능이 충분하다는 것은 다른 문제입니다.
bundle에 성능지표가 있다면 FP/FN·Score 분포·AUROC 등을 참고하고, 최종적으로는 현장의 품질기준과 전문지식으로 검증합니다.
</div>
""",
        unsafe_allow_html=True,
    )

# ------------------------------------------------------------
# 4. 프로젝트 연결
# ------------------------------------------------------------
with tabs[3]:
    st.markdown("### 모델 제작 → 검사시스템 연결")
    st.markdown(
        """
**4차시**

`프로젝트 데이터 → GOOD 중심 학습 → EfficientAD → model.ckpt → Score 분석 → Threshold 또는 review_low/ng_high → model bundle`

**5차시**

`model bundle → 실제 Dashboard → 새 이미지 추론 → bundle의 Score/판정기준 → OK·REVIEW·NG(또는 OK·NG) → 이상영역 → 사람의 전공지식 검증 → 기록`
"""
    )

    st.markdown(
        """
<div class="edu-note">
<b>핵심 질문: 모델을 만들면 끝인가?</b><br>
아닙니다. 실제 AI 프로젝트에서는 모델을 입력·판정기준·시각화·사람의 검증·기록과 연결해야 합니다.
학교에서는 기업 장비 전체를 복제하지 않고 이 문제해결 구조를 교육용 Dashboard로 경험합니다.
</div>
""",
        unsafe_allow_html=True,
    )
