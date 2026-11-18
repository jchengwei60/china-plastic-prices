"""Render the alerts page (/alerts/) and its RSS feed (/alerts.xml) by
structural substitution on the previous build.

The 2026-11-10 bundle page is the template; the 90-day event table, the
year counts, the "latest event" lines and every date stamp are
regenerated from the price series. Validated by re-rendering
2026-11-10 and diffing (tests/verify_alerts.py).

Alert rules (verified against the published page):
  * an alert is one variety's single-day change with |precise change|
    >= 2% (threshold on the precise value, as in render_rank).
  * the table lists the last 90 days' alerts (date > today - 90 days),
    newest first; same-day rows sort by |change| descending. This
    reproduces the published 48 rows, including the 2026-10-27 order
    PS +4.14% / ABS +3.94% / PP +3.26% / PVC -2.23%.
  * the "近一年异动次数" counts are per-variety totals over the whole
    loaded series, sorted by count descending with ties in SLUGS
    order. All 8 match the published page; a 365-calendar-day window
    does NOT reproduce it — it gives PS 16 instead of 17, because the
    series starts 2025-10-09 and PS had an alert on 2025-10-13, 393
    days before 2026-11-10. So the published counts are whole-history
    counts (the series is only ~13 months long, so "近一年" and whole
    history nearly coincide). If the history grows much longer, this
    should be revisited to a true 365-day window.
  * the RSS feed carries the 40 most recent alerts in the same order,
    each published at 10:00 +0800 on its date.
  * prices display integer-rounded; changes display with two decimals.
"""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta, timezone
from email.utils import format_datetime

from .dataio import NAMES, SLUGS

UP_COLOR = "#d4281f"
DN_COLOR = "#188038"
RSS_LIMIT = 40


def find_alerts(series):
    """All alerts, newest first; same-day rows by |change| descending.

    Each alert is {date, slug, prev, price, chg} with chg the precise
    (unrounded) percentage change.
    """
    out = []
    for slug in SLUGS:
        ser = series[slug]
        for i in range(1, len(ser)):
            d, price = ser[i]
            prev = ser[i - 1][1]
            chg = (price / prev - 1) * 100
            if abs(chg) >= 2:
                out.append({"date": d, "slug": slug, "prev": prev,
                            "price": price, "chg": chg})
    out.sort(key=lambda e: (e["date"], abs(e["chg"])), reverse=True)
    return out


def _fmt2(chg):
    """Signed two-decimal change; exact zero prints +0.00% (never -0.00%)."""
    r = round(chg, 2)
    if r == 0:
        r = 0.0
    return f"{r:+.2f}%"


def _latest_str(ev):
    verb = "上涨" if ev["chg"] > 0 else "下跌"
    # NB: the page writes "下跌 2.02%" with a space; the RSS title
    # writes "下跌2.02%" without one (see render_alerts_xml).
    return f'{ev["date"]} {NAMES[ev["slug"]]} 单日{verb} {abs(round(ev["chg"], 2)):.2f}%'


def _m_d(d):  # '2026-11-10' -> '11月10日'
    return f"{int(d[5:7])}月{int(d[8:10])}日"


def _price(p):
    return int(p + 0.5)


def _row(ev):
    color = UP_COLOR if ev["chg"] > 0 else DN_COLOR
    return (
        f'<tr><td>{ev["date"]}</td>'
        f'<td><a href="/{ev["slug"]}/">{NAMES[ev["slug"]]}</a></td>'
        f'<td>{_price(ev["prev"])} → {_price(ev["price"])}</td>'
        f'<td class="n" style="color:{color};font-weight:600">'
        f'{_fmt2(ev["chg"])}</td></tr>'
    )


def render_alerts(ctx, sample, series):
    h = sample
    today = ctx["today"]
    today_d = date.fromisoformat(today)
    date_s = _m_d(today)
    alerts = find_alerts(series)
    recent = [e for e in alerts if date.fromisoformat(e["date"]) > today_d - timedelta(days=90)]
    latest = _latest_str(alerts[0])
    counts = {}
    for ev in alerts:
        counts[ev["slug"]] = counts.get(ev["slug"], 0) + 1
    order = sorted(SLUGS, key=lambda s: (-counts.get(s, 0), SLUGS.index(s)))

    # meta description + og:description ("最近一次：…" sentence)
    h = re.sub(r"最近一次：[^。]*。", f"最近一次：{latest}。", h)
    # article modified time + Dataset dateModified
    h = re.sub(r'(article:modified_time" content=")\d{4}-\d{2}-\d{2}(T15:00:00\+08:00")',
               rf"\g<1>{today}\g<2>", h, count=1)
    h = re.sub(r'("dateModified": ")\d{4}-\d{2}-\d{2}(")',
               rf"\g<1>{today}\g<2>", h, count=1)
    # nav stamp
    h = re.sub(r">\d+月\d+日已更新 ·", f">{date_s}已更新 ·", h, count=1)
    # sub line
    sub = (f"单日涨跌 ≥ 2% 的记录，按生意社品种基准价计算，每天更新。"
           f"最近一次：{latest}。近90天共 {len(recent)} 次单日涨跌超过2%。")
    h = re.sub(r'<div class="sub">单日涨跌 ≥ 2%.*?</div>',
               f'<div class="sub">{sub}</div>', h, count=1, flags=re.S)
    # year counts grid
    grid = "　".join(
        f'<a href="/{s}/">{NAMES[s]}</a> {counts.get(s, 0)}次' for s in order)
    h = re.sub(r'(近一年异动次数</b><div style="margin-top:6px">).*?(</div>)',
               rf"\g<1>{grid}\g<2>", h, count=1, flags=re.S)
    # 90-day table
    table = (
        '<table style="width:100%"><tr><th>日期</th><th>品种</th>'
        '<th>前一日 → 当日（元/吨）</th><th class="n">涨跌</th></tr>'
        + "".join(_row(e) for e in recent) + "</table>"
    )
    h = re.sub(r'<table style="width:100%"><tr><th>日期</th>.*?</table>',
               table, h, count=1, flags=re.S)
    # footer date
    h = re.sub(r"整理于 \d{4}-\d{2}-\d{2}", f"整理于 {today}", h)
    return h


def render_alerts_xml(series):
    """The /alerts.xml RSS feed: the 40 most recent alerts."""
    alerts = find_alerts(series)[:RSS_LIMIT]
    items = []
    for ev in alerts:
        d = ev["date"]
        verb = "上涨" if ev["chg"] > 0 else "下跌"
        pub = format_datetime(
            datetime.fromisoformat(d).replace(
                hour=10, tzinfo=timezone(timedelta(hours=8))))
        items.append(
            f'<item><title>{NAMES[ev["slug"]]} {d} 单日{verb}'
            f'{abs(round(ev["chg"], 2)):.2f}%</title>'
            f'<link>https://pla365.com/{ev["slug"]}/</link>'
            f'<guid isPermaLink="false">pla365-{ev["slug"]}-{d}</guid>'
            f'<pubDate>{pub}</pubDate>'
            f'<description>{NAMES[ev["slug"]]}生意社基准价 '
            f'{_price(ev["prev"])} → {_price(ev["price"])} 元/吨'
            f'（{_fmt2(ev["chg"])}）</description></item>'
        )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<rss version="2.0"><channel>'
        '<title>塑价365 塑料价格异动</title>'
        '<link>https://pla365.com/alerts/</link>'
        '<description>国内塑料原料单日涨跌超过2%的提醒（生意社品种基准价）</description>'
        + "".join(items) + "</channel></rss>"
    )
