"""Render /grade/ pages (53 grades + the index).

Two page types, both driven by the parent variety's daily series:
- REF (45): an explainer page whose dynamic parts are the 90-day
  chart card, the 参考价 box and FAQ Q1 (parent benchmark price,
  daily change, 30-day change).
- BENCH (8): grades that ARE the benchmark spec (L5E89, SG-5,
  PET水瓶级, 7042, 5000S, 2426H, 0215A, GPPS 525). Price-page layout:
  dated title/H1/meta, a hero price card (price, change, update
  stamp, week/month changes, 3-month average), the chart card twice,
  FAQ Q1 with the spec wording and a month-direction FAQ.

Per-grade static facts (parent, display name, spec) are read from
each page's own sample at render time. Chart geometry fitted on the
2026-11-10 bundle: last 90 entries, axis = data range padded 8%
(labels rounded, point mapping on the unrounded axis), plot
x 58..628, y 14..212. Verified in tests/verify_grades.py.
"""
from __future__ import annotations

import re

from .compute import stats_3m
from .dataio import NAMES
from .render_history import _chg_span, _m_d, _stamps
from .spot import match_rows, quote_text, spec_key

SHORT = {"pp": "PP", "lldpe": "LLDPE", "hdpe": "HDPE", "ldpe": "LDPE",
         "pvc": "PVC", "abs": "ABS", "ps": "PS", "pet": "PET"}


def _f1(v):
    return f"{v:.1f}"


def chart_card(win, title):
    """The site's 640x240 line-chart card for a [(date, value)] window.

    `title` is used verbatim for the heading and the svg aria-label.
    Geometry: axis = data range padded 8% (labels rounded to ints,
    point mapping on the unrounded axis), plot x 58..628, y 14..212,
    max/min marked with red/green dots at their first occurrences.
    """
    prices = [p for _, p in win]
    dates = [d for d, _ in win]
    lo, hi = min(prices), max(prices)
    span = hi - lo
    amin_u, amax_u = lo - 0.08 * span, hi + 0.08 * span
    amin, amax = round(amin_u), round(amax_u)
    n = len(prices)

    def x(i):
        return 58 + i * 570 / (n - 1)

    def y(v):
        return 212 - (v - amin_u) * 198 / (amax_u - amin_u)

    pts = [f"{_f1(x(i))},{_f1(round(y(v), 1))}" for i, v in enumerate(prices)]
    svg = [f'<svg viewBox="0 0 640 240" width="100%" role="img" '
           f'aria-label="{title}">']
    for i in range(5):
        # gridline y goes through the axis mapping (its float path is
        # observable: PS lands on 163/63 where a pure 49.5-step
        # rounding would give 162/64)
        gv = amin_u + i * (amax_u - amin_u) / 4
        gy = round(212 - (gv - amin_u) * 198 / (amax_u - amin_u))
        label = int(round(amin + i * (amax - amin) / 4))
        svg.append(f'<line x1="58" x2="628" y1="{gy}" y2="{gy}" stroke="#8883"/>'
                   f'<text x="52" y="{gy + 4}" font-size="11" fill="#8a93a3" '
                   f'text-anchor="end">{label}</text>')
    poly = " ".join([f"58.0,212"] + pts + [f"{_f1(x(n - 1))},212"])
    svg.append(f'<polygon fill="currentColor" fill-opacity=".08" points="{poly}"/>')
    svg.append(f'<polyline fill="none" stroke="currentColor" stroke-width="2" '
               f'points="{" ".join(pts)}"/>')
    i_hi, i_lo = prices.index(hi), prices.index(lo)
    svg.append(f'<circle cx="{_f1(x(i_hi))}" cy="{_f1(round(y(hi), 1))}" r="3.5" fill="#d93025"/>')
    svg.append(f'<circle cx="{_f1(x(i_lo))}" cy="{_f1(round(y(lo), 1))}" r="3.5" fill="#188038"/>')
    mid = n // 2
    svg.append(f'<text x="58" y="232" font-size="11" fill="#8a93a3" text-anchor="start">{dates[0][5:]}</text>')
    svg.append(f'<text x="{round(x(mid))}" y="232" font-size="11" fill="#8a93a3" text-anchor="middle">{dates[mid][5:]}</text>')
    svg.append(f'<text x="628" y="232" font-size="11" fill="#8a93a3" text-anchor="end">{dates[-1][5:]}</text>')
    svg.append('</svg>')
    return (f'<div class="card"><b>{title}</b>'
            f'<span class="sub" style="float:right">高 {hi:.0f}（{dates[i_hi]}）· '
            f'低 {lo:.0f}（{dates[i_lo]}）</span>{"".join(svg)}</div>')


def grade_chart_card(series_parent, parent_name):
    return chart_card(series_parent[-90:],
                      f"{parent_name}近90天价格走势（元/吨）")


def _parent_slug(sample):
    m = re.search(r'<a href="/">首页</a> › <a href="/([a-z0-9-]+)/">', sample)
    return m.group(1)


def _changes(ent, today):
    dates = [d for d, _ in ent]
    i = dates.index(today)
    price = ent[i][1]
    chg = (price / ent[i - 1][1] - 1) * 100
    week = (price / ent[i - 7][1] - 1) * 100
    month = (price / ent[i - 30][1] - 1) * 100
    return price, chg, week, month


def render_grade(sample, series, today, updated, spot=None,
                 grade_slug=None):
    parent = _parent_slug(sample)
    pname = NAMES[parent]
    spot_rows = (spot or {}).get(parent) or []
    ent = series[parent]
    price, chg, week, month = _changes(ent, today)
    md = _m_d(today)
    card = grade_chart_card(ent, pname)
    h = re.sub(r'<div class="card"><b>' + re.escape(pname) +
               r'近90天价格走势（元/吨）</b>.*?</svg></div>',
               lambda m: card, sample, flags=re.S)
    if '规格计算' in h:  # BENCH price page
        disp = re.search(r'<h1>([^<]+?)价格今日（', h).group(1)
        spec = re.search(r'按 ([^<]+?) 规格计算', h).group(1)
        title = f"{disp}价格今日{md}_塑价365"
        desc = (f"{md}生意社{pname}基准价（按{spec}规格）{price:.0f}元/吨。"
                f"附{disp}物性、用途和近90天走势。")
        h = re.sub(r"<title>.*?</title>", f"<title>{title}</title>", h, count=1)
        for prop in ('name="description"', 'property="og:description"'):
            h = re.sub(rf'(<meta {prop} content=")[^"]*(")',
                       lambda m: m.group(1) + desc + m.group(2), h, count=1)
        h = re.sub(r'(<meta property="og:title" content=")[^"]*(")',
                   lambda m: m.group(1) + title + m.group(2), h, count=1)
        h = re.sub(r"<h1>[^<]+?价格今日（[^）]+）</h1>",
                   f"<h1>{disp}价格今日（{md}）</h1>", h, count=1)
        cls, ctxt = _chg_span(chg, 2)
        h = re.sub(r'<div class="big">\S+ <small style="font-size:16px">元/吨</small></div>',
                   f'<div class="big">{price:.0f} <small style="font-size:16px">元/吨</small></div>',
                   h, count=1)
        h = re.sub(r'(基准价按 [^<]+? 规格计算，今天 <b>)[^<]+(</b> 元/吨（)<span class="[^"]*">[^<]*</span>(），更新于 )[^<]+(。)',
                   rf'\g<1>{price:.0f}\g<2><span class="{cls}">{ctxt}</span>\g<3>{updated[parent]}\g<4>',
                   h, count=1)
        wcls, wtxt = _chg_span(week, 1)
        mcls, mtxt = _chg_span(month, 1)
        avg3 = int(round(stats_3m(ent)["avg"]))
        h = re.sub(r'(较一周前<b><span class=")[^"]*(">)[^<]*(</span></b></div>)',
                   rf'\g<1>{wcls}\g<2>{wtxt}\g<3>', h, count=1)
        h = re.sub(r'(较一月前<b><span class=")[^"]*(">)[^<]*(</span></b></div>)',
                   rf'\g<1>{mcls}\g<2>{mtxt}\g<3>', h, count=1)
        h = re.sub(r'(三个月均价<b>)[^<]+(</b>)', rf'\g<1>{avg3}\g<2>', h, count=1)
        faq1 = f"{md}生意社{pname}基准价（{spec}规格）{price:.0f}元/吨。"
        # FAQ wording has no 按 (the meta description does — don't touch it)
        h = re.sub(r'\d+月\d+日生意社' + re.escape(pname) + r'基准价（(?!按)[^）]+规格）\S+?元/吨。',
                   faq1, h)
        word = "上涨" if month > 0 else ("下跌" if month < 0 else "持平")
        mfaq = (f"按{pname}基准价，近一个月{word}{abs(month):.1f}%。"
                if month != 0 else f"按{pname}基准价，近一个月持平。")
        h = re.sub(r'按' + re.escape(pname) + r'基准价，近一个月[^<"]*。', mfaq, h)
        # spot quotes for this very spec, split by brand/market
        keys = {spec_key(spec)}
        if grade_slug:
            keys.add(grade_slug)
        matched = [r for r in spot_rows if spec_key(r["spec"]) in keys]
        if matched:
            box = (f'<div class="box"><b>{disp}分市场现货参考价</b>'
                   f'（{md}，生意社）<br>{quote_text(matched)}</div>')
            anchor = (f'<div class="card"><b>{pname}近90天价格走势'
                      f'（元/吨）</b>')
            if anchor in h:
                h = h.replace(anchor, box + anchor, 1)
    else:  # REF explainer page
        disp = re.search(r'<p>([^<]+?)没有公开的每日牌号报价。可参考同品种', h).group(1)
        cls, ctxt = _chg_span(chg, 2)
        mcls, mtxt = _chg_span(month, 1)
        matched = match_rows(spot_rows, spec_key(disp))
        if matched:
            # a real grade-level quote exists today: show it instead
            # of the no-public-quote wording
            h = re.sub(r'没有公开的每日牌号报价。可参考同品种生意社' + re.escape(pname) +
                       r'基准价：\d+月\d+日 \S+ 元/吨（<span class="[^"]*">[^<]*</span>），近一个月<span class="[^"]*">[^<]*</span>',
                       f'生意社现货参考价（{md}）：{quote_text(matched)}。'
                       f'同品种{pname}基准价 {price:.0f} 元/吨'
                       f'（<span class="{cls}">{ctxt}</span>），近一个月<span class="{mcls}">{mtxt}</span>',
                       h, count=1)
            faq1 = (f"{disp}现货参考价（{md}，生意社）：{quote_text(matched)}；"
                    f"同品种{pname}基准价{price:.0f}元/吨，"
                    f"实际成交价因厂家、地区、批量有升贴水。")
            h = re.sub(re.escape(disp) + r'没有公开的每日牌号报价，可参考\d+月\d+日生意社' +
                       re.escape(pname) + r'基准价\S+?元/吨；实际成交价因厂家、地区、批量有升贴水。',
                       faq1, h)
        else:
            h = re.sub(r'没有公开的每日牌号报价。可参考同品种生意社' + re.escape(pname) +
                       r'基准价：\d+月\d+日 \S+ 元/吨（<span class="[^"]*">[^<]*</span>），近一个月<span class="[^"]*">[^<]*</span>',
                       f'没有公开的每日牌号报价。可参考同品种生意社{pname}基准价：{md} {price:.0f} 元/吨'
                       f'（<span class="{cls}">{ctxt}</span>），近一个月<span class="{mcls}">{mtxt}</span>',
                       h, count=1)
            faq1 = (f"{disp}没有公开的每日牌号报价，可参考{md}生意社{pname}基准价"
                    f"{price:.0f}元/吨；实际成交价因厂家、地区、批量有升贴水。")
            h = re.sub(re.escape(disp) + r'没有公开的每日牌号报价，可参考\d+月\d+日生意社' +
                       re.escape(pname) + r'基准价\S+?元/吨；实际成交价因厂家、地区、批量有升贴水。',
                       faq1, h)
    return _stamps(h, today)


def render_grade_index(sample, series, today):
    h = sample
    for slug, name in NAMES.items():
        price = series[slug][-1][1]
        # anchor on <h2> so LDPE does not match inside LLDPE's heading
        h = re.sub(re.escape(f"<h2>{name}（今日 ") + r'\S+?( 元/吨）</h2>)',
                   f"<h2>{name}（今日 {price:.0f}" + r'\g<1>', h, count=1)
    return _stamps(h, today)
