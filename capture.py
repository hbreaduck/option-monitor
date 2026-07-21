# -*- coding: utf-8 -*-
"""
자동 스냅샷 캡처 — 화면 없이 돌며 4종목을 조회해 data/snapshots.csv에 append.
GitHub Actions(cron)가 미국장 시간에 자동 실행한다. 로컬 테스트: python capture.py
"""

import os
import csv
from datetime import datetime, timezone, timedelta

from monitor_core import TICKERS, CSV_PATH, CSV_COLUMNS, fetch_one

KST = timezone(timedelta(hours=9))


def _row(symbol: str, now_kst: datetime, now_utc: datetime) -> dict:
    r = fetch_one(symbol)
    ed = r.get("earn_date")
    return {
        "ts_kst": now_kst.strftime("%Y-%m-%d %H:%M"),
        "ts_utc": now_utc.strftime("%Y-%m-%d %H:%M"),
        "symbol": symbol,
        "price": round(r["price"], 2) if r.get("ok") else "",
        "chg_pct": round(r["chg_pct"], 2) if r.get("ok") else "",
        "pc_ratio": (round(r["pc_ratio"], 3) if r.get("ok") and r["pc_ratio"] == r["pc_ratio"] else ""),
        "call_vol": r.get("call_vol", "") if r.get("ok") else "",
        "put_vol": r.get("put_vol", "") if r.get("ok") else "",
        "iv": (round(r["iv"], 2) if r.get("ok") and r["iv"] == r["iv"] else ""),
        "iv_src": r.get("iv_src", "") or "",
        "hv": (round(r["hv"], 1) if r.get("ok") and r["hv"] == r["hv"] else ""),
        "iv_hv": (round(r["iv_hv"], 3) if r.get("ok") and r["iv_hv"] == r["iv_hv"] else ""),
        "earn_date": ed.isoformat() if ed else "",
        "earn_days": r.get("earn_days", "") if r.get("ok") else "",
        "expiry": r.get("expiry", "") if r.get("ok") else "",
        "_ok": r.get("ok"),
        "_err": r.get("error"),
    }


def main() -> None:
    now_utc = datetime.now(timezone.utc)
    now_kst = now_utc.astimezone(KST)

    os.makedirs(os.path.dirname(CSV_PATH), exist_ok=True)
    new_file = not os.path.exists(CSV_PATH) or os.path.getsize(CSV_PATH) == 0

    rows = [_row(s, now_kst, now_utc) for s in TICKERS]

    with open(CSV_PATH, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=CSV_COLUMNS, extrasaction="ignore")
        if new_file:
            w.writeheader()
        for row in rows:
            w.writerow(row)

    ok = sum(1 for r in rows if r.get("_ok"))
    print(f"[capture] {now_kst:%Y-%m-%d %H:%M} KST · {ok}/{len(rows)} 종목 성공 → {CSV_PATH}")
    for r in rows:
        status = "OK" if r.get("_ok") else f"FAIL({r.get('_err')})"
        print(f"  {r['symbol']:5} price={r['price']} iv={r['iv']}({r['iv_src']}) pc={r['pc_ratio']} [{status}]")


if __name__ == "__main__":
    main()
