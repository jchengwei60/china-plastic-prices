"""Render /spread/ pages: 4 variety-pair spreads + the index.

Spread = daily difference of two varieties' 生意社 benchmark prices.
"近一年" is the last 366 entries (a year ago = the window's first
entry); percentile = share of window days with spread <= today's,
position bands at 80/20 like the site's temperature rule. Verified
against the 2026-11-10 bundle in tests/verify_spread.py.
"""
from __future__ import annotations

import re

from .dataio import NAMES
from .render_grades import chart_card
from .render_history import _m_d, _stamps

PAIRS = [("pp-lldpe", "pp", "lldpe"), ("hdpe-lldpe", "hdpe", "lldpe"),
         ("ldpe-lldpe", "ldpe", "lldpe"), ("abs-ps", "abs", "ps")]


def spread_series(series, a, b):
    bd = dict(series[b])
    return [(d, p - bd[d]) for d, p in series[a]]


def spread_stats(ent, today):
    dates = [d for d, _ in ent]
    i = dates.index(today)
    win = [v for _, v in ent[i - 365: i + 1]]
    cur = ent[i][1]
    pct = int(round(100 * sum(1 for v in win if v <= cur) / len(win)))
    return {
        "cur": cur,
        "month_ago": ent[i - 30][1],
        "year_ago": ent[i - 365][1],
        "mean": sum(win) / len(win),
        "pct": pct,
        "band": "偏高" if pct >= 80 else ("偏低" if pct <= 20 else "中间"),
    }


def narrative(today, a_name, b_name, st):
    cur = st["cur"]
    if cur > 0:
        rel = f"比{b_name}高{cur:,.0f}元/吨"
    elif cur < 0:
        rel = f"比{b_name}低{-cur:,.0f}元/吨"
    else:
        rel = f"与{b_name}价格相同"
    return (f"截至{today}，生意社{a_name}基准价{rel}，"
            f"近一年均值{st['mean']:,.0f}元/吨，当前处在近一年{st['band']}位置"
            f"（高于近一年{st['pct']}%的日子）。")


def _advice(a_name, b_name, band):
    if band == "偏高":
        return (f"价差偏大时，能用{b_name}的产品可以考虑多用{b_name}或提高配比，"
                f"先小批量试产确认性能。")
    if band == "偏低":
        return (f"价差偏小时，{a_name}相对划算，原本用{b_name}的产品可以评估"
                f"改用或多配{a_name}。")
    return "价差处于正常区间，换料的成本优势不明显，按产品性能选料即可。"


def render_spread(sample, series, a, b, today):
    a_name, b_name = NAMES[a], NAMES[b]
    ent = spread_series(series, a, b)
    st = spread_stats(ent, today)
    nar = narrative(today, a_name, b_name, st)
    h = sample
    h = re.sub(r"(<h1>[^<]+?价差今日多少？（)[^）]+(）</h1>)",
               rf"\g<1>{_m_d(today)}\g<2>", h, count=1)
    h = re.sub(r'<div class="big">[+-]?[\d,]+ <small style="font-size:16px">元/吨</small></div>',
               f'<div class="big">{st["cur"]:+,.0f} <small style="font-size:16px">元/吨</small></div>',
               h, count=1)
    h = re.sub(r'(，生意社品种基准价，)\d{4}-\d{2}-\d{2}',
               rf'\g<1>{today}', h, count=1)
    grid = (f'<div>一个月前<b>{st["month_ago"]:+,.0f}</b></div>'
            f'<div>一年前<b>{st["year_ago"]:+,.0f}</b></div>'
            f'<div>近一年均值<b>{st["mean"]:+,.0f}</b></div>'
            f'<div>近一年区间<b>{min(v for _, v in ent[-366:]):+,.0f} ~ '
            f'{max(v for _, v in ent[-366:]):+,.0f}</b></div>'
            f'<div>历史分位<b>{st["pct"]}%</b></div>')
    h = re.sub(r'<div>一个月前<b>.*?</div><div>一年前<b>.*?</div><div>近一年均值<b>.*?</div>'
               r'<div>近一年区间<b>.*?</div><div>历史分位<b>.*?</div>',
               grid, h, count=1, flags=re.S)
    h = re.sub(r'截至\d{4}-\d{2}-\d{2}，生意社[^<"]*?（高于近一年\d+%的日子）。', nar, h)
    h = re.sub(r'(对工厂选料的参考</b><p>)[^<]*(</p>)',
               lambda m: m.group(1) + _advice(a_name, b_name, st["band"]) + m.group(2),
               h, count=1)
    for prop in ('name="description"', 'property="og:description"'):
        h = re.sub(rf'(<meta {prop} content=")[^"]*(")',
                   lambda m: m.group(1) + nar + m.group(2), h, count=1)
    year_card = chart_card(ent[-366:], f"{a_name}−{b_name}价差近一年走势（元/吨）")
    h = re.sub(r'<div class="card"><b>' + re.escape(a_name) + '−' + re.escape(b_name) +
               r'价差近一年走势（元/吨）</b>.*?</svg></div>',
               lambda m: year_card, h, count=1, flags=re.S)
    d90_card = chart_card(ent[-90:], "近90天价差（元/吨）")
    h = re.sub(r'<div class="card"><b>近90天价差（元/吨）</b>.*?</svg></div>',
               lambda m: d90_card, h, count=1, flags=re.S)
    return _stamps(h, today)


def render_spread_index(sample, series, today):
    h = re.sub(r'(<h1>塑料品种价差（)\d{4}-\d{2}-\d{2}(）</h1>)',
               rf'\g<1>{today}\g<2>', sample, count=1)
    for slug, a, b in PAIRS:
        ent = spread_series(series, a, b)
        st = spread_stats(ent, today)
        row_vals = (f'<td class="n"><b>{st["cur"]:+,.0f}</b></td>'
                    f'<td class="n">{st["month_ago"]:+,.0f}</td>'
                    f'<td class="n">{st["mean"]:+,.0f}</td>'
                    f'<td class="n">{st["pct"]}%</td>')
        h = re.sub(r'(<tr><td><a href="/spread/' + slug + r'/">[^<]+</a></td>)'
                   r'<td class="n">.*?</td><td class="n">.*?</td><td class="n">.*?</td><td class="n">.*?</td>',
                   lambda m: m.group(1) + row_vals, h, count=1, flags=re.S)
    return _stamps(h, today)
