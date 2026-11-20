"""Render the ranking page (/rank/) by structural substitution on the
previous build.

The 2026-11-10 bundle page is the template; the four ranking panels
(day / week / month / year) are regenerated from the price series, and
every date stamp, summary line, FAQ answer and JSON-LD list follows
from the same rankings. Validated by re-rendering 2026-11-10 and
diffing (tests/verify_rank.py).

Ranking rules (verified against the published page):
  * windows are entries back in the daily series: day 1, week 7,
    month 30, year 365 (the FAQ states the same windows).
  * rows sort by the precise (unrounded) change, descending; ties keep
    the SLUGS order. This reproduces the published order, including
    the week tie where HDPE (-3.75%) ranks above LLDPE (-3.78%)
    although both display as -3.8%.
  * changes display to one decimal; prices are integer-rounded.
"""
from __future__ import annotations

import json
import re

from .dataio import NAMES, SLUGS

WINDOWS = [
    (0, "日榜", "日涨跌", 1),
    (1, "周榜", "近一周", 7),
    (2, "月榜", "近一月", 30),
    (3, "年榜", "近一年", 365),
]


def _md(date):  # '2026-11-10' -> ('11', '10')
    return date[5:7], date[8:10]


def _m_d(date):  # -> '11月10日'
    m, d = _md(date)
    return f"{int(m)}月{int(d)}日"


def _fmt1(chg):
    """Signed one-decimal change; exact zero prints +0.0% (never -0.0%)."""
    r = round(chg, 1)
    if r == 0:
        r = 0.0
    return f"{r:+.1f}%"


def _cls(chg):
    r = round(chg, 1)
    return "up" if r > 0 else ("dn" if r < 0 else "")


def _rankings(series):
    """{panel_index: [(slug, price, precise_chg), ...]} sorted desc."""
    out = {}
    for idx, _, _, back in WINDOWS:
        rows = []
        for slug in SLUGS:
            ser = series[slug]
            price = ser[-1][1]
            prev = ser[-1 - back][1]
            rows.append((slug, price, (price / prev - 1) * 100))
        rows.sort(key=lambda r: -r[2])  # stable: ties keep SLUGS order
        out[idx] = rows
    return out


def _table(label, ranking):
    rows = (
        f'<tr><th>排名</th><th>品种</th><th class="n">价格</th>'
        f'<th class="n">{label}</th></tr>'
    )
    for i, (slug, price, chg) in enumerate(ranking, 1):
        rows += (
            f'<tr><td>{i}</td><td><a href="/{slug}/">{NAMES[slug]}</a></td>'
            f'<td class="n">{int(price + 0.5)}</td>'
            f'<td class="n"><span class="{_cls(chg)}">{_fmt1(chg)}</span></td></tr>'
        )
    return f"<table>{rows}</table>"


def _leader(ranking, which):
    slug, _, chg = ranking[0] if which == "max" else ranking[-1]
    return f"{NAMES[slug]} {_fmt1(chg)}"


def render_rank(ctx, sample, series):
    h = sample
    today = ctx["today"]
    date_s = _m_d(today)
    rankings = _rankings(series)
    day, week, month = rankings[0], rankings[1], rankings[2]

    week_max = _leader(week, "max")
    week_min = _leader(week, "min")
    month_max = _leader(month, "max")
    month_min = _leader(month, "min")
    day_max = _leader(day, "max")

    # title / meta / og
    title = f"塑料价格涨跌榜{date_s}_近7日涨跌幅_塑价365"
    h = re.sub(r"<title>[^<]*</title>", f"<title>{title}</title>", h, count=1)
    meta = (f"{date_s}国内8大塑料品种涨跌幅排行：日涨跌、近一周、近一月、近一年。"
            f"近一周涨得最多：{week_max}；跌得最多：{week_min}。")
    h = re.sub(r'(<meta name="description" content=")[^"]*(")',
               rf"\g<1>{meta}\g<2>", h, count=1)
    h = re.sub(r'(<meta property="og:title" content=")[^"]*(")',
               rf"\g<1>{title}\g<2>", h, count=1)
    h = re.sub(r'(<meta property="og:description" content=")[^"]*(")',
               rf"\g<1>{meta}\g<2>", h, count=1)
    h = re.sub(r'(article:modified_time" content=")\d{4}-\d{2}-\d{2}(T15:00:00\+08:00")',
               rf"\g<1>{today}\g<2>", h, count=1)
    # header stamp + h1 + sub line
    h = re.sub(r">\d+月\d+日已更新 ·", f">{date_s}已更新 ·", h, count=1)
    h = re.sub(r"<h1>塑料价格涨跌榜（\d{4}-\d{2}-\d{2}）</h1>",
               f"<h1>塑料价格涨跌榜（{today}）</h1>", h, count=1)
    sub = (f"近一周涨得最多：{week_max}；跌得最多：{week_min}。"
           f"近一月领涨：{month_max}。按生意社基准价计算，每天更新。"
           f'单日涨跌超过2%的记录见<a href="/alerts/">价格异动</a>。')
    h = re.sub(r'<div class="sub">.*?</div>', f'<div class="sub">{sub}</div>',
               h, count=1, flags=re.S)
    # four ranking panels
    for idx, _, label, _ in WINDOWS:
        h = re.sub(rf'(<div class="pn" id="pn{idx}">.*?)<table>.*?</table>',
                   rf"\g<1>{_table(label, rankings[idx])}",
                   h, count=1, flags=re.S)
    # FAQ cards
    q1 = f"{date_s}塑料哪个品种涨得最多？"
    a1 = f"日涨幅最大：{day_max}；近一周：{week_max}；近一月：{month_max}。"
    h = re.sub(r'<div class="card"><b>\d+月\d+日塑料哪个品种涨得最多？</b><p>.*?</p></div>',
               f'<div class="card"><b>{q1}</b><p>{a1}</p></div>',
               h, count=1, flags=re.S)
    h = re.sub(r'<div class="card"><b>近一个月塑料哪个品种跌得最多？</b><p>.*?</p></div>',
               f'<div class="card"><b>近一个月塑料哪个品种跌得最多？</b><p>{month_min}。</p></div>',
               h, count=1, flags=re.S)
    # JSON-LD: week ItemList + FAQ answers
    def fix_ld(m):
        try:
            data = json.loads(m.group(1))
        except json.JSONDecodeError:
            return m.group(0)
        if data.get("@type") == "ItemList":
            data["itemListElement"] = [
                {"@type": "ListItem", "position": i + 1,
                 "name": NAMES[slug],
                 "url": f"https://pla365.com/{slug}/"}
                for i, (slug, _, _) in enumerate(week)
            ]
        elif data.get("@type") == "FAQPage":
            for ent in data.get("mainEntity", []):
                name = ent.get("name", "")
                if "哪个品种涨得最多" in name:
                    ent["name"] = q1
                    ent["acceptedAnswer"]["text"] = a1
                elif "跌得最多" in name:
                    ent["acceptedAnswer"]["text"] = f"{month_min}。"
        return ('<script type="application/ld+json">'
                + json.dumps(data, ensure_ascii=False) + "</script>")
    h = re.sub(r'<script type="application/ld\+json">(\{[^<]*\})</script>',
               fix_ld, h)
    # footer date
    h = re.sub(r"整理于 \d{4}-\d{2}-\d{2}", f"整理于 {today}", h)
    return h
