"""Render one variety page (/pp/, /eps/, ...) by structural substitution
on the previous build.

The 2026-11-10 bundle page is the template; every data-derived fragment
is regenerated from the variety's price series. Two templates exist:

  * 8 mains (pp, lldpe, hdpe, ldpe, pvc, abs, ps, pet): full daily
    series in history.csv, 3-month stats, futures for pp/lldpe/pvc/pet,
    a grade section (static, carried over) and a 30-day daily table.
  * 7 board extras (eps, pc, pa6, pa66, eva, pmma, pp-fiber): sparse
    bulk-list series (trading days only), no futures, no grades, YoY is
    the value 生意社 publishes (passed in, not computed), and the daily
    table covers the whole series.

Daily-table rule (verified on both templates): rows run newest-first
over the last 30 entries of the series (mains are daily, so that is
the last 30 calendar days; extras are sparse bulk-list entries).
A run of equal prices contributes its first day as its own row (with
that day's real change); the remaining days of the run merge into one
row "MM-DD 至 MM-DD / 持平" when there are at least two of them, and
stay as a single "0.0%" row when there is only one. The first 10 data
rows are visible, the rest get class=mr and an expand button.

Deliberate changes vs the old generator:
  * PP's hero futures line no longer uses the dead 中油T30S basis
    (+1,601, 2026-10-21). It now shows the 生意社 basis (+1,759,
    2026-11-09), the same caliber as the homepage hero, the basis
    page and the PP FAQ card (which already used it). This follows
    Jiang's 2026-11-18 approval of the basis-page redesign.
  * Meta description appends the variety blurb truncated to 30 chars
    (the published pages do this: PP/ABS blurbs are 31 chars and lose
    their last character in the meta, shorter blurbs survive whole).

Inputs the caller must supply (the pipeline does not yet store them):
  * extras series: the bulk-list history per extra variety (the
    scraper appends one bulk-list price per day; no stored file yet).
  * extras YoY: 生意社's published year-on-year % per extra variety.
  * futures daily closes + settlement price per futures variety
    (futures.py fetch_klines / the exchange daily file).
Validated by re-rendering 2026-11-10 and diffing
(tests/verify_variety.py); a same-date re-render should be
byte-identical except the known PS source revision (see the test) and
the PP hero basis change above.
"""
from __future__ import annotations

import datetime as dt
import json
import re

from .article_links import inject, variety_section
from .compute import chg_pct, percentile, pos_label, stats_3m, temperature_label
from .dataio import SLUGS

FUTURES = {
    "pp": ("大商所", "聚丙烯PP"),
    "lldpe": ("大商所", "塑料LLDPE"),
    "pvc": ("大商所", "PVC"),
    "pet": ("郑商所", "瓶片PR"),
}

EXTRAS = ["eps", "pc", "pa6", "pa66", "eva", "pmma", "pp-fiber"]


def _md(date):  # '2026-11-10' -> ('11', '10')
    return date[5:7], date[8:10]


def _m_d(date):  # -> '11月10日'
    m, d = _md(date)
    return f"{int(m)}月{int(d)}日"


def _fmt_int(x):
    return f"{x:,.0f}"


def _cls(chg):
    return "up" if chg > 0 else ("dn" if chg < 0 else "fl")


def _chg1(chg):
    """Signed 1-decimal change as shown in kv cells and daily tables."""
    if chg > 0:
        return f"+{chg:.1f}%"
    if chg < 0:
        return f"{chg:.1f}%"
    return "0.0%"


def _chg_raw(today, prev):
    """Unrounded % change; 1-decimal displays format this directly, so
    a 2-decimal pre-rounding cannot double-round them (e.g. +1.45%
    must show +1.5%, not +1.4%)."""
    if not prev:
        return 0.0
    return (today / prev - 1) * 100


def _on_or_before(series, date):
    """Price of the last entry dated on or before `date` (ISO strings)."""
    price = None
    for d, p in series:
        if d <= date:
            price = p
        else:
            break
    return price


def _date_minus(date, days):
    d = dt.date.fromisoformat(date) - dt.timedelta(days=days)
    return d.isoformat()


def _ly_series(series):
    """Last-year overlay for the chart: [date, price 365 days earlier]."""
    by_date = dict(series)
    out = []
    for d, _ in series:
        prev = _date_minus(d, 365)
        if prev in by_date:
            out.append([d, by_date[prev]])
    return out


def _daily_rows(series, window):
    """Grouped daily-table rows for `window` (the last 30 entries of the
    full `series`), newest first. Runs are computed over the FULL
    series, so a run straddling the window edge contributes its
    in-window portion as one merged row starting at the window's first
    entry (e.g. PMMA's 09-11..10-21 run shows as "09-15 至 10-21").
    Previous prices come from the full series.

    Each row: (date_label, href_month, price, chg_or_None, merged).
    chg_or_None is None for a merged flat run (shown as 持平).
    """
    window_start = window[0][0]
    idx = {d: i for i, (d, _) in enumerate(series)}

    def prev_price(d):
        i = idx[d]
        return series[i - 1][1] if i > 0 else None

    # runs of equal price over the full series
    runs = []
    for d, p in series:
        if runs and runs[-1]["price"] == p:
            runs[-1]["days"].append((d, p))
        else:
            runs.append({"price": p, "days": [(d, p)]})
    rows = []
    for run in runs:
        days = run["days"]
        in_win = [e for e in days if e[0] >= window_start]
        if not in_win:
            continue
        if days[0][0] >= window_start:
            # run starts inside the window: first day is its own row
            first_d, first_p = days[0]
            pp = prev_price(first_d)
            chg = _chg_raw(first_p, pp) if pp is not None else 0.0
            rows.append((first_d, first_d[:7], first_p, chg, False))
            rest = in_win[1:]
        else:
            # run started before the window: only continuations show
            rest = in_win
        if len(rest) >= 2:
            rows.append((f"{rest[0][0][5:]} 至 {rest[-1][0][5:]}",
                         rest[0][0][:7], run["price"], None, True))
        elif len(rest) == 1:
            d, p = rest[0]
            rows.append((d, d[:7], p, 0.0, False))
    rows.reverse()
    return rows


def _daily_table(series, today, is_main):
    # Both templates show the last 30 entries: for mains the series is
    # daily, so that is the last 30 calendar days; for extras it is
    # the last 30 bulk-list entries (e.g. 2026-09-15..2026-11-09).
    window = series[-30:]
    rows = _daily_rows(series, window)
    out = []
    for i, (label, month, price, chg, merged) in enumerate(rows):
        cls = " class=mr" if i >= 10 else ""
        if merged:
            first, last = label.split(" 至 ")
            out.append(
                f'<tr{cls}><td><a href="/history/{month}/">{first}</a> 至 {last}</td>'
                f'<td class="n">{_fmt_int(price)}</td>'
                f'<td class="n fl">持平</td></tr>')
        else:
            out.append(
                f'<tr{cls}><td><a href="/history/{month}/">{label}</a></td>'
                f'<td class="n">{_fmt_int(price)}</td>'
                f'<td class="n {_cls(chg)}">{_chg1(chg)}</td></tr>')
    mr = sum(1 for i in range(len(rows)) if i >= 10)
    table = ('<div class="tbw"><table class="m10">'
             '<tr><th>日期</th><th class="n">元/吨</th><th class="n">日涨跌</th></tr>'
             + "".join(out) + "</table></div>")
    if mr:
        table += (
            '<button class="btn" type="button" style="margin-top:4px" '
            "onclick=\"this.previousElementSibling.querySelector('table')"
            f".classList.add('open');this.remove()\">展开（再看{mr}行）</button>")
    return table


def _hero(ctx, view, series, slug, is_main, fut_row, yoy):
    today = ctx["today"]
    name = view["name"]
    price = view["price"]
    chg = view["chg"]
    pct = view["pct"]
    temp = view["temp"]
    if is_main:
        temp_note = f"不低于近一年{pct}%的日子"
        week = _chg_raw(price, _on_or_before(series, _date_minus(today, 7)))
        month = _chg_raw(price, _on_or_before(series, _date_minus(today, 30)))
        ly_date = _date_minus(today, 365)
        ly_price = _on_or_before(series, ly_date)
        # series is daily, so the on-or-before lookup is the exact day
        yoy_val = _chg_raw(price, ly_price)
        win1y = series[-365:]
        lo1y = min(p for _, p in win1y)
        hi1y = max(p for _, p in win1y)
        kv = (
            f'<div>较一周前<b class="{_cls(week)}">{_chg1(week)}</b></div>'
            f'<div>较一月前<b class="{_cls(month)}">{_chg1(month)}</b></div>'
            f'<div>较去年同期<b class="{_cls(yoy_val)}">{_chg1(yoy_val)}</b></div>'
            f'<div>近一年区间<b class="n">{_fmt_int(lo1y)}–{_fmt_int(hi1y)}</b></div>')
        extra_lines = ""
        if fut_row is not None:
            exch, disp = FUTURES[slug]
            close = fut_row["close"]
            if slug == "pp":
                basis = fut_row["basis"]
                basis_s = f"+{basis:,}" if basis > 0 else f"{basis:,}"
                extra_lines += (
                    f'<div style="margin-top:10px;font-size:14px">{exch}{disp}主力 '
                    f'{ctx["fut_date"]} 收盘 <b class="n">{_fmt_int(close)}</b>'
                    f'　·　生意社基差 <b class="n">{basis_s}</b>'
                    f'（{ctx["fut_date"][5:]}） <a href="/basis/">看期现 ›</a></div>')
            else:
                extra_lines += (
                    f'<div style="margin-top:10px;font-size:14px">{exch}{disp}主力 '
                    f'{ctx["fut_date"]} 收盘 <b class="n">{_fmt_int(close)}</b></div>')
        hi_lo = "高" if yoy_val > 0 else "低"
        extra_lines += (
            f'<div class="ly">去年今天（{ly_date}）<b class="n">{_fmt_int(ly_price)}</b> '
            f'元/吨，现在比那时{hi_lo} <b class="{_cls(yoy_val)}">{abs(yoy_val):.1f}%</b> '
            f'<span class="src">本站记录的生意社{name}基准价</span></div>')
        st = stats_3m(series)
        pos1y = pos_label(price, lo1y, hi1y)
        src = (f'生意社{name}品种基准价（市场均价），更新于 {ctx["updated"].get(slug, "")}，'
               f'不是牌号成交价。三个月均价 {st["avg"]:,.0f}，处于一年{pos1y}。')
    else:
        days = len(series)
        start = series[0][0]
        temp_note = (f"按本站{days}天数据（{start}起，不足一年），"
                     f"不低于其中{pct}%的日子，<a href=\"/wendu/\">规则</a>")
        data_date = series[-1][0]
        week = _chg_raw(price, _on_or_before(series, _date_minus(data_date, 7)))
        month = _chg_raw(price, _on_or_before(series, _date_minus(data_date, 30)))
        kv = (
            f'<div>较一周前<b class="{_cls(week)}">{_chg1(week)}</b></div>'
            f'<div>较一月前<b class="{_cls(month)}">{_chg1(month)}</b></div>'
            f'<div>同比去年<b class="{_cls(yoy)}">{yoy:+.2f}%</b></div>'
            f'<div>数据起始<b class="n">{start[5:]}</b></div>')
        extra_lines = ""
        src = f"生意社橡塑大宗榜 {data_date}，元/吨；同比去年为生意社公布值。"
    temp_disp = temp + ("*" if not is_main else "")
    return (
        f'<div class="box"><div class="big">{_fmt_int(price)} <small>元/吨</small></div>'
        f'<div style="margin-top:6px"><span class="{view["chg_cls"]}">{view["chg_str"]}</span> · '
        f'采购温度 <span class="tg {view["temp_cls"]}">{temp_disp}</span> '
        f'<span class="src">{temp_note}</span></div>'
        f'<div class="kv">{kv}</div>{extra_lines}'
        f'<div class="src">{src}</div></div>')


def _chart_json(view, series, fut_series, is_main):
    ly = _ly_series(series) if is_main else []
    fut = [[d, c] for d, c in (fut_series or [])]
    data = {"spot": [[d, p] for d, p in series], "fut": fut, "ly": ly,
            "name": view["name"], "slug": view["slug"]}
    # NOTE: no ensure_ascii=False — the published chart JSON escapes
    # non-ASCII in the name field ("PP\u62c9\u4e1d"), unlike the
    # FAQPage JSON-LD in the head, which keeps raw characters.
    return json.dumps(data, separators=(",", ":"))


def _chart_src(ctx, view, series, slug, is_main, fut_row, bulk):
    name = view["name"]
    if is_main:
        start = series[0][0]
        ly_n = len(_ly_series(series))
        base = f"现货：生意社{name}基准价；"
        if fut_row is not None:
            exch, disp = FUTURES[slug]
            base += f"期货：{exch}{disp}主力连续收盘（新浪财经）；"
        else:
            base += "该品种暂无对应期货；"
        return (base + f"去年同期 = 365天前同日现货价（本站历史从{start}起，"
                f"去年同期目前只有最近{ly_n}天）。数据截至 {ctx['today']}。")
    start = series[0][0]
    return (f"现货：生意社橡塑大宗榜{bulk}价格；该品种暂无对应期货；"
            f"去年同期 = 365天前同日现货价（本站历史从{start}起，"
            f"暂无去年同期数据）。数据截至 {series[-1][0]}。")


def _faq_texts(ctx, view, series, slug, is_main, fut_row, settle, yoy,
               bulk=None, sub=""):
    today = ctx["today"]
    date_s = _m_d(today)
    name = view["name"]
    price = view["price"]
    chg = view["chg"]
    out = {}
    if is_main:
        out[f"{name}今天多少钱一吨？"] = (
            f"{date_s}{name}生意社基准价{price:.0f}元/吨，涨跌{chg:.2f}%，"
            f"更新于{ctx['updated'].get(slug, '')}。")
        st = stats_3m(series)
        win1y = series[-365:]
        pos1y = pos_label(price, min(p for _, p in win1y), max(p for _, p in win1y))
        pos2y = pos_label(price, min(p for _, p in series), max(p for _, p in series))
        out[f"{name}现在价格高吗？"] = (
            f"处于一年{pos1y}、两年{pos2y}；三个月均价{st['avg']:.0f}元/吨，"
            f"区间{st['lo']:.0f}–{st['hi']:.0f}元/吨。")
        if fut_row is not None:
            exch, disp = FUTURES[slug]
            basis = fut_row["basis"]
            basis_s = f"+{basis}" if basis > 0 else f"{basis}"
            out[f"{name}期货今天收多少？基差多少？"] = (
                f"{ctx['fut_date']}{exch}{disp}主力连续收盘{fut_row['close']:.0f}元/吨，"
                f"结算价{settle:.0f}；生意社现货{fut_row['spot']:.0f}元/吨，基差{basis_s}元/吨。")
        ly_date = _date_minus(today, 365)
        ly_price = _on_or_before(series, ly_date)
        yoy_val = _chg_raw(price, ly_price)
        out[f"{name}比去年涨了多少？"] = (
            f"{ly_date}生意社{name}价格{ly_price:.0f}元/吨，{date_s}为{price:.0f}元/吨，"
            f"同比{yoy_val:+.1f}%。")
    else:
        data_date = series[-1][0]
        bulk_name = bulk or name
        out[f"{name}今天多少钱一吨？"] = (
            f"{data_date}生意社{bulk_name}价格{price:.0f}元/吨，"
            f"日涨跌{chg:.2f}%，同比去年{yoy:+.2f}%。")
        out[f"{name}是什么料？"] = f"{name}：{sub}。"
        month = _chg_raw(price,
                         _on_or_before(series, _date_minus(data_date, 30)))
        if abs(month) < 0.05:
            out[f"{name}近一个月涨了多少？"] = "近一个月持平。"
        else:
            word = "上涨" if month > 0 else "下跌"
            out[f"{name}近一个月涨了多少？"] = f"近一个月{word}{abs(month):.1f}%。"
    return out


def render_variety(ctx, sample, slug, series, fut_series=None, settle=None,
                   yoy=None, bulk=None):
    """Render one variety page. `series` is the full price series
    [(date, price)]; `fut_series` the futures daily closes for the four
    futures varieties; `settle` that variety's settlement price;
    `yoy`/`bulk` the published YoY % and bulk-list name for extras."""
    is_main = slug in SLUGS
    today = ctx["today"]
    date_s = _m_d(today)
    views = ctx["mains"] + ctx["extras"]
    view = next(v for v in views if v["slug"] == slug)
    name = view["name"]
    sub_m = re.search(r'<div class="sub">(.*?)</div>', sample, re.S)
    sub = sub_m.group(1) if sub_m else ""
    fut_row = None
    if is_main:
        fut_row = next((r for r in ctx["futures"] if r["slug"] == slug), None)

    h = sample
    # --- head: title, meta, og, modified time, Dataset LD ---
    h = re.sub(r"今日\d+月\d+日", f"今日{date_s}", h)
    if is_main:
        st = stats_3m(series)
        meta = (f"{date_s}{name}价格{view['price']:.0f}元/吨，"
                f"涨跌{view['chg']:.2f}%，三个月均价{st['avg']:.0f}。{sub[:30]}")
    else:
        data_date = series[-1][0]
        meta = (f"{data_date}{name}价格{view['price']:.0f}元/吨，"
                f"日涨跌{view['chg']:.2f}%，同比{yoy:+.2f}%。{sub[:30]}")
    h = re.sub(r'(<meta name="description" content=")[^"]*(")',
               rf"\g<1>{meta}\g<2>", h, count=1)
    h = re.sub(r'(<meta property="og:description" content=")[^"]*(")',
               rf"\g<1>{meta}\g<2>", h, count=1)
    h = re.sub(r'(article:modified_time" content=")\d{4}-\d{2}-\d{2}(T15:00:00\+08:00")',
               rf"\g<1>{today}\g<2>", h, count=1)
    if is_main:
        h = re.sub(r'("temporalCoverage": ")[^"]*/\d{4}-\d{2}-\d{2}(")',
                   rf"\g<1>{series[0][0]}/{today}\g<2>", h, count=1)
        h = re.sub(r'("dateModified": ")\d{4}-\d{2}-\d{2}(")',
                   rf"\g<1>{today}\g<2>", h, count=1)
    # --- nav stamp + h1 ---
    h = re.sub(r">\d+月\d+日已更新 ·", f">{date_s}已更新 ·", h, count=1)
    h = re.sub(r"<h1>([^<]*)（\d+月\d+日）</h1>",
               rf"<h1>\g<1>（{date_s}）</h1>", h, count=1)
    # --- hero box ---
    hero = _hero(ctx, view, series, slug, is_main, fut_row, yoy)
    start = h.index('<div class="box"><div class="big">')
    end = h.index("<h2>价格走势</h2>", start)
    h = h[:start] + hero + h[end:]
    # --- chart JSON + chart src line ---
    chart = _chart_json(view, series, fut_series, is_main)
    # lambda replacement: the JSON now contains \uXXXX escapes, which
    # re.sub would misread as escapes in a plain replacement string.
    h = re.sub(r'<script type="application/json" class="chd">\{.*?\}</script>',
               lambda m: ('<script type="application/json" class="chd">'
                          + chart + "</script>"),
               h, count=1, flags=re.S)
    src = _chart_src(ctx, view, series, slug, is_main, fut_row, bulk or name)
    h = re.sub(r'(</script><div class="src">).*?(</div>)',
               rf"\g<1>{src}\g<2>", h, count=1, flags=re.S)
    # --- daily table ---
    table = _daily_table(series, today, is_main)
    h = re.sub(r'<div class="tbw"><table class="m10">.*?</table></div>'
               r'(<button class="btn"[^>]*>展开（再看\d+行）</button>)?',
               table, h, count=1, flags=re.S)
    # --- FAQ cards + FAQPage LD ---
    faq = _faq_texts(ctx, view, series, slug, is_main, fut_row, settle, yoy,
                     bulk=bulk, sub=sub)
    for q, a in faq.items():
        h = re.sub(r'(<div class="card"><b>' + re.escape(q) + r'</b><p>).*?(</p></div>)',
                   rf"\g<1>{a}\g<2>", h, count=1, flags=re.S)
    # FAQPage JSON-LD: sync the same answers by question name
    def fix_ld(m):
        try:
            data = json.loads(m.group(1))
        except json.JSONDecodeError:
            return m.group(0)
        for ent in data.get("mainEntity", []):
            if ent.get("name") in faq:
                ent["acceptedAnswer"]["text"] = faq[ent["name"]]
        return ('<script type="application/ld+json">'
                + json.dumps(data, ensure_ascii=False) + "</script>")
    h = re.sub(r'<script type="application/ld\+json">(\{[^<]*"FAQPage"[^<]*\})</script>',
               fix_ld, h, count=1)
    # --- footer date ---
    h = re.sub(r"整理于 \d{4}-\d{2}-\d{2}", f"整理于 {today}", h)
    # article entry point (approved 2026-11-19)
    h = inject(h, variety_section(slug))
    return h
