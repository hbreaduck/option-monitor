# -*- coding: utf-8 -*-
"""
반도체 옵션 수급 모니터 — 공용 계산 로직 (Streamlit 비의존)
대시보드(options_monitor.py)와 자동 캡처(capture.py)가 함께 사용한다.
"""

import math
from datetime import date

import yfinance as yf
import pandas as pd
import numpy as np

RISK_FREE = 0.043  # 무위험 이자율 근사 (IV 역산용)
HV_WINDOW = 20     # 실현변동성 계산 기간(거래일)

TICKERS = {
    "NVDA": "엔비디아",
    "MU": "마이크론",
    "SKHY": "SK하이닉스 ADR",
    "SOXX": "iShares 반도체 ETF",
}

# 스냅샷 CSV 스키마 (capture.py가 기록, 대시보드가 읽음)
CSV_PATH = "data/snapshots.csv"
CSV_COLUMNS = [
    "ts_kst", "ts_utc", "symbol", "price", "chg_pct", "pc_ratio",
    "call_vol", "put_vol", "iv", "iv_src", "hv", "iv_hv",
    "earn_date", "earn_days", "expiry",
]


def _norm_cdf(x: float) -> float:
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def _bs_price(S: float, K: float, T: float, r: float, sig: float, call: bool) -> float:
    if sig <= 0 or T <= 0:
        return max(0.0, (S - K) if call else (K - S))
    d1 = (math.log(S / K) + (r + sig * sig / 2) * T) / (sig * math.sqrt(T))
    d2 = d1 - sig * math.sqrt(T)
    if call:
        return S * _norm_cdf(d1) - K * math.exp(-r * T) * _norm_cdf(d2)
    return K * math.exp(-r * T) * _norm_cdf(-d2) - S * _norm_cdf(-d1)


def implied_vol(mkt: float, S: float, K: float, T: float, r: float, call: bool) -> float:
    """옵션 시장가로부터 Black-Scholes IV를 이분법으로 역산."""
    if mkt is None or mkt <= 0 or T <= 0 or S <= 0 or K <= 0:
        return float("nan")
    lo, hi = 1e-4, 5.0
    if _bs_price(S, K, T, r, hi, call) < mkt:  # 시장가가 상한을 넘으면 실패
        return float("nan")
    for _ in range(80):
        mid = (lo + hi) / 2
        if _bs_price(S, K, T, r, mid, call) > mkt:
            hi = mid
        else:
            lo = mid
    return (lo + hi) / 2


def atm_iv(df: pd.DataFrame, price: float, T: float, call: bool):
    """현재가에 가장 가까운 5개 계약의 시장가로 역산한 IV 평균.

    Yahoo의 impliedVolatility 필드는 종종 placeholder(0.00001 등)라 신뢰할 수
    없으므로 직접 역산한다. 호가(bid/ask)가 있으면 그 중간값을 우선 사용하고,
    (정규장 마감 등으로) 호가가 없으면 최종가(lastPrice)로 대체한다.
    반환: (iv_fraction, source)  source ∈ {"quote", "last", None}
    """
    if df is None or df.empty or "strike" not in df:
        return float("nan"), None
    d = df.copy()
    d["dist"] = (d["strike"] - price).abs()
    quote_ivs, last_ivs = [], []
    for _, row in d.nsmallest(5, "dist").iterrows():
        K = float(row["strike"])
        bid = float(row.get("bid") or 0)
        ask = float(row.get("ask") or 0)
        if bid > 0 and ask > 0:
            iv = implied_vol((bid + ask) / 2, price, K, T, RISK_FREE, call)
            if not math.isnan(iv):
                quote_ivs.append(iv)
        else:
            iv = implied_vol(float(row.get("lastPrice") or 0), price, K, T, RISK_FREE, call)
            if not math.isnan(iv):
                last_ivs.append(iv)
    if quote_ivs:  # 호가 기반이 하나라도 있으면 그것만 사용
        return sum(quote_ivs) / len(quote_ivs), "quote"
    if last_ivs:
        return sum(last_ivs) / len(last_ivs), "last"
    return float("nan"), None


def realized_vol(close: pd.Series, window: int = HV_WINDOW):
    """연율화 실현변동성(HV, %)과 최근 1년 내 백분위 반환.

    HV = 최근 window일 로그수익률 표준편차 × √252. IV(옵션이 예상하는 변동성)와
    비교하면 "옵션이 실제 움직임 대비 비싼가"를 알 수 있다.
    반환: (hv_pct, hv_percentile)  값 없으면 nan.
    """
    if close is None or len(close) < window + 1:
        return float("nan"), float("nan")
    ret = np.log(close / close.shift(1)).dropna()
    hv_now = float(ret.tail(window).std() * math.sqrt(252) * 100)
    roll = (ret.rolling(window).std() * math.sqrt(252) * 100).dropna()
    pct = float((roll < hv_now).mean() * 100) if len(roll) > 1 else float("nan")
    return hv_now, pct


def next_earnings(tk: yf.Ticker):
    """다음 실적 발표일과 남은 일수 반환. ETF 등 없으면 (None, None)."""
    try:
        ed = tk.get_earnings_dates(limit=12)
        if ed is None or ed.empty:
            return None, None
        today = date.today()
        future = [d.date() for d in ed.index if d.date() >= today]
        if not future:
            return None, None
        nxt = min(future)
        return nxt, (nxt - today).days
    except Exception:
        return None, None


def fetch_one(symbol: str) -> dict:
    """한 종목의 주가 + 옵션 지표 조회."""
    out = {"symbol": symbol, "ok": False, "error": None}
    try:
        tk = yf.Ticker(symbol)

        # --- 주가 / 등락률 / 실현변동성(1년 이력) ---
        hist = tk.history(period="1y")
        if hist.empty:
            raise ValueError("주가 데이터 없음")
        close = hist["Close"]
        price = float(close.iloc[-1])
        prev = float(close.iloc[-2]) if len(close) >= 2 else price
        chg_pct = (price / prev - 1) * 100 if prev else 0.0
        hv, hv_pct = realized_vol(close)
        earn_date, earn_days = next_earnings(tk)
        out.update(
            price=price, chg_pct=chg_pct, hv=hv, hv_pct=hv_pct,
            earn_date=earn_date, earn_days=earn_days,
        )

        # --- 옵션체인 (오늘 만기 0DTE는 IV가 왜곡되므로 그 다음 만기 우선) ---
        expiries = tk.options
        if not expiries:
            raise ValueError("옵션 데이터 없음")
        today = date.today()
        future = [e for e in expiries if date.fromisoformat(e) > today]
        expiry = future[0] if future else expiries[0]
        chain = tk.option_chain(expiry)
        calls, puts = chain.calls, chain.puts

        call_vol = int(calls["volume"].fillna(0).sum())
        put_vol = int(puts["volume"].fillna(0).sum())
        pc_ratio = put_vol / call_vol if call_vol > 0 else float("nan")

        # --- ATM IV: 콜/풋 각각의 근가 계약을 시장가로 역산 후 평균 ---
        T = max((date.fromisoformat(expiry) - today).days, 1) / 365
        c_iv, c_src = atm_iv(calls, price, T, True)
        p_iv, p_src = atm_iv(puts, price, T, False)
        pairs = [(v, s) for v, s in ((c_iv, c_src), (p_iv, p_src)) if not math.isnan(v)]
        # 호가 기반이 하나라도 있으면 그것만 채택 (더 신뢰도 높음)
        if any(s == "quote" for _, s in pairs):
            pairs = [(v, s) for v, s in pairs if s == "quote"]
        iv = (sum(v for v, _ in pairs) / len(pairs) * 100) if pairs else float("nan")
        iv_src = pairs[0][1] if pairs else None
        # IV/HV: 옵션이 실제 변동성 대비 비싼가 (>1.2 비쌈, <0.9 쌈)
        iv_hv = (iv / out["hv"]) if (not math.isnan(iv) and out["hv"] and not math.isnan(out["hv"])) else float("nan")

        out.update(
            ok=True,
            expiry=expiry,
            call_vol=call_vol,
            put_vol=put_vol,
            pc_ratio=pc_ratio,
            iv=iv,
            iv_src=iv_src,
            iv_hv=iv_hv,
        )
    except Exception as e:
        out["error"] = str(e)
    return out


def interpret(r: dict, prev_iv):
    """(뱃지 텍스트, 색상) — 주가·IV 조합으로 심리 해석."""
    if not r["ok"]:
        return ("데이터 준비 중", "gray")
    if prev_iv is None or math.isnan(r.get("iv", float("nan"))):
        return ("첫 조회 — 다음 조회부터 IV 방향 비교", "gray")

    up = r["chg_pct"] > 0
    iv_down = r["iv"] < prev_iv
    iv_up = r["iv"] > prev_iv

    if up and iv_down:
        return ("위험회피 완화 (주가↑ IV↓)", "green")
    if up and iv_up:
        return ("불안 속 반등 (주가↑ IV↑)", "orange")
    if (not up) and iv_up:
        return ("불안 심리 강화 (주가↓ IV↑)", "red")
    if (not up) and iv_down:
        return ("낙폭 진정 (주가↓ IV↓)", "orange")
    return ("중립", "gray")
