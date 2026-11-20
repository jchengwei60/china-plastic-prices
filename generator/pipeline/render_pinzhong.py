"""Render the variety index page (/pinzhong/) by structural substitution
on the previous build.

The 2026-11-10 bundle page is the template; the 15 variety cards are
regenerated from the render context with the same card builder as the
homepage (render_home._card), and the date stamps move to the new day.
The "常用牌号" section is static grade-page links and is carried over
unchanged. Validated by re-rendering 2026-11-10 and diffing
(tests/verify_pinzhong.py); a same-date re-render should be
byte-identical.
"""
from __future__ import annotations

import re

from .render_home import _card


def _md(date):  # '2026-11-10' -> ('11', '10')
    return date[5:7], date[8:10]


def _m_d(date):  # -> '11月10日'
    m, d = _md(date)
    return f"{int(m)}月{int(d)}日"


def render_pinzhong(ctx, sample):
    h = sample
    today = ctx["today"]
    date_s = _m_d(today)
    # Title targets 今日报价表, the highest-frequency modifier in the
    # Baidu dropdown research (2026-11-20); this page is the site's
    # quote table, no other page carried the term.
    title = f"塑料价格今日报价表{date_s}_15个品种价格大全_塑价365"
    h = re.sub(r"<title>[^<]*</title>", f"<title>{title}</title>",
               h, count=1)
    h = re.sub(r'(<meta property="og:title" content=")[^"]*(")',
               rf"\g<1>{title}\g<2>", h, count=1)
    meta = (f"{date_s}塑料价格今日报价表：国内15个塑料品种今日价格、"
            f"涨跌和近一年区间，以及各品种常用牌号价格页。")
    # meta description + og:description (same text in both)
    h = re.sub(r'(<meta name="description" content=")[^"]*(")',
               rf"\g<1>{meta}\g<2>", h, count=1)
    h = re.sub(r'(<meta property="og:description" content=")[^"]*(")',
               rf"\g<1>{meta}\g<2>", h, count=1)
    # nav stamp + h1 date
    h = re.sub(r">\d+月\d+日已更新 ·", f">{date_s}已更新 ·", h, count=1)
    h = re.sub(r"<h1>塑料品种价格（\d{4}-\d{2}-\d{2}）</h1>",
               f"<h1>塑料品种价格（{today}）</h1>", h, count=1)
    # article modified time: date moves, 15:00 publish time kept
    h = re.sub(r'(article:modified_time" content=")\d{4}-\d{2}-\d{2}(T15:00:00\+08:00")',
               rf"\g<1>{today}\g<2>", h, count=1)
    # variety cards: 8 mains, then 7 board extras
    for v in ctx["mains"]:
        h = re.sub(rf'<a class="cd" href="/{v["slug"]}/" data-s="{v["slug"]}">.*?</a>',
                   _card(v), h, count=1, flags=re.S)
    for v in ctx["extras"]:
        h = re.sub(rf'<a class="cd" href="/{v["slug"]}/" data-s="{v["slug"]}">.*?</a>',
                   _card(v, extra=True), h, count=1, flags=re.S)
    # footer date
    h = re.sub(r"整理于 \d{4}-\d{2}-\d{2}", f"整理于 {today}", h, count=1)
    return h
