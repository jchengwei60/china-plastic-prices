"""Render /history/ pages: day snapshots, month pages, and the index.

All values come from history.csv (the 8 main varieties' daily series).
Verified against the 2026-11-10 bundle in tests/verify_history.py:
month pages and the index reproduce byte-identically; the day page
differs only in the PS row (the known source-revision artifact —
the bundle's own month page agrees with history.csv, its day page
and latest.json were computed from the pre-revision PS value).
"""
from __future__ import annotations

import re

from .basis_data import _round_half_away
from .dataio import NAMES

SLUGS = ["pp", "lldpe", "hdpe", "ldpe", "pvc", "abs", "ps", "pet"]


def _label(ym):  # '2026-11' -> '2026年11月'
    return f"{ym[:4]}年{int(ym[5:7])}月"


def _date_zh(d):  # '2026-11-10' -> '2026年11月10日'
    return f"{d[:4]}年{int(d[5:7])}月{int(d[8:10])}日"


def _m_d(d):
    return f"{int(d[5:7])}月{int(d[8:10])}日"


def _meta_truncate(text, limit=80):
    """Description metas on the history pages: full text cut at the
    last '，' at or before `limit` chars (fits both 2026-11 samples:
    day -> 70 chars, month -> 77 chars)."""
    if len(text) <= limit:
        return text
    cut = text[:limit]
    i = cut.rfind("，")
    return cut[: i + 1] if i >= 0 else cut


def _month_entries(series, ym):
    return {s: [(d, p) for d, p in series[s] if d.startswith(ym)] for s in SLUGS}


def month_stats(series, ym):
    ent = _month_entries(series, ym)
    out = {}
    for s in SLUGS:
        vals = [p for _, p in ent[s]]
        if not vals:
            continue
        out[s] = {
            # the published averages round half-to-even (5026.5 -> 5026)
            "avg": int(round(sum(vals) / len(vals))),
            "high": max(vals), "low": min(vals),
            "chg": (vals[-1] / vals[0] - 1) * 100,
            "days": len(vals),
        }
    return out


def _chg_span(chg, digits):
    if chg > 0:
        return "up", f"{chg:+.{digits}f}%"
    if chg < 0:
        return "dn", f"{chg:.{digits}f}%"
    return "", f"{0:.{digits}f}%"


def _stamps(h, today):
    h = re.sub(r'(article:modified_time" content=")\d{4}-\d{2}-\d{2}(T15:00:00\+08:00")',
               rf"\g<1>{today}\g<2>", h, count=1)
    h = re.sub(r">\d+月\d+日已更新 ·", f">{_m_d(today)}已更新 ·", h, count=1)
    h = re.sub(r"整理于 \d{4}-\d{2}-\d{2}", f"整理于 {today}", h)
    return h


def _metas(h, title, desc):
    h = re.sub(r"<title>.*?</title>", f"<title>{title}</title>", h, count=1)
    h = re.sub(r'(<meta property="og:title" content=")[^"]*(")',
               lambda m: m.group(1) + title + m.group(2), h, count=1)
    for prop in ('name="description"', 'property="og:description"'):
        h = re.sub(rf'(<meta {prop} content=")[^"]*(")',
                   lambda m: m.group(1) + desc + m.group(2), h, count=1)
    return h


def render_day(date, series, sample, today):
    rows = ""
    full = f"{_date_zh(date)}国内塑料价格："
    items = []
    for s in SLUGS:
        ent = series[s]
        idx = [d for d, _ in ent].index(date)
        price, prev = ent[idx][1], ent[idx - 1][1]
        chg = (price / prev - 1) * 100
        cls, txt = _chg_span(chg, 2)
        rows += (f'<tr><td><a href="/{s}/">{NAMES[s]}</a></td>'
                 f'<td class="n">{price:.0f}</td>'
                 f'<td class="n"><span class="{cls}">{txt}</span></td></tr>')
        items.append(f"{NAMES[s]}{price:.0f}元/吨")
    full += "，".join(items) + "。"
    h = sample
    h = _metas(h, f"塑料价格{_date_zh(date)}_塑价365", _meta_truncate(full))
    h = re.sub(r"(<a href=\"/history/\">历史价格</a> › )<a href=\"/history/\d{4}-\d{2}-\d{2}/\">[^<]*</a>",
               rf'\g<1><a href="/history/{date}/">{_m_d(date)}</a>', h, count=1)
    h = re.sub(r"<h1>\d{4}年\d+月\d+日塑料价格</h1>", f"<h1>{_date_zh(date)}塑料价格</h1>", h, count=1)
    h = re.sub(r'<table><tr><th>品种</th><th class="n">元/吨</th><th class="n">涨跌</th></tr>.*?</table>',
               '<table><tr><th>品种</th><th class="n">元/吨</th><th class="n">涨跌</th></tr>'
               + rows + '</table>', h, count=1, flags=re.S)
    return _stamps(h, today)


def render_month(ym, series, sample, today, day_dates=()):
    st = month_stats(series, ym)
    label = _label(ym)
    intro_items = "，".join(f"{NAMES[s]}月均{st[s]['avg']}元/吨" for s in SLUGS)
    intro = f"{label}生意社塑料价格：{intro_items}。"
    best = max(SLUGS, key=lambda s: st[s]["chg"])
    bcls, btxt = _chg_span(st[best]["chg"], 1)
    sub = intro + f"当月涨幅最大的是{NAMES[best]}（{btxt}）。"
    summary = ""
    for s in SLUGS:
        cls, txt = _chg_span(st[s]["chg"], 1)
        summary += (f'<tr><td><a href="/{s}/">{NAMES[s]}</a></td>'
                    f'<td class="n"><b>{st[s]["avg"]}</b></td>'
                    f'<td class="n">{st[s]["high"]:.0f}</td>'
                    f'<td class="n">{st[s]["low"]:.0f}</td>'
                    f'<td class="n"><span class="{cls}">{txt}</span></td></tr>')
    ent = _month_entries(series, ym)
    dates = sorted({d for s in SLUGS for d, _ in ent[s]}, reverse=True)
    daily = ""
    for d in dates:
        cells = "".join(
            f'<td class="n">{dict(ent[s])[d]:.0f}</td>' for s in SLUGS)
        # dates that have a day-snapshot page are linked, others plain
        dcell = (f'<td><a href="/history/{d}/">{d[5:]}</a></td>'
                 if d in day_dates else f'<td>{d[5:]}</td>')
        daily += f'<tr>{dcell}{cells}</tr>'
    months = sorted({d[:7] for s in SLUGS for d, _ in series[s]})
    i = months.index(ym)
    nav = ""
    if i > 0:
        nav += f'<a href="/history/{months[i - 1]}/">‹ 上一月：{_label(months[i - 1])}</a>'
    if i < len(months) - 1:
        if nav:
            nav += "　"
        nav += f'<a href="/history/{months[i + 1]}/">下一月 ›：{_label(months[i + 1])}</a>'
    h = sample
    h = _metas(h, f"{label}塑料价格_塑价365", _meta_truncate(intro))
    h = re.sub(r"(<a href=\"/history/\">历史价格</a> › )<a href=\"/history/\d{4}-\d{2}/\">[^<]*</a>",
               rf'\g<1><a href="/history/{ym}/">{label}</a>', h, count=1)
    h = re.sub(r"<h1>\d{4}年\d+月塑料价格</h1>", f"<h1>{label}塑料价格</h1>", h, count=1)
    h = re.sub(r'<div class="sub">\d{4}年\d+月生意社塑料价格：.*?</div>',
               f'<div class="sub">{sub}</div>', h, count=1, flags=re.S)
    h = re.sub(r'(<h2>月度汇总（元/吨）</h2><table><tr><th>品种</th>.*?</tr>).*?</table>',
               lambda m: m.group(1) + summary + '</table>', h, count=1, flags=re.S)
    h = re.sub(r'(<h2>每日价格（元/吨）</h2><div class="tw"><table><tr><th>日期</th>.*?</tr>).*?</table>',
               lambda m: m.group(1) + daily + '</table>', h, count=1, flags=re.S)
    h = re.sub(r'<p class="sub"><a href="/history/\d{4}-\d{2}/">‹ 上一月：.*?</p>',
               f'<p class="sub">{nav}</p>', h, count=1, flags=re.S)
    return _stamps(h, today)


def render_index(series, sample, today, day_dates):
    months = sorted({d[:7] for s in SLUGS for d, _ in series[s]}, reverse=True)
    cur = months[0]
    st_cur = month_stats(series, cur)
    old_ym = f"{int(cur[:4]) - 1}{cur[4:]}"
    h = sample
    if old_ym in months:
        st_old = month_stats(series, old_ym)
        intro = (f"PP拉丝 {_label(old_ym)}均价 {st_old['pp']['avg']:,} 元/吨"
                 f"（本站有{st_old['pp']['days']}天数据），"
                 f"{_label(cur)}至今均价 {st_cur['pp']['avg']:,} 元/吨。")
        h = re.sub(r"<p>PP拉丝 \d{4}年\d+月均价 .*?</p>", f"<p>{intro}</p>", h, count=1, flags=re.S)
    body = ""
    for ym in months[:13]:
        st = month_stats(series, ym)
        cells = "".join(f'<td class="n">{st[s]["avg"]:,}</td>' for s in SLUGS)
        body += (f'<tr><td><a href="/history/{ym}/">{_label(ym)}</a></td>'
                 f'{cells}<td class="n">{st["pp"]["days"]}</td></tr>')
    h = re.sub(r'(<tbody>).*?(</tbody>)', lambda m: m.group(1) + body + m.group(2),
               h, count=1, flags=re.S)
    mlist = "".join(
        f'<li><a href="/history/{ym}/">{_label(ym)}塑料价格</a></li>' for ym in months)
    h = re.sub(r'(<h2>按月份</h2><ul>).*?(</ul>)',
               lambda m: m.group(1) + mlist + m.group(2), h, count=1, flags=re.S)
    dlist = "".join(
        f'<li><a href="/history/{d}/">{_date_zh(d)}塑料价格</a></li>'
        for d in sorted(day_dates, reverse=True))
    h = re.sub(r'(<h2>每日快照</h2><ul>).*?(</ul>)',
               lambda m: m.group(1) + dlist + m.group(2), h, count=1, flags=re.S)
    return _stamps(h, today)
