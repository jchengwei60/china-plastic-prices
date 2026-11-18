"""Render the remaining small dynamic surfaces: /fupan/, /llms.txt,
/download/ (+ its Excel file) and the /today/ page.

/fupan/ scores fixed judgment records (kept below as data — new
records come from articles, an editorial input) 14 days later with
the site's fixed rules: 买/等 are scored 对/错 at a ±0.5% band,
分批 is only recorded, <14 days is 待验证.
"""
from __future__ import annotations

import io
import re

from .compute import pos_label
from .dataio import NAMES
from .render_history import _m_d, _stamps

SHORT = {"pp": "PP", "lldpe": "LLDPE", "hdpe": "HDPE", "ldpe": "LDPE",
         "pvc": "PVC", "abs": "ABS", "ps": "PS", "pet": "PET"}

# date, slug, judgment text, trigger text, source article (HTML-escaped
# text as it appears on the page)
JUDGMENTS = [
    ("2026-10-21", "pp",
     "分批(库存&lt;10天补7-10天量；够10天不补)",
     "T30S华东&lt;=10600或基差&lt;=1200补半月量；杭州拉丝&gt;=10800且PP2701&gt;9600补一批",
     "/articles/2026-10-pp-hormuz-soften/"),
    ("2026-10-19", "pp",
     "分批(库存&lt;10天补7-10天量；库存够不补)",
     "T30S华东&lt;=10600或基差&lt;=1200补半月量；PP2701&gt;9600且现货不跌补一批",
     "/articles/2026-10-pp-basis-weekly/"),
]


def _price_on_or_before(ent, date):
    out = None
    for d, p in ent:
        if d <= date:
            out = p
        else:
            break
    return out


def _price_on_or_after(ent, date):
    for d, p in ent:
        if d >= date:
            return d, p
    return None, None


def render_fupan(sample, series, today):
    import datetime as _dt
    rows = ""
    verified = right = wrong = pending = 0
    for date, slug, judgment, trigger, article in JUDGMENTS:
        ent = series[slug]
        start = _price_on_or_before(ent, date)
        target = (_dt.date.fromisoformat(date) + _dt.timedelta(days=14)).isoformat()
        end_date, end = _price_on_or_after(ent, target)
        kind = judgment.split("(")[0]
        if end is None:
            pending += 1
            rows += (f'<tr><td>{date}</td><td>{SHORT[slug]}</td><td>{judgment}</td>'
                     f'<td>{trigger}</td><td class="n">{start:,.0f}</td>'
                     f'<td class="n">—</td><td class="n">—</td>'
                     f'<td class="pd">待验证</td>'
                     f'<td><a href="{article}">原文</a></td></tr>')
            continue
        chg = (end / start - 1) * 100
        if kind == "分批":
            result = "只记录"
        elif kind == "买":
            result = "对" if chg >= 0.5 else ("错" if chg <= -0.5 else "持平不计")
        elif kind == "等":
            result = "对" if chg <= -0.5 else ("错" if chg >= 0.5 else "持平不计")
        else:
            result = "只记录"
        if result in ("对", "错"):
            verified += 1
            right += result == "对"
            wrong += result == "错"
        rows += (f'<tr><td>{date}</td><td>{SHORT[slug]}</td><td>{judgment}</td>'
                 f'<td>{trigger}</td><td class="n">{start:,.0f}</td>'
                 f'<td class="n">{end:,.0f}（{end_date[5:]}）</td>'
                 f'<td class="n">{chg:+.1f}%</td><td class="pd">{result}</td>'
                 f'<td><a href="{article}">原文</a></td></tr>')
    h = sample
    if verified >= 10:
        rate = round(100 * right / verified)
        summary = (f'<div class="big" style="font-size:28px">正确率 {rate}%</div>'
                   f'<div class="src">已验证 {verified} 条（{right}对 / {wrong}错）；待验证 {pending} 条。</div>')
    else:
        summary = (f'<div class="big" style="font-size:28px">样本不足</div>'
                   f'<div class="src">已验证 {verified} 条（{right}对 / {wrong}错），'
                   f'至少 10 条才计算正确率；待验证 {pending} 条。不凑数。</div>')
    h = re.sub(r'<div class="big" style="font-size:28px">.*?</div><div class="src">已验证 .*?</div>',
               summary, h, count=1, flags=re.S)
    h = re.sub(r'(<div class="src">数据截至 )\d{4}-\d{2}-\d{2}',
               rf'\g<1>{today}', h, count=1)
    h = re.sub(r'(<tr><th>判断日</th>.*?</tr>)(<tr>.*?</tr>)*',
               lambda m: m.group(1) + rows, h, count=1, flags=re.S)
    return _stamps(h, today)


def render_llms(sample, series, today):
    lines = []
    for s in ("pp", "lldpe", "hdpe", "ldpe", "pvc", "abs", "ps", "pet"):
        ent = series[s]
        price, prev = ent[-1][1], ent[-2][1]
        chg = (price / prev - 1) * 100
        win = [p for _, p in ent[-365:]]
        lines.append(f"- [{NAMES[s]}](https://pla365.com/{s}/): {price:.0f} 元/吨，"
                     f"涨跌 {chg:.2f}%，一年{pos_label(price, min(win), max(win))}")
    body = "\n".join(lines)
    return re.sub(r'## \d{4}-\d{2}-\d{2} 价格\n(- .*\n)+',
                  f"## {today} 价格\n{body}\n", sample, count=1)


def render_download(sample, today):
    h = re.sub(r'已填好 \d{4}-\d{2}-\d{2} 的 8 个品种价格',
               f'已填好 {today} 的 8 个品种价格', sample, count=1)
    return _stamps(h, today)


def make_xlsx(template_bytes, series, updated, today):
    """Update the downloadable cost workbook: the price sheet
    (int price / day change / update stamp per variety), the date
    lines, and the 调价测算 defaults (PP 3-month avg -> PP today)."""
    import openpyxl
    from .compute import stats_3m
    wb = openpyxl.load_workbook(io.BytesIO(template_bytes))
    ws = wb["产品成本"]
    ws["A2"] = f"价格日期 {today} · 橙色格子填写，其余自动计算 · 来源 pla365.com"
    ws = wb["原料价格"]
    ws["A1"] = f"原料价格（{today} 生意社基准价，元/吨，含税）"
    for r, s in enumerate(("pp", "lldpe", "hdpe", "ldpe", "pvc", "abs", "ps", "pet"),
                          start=5):
        ent = series[s]
        price, prev = ent[-1][1], ent[-2][1]
        ws.cell(row=r, column=2, value=int(round(price)))
        ws.cell(row=r, column=3, value=f"{(price / prev - 1) * 100:.2f}%")
        ws.cell(row=r, column=4, value=updated[s])
    ws = wb["调价测算"]
    ws["B3"] = int(round(stats_3m(series["pp"])["avg"]))
    ws["B4"] = int(round(series["pp"][-1][1]))
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


def render_today_page(sample, today):
    h = re.sub(r"<title>今日塑料价格一图_.*?</title>",
               f"<title>今日塑料价格一图_{today}_塑价365</title>", sample, count=1)
    h = re.sub(r'(<meta property="og:title" content=")[^"]*(")',
               lambda m: m.group(1) + f"今日塑料价格一图_{today}_塑价365" + m.group(2),
               h, count=1)
    h = re.sub(r"/today/today\.jpg\?d=\d{4}-\d{2}-\d{2}",
               f"/today/today.jpg?d={today}", h, count=1)
    h = re.sub(r'(<img src="/today/today\.jpg[^>]*alt=")[^"]*(")',
               rf'\g<1>{today}塑料价格表\g<2>', h, count=1)
    h = re.sub(r'(<h1>今日塑料价格一图</h1><div class="sub">)\d{4}-\d{2}-\d{2}',
               rf'\g<1>{today}', h, count=1)
    return _stamps(h, today)
