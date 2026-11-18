"""Futures closes from Sina Finance's free quote API (verified 2026-11-17).

Symbols are the continuous main-contract series:
  PP -> nf_PP0 (DCE), LLDPE -> nf_L0 (DCE), PVC -> nf_V0 (DCE),
  PET bottle flakes -> nf_PR0 (CZCE).
Field layout of the nf_ payload (GBK, comma separated):
  [0] name, [1] time HHMMSS, [2] open, [3] high, [4] low,
  [5] latest, [6] bid, [7] ask, [8] close-of-day latest, [9] prev settle,
  [10] prev close, [13] open interest, [14] volume, [17] date
  (field layout re-verified live 2026-11-18).
After the 15:00 close, [8] is the day's closing price; the daily change
the site publishes is close / prev_close - 1.
"""
from __future__ import annotations

import urllib.request

SYMBOLS = {"pp": "nf_PP0", "lldpe": "nf_L0", "pvc": "nf_V0", "pet": "nf_PR0"}
URL = "https://hq.sinajs.cn/list="


def fetch_closes(timeout=20):
    codes = ",".join(SYMBOLS.values())
    req = urllib.request.Request(
        URL + codes,
        headers={
            "Referer": "https://finance.sina.com.cn/",
            "User-Agent": "Mozilla/5.0 (pla365-pipeline)",
        },
    )
    raw = urllib.request.urlopen(req, timeout=timeout).read()
    text = raw.decode("gbk", "replace")
    out = {}
    for slug, code in SYMBOLS.items():
        marker = f'var hq_str_{code}="'
        if marker not in text:
            out[slug] = None
            continue
        payload = text.split(marker, 1)[1].split('"', 1)[0]
        f = payload.split(",")
        close = float(f[8])
        prev_close = float(f[10])
        out[slug] = {
            "close": close,
            "prev_close": prev_close,
            "chg": round((close / prev_close - 1) * 100, 2) if prev_close else 0.0,
            "date": f[17] if len(f) > 17 else None,
            "name": f[0],
        }
    return out


PREFIX = {"pp": "PP", "lldpe": "L", "pvc": "V", "pet": "PR"}


def _contract_code(slug, year, month):
    """Sina symbol suffix for a specific contract month (YYMM for all
    exchanges on Sina, CZCE included: nf_PR2701 works, nf_PR701 does not)."""
    return f"{PREFIX[slug]}{year % 100:02d}{month:02d}"


def fetch_main_contracts(today=None, timeout=20):
    """Resolve each variety's current main contract by open interest.

    Sina's continuous quotes (nf_PP0 ...) do not name the contract, so
    scan the listed months around today and pick the one with the
    largest open interest (field 15). Returns
    {slug: {contract: 'YYMM', close, open_interest}}.
    The continuous series IS the main contract, so the resolved close
    should match fetch_closes().
    """
    import datetime as _dt

    today = today or _dt.date.today()
    months = []
    y, m = today.year, today.month
    for _ in range(14):
        months.append((y, m))
        m += 1
        if m > 12:
            y, m = y + 1, 1
    codes = []
    for slug in PREFIX:
        for (yy, mm) in months:
            codes.append("nf_" + _contract_code(slug, yy, mm))
    req = urllib.request.Request(
        URL + ",".join(codes),
        headers={
            "Referer": "https://finance.sina.com.cn/",
            "User-Agent": "Mozilla/5.0 (pla365-pipeline)",
        },
    )
    text = urllib.request.urlopen(req, timeout=timeout).read().decode("gbk", "replace")
    out = {}
    for slug in PREFIX:
        best = None
        for (yy, mm) in months:
            code = "nf_" + _contract_code(slug, yy, mm)
            marker = f'var hq_str_{code}="'
            if marker not in text:
                continue
            payload = text.split(marker, 1)[1].split('"', 1)[0]
            if not payload:
                continue
            f = payload.split(",")
            try:
                oi = float(f[13])
                close = float(f[8])
            except (IndexError, ValueError):
                continue
            if oi > 0 and (best is None or oi > best["open_interest"]):
                best = {
                    "contract": f"{yy % 100:02d}{mm:02d}",
                    "close": close,
                    "open_interest": oi,
                }
        out[slug] = best
    return out


KLINE_URL = ("https://stock.finance.sina.com.cn/futures/api/jsonp.php/"
             "var%20x=/InnerFuturesNewService.getDailyKLine?symbol=")


def fetch_klines(code, timeout=20):
    """Daily bars for a Sina futures symbol (e.g. 'PP0' or 'PP2701').

    Returns [(date, close, open_interest)] ascending by date. Verified
    2026-11-18: PP2701 bars are identical to the PP0 continuous series
    while 2701 is the main contract, and closes match hq.sinajs.cn.
    """
    import json as _json
    import re as _re

    req = urllib.request.Request(
        KLINE_URL + code,
        headers={
            "Referer": "https://finance.sina.com.cn/",
            "User-Agent": "Mozilla/5.0 (pla365-pipeline)",
        },
    )
    text = urllib.request.urlopen(req, timeout=timeout).read().decode("gbk", "replace")
    m = _re.search(r"\((\[.*\])\)", text, _re.S)
    if not m:
        return []
    bars = _json.loads(m.group(1))
    return [(b["d"], float(b["c"]), float(b["p"])) for b in bars]


def latest_completed(slug, today, main_contracts=None):
    """Latest completed trading day for a variety's main contract:
    {date, close, chg, contract}. The morning run takes the last kline
    bar dated before `today` (today's bar is intraday, not a close)."""
    main_contracts = main_contracts or fetch_main_contracts()
    mc = main_contracts.get(slug)
    if not mc:
        return None
    code = PREFIX[slug] + mc["contract"]
    bars = [b for b in fetch_klines(code) if b[0] < today]
    if len(bars) < 2:
        return None
    (date, close, _), (_, prev_close, _) = bars[-1], bars[-2]
    return {
        "date": date,
        "close": close,
        "chg": round((close / prev_close - 1) * 100, 2) if prev_close else 0.0,
        "contract": mc["contract"],
    }


CONTINUOUS = {"pp": "PP0", "lldpe": "L0", "pvc": "V0", "pet": "PR0"}


def fetch_continuous(slug, timeout=20):
    """Daily bars for a variety's continuous contract (Sina PP0/L0/V0/PR0).

    Returns [(date, close, settle)] ascending. Verified 2026-11-19:
    for all four varieties the closes reproduce the published variety
    pages' embedded futures series exactly (264 bars, 2025-10-09 to
    2026-11-09), and the settle field matches the pages' FAQ
    settlement prices (PP 2026-11-09: close 9341, settle 9461).
    """
    import json as _json
    import re as _re

    req = urllib.request.Request(
        KLINE_URL + CONTINUOUS[slug],
        headers={
            "Referer": "https://finance.sina.com.cn/",
            "User-Agent": "Mozilla/5.0 (pla365-pipeline)",
        },
    )
    text = urllib.request.urlopen(req, timeout=timeout).read().decode("gbk", "replace")
    m = _re.search(r"\((\[.*\])\)", text, _re.S)
    if not m:
        return []
    bars = _json.loads(m.group(1))
    return [(b["d"], float(b["c"]), float(b["s"])) for b in bars]


def continuous_state(slug, today, series_start=None):
    """Futures inputs for one variety from its continuous series:
    the latest completed bar (dated before `today`) with its close,
    1-decimal change and settlement, plus the (date, close) series
    the variety pages embed (from the site history start)."""
    bars = fetch_continuous(slug)
    done = [b for b in bars if b[0] < today]
    if len(done) < 2:
        return None
    date, close, settle = done[-1]
    prev = done[-2][1]
    fut_series = [(d, c) for d, c, _ in bars
                  if (series_start is None or d >= series_start) and d < today]
    return {
        "date": date, "close": close, "settle": settle,
        "chg": round((close / prev - 1) * 100, 1) if prev else 0.0,
        "fut_series": fut_series,
    }
