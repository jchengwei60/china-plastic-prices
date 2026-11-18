"""Read/write the pla365 data files (repo formats + site /data formats).

Formats (all verified against the 2026-11-10 published files):
  history.csv  wide: date,pp,lldpe,hdpe,ldpe,pvc,abs,ps,pet (daily, 2025-10-09..)
  latest.json  {date, items: [{slug, name, price, chg, updated, avg3m,
               hi3m, lo3m, pos1y, pos2y, spot, source}]}
  latest.csv   long, cumulative since 2026-10-09, integer-rounded values
  daily/YYYY-MM-DD.json  same payload as latest.json for that day
"""
from __future__ import annotations

import csv
import io
import json

from .compute import chg_pct, fmt_chg, percentile, pos_label, stats_3m

SLUGS = ["pp", "lldpe", "hdpe", "ldpe", "pvc", "abs", "ps", "pet"]
NAMES = {
    "pp": "PP拉丝", "lldpe": "LLDPE", "hdpe": "HDPE", "ldpe": "LDPE",
    "pvc": "PVC SG-5", "abs": "ABS", "ps": "PS", "pet": "PET",
}
SOURCES = {
    "pp": "https://www.100ppi.com/rawmex/detail-718.html",
    "lldpe": "https://www.100ppi.com/rawmex/detail-435.html",
    "hdpe": "https://www.100ppi.com/rawmex/detail-295.html",
    "ldpe": "https://www.100ppi.com/rawmex/detail-334.html",
    "pvc": "https://www.100ppi.com/rawmex/detail-107.html",
    "abs": "https://www.100ppi.com/rawmex/detail-713.html",
    "ps": "https://www.100ppi.com/rawmex/detail-465.html",
    "pet": "https://www.100ppi.com/rawmex/detail-173.html",
}


def load_history(text):
    """Parse wide history.csv text into {slug: [(date, price), ...]}."""
    series = {s: [] for s in SLUGS}
    for row in csv.DictReader(io.StringIO(text)):
        for s in SLUGS:
            if row.get(s):
                series[s].append((row["date"], float(row[s])))
    return series


def dump_history(series):
    dates = [d for d, _ in series[SLUGS[0]]]
    by_date = {s: dict(series[s]) for s in SLUGS}
    out = io.StringIO()
    w = csv.writer(out, lineterminator="\n")
    w.writerow(["date"] + SLUGS)
    for d in dates:
        w.writerow([d] + [f"{by_date[s][d]:.2f}" for s in SLUGS])
    return out.getvalue()


def build_latest(series, updated):
    """Build the latest.json payload. `updated`: {slug: 'MM-DD HH:MM'}."""
    items = []
    date = series[SLUGS[0]][-1][0]
    for s in SLUGS:
        ser = series[s]
        price = ser[-1][1]
        prev = ser[-2][1] if len(ser) > 1 else price
        st = stats_3m(ser)
        win1y = ser[-365:]
        win_all = ser
        items.append({
            "slug": s,
            "name": NAMES[s],
            "price": price,
            "chg": fmt_chg(chg_pct(price, prev)),
            "updated": updated.get(s, ""),
            "avg3m": st["avg"],
            "hi3m": st["hi"],
            "lo3m": st["lo"],
            "pos1y": pos_label(price, min(p for _, p in win1y), max(p for _, p in win1y)),
            "pos2y": pos_label(price, min(p for _, p in win_all), max(p for _, p in win_all)),
            "spot": [],
            "source": SOURCES[s],
        })
    return {"date": date, "items": items}


def latest_csv_rows(payload):
    """One day's rows for the cumulative latest.csv (integer-rounded)."""
    rows = []
    for it in payload["items"]:
        rows.append([
            payload["date"], it["name"], f"{it['price']:.0f}", it["chg"],
            f"{it['avg3m']:.0f}", f"{it['hi3m']:.0f}", f"{it['lo3m']:.0f}",
            it["source"],
        ])
    return rows


def dump_json(payload):
    return json.dumps(payload, ensure_ascii=False, indent=1)
