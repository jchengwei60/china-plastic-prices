"""Core computations for the pla365 pipeline.

All functions operate on a price series: a list of (date, price) sorted by
date, one entry per calendar day (the source publishes daily, weekends
repeat the previous benchmark).
"""
from __future__ import annotations

import datetime as dt


def stats_3m(series):
    """The site's '3-month' stats: last 91 daily entries.

    Verified against the published 2026-11-10 latest.json: a 91-entry
    window reproduces avg/high/low exactly for 7 of 8 varieties (PS avg
    differs by 13 yuan, a source-data revision artifact). A 90-entry
    window matches none.
    """
    return stats_window(series, 91)


def stats_window(series, days):
    """avg/high/low over the last `days` entries (including the latest)."""
    window = series[-days:]
    prices = [p for _, p in window]
    return {
        "avg": round(sum(prices) / len(prices), 2),
        "hi": max(prices),
        "lo": min(prices),
        "n": len(prices),
    }


def percentile(series, days=365):
    """Share of days in the window whose price <= latest price, in percent."""
    window = series[-days:]
    latest = window[-1][1]
    le = sum(1 for _, p in window if p <= latest)
    return round(le / len(window) * 100, 1)


def temperature_label(pct):
    """Site rule: >=80 偏贵, <=20 偏便宜, else 正常."""
    if pct >= 80:
        return "偏贵"
    if pct <= 20:
        return "偏便宜"
    return "正常"


def pos_label(price, lo, hi):
    """Position label from where the price sits inside its range."""
    if hi <= lo:
        return "中位"
    r = (price - lo) / (hi - lo)
    if r >= 0.8:
        return "高位"
    if r >= 0.6:
        return "中高位"
    if r >= 0.4:
        return "中位"
    if r >= 0.2:
        return "中低位"
    return "低位"


def chg_pct(today, prev):
    if not prev:
        return 0.0
    return round((today / prev - 1) * 100, 2)


def fmt_chg(x):
    return f"{x:.2f}%"
