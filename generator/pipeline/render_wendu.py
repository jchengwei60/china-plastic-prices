"""Render the procurement-temperature page (/wendu/) by structural
substitution on the previous build.

The 2026-11-10 bundle page is the template; the table is regenerated
from the render context (8 mains + 7 board extras), sorted by
percentile descending (stable sort, so ties keep the context order:
mains in slug order, then extras in the order supplied).
Validated by re-rendering 2026-11-10 and diffing (tests/verify_wendu.py);
a same-date re-render should be byte-identical.
"""
from __future__ import annotations

import re

RULE_SUFFIX = "按近一年百分位≥80%偏贵、≤20%偏便宜，规则公开。"


def _md(date):  # '2026-11-10' -> ('11', '10')
    return date[5:7], date[8:10]


def _m_d(date):  # -> '11月10日'
    m, d = _md(date)
    return f"{int(m)}月{int(d)}日"


def _sample(v):
    if v["days"] >= 365:
        return "近一年 365天"
    start = v.get("start", "")
    return f"仅{v['days']}天（{start}起）" if start else f"仅{v['days']}天"


def _row(v):
    star = "*" if v["days"] < 365 else ""
    return (
        f'<tr><td><a href="/{v["slug"]}/">{v["name"]}</a></td>'
        f'<td class="n">{v["price_card"]}</td>'
        f'<td class="n">{v["pct"]}%</td>'
        f'<td><span class="tg {v["temp_cls"]}">{v["temp"]}{star}</span></td>'
        f'<td class="n">{v["lo_s"]}–{v["hi_s"]}</td>'
        f"<td>{_sample(v)}</td></tr>"
    )


def summary_text(ctx):
    views = ctx["mains"] + ctx["extras"]
    hot = sum(1 for v in views if v["temp"] == "偏贵")
    cold = sum(1 for v in views if v["temp"] == "偏便宜")
    rest = len(views) - hot - cold
    return (f"{ctx['today']}：{len(views)}个品种中 {hot} 个偏贵、"
            f"{cold} 个偏便宜、{rest} 个正常或数据不足。")


def render_wendu(ctx, sample):
    h = sample
    today = ctx["today"]
    date_s = _m_d(today)
    summary = summary_text(ctx)

    # summary sentence: meta description, og:description, hero line
    h = re.sub(
        r"\d{4}-\d{2}-\d{2}：\d+个品种中 \d+ 个偏贵、\d+ 个偏便宜、\d+ 个正常或数据不足。",
        summary, h)
    # nav stamp + h1 date
    h = re.sub(r"\d+月\d+日已更新 ·", f"{date_s}已更新 ·", h, count=1)
    h = re.sub(r"（\d+月\d+日）</h1>", f"（{date_s}）</h1>", h, count=1)
    # table, sorted by percentile desc (stable)
    views = sorted(ctx["mains"] + ctx["extras"], key=lambda v: -v["pct"])
    table = ('<table class="mt"><tr><th>品种</th><th class="n">今日价</th>'
             '<th class="n">百分位</th><th>温度</th><th class="n">区间</th>'
             '<th>样本</th></tr>' + "".join(_row(v) for v in views) + "</table>")
    h = re.sub(r'<table class="mt">.*?</table>', table, h, count=1, flags=re.S)
    # article modified time: date moves, 15:00 publish time kept
    h = re.sub(r'(article:modified_time" content=")\d{4}-\d{2}-\d{2}(T15:00:00\+08:00")',
               rf"\g<1>{today}\g<2>", h, count=1)
    # footer date
    h = re.sub(r"整理于 \d{4}-\d{2}-\d{2}", f"整理于 {today}", h, count=1)
    return h
