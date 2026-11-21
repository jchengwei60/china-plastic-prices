"""Build the render context shared by all page renderers.

Inputs:
  series   {slug: [(date, price), ...]} for the 8 main varieties (incl. today)
  extras   list of dicts for the 7 board varieties:
           {slug, name, series: [(date, price), ...]} (their own records)
  futures  {slug: {close, chg, date}} for pp/lldpe/pvc/pet (latest close)
  today    'YYYY-MM-DD' (the benchmark date being published)
  updated  {slug: 'MM-DD HH:MM'} source update stamps for the 8 mains
"""
from __future__ import annotations

from .compute import chg_pct, percentile, pos_label, temperature_label
from .dataio import NAMES

FUT_ROWS = [
    ("pp", "聚丙烯PP", "大商所"),
    ("lldpe", "塑料LLDPE", "大商所"),
    ("pvc", "PVC", "大商所"),
    ("pet", "瓶片PR", "郑商所"),
]


def fmt_int(x):
    return f"{x:,.0f}"


def sparkline(series, days=30):
    """SVG polyline points for the last `days` entries (canonical mapping
    verified against the 2026-11-10 bundle: y = 29 - (p-min)/(max-min)*26,
    x spread over 0..120). Returns (points_str, direction)."""
    win = series[-days:]
    prices = [p for _, p in win]
    if len(prices) < 2:
        return "", "up"
    lo, hi = min(prices), max(prices)
    n = len(prices)
    pts = []
    for i, p in enumerate(prices):
        x = i * 120 / (n - 1)
        y = 29 - (p - lo) / (hi - lo) * 26 if hi > lo else 16.0
        pts.append(f"{x:.1f},{y:.1f}")
    direction = "dn" if prices[-1] < prices[0] else "up"
    return " ".join(pts), direction


def _chg_cls(chg):
    return "up" if chg > 0 else ("dn" if chg < 0 else "fl")


def _temp_cls(temp):
    return {"偏贵": "hot", "偏便宜": "cold"}.get(temp, "mid")


# Board varieties promoted to the mains' statistical treatment
# (365-day window percentile, no sparse-basis star): their series
# are gap-filled to daily density in the state (PC, 2026-11-21).
PROMOTED = {"pc"}


def variety_view(slug, name, series, sample_days=None):
    """All display values for one variety card / row."""
    price = series[-1][1]
    prev = series[-2][1] if len(series) > 1 else price
    chg = chg_pct(price, prev)
    win = series[-365:]
    lo = min(p for _, p in win)
    hi = max(p for _, p in win)
    pct = percentile(series, 365) if sample_days is None else percentile(series, len(series))
    pts, direction = sparkline(series)
    week_ago = series[-8][1] if len(series) > 7 else series[0][1]
    return {
        "slug": slug, "name": name, "price": price,
        "price_card": fmt_int(price),
        "chg": chg, "chg_str": f"{chg:+.2f}%" if chg > 0 else f"{chg:.2f}%",
        "chg_cls": _chg_cls(chg),
        "temp": temperature_label(pct), "temp_cls": _temp_cls(temperature_label(pct)),
        "pct": int(round(pct)),
        "lo": lo, "hi": hi, "lo_s": fmt_int(lo), "hi_s": fmt_int(hi),
        "pos_pct": int(round((price - lo) / (hi - lo) * 100)) if hi > lo else 50,
        "spark": pts, "spark_dir": direction,
        "weekly_chg": chg_pct(price, week_ago),
        "days": sample_days if sample_days is not None else len(win),
        "sparse": sample_days is not None,
        "start": series[0][0][5:] if series else "",
    }


def build_context(series, extras, futures, today, updated):
    mains = [variety_view(s, NAMES[s], series[s]) for s in
             ["pp", "lldpe", "hdpe", "ldpe", "pvc", "abs", "ps", "pet"]]
    extra_views = []
    for ex in extras:
        if ex["slug"] in PROMOTED:
            v = variety_view(ex["slug"], ex["name"], ex["series"])
        else:
            v = variety_view(ex["slug"], ex["name"], ex["series"],
                             sample_days=len(ex["series"]))
        extra_views.append(v)
    fut_date = futures["pp"]["date"]
    fut_rows = []
    for slug, disp, exch in FUT_ROWS:
        f = futures[slug]
        # spot benchmark on the futures date (last record on/before it)
        spot = None
        for d, p in series[slug]:
            if d <= fut_date:
                spot = p
            else:
                break
        fut_rows.append({
            "slug": slug, "disp": disp, "exch": exch,
            "close": f["close"], "chg": f["chg"], "spot": spot,
            "basis": int(round(spot - f["close"])),
        })
    pp = mains[0]
    pp_basis = fut_rows[0]["basis"]
    hot = [v for v in mains if v["temp"] == "偏贵"]
    hot_sorted = sorted(hot, key=lambda v: -v["pct"])
    return {
        "today": today,
        "mains": mains,
        "extras": extra_views,
        "futures": fut_rows,
        "fut_date": fut_date,
        "pp": pp,
        "pp_basis": pp_basis,
        "pp_updated": updated.get("pp", ""),
        "updated": updated,
        "hot_count": len(hot),
        "hot_names": [v["name"] for v in hot_sorted],
        "risers": sum(1 for v in mains if v["chg"] > 0),
        "alerts": [v for v in mains if abs(v["chg"]) >= 2],
    }
