"""Spot reference quotes (生意社现货参考价): the grade-level quotes
shown on each variety's 100ppi detail page. They are the constituent
quotes the benchmark is averaged from (verified 2026-11-21: LLDPE
benchmark 9016.67 = mean of its two 7042 quotes). Coverage is thin
and varies by day: PP 3 rows, LLDPE/PVC/PET 2, ABS 1, and HDPE/LDPE/
PS had no table at all on 2026-11-21 — every consumer must treat
rows as optional.

Rows are dicts {spec, brand, market, price, time} where spec is the
grade text as printed (e.g. "T30S", "SG-5 优等品", "水瓶级") and
time is the page's own stamp ("2026-11-21 09:00").
"""
from __future__ import annotations

import re

_ALIASES = {"水瓶级": "pet-bottle", "纤维级": "pet-fiber"}


def spec_key(spec):
    """Normalise a grade/spec string (from a quote row, a grade page's
    spec text, or a display name) to a comparable key."""
    s = re.sub(r"\s+", "", str(spec)).replace("优等品", "")
    if s in _ALIASES:
        return _ALIASES[s]
    return s.lower()


def parse_spot_rows(raw):
    """Raw DOM rows [name, spec, brand, market, price, time] -> dicts.
    Unparseable rows are dropped."""
    out = []
    for r in raw or []:
        if not isinstance(r, (list, tuple)) or len(r) < 6:
            continue
        try:
            price = float(str(r[4]).replace(",", ""))
        except (TypeError, ValueError):
            continue
        spec = str(r[1]).strip()
        if not spec:
            continue
        out.append({"spec": spec, "brand": str(r[2]).strip(),
                    "market": str(r[3]).strip(), "price": price,
                    "time": str(r[5]).strip()})
    return out


def match_rows(rows, key):
    return [r for r in rows or [] if spec_key(r["spec"]) == key]


def diff_text(price, bench):
    d = price - bench
    if abs(d) < 0.5:
        return "与基准价持平"
    return f"较基准价{'高' if d > 0 else '低'}{abs(d):,.0f}元"


def quote_text(rows):
    """'镇海炼化（浙江）11,260 元/吨；抚顺石化（山东）10,083 元/吨'"""
    return "；".join(
        f'{r["brand"]}（{r["market"]}）{r["price"]:,.0f} 元/吨'
        for r in rows)


def spot_section(rows, bench_price):
    """The variety-page 现货参考价 table for one variety's rows."""
    if not rows:
        return ""
    trs = []
    for r in rows:
        d = r["price"] - bench_price
        if abs(d) < 0.5:
            dtxt, cls = "持平", "fl"
        else:
            dtxt = f"{d:+,.0f}"
            cls = "up" if d > 0 else "dn"
        trs.append(
            f'<tr><td>{r["spec"]}</td><td>{r["brand"]}</td>'
            f'<td>{r["market"]}</td><td class="n">{r["price"]:,.0f}</td>'
            f'<td class="n {cls}">{dtxt}</td></tr>')
    return ('<h2>现货参考价（牌号）</h2>'
            '<div class="tbw"><table class="m10"><tr><th>牌号</th>'
            '<th>厂家</th><th>市场</th><th class="n">参考价（元/吨）</th>'
            '<th class="n">较基准价</th></tr>'
            + "".join(trs) + "</table></div>"
            f'<p class="src">数据来源：生意社现货参考价（{rows[0]["time"]}更新）。'
            "品种基准价由现货报价综合得出；牌号价因厂家、地区不同有差异，"
            "实际成交以厂家报价为准。</p>")
