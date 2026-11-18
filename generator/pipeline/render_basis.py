"""Render /basis/ — redesigned 2026-11 around the unified caliber.

The old page led with the 华东中油T30S series, which stopped updating
on 2026-10-21 (its spot source, 同花顺iFinD via iNews, went silent).
Per Jiang's 2026-11-18 decision the page now leads with the same
caliber as the rest of the site — 生意社品种基准价 − 期货主力收盘 —
for the four futures varieties. The T30S table is preserved verbatim
at the bottom as an archive (pipeline/t30s_archive.html).

The multi-variety boxes and the 10-day detail table regenerate from
sf_basis data and reproduce the published page exactly (chart points
within 0.2px; the old charts were drawn from pre-revision values).
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from .basis_data import BOX_NAMES, SLUGS, big_chart, fmt_signed, small_chart, stats

ARCHIVE = (Path(__file__).parent / "t30s_archive.html").read_text(encoding="utf-8")
REF_LINE = 800


def _m_d(date):
    return f"{int(date[5:7])}月{int(date[8:10])}日"


def pp_narrative(rows):
    st = stats(rows)
    last, prev = st["last"], st["prev"]
    basis, delta = last["basis"], st["delta"]
    if delta > 0:
        d_txt = f"比上一个交易日（{prev['date']}）扩大{abs(delta):,.0f}元"
    elif delta < 0:
        d_txt = f"比上一个交易日（{prev['date']}）缩小{abs(delta):,.0f}元"
    else:
        d_txt = f"与上一个交易日（{prev['date']}）持平"
    if basis > REF_LINE:
        r_txt = f"，比{REF_LINE}元参考线高{basis - REF_LINE:,.0f}元"
    elif basis < REF_LINE:
        r_txt = f"，比{REF_LINE}元参考线低{REF_LINE - basis:,.0f}元"
    else:
        r_txt = f"，正处在{REF_LINE}元参考线"
    return (
        f"{last['date']}，生意社PP拉丝品种基准价{last['spot']:,.0f}元/吨，"
        f"大商所PP主力合约收盘{last['close']:,.0f}元/吨，"
        f"基差{fmt_signed(basis)}元/吨，{d_txt}{r_txt}。"
    )


def _hero(rows, narrative):
    st = stats(rows)
    last = st["last"]
    basis = last["basis"]
    return (
        '<div class="card"><div class="big">'
        f'{fmt_signed(basis)} <small style="font-size:16px">元/吨</small></div>'
        f'<div class="sub">生意社PP拉丝基准价 − 大商所PP主力收盘，{last["date"]}</div>'
        '<div class="grid">'
        f'<div>现货（生意社PP拉丝基准价）<b>{last["spot"]:,.0f}</b></div>'
        f'<div>期货主力收盘<b>{last["close"]:,.0f}</b></div>'
        f'<div>距{REF_LINE}元参考线<b>{fmt_signed(basis - REF_LINE)}</b></div>'
        '</div></div>'
        f'<p>{narrative}</p>'
    )


def _box(slug, rows):
    st = stats(rows)
    last = st["last"]
    return (
        f'<div class="box" style="margin:0"><b>{BOX_NAMES[slug]}</b> '
        f'<span class="src">主力 {last["contract"]}</span>'
        f'<div style="font-size:24px;font-weight:700" class="n">{fmt_signed(last["basis"])} '
        '<small style="font-size:12px;color:var(--tx2);font-weight:400">元/吨</small></div>'
        f'<div class="src">{last["date"]}：基准价 {last["spot"]:,.0f} − 主力 {last["close"]:,.0f}，'
        f'较前一日{st["delta"]:+.0f}；{st["first_date"]}起 {st["count"]} 个交易日，'
        f'区间 {st["min"]:,.0f} ~ {fmt_signed(st["max"])}；图为最近120个交易日</div>'
        + small_chart(rows) + '</div>'
    )


def _pp_table(rows):
    body = ""
    for r in reversed(rows[-10:]):
        body += (
            f'<tr><td>{r["date"]}</td><td class="n">{r["spot"]:,.0f}</td>'
            f'<td class="n">{r["contract"]}</td><td class="n">{r["close"]:,.0f}</td>'
            f'<td class="n"><b>{fmt_signed(r["basis"])}</b></td></tr>'
        )
    return (
        '<div class="tw"><table><tr><th>日期</th><th class="n">生意社PP拉丝基准价</th>'
        '<th class="n">主力合约</th><th class="n">期货主力收盘</th><th class="n">基差</th></tr>'
        + body + '</table></div>'
    )


def _detail_table(series):
    body = ""
    for slug in SLUGS:
        for r in reversed(series[slug][-10:]):
            body += (
                f'<tr><td>{r["date"]}</td><td>{BOX_NAMES[slug]}</td>'
                f'<td class="n">{r["spot"]:,.0f}</td><td class="n">{r["contract"]}</td>'
                f'<td class="n">{r["close"]:,.0f}</td>'
                f'<td class="n"><b>{fmt_signed(r["basis"])}</b></td></tr>'
            )
    return (
        '<details class="more"><summary>看最近10个交易日明细 ›</summary>'
        '<div class="tw"><table><tr><th>日期</th><th>品种</th><th class="n">基准价</th>'
        '<th class="n">主力</th><th class="n">主力价</th><th class="n">基差</th></tr>'
        + body + '</table></div></details>'
    )


def render_basis(ctx, sample):
    series = ctx["basis"]
    today = ctx["today"]
    pp = series["pp"]
    last = pp[-1]
    basis_date = last["date"]
    narrative = pp_narrative(pp)
    h = sample

    new_title = f"期现基差_生意社基准价对期货主力_{_m_d(today)}_塑价365"
    h = re.sub(r"<title>.*?</title>", f"<title>{new_title}</title>", h, count=1)
    h = re.sub(r'(<meta property="og:title" content=")[^"]*(")',
               lambda m: m.group(1) + new_title + m.group(2), h, count=1)
    # the site truncates the narrative to 78 chars for description metas
    desc = narrative[:78]
    h = re.sub(r'(<meta name="description" content=")[^"]*(")',
               lambda m: m.group(1) + desc + m.group(2), h, count=1)
    h = re.sub(r'(<meta property="og:description" content=")[^"]*(")',
               lambda m: m.group(1) + desc + m.group(2), h, count=1)
    h = re.sub(r'(article:modified_time" content=")\d{4}-\d{2}-\d{2}(T15:00:00\+08:00")',
               rf"\g<1>{today}\g<2>", h, count=1)
    h = re.sub(r">\d+月\d+日已更新 ·", f">{_m_d(today)}已更新 ·", h, count=1)
    h = re.sub(r"<h1>PP期现基差今日多少？华东T30S对期货主力（\d+月\d+日）</h1>",
               f"<h1>期现基差今日多少？生意社基准价对期货主力（{_m_d(basis_date)}）</h1>", h, count=1)
    h = h.replace(
        '<div class="sub">每天跟踪华东现货和期货差多少，帮工厂判断现货贵不贵、什么时候补库。</div>',
        '<div class="sub">每天跟踪生意社现货基准价和期货主力差多少，帮工厂判断现货贵不贵、什么时候补库。</div>')
    # hero + narrative
    h = re.sub(r'<div class="card"><div class="big">.*?</p>',
               _hero(pp, narrative), h, count=1, flags=re.S)
    # big chart card
    chart_card = (
        '<div class="card"><b>PP期现基差走势（元/吨）</b>'
        '<span class="sub" style="float:right">'
        '<span style="color:var(--brand)">━ 生意社PP拉丝基准价 − 期货主力</span>　'
        '<span style="color:#d93025">┅ 800元参考线</span></span>'
        + big_chart(pp) + '</div>'
    )
    h = re.sub(r'<div class="card"><b>PP期现基差走势（元/吨）</b>.*?</svg></div>',
               chart_card, h, count=1, flags=re.S)
    # explainer example
    expl = (
        f'<p>基差就是“现货价减期货价”。比如今天生意社PP拉丝基准价{last["spot"]:.0f}元，'
        f'期货主力合约收在{last["close"]:.0f}元，基差就是{last["basis"]:.0f}元。'
        '基差为正，说明现在马上拿货比买远期期货贵，市场愿意为“现在就有货”多付钱；基差为负则相反。</p>'
    )
    h = re.sub(r'<p>基差就是.*?</p>', expl, h, count=1, flags=re.S)
    # daily data: PP table + source note
    note = (
        '<p class="sub">数据来源：现货为生意社PP拉丝品种基准价；期货为大连商品交易所聚丙烯主力合约收盘价'
        f'（经新浪财经，当前主力为{last["contract"]}）。查不到当日现货报价或期货未交易的日子不计算、不补数。</p>'
    )
    h = re.sub(r'(<h2>每日数据</h2>)<div class="tw"><table>.*?</table></div><p class="sub">.*?</p>',
               lambda m: m.group(1) + _pp_table(pp) + note, h, count=1, flags=re.S)
    # multi-variety section
    h = h.replace('<h2 id="sf">多品种基差（生意社口径）</h2>', '<h2 id="sf">多品种基差</h2>')
    h = re.sub(r'<div class="al none" style="font-size:13.5px">⚠ 口径不同.*?</div>',
               '<p class="sub">本站基差统一按「生意社品种基准价 − 期货主力合约收盘价」计算，'
               '四个有期货的品种如下，逐日更新。</p>', h, count=1, flags=re.S)
    for slug in SLUGS:
        h = re.sub(rf'<div class="box" style="margin:0"><b>{re.escape(BOX_NAMES[slug])}</b>.*?</svg></div>',
                   _box(slug, series[slug]), h, count=1, flags=re.S)
    h = re.sub(r'<details class="more"><summary>看最近10个交易日明细 ›</summary>.*?</details>',
               _detail_table(series), h, count=1, flags=re.S)
    src_note = (
        '<div class="src">来源：现货基准价取自<a href="https://www.100ppi.com/sf/" rel="nofollow noopener" '
        'target="_blank">生意社现期表</a>，期货主力合约与收盘价经新浪财经；基差 = 基准价 − 主力收盘，'
        '本站逐日计算。周末、节假日和页面取不到的日子不补数。PE 对应大商所线型低密度聚乙烯（LLDPE），'
        'PVC 对应大商所聚氯乙烯，PET 瓶片对应郑商所瓶片。'
        '<a href="/data/sf_basis.csv">下载全部历史 CSV</a></div>'
    )
    h = re.sub(r'<div class="src">来源：<a href="https://www\.100ppi\.com/sf/".*?</div>',
               src_note, h, count=1, flags=re.S)
    # T30S archive before FAQ
    h = h.replace('<h2>常见问题</h2>', ARCHIVE + '<h2>常见问题</h2>', 1)
    # FAQ cards
    h = re.sub(r'<div class="card"><b>PP基差今天多少？</b><p>.*?</p></div>',
               f'<div class="card"><b>PP基差今天多少？</b><p>{narrative}</p></div>',
               h, count=1, flags=re.S)
    calc_txt = ('基差 = 生意社品种基准价 − 期货主力合约同一交易日收盘价，单位元/吨。'
                '本站跟踪 PP、LLDPE、PVC、PET 瓶片四个品种。')
    h = re.sub(r'<div class="card"><b>基差怎么算？</b><p>.*?</p></div>',
               f'<div class="card"><b>基差怎么算？</b><p>{calc_txt}</p></div>',
               h, count=1, flags=re.S)
    # JSON-LD blocks
    def fix_faq(m):
        try:
            data = json.loads(m.group(1))
        except json.JSONDecodeError:
            return m.group(0)
        for ent in data.get("mainEntity", []):
            if ent.get("name") == "PP基差今天多少？":
                ent["acceptedAnswer"]["text"] = narrative
            elif ent.get("name") == "基差怎么算？":
                ent["acceptedAnswer"]["text"] = calc_txt
        return ('<script type="application/ld+json">'
                + json.dumps(data, ensure_ascii=False) + "</script>")
    h = re.sub(r'<script type="application/ld\+json">(\{[^<]*"FAQPage"[^<]*\})</script>',
               fix_faq, h, count=1)
    def fix_dataset(m):
        try:
            data = json.loads(m.group(1))
        except json.JSONDecodeError:
            return m.group(0)
        data["name"] = "期现基差每日数据（生意社基准价对期货主力）"
        data["description"] = ("生意社品种基准价与期货主力合约收盘价之差，"
                               "覆盖PP、LLDPE、PVC、PET瓶片四个品种，每日更新，元/吨。")
        data["dateModified"] = basis_date
        return ('<script type="application/ld+json">'
                + json.dumps(data, ensure_ascii=False) + "</script>")
    h = re.sub(r'<script type="application/ld\+json">(\{[^<]*"Dataset"[^<]*\})</script>',
               fix_dataset, h, count=1)
    h = re.sub(r"整理于 \d{4}-\d{2}-\d{2}", f"整理于 {today}", h)
    return h
