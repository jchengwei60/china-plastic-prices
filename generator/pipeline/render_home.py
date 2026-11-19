"""Render the homepage by structural substitution on the previous build.

The 2026-11-10 bundle page is the template; every data-derived fragment
is regenerated from the render context. Validated by re-rendering
2026-11-10 and diffing (tests/verify_home.py).

Deliberate changes vs the old generator (flagged for review):
  * Headline basis uses the same口径 as the basis table below it
    （生意社现货 - 期货主力） instead of the separate 中油T30S feed,
    which died on 2026-10-21 and made the headline contradict the table.
  * The auto-FAQ "哪个品种涨得最多" no longer names a 0.00% variety on
    days when nothing rose.
"""
from __future__ import annotations

import json
import re

from .article_links import home_section, inject

ADVICE = {
    "偏贵": "按需采购、不建议囤货",
    "偏便宜": "可以考虑分批补货",
    "正常": "按计划正常采购",
}


def _md(date):  # '2026-11-10' -> ('11', '10')
    return date[5:7], date[8:10]


def _m_d(date):  # -> '11月10日'
    m, d = _md(date)
    return f"{int(m)}月{int(d)}日"


def _card(v, extra=False):
    slug, name = v["slug"], v["name"]
    if extra:
        title = f"本站{v['days']}天百分位 {v['pct']}%"
        temp = v["temp"] + "*"
        rg_title = f"本站{v['days']}天区间位置"
        mid = f"本站{v['days']}天"
    else:
        title = f"近一年百分位 {v['pct']}%"
        temp = v["temp"]
        rg_title = "近一年区间位置"
        mid = "近一年"
    return (
        f'<a class="cd" href="/{slug}/" data-s="{slug}">'
        f'<button class="st" type="button" data-s="{slug}" aria-label="收藏{name}">☆</button>'
        f'<div class="nm">{name}</div>'
        f'<div class="pr">{v["price_card"]} <small>元/吨</small></div>'
        f'<div><span class="ch {v["chg_cls"]}">{v["chg_str"]}</span> · '
        f'<span class="tg {v["temp_cls"]}" title="{title}">{temp}</span></div>'
        f'<svg class="sp" viewBox="0 0 120 32" preserveAspectRatio="none" aria-hidden="true">'
        f'<polyline fill="none" style="stroke:var(--{v["spark_dir"]})" stroke-width="1.6" points="{v["spark"]}"/></svg>'
        f'<div class="rg" title="{rg_title}"><i style="left:{v["pos_pct"]}%"></i></div>'
        f'<div class="rl"><span class="n">{v["lo_s"]}</span><span>{mid}</span><span class="n">{v["hi_s"]}</span></div></a>'
    )


def _hero(ctx):
    pp = ctx["pp"]
    m, d = _md(ctx["fut_date"])
    basis = ctx["pp_basis"]
    basis_s = f"+{basis:,}" if basis > 0 else f"{basis:,}"
    names = "、".join(ctx["hot_names"][:4])
    if ctx["hot_count"] > 4:
        names += "等"
    if ctx["hot_count"] == 0:
        sub = "8个主要品种里没有处在近一年偏贵区间的。"
    else:
        sub = f'8个主要品种里 {ctx["hot_count"]} 个处在近一年偏贵区间（{names}）。'
    um, ud = _md(ctx["today"])
    return (
        f'<div class="box hero"><b>今天 PP 拉丝{pp["temp"]}（{pp["price_card"]}元/吨，'
        f'不低于近一年{pp["pct"]}%的日子），PP基差 {basis_s} 元（{m}-{d}），{ADVICE[pp["temp"]]}。</b>'
        f'<div style="margin-top:4px;color:var(--tx2);font-size:14px">{sub}</div>'
        f'<div class="src">数据：生意社品种基准价 {um}-{ud} {ctx["pp_updated"].split(" ")[-1] if ctx["pp_updated"] else ""}；'
        f'基差 = 生意社PP拉丝基准价 − 大商所PP主力收盘（{ctx["fut_date"]}）。'
        f'按下方公开规则自动生成，仅供参考，不构成建议。</div></div>'
    )


def _alerts(ctx):
    if not ctx["alerts"]:
        return ""
    inner = ""
    for v in ctx["alerts"]:
        cls = "up" if v["chg"] > 0 else "dn"
        inner += (
            f'<div><a href="/{v["slug"]}/"><b>{v["name"]}</b></a> '
            f'<span class="{cls}">{v["chg"]:.2f}%</span>（{v["price_card"]}）'
            f'<div class="src">单日涨跌≥±2%，生意社品种基准价。<a href="/alerts/">异动记录 ›</a></div></div>'
        )
    return f'<div class="al">⚡{inner}</div>'


def _minirank(ctx):
    ranked = sorted(ctx["mains"], key=lambda v: -v["weekly_chg"])
    top = ranked[:3]
    worst = ranked[-1]
    def item(i, v):
        cls = "up" if v["weekly_chg"] > 0 else ("dn" if v["weekly_chg"] < 0 else "fl")
        return f'{i}. <a href="/{v["slug"]}/">{v["name"]}</a> <span class="{cls}">{v["weekly_chg"]:.1f}%</span>'
    wcls = "up" if worst["weekly_chg"] > 0 else ("dn" if worst["weekly_chg"] < 0 else "fl")
    return (
        '<div class="box" id="rank"><b>近一周涨跌榜</b>　'
        + "　".join(item(i + 1, v) for i, v in enumerate(top))
        + f'　…　跌最多：<a href="/{worst["slug"]}/">{worst["name"]}</a> '
          f'<span class="{wcls}">{worst["weekly_chg"]:.1f}%</span>'
          '　<a href="/rank/">完整涨跌榜 ›</a></div>'
    )


def _futures_table(ctx):
    rows = ""
    for r in ctx["futures"]:
        cls = "up" if r["chg"] > 0 else ("dn" if r["chg"] < 0 else "fl")
        basis = r["basis"]
        basis_s = f"+{basis}" if basis > 0 else f"{basis}"
        rows += (
            f'<tr><td><a href="/{r["slug"]}/">{r["disp"]}</a><br><small class="sub">{r["exch"]}</small></td>'
            f'<td class="n"><b>{r["close"]:.0f}</b></td>'
            f'<td class="n"><span class="{cls}">{r["chg"]:.1f}%</span></td>'
            f'<td class="n">{r["spot"]:.0f}</td>'
            f'<td class="n"><b>{basis_s}</b></td></tr>'
        )
    return (
        '<div class="tw"><table><tr><th>期货主力连续</th><th class="n">收盘价</th>'
        '<th class="n">涨跌</th><th class="n">生意社现货</th><th class="n">基差</th></tr>'
        + rows + '</table></div>'
    )


def faq_texts(ctx):
    date_s = _m_d(ctx["today"])
    q1 = date_s + "国内塑料基准价：" + "；".join(
        f'{v["name"]} {v["price"]:.0f}元/吨（{v["chg"]:.2f}%）' for v in ctx["mains"]
    ) + "。来源：生意社。"
    best = max(ctx["mains"], key=lambda v: v["chg"])
    q3q = f"{date_s}哪个塑料品种涨得最多？"
    if best["chg"] > 0:
        q3 = f'{best["name"]}，{best["chg"]:.2f}%，报{best["price"]:.0f}元/吨。'
    else:
        q3 = (f'今天没有品种上涨，{best["name"]}跌幅最小（{best["chg"]:.2f}%），'
              f'报{best["price"]:.0f}元/吨。')
    return q1, q3q, q3


def render_home(ctx, sample):
    h = sample
    today = ctx["today"]
    date_s = _m_d(today)
    q1, q3q, q3 = faq_texts(ctx)

    h = re.sub(r"<title>今日塑料价格\d+月\d+日_塑价365</title>",
               f"<title>今日塑料价格{date_s}_塑价365</title>", h)
    meta = (f'{date_s}国内塑料价格：PP拉丝、LLDPE、HDPE、LDPE、PVC、ABS、PS、PET'
            f'基准价及涨跌，{ctx["risers"]}个品种上涨。每日更新。')
    h = re.sub(r'(<meta name="description" content=")[^"]*(")', rf"\g<1>{meta}\g<2>", h)
    h = re.sub(r">\d+月\d+日已更新 ·", f">{date_s}已更新 ·", h)
    h = re.sub(r"<h1>今日塑料价格（\d{4}-\d{2}-\d{2}）</h1>",
               f"<h1>今日塑料价格（{today}）</h1>", h)
    h = re.sub(r'<div class="box hero">.*?</div></div>', _hero(ctx), h, count=1, flags=re.S)
    # alert strip: replace if present in sample, else insert after hero
    if '<div class="al">' in h:
        h = re.sub(r'<div class="al">.*?</div></div></div>', _alerts(ctx), h, count=1, flags=re.S)
    elif _alerts(ctx):
        h = h.replace(_hero(ctx), _hero(ctx) + _alerts(ctx), 1)
    # variety cards
    for v in ctx["mains"]:
        h = re.sub(rf'<a class="cd" href="/{v["slug"]}/" data-s="{v["slug"]}">.*?</a>',
                   _card(v), h, count=1, flags=re.S)
    for v in ctx["extras"]:
        h = re.sub(rf'<a class="cd" href="/{v["slug"]}/" data-s="{v["slug"]}">.*?</a>',
                   _card(v, extra=True), h, count=1, flags=re.S)
    # source stamps
    h = re.sub(r"更新于 \d{2}-\d{2} \d{2}:\d{2}", f'更新于 {ctx["pp_updated"]}', h, count=1)
    h = re.sub(r"生意社橡塑大宗榜 \d{4}-\d{2}-\d{2}",
               f'生意社橡塑大宗榜 {ctx["fut_date"]}', h, count=1)
    # mini weekly rank
    h = re.sub(r'<div class="box" id="rank">.*?</div>', _minirank(ctx), h, count=1, flags=re.S)
    # explainer wording (basis口径 unified)
    h = h.replace("PP 的温度和华东基差", "PP 的温度和基差")
    # futures block
    h = re.sub(r"<h2>期货与基差（\d{4}-\d{2}-\d{2}）</h2>",
               f'<h2>期货与基差（{ctx["fut_date"]}）</h2>', h)
    h = re.sub(r'<div class="tw"><table><tr><th>期货主力连续</th>.*?</table></div>',
               _futures_table(ctx), h, count=1, flags=re.S)
    # FAQ cards
    h = re.sub(r'<div class="card"><b>今天塑料价格多少？</b><p>.*?</p></div>',
               f'<div class="card"><b>今天塑料价格多少？</b><p>{q1}</p></div>',
               h, count=1, flags=re.S)
    h = re.sub(r'<div class="card"><b>\d+月\d+日哪个塑料品种涨得最多？</b><p>.*?</p></div>',
               f'<div class="card"><b>{q3q}</b><p>{q3}</p></div>',
               h, count=1, flags=re.S)
    # FAQ JSON-LD: update the two dynamic answers + dated question
    def fix_ld(m):
        try:
            data = json.loads(m.group(1))
        except json.JSONDecodeError:
            return m.group(0)
        for ent in data.get("mainEntity", []):
            name = ent.get("name", "")
            if name == "今天塑料价格多少？":
                ent["acceptedAnswer"]["text"] = q1
            elif "哪个塑料品种涨得最多" in name:
                ent["name"] = q3q
                ent["acceptedAnswer"]["text"] = q3
        return ('<script type="application/ld+json">'
                + json.dumps(data, ensure_ascii=False) + "</script>")
    h = re.sub(r'<script type="application/ld\+json">(\{[^<]*"FAQPage"[^<]*\})</script>',
               fix_ld, h, count=1)
    # footer date
    h = re.sub(r"整理于 \d{4}-\d{2}-\d{2}", f"整理于 {today}", h)
    # article entry point (approved 2026-11-19)
    h = inject(h, home_section())
    return h
