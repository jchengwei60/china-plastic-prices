"""Basis (期现基差) data layer: the sf_basis series and its charts.

Series rows: {date, spot, contract, close, basis} per variety, where
basis = 生意社品种基准价 - 期货主力收盘 (the site's unified caliber
since the 2026-11 redesign; before that this series already existed
as the reference section of /basis/).
"""
from __future__ import annotations

import csv
import io

SLUGS = ["pp", "lldpe", "pvc", "pet"]
BOX_NAMES = {
    "pp": "PP（聚丙烯）",
    "lldpe": "PE（LLDPE线性）",
    "pvc": "PVC",
    "pet": "PET瓶片",
}
HEADER = ["日期", "品种", "生意社品种基准价", "主力合约", "主力合约价", "基差(基准价-主力)"]


def load_sf_basis(text):
    series = {s: [] for s in SLUGS}
    for row in csv.reader(io.StringIO(text.lstrip("\ufeff"))):
        if not row or row[0] == "日期":
            continue
        d, slug, spot, contract, close, basis = row
        series[slug].append({
            "date": d, "spot": float(spot), "contract": contract,
            "close": float(close), "basis": float(basis),
        })
    for s in SLUGS:
        series[s].sort(key=lambda r: r["date"])
    return series


def dump_sf_basis(series):
    out = io.StringIO()
    w = csv.writer(out, lineterminator="\n")
    w.writerow(HEADER)
    for slug in SLUGS:
        for r in series[slug]:
            w.writerow([r["date"], slug, _num(r["spot"]), r["contract"],
                        _num(r["close"]), _num(r["basis"])])
    return "\ufeff" + out.getvalue()


def _num(x):
    return str(int(x)) if float(x) == int(x) else str(x)


def append_basis_row(series, slug, date, spot, contract, close):
    """Add one trading day (idempotent: replaces a same-date row)."""
    basis = round(spot - close)
    rows = [r for r in series[slug] if r["date"] != date]
    rows.append({"date": date, "spot": spot, "contract": contract,
                 "close": close, "basis": float(basis)})
    rows.sort(key=lambda r: r["date"])
    series[slug] = rows


def stats(rows):
    last, prev = rows[-1], rows[-2]
    return {
        "last": last, "prev": prev,
        "delta": last["basis"] - prev["basis"],
        "count": len(rows),
        "first_date": rows[0]["date"],
        "min": min(r["basis"] for r in rows),
        "max": max(r["basis"] for r in rows),
    }


def fmt_signed(v, comma=True):
    if v == 0:
        return "0"
    return f"{v:+,.0f}" if comma else f"{v:+.0f}"


def _round_half_away(x):
    import math
    return math.floor(x + 0.5) if x >= 0 else -math.floor(-x + 0.5)


def chart_axis(vals, include_zero=True):
    """Axis rule reverse-engineered from the 2026-11-10 bundle and
    verified on all four variety charts: take the data range (zero
    included when include_zero), expand by 5% of the span each side,
    round to integers."""
    lo = min(min(vals), 0.0) if include_zero else min(vals)
    hi = max(max(vals), 0.0) if include_zero else max(vals)
    span = hi - lo
    return _round_half_away(lo - 0.05 * span), _round_half_away(hi + 0.05 * span)


def small_chart(rows, days=120):
    """The 320x120 variety chart. Geometry verified against the bundle:
    plot y in [12, 98], x spread over 44..314, zero line dashed.
    (A few published points differ by 0.1-0.2px from any linear fit -
    the old chart was drawn from pre-revision spot values.)"""
    win = rows[-days:]
    vals = [r["basis"] for r in win]
    amin, amax = chart_axis(vals)
    k = 86 / (amax - amin)
    def y(v):
        return 98 - (v - amin) * k
    n = len(win)
    pts = " ".join(
        f"{44 + i * 270 / (n - 1):.1f},{y(v):.1f}" for i, v in enumerate(vals))
    def short(d):
        return d[2:]
    return (
        '<svg viewBox="0 0 320 120" width="100%" role="img" aria-label="基差走势">'
        f'<text x="40" y="102" font-size="10" fill="#8a93a3" text-anchor="end">{amin:,}</text>'
        f'<text x="40" y="16" font-size="10" fill="#8a93a3" text-anchor="end">{amax:,}</text>'
        f'<line x1="44" x2="314" y1="{y(0):.1f}" y2="{y(0):.1f}" stroke="#8883" stroke-dasharray="3,3"/>'
        f'<polyline fill="none" stroke="var(--brand)" stroke-width="1.6" points="{pts}"/>'
        f'<text x="44" y="116" font-size="10" fill="#8a93a3">{short(win[0]["date"])}</text>'
        f'<text x="314" y="116" font-size="10" fill="#8a93a3" text-anchor="end">{short(win[-1]["date"])}</text>'
        '</svg>'
    )


def big_chart(rows, days=120):
    """Hero chart for the PP basis (640x250, same visual family as the
    old T30S chart: 5 gridlines, red dashed 800-yuan reference line)."""
    win = rows[-days:]
    vals = [r["basis"] for r in win]
    amin, amax = chart_axis(vals, include_zero=False)
    span = amax - amin
    def y(v):
        return 222 - (v - amin) * 208 / span
    n = len(win)
    pts = " ".join(
        f"{58 + i * 570 / (n - 1):.1f},{y(v):.1f}" for i, v in enumerate(vals))
    grid = ""
    for i in range(5):
        gv = amin + span * i / 4
        gy = 222 - 52 * i
        grid += (f'<line x1="58" x2="628" y1="{gy}" y2="{gy}" stroke="#8883"/>'
                 f'<text x="52" y="{gy + 4}" font-size="11" fill="#8a93a3" text-anchor="end">{gv:,.0f}</text>')
    ref = ""
    if amin < 800 < amax:
        ref = (f'<line x1="58" x2="628" y1="{y(800):.1f}" y2="{y(800):.1f}" '
               f'stroke="#d93025" stroke-dasharray="5,4"/>')
    def md(d):
        return d[5:]
    mid = win[n // 2]
    dates = (
        f'<text x="58" y="244" font-size="11" fill="#8a93a3">{md(win[0]["date"])}</text>'
        f'<text x="343" y="244" font-size="11" fill="#8a93a3" text-anchor="middle">{md(mid["date"])}</text>'
        f'<text x="628" y="244" font-size="11" fill="#8a93a3" text-anchor="end">{md(win[-1]["date"])}</text>'
    )
    return (
        '<svg viewBox="0 0 640 250" width="100%" role="img" aria-label="PP期现基差走势">'
        + grid + ref
        + f'<polyline fill="none" stroke="var(--brand)" stroke-width="1.6" points="{pts}"/>'
        + dates + '</svg>'
    )
