# -*- coding: utf-8 -*-
"""
반도체 옵션 수급 모니터 (NVDA / MU / SKHY / SOXX) — 대시보드
- "지금 조회" 버튼: 그 순간의 옵션 수급을 라이브로 조회 (버튼 누를 때만)
- "지난 밤 자동 기록": GitHub Actions가 미국장 시간에 캡처한 data/snapshots.csv 추이
- 실행: streamlit run options_monitor.py
- 필요: pip install -r requirements.txt
"""

import math
import os
from datetime import datetime

import streamlit as st
import pandas as pd

from monitor_core import (
    TICKERS, CSV_PATH, fetch_one, interpret,
)

st.set_page_config(page_title="반도체 옵션 수급 모니터", layout="wide")
st.title("반도체 옵션 수급 모니터")
st.caption("풋/콜 거래량 비율 · ATM 내재변동성 (Yahoo Finance, 약 15분 지연)")


@st.cache_data(ttl=300)
def load_snapshots() -> pd.DataFrame:
    """자동 캡처 CSV를 읽어 정렬된 DataFrame으로 반환 (없으면 빈 DF)."""
    if not os.path.exists(CSV_PATH):
        return pd.DataFrame()
    try:
        df = pd.read_csv(CSV_PATH)
        df["ts"] = pd.to_datetime(df["ts_kst"], errors="coerce")
        return df.dropna(subset=["ts"]).sort_values("ts")
    except Exception:
        return pd.DataFrame()


# ── 세션 상태 ─────────────────────────────────────────────
if "data" not in st.session_state:
    st.session_state.data = None
    st.session_state.prev_iv = {}
    st.session_state.fetched_at = None

# ── 조회 버튼 (라이브) ─────────────────────────────────────
if st.button("🔄 지금 조회 (라이브)", type="primary", use_container_width=True):
    with st.spinner("옵션체인 조회 중..."):
        new_data = {s: fetch_one(s) for s in TICKERS}
    if st.session_state.data:  # 직전 조회 IV 저장 → 방향 비교용
        st.session_state.prev_iv = {
            s: r["iv"]
            for s, r in st.session_state.data.items()
            if r["ok"] and not math.isnan(r.get("iv", float("nan")))
        }
    st.session_state.data = new_data
    st.session_state.fetched_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

# ── 라이브 카드 ───────────────────────────────────────────
if st.session_state.data is None:
    st.info("위 버튼을 누르면 지금 이 순간의 옵션 수급을 조회합니다. "
            "미국 정규장(한국 밤 10:30~새벽 5:00)에 눌러야 IV가 실시간 호가로 정확합니다.")
else:
    st.caption(f"라이브 조회 시각: {st.session_state.fetched_at}")
    cols = st.columns(len(TICKERS))
    for col, (sym, name) in zip(cols, TICKERS.items()):
        r = st.session_state.data[sym]
        prev_iv = st.session_state.prev_iv.get(sym)
        badge, color = interpret(r, prev_iv)
        with col:
            with st.container(border=True):
                st.subheader(f"{name} ({sym})")
                if not r["ok"]:
                    st.warning(f"데이터 준비 중\n\n({r['error']})")
                    continue

                st.metric("현재가", f"${r['price']:,.2f}", f"{r['chg_pct']:+.2f}%")

                pc = r["pc_ratio"]
                has_pc = not math.isnan(pc)
                pc_label = f"{pc:.2f}" if has_pc else "N/A"
                if has_pc and pc > 1:
                    st.markdown(f"**풋/콜 비율: :red[{pc_label}]** (풋 우위 — 방어적)")
                elif has_pc:
                    st.markdown(f"**풋/콜 비율: :green[{pc_label}]** (콜 우위)")
                else:
                    st.markdown(f"**풋/콜 비율: {pc_label}**")
                st.caption(f"콜 {r['call_vol']:,} / 풋 {r['put_vol']:,} · 만기 {r['expiry']}")

                if math.isnan(r["iv"]):
                    st.markdown("**ATM IV: N/A** (가격 데이터 없음)")
                else:
                    iv_arrow = ""
                    if prev_iv is not None:
                        iv_arrow = " ▲" if r["iv"] > prev_iv else (" ▼" if r["iv"] < prev_iv else " ―")
                    st.markdown(f"**ATM IV: {r['iv']:.1f}%{iv_arrow}**")
                    if r.get("iv_src") == "last":
                        st.caption("⚠ 최종가 기준 (정규장 호가 없음 · 참고용)")

                # --- 실현변동성(HV) · IV/HV: 옵션이 평소 대비 비싼가 ---
                hv = r.get("hv", float("nan"))
                if hv and not math.isnan(hv):
                    hv_pct = r.get("hv_pct", float("nan"))
                    pct_txt = f" · 1년 중 상위 {100 - hv_pct:.0f}%" if not math.isnan(hv_pct) else ""
                    st.caption(f"실현변동성(HV): {hv:.0f}%{pct_txt}")
                    iv_hv = r.get("iv_hv", float("nan"))
                    if not math.isnan(iv_hv):
                        if iv_hv >= 1.2:
                            st.markdown(f"**IV/HV: :red[{iv_hv:.2f}배]** (옵션 비쌈)")
                        elif iv_hv <= 0.9:
                            st.markdown(f"**IV/HV: :green[{iv_hv:.2f}배]** (옵션 쌈)")
                        else:
                            st.markdown(f"**IV/HV: {iv_hv:.2f}배** (적정)")

                # --- 실적 발표 D-day (임박 시 IV crush 경고) ---
                ed, dd = r.get("earn_date"), r.get("earn_days")
                if ed is None:
                    st.caption("실적: 해당 없음 (ETF)")
                elif dd is not None:
                    if dd <= 10:
                        st.markdown(f":orange[📅 실적 **D-{dd}** ({ed}) ⚠ IV crush 주의]")
                    else:
                        st.caption(f"📅 실적 D-{dd} ({ed})")

                st.markdown(f":{color}[● {badge}]")


# ── 지난 밤 자동 기록 (추이) ───────────────────────────────
st.divider()
st.subheader("📈 지난 밤 자동 기록 (추이)")
st.caption("GitHub Actions가 미국장 시간에 자동 캡처한 기록 — 자는 동안 잡은 '라이브 IV'라 정확합니다.")

snap = load_snapshots()
if snap.empty:
    st.info("아직 자동 기록이 없습니다. 클라우드 배포 후 미국장 시간에 GitHub Actions가 채웁니다. "
            "(로컬 테스트: `python capture.py`)")
else:
    days = st.radio("표시 기간", [1, 3, 7], index=1, horizontal=True,
                    format_func=lambda d: f"최근 {d}일")
    cutoff = snap["ts"].max() - pd.Timedelta(days=days)
    recent = snap[snap["ts"] >= cutoff]

    last_ts = snap["ts"].max().strftime("%Y-%m-%d %H:%M")
    st.caption(f"기록 {len(snap):,}건 · 최근 캡처 {last_ts} (KST)")

    m1, m2 = st.columns(2)
    with m1:
        st.markdown("**ATM IV 추이 (%)**")
        iv_wide = recent.pivot_table(index="ts", columns="symbol", values="iv")
        iv_wide = iv_wide.reindex(columns=[s for s in TICKERS if s in iv_wide.columns])
        st.line_chart(iv_wide, height=260)
    with m2:
        st.markdown("**풋/콜 비율 추이**")
        pc_wide = recent.pivot_table(index="ts", columns="symbol", values="pc_ratio")
        pc_wide = pc_wide.reindex(columns=[s for s in TICKERS if s in pc_wide.columns])
        st.line_chart(pc_wide, height=260)

    # 종목별 최근값 + 직전 대비 IV 변화
    st.markdown("**종목별 최근 스냅샷 (직전 대비 IV 변화)**")
    rows = []
    for sym in TICKERS:
        g = snap[snap["symbol"] == sym].dropna(subset=["iv"])
        if g.empty:
            continue
        last = g.iloc[-1]
        prev = g.iloc[-2] if len(g) >= 2 else None
        arrow = ""
        if prev is not None:
            arrow = " ▲" if last["iv"] > prev["iv"] else (" ▼" if last["iv"] < prev["iv"] else " ―")
        rows.append({
            "종목": f"{TICKERS[sym]} ({sym})",
            "현재가": f"${last['price']:,.2f}" if pd.notna(last.get("price")) else "-",
            "등락률": f"{last['chg_pct']:+.2f}%" if pd.notna(last.get("chg_pct")) else "-",
            "풋/콜": f"{last['pc_ratio']:.2f}" if pd.notna(last.get("pc_ratio")) else "-",
            "IV": f"{last['iv']:.1f}%{arrow}" if pd.notna(last.get("iv")) else "-",
            "IV/HV": f"{last['iv_hv']:.2f}배" if pd.notna(last.get("iv_hv")) else "-",
            "실적D": f"D-{int(last['earn_days'])}" if pd.notna(last.get("earn_days")) else "—",
            "캡처시각": last["ts"].strftime("%m-%d %H:%M"),
        })
    if rows:
        st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)


# ── 하단: 지표 읽는 법 (항상 표시) ─────────────────────────
st.divider()
with st.expander("📖 지표 읽는 법 — 풋/콜 비율 · 주가×IV · 직관 확인법", expanded=False):
    t1, t2 = st.columns(2)
    with t1:
        st.markdown("**① 풋/콜 비율 (거래량 기준)** — 방어냐 공격이냐")
        st.markdown(
            "| 값 | 의미 |\n"
            "|---|---|\n"
            "| **> 1** | 🛡 풋 우위 — 방어·헤지 심리 (빨강) |\n"
            "| **≈ 1** | 중립 |\n"
            "| **< 1** | 🚀 콜 우위 — 상승 베팅 (초록) |"
        )
        st.caption("공식: 풋 거래량 ÷ 콜 거래량 · 극단값(1.5↑ / 0.6↓)·추세 변화가 신호")
    with t2:
        st.markdown("**② 주가 × IV 조합** — 투자심리 (2회차부터 IV 방향 비교)")
        st.markdown(
            "| 조합 | 심리 |\n"
            "|---|---|\n"
            "| 주가↑ + IV↓ | 😌 위험회피 완화 |\n"
            "| 주가↓ + IV↑ | 😨 불안 심리 강화 |\n"
            "| 주가↑ + IV↑ | 😬 불안 속 반등 |\n"
            "| 주가↓ + IV↓ | 🙂 낙폭 진정 |"
        )
        st.caption("IV는 '방향'이 아니라 '폭' — 주가와 묶어야 심리가 읽힘")

    st.markdown("**③ IV/HV · 실적 D-day** — 옵션이 '평소 대비' 비싼가")
    g1, g2 = st.columns(2)
    with g1:
        st.markdown(
            "| IV/HV | 의미 |\n"
            "|---|---|\n"
            "| **≥ 1.2배** | 🔴 옵션 비쌈 (변동성 프리미엄 큼) |\n"
            "| 0.9~1.2배 | 적정 |\n"
            "| **≤ 0.9배** | 🟢 옵션 쌈 |"
        )
        st.caption("HV=실제(실현) 변동성 · IV=옵션이 예상하는 변동성. IV가 HV보다 크게 높으면 옵션이 비싼 국면")
    with g2:
        st.markdown(
            "- **실적 D-day**: 발표가 가까울수록 IV가 오름 → 발표 직후 **IV crush**(급락) 위험\n"
            "- D-10 이내면 카드에 ⚠ 경고 표시\n"
            "- ETF(SOXX)는 실적이 없어 '해당 없음'"
        )
        st.caption("※ yfinance는 과거 IV 이력을 안 줘서 'IV 백분위' 대신 IV/HV로 대체함")

    st.markdown("**④ 직관 확인법**")
    st.markdown(
        "- **IV ÷ 16 ≈ 하루 예상 변동폭(%)** — 예: IV 64% → 하루 약 **±4%** 움직일 것으로 시장이 봄\n"
        "- **ATM** = 현재가에 가장 가까운 행사가 (변동성에 가장 민감한 순수 신호)\n"
        "- **IV 높음** = 큰 출렁임/이벤트 임박 = 옵션 비쌈 · **IV 낮음** = 잔잔할 것으로 예상\n"
        "- **정규장** = 미국 09:30–16:00 ET (한국 밤 10:30~새벽 5:00, 서머타임 기준). "
        "이 시간에만 실시간 호가로 IV가 정확 — 장 마감 시엔 '⚠ 최종가 기준'으로 표시됨"
    )
