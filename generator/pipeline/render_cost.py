"""Render /cost/ product pages + index, and refresh the price
constant embedded in the calculator/tool pages.

Every cost page carries a script constant with all 8 varieties'
rounded prices today / 30 entries ago / 365 entries ago:
  const C={"pp": {"n": "PP拉丝", "p": 11100, "m": 10583, "y": 6707}, ...}
The same constant (plus the global date stamps) is the only dynamic
content of six /tools/ pages. All cost math uses the rounded int
prices (the p/m/y values): single = price * grams * (1+loss) / 1e6;
per-10000 = round(single * 10000); diffs = round(delta_single * 10000);
units per tonne = round(1e6 / (grams * (1+loss))).
Verified against the 2026-11-10 bundle in tests/verify_cost.py.
"""
from __future__ import annotations

import json
import re

from .dataio import NAMES
from .render_history import _meta_truncate, _stamps

SLUGS = ["pp", "lldpe", "hdpe", "ldpe", "pvc", "abs", "ps", "pet"]


def price_triple(ent, today):
    dates = [d for d, _ in ent]
    i = dates.index(today)
    return (int(round(ent[i][1])), int(round(ent[i - 30][1])),
            int(round(ent[i - 365][1])))


def const_c(series, today):
    obj = {}
    for s in SLUGS:
        p, m, y = price_triple(series[s], today)
        obj[s] = {"n": NAMES[s], "p": p, "m": m, "y": y}
    return "const C=" + json.dumps(obj, ensure_ascii=False) + ";"


def render_const_c(sample, series, today):
    """Pages whose only dynamics are the C constant + date stamps."""
    h = re.sub(r"const C=\{.*?\};", lambda m: const_c(series, today),
               sample, count=1, flags=re.S)
    return _stamps(h, today)


def _g(x):
    return f"{x:g}"


def _costs(price, grams, loss):
    single = price * grams * (1 + loss / 100) / 1e6
    return single, round(single * 10000), round(1e6 / (grams * (1 + loss / 100)))


def product_params(sample):
    m = (re.search(r'<input type="hidden" id="v" value="([a-z]+)">', sample)
         or re.search(r'<option value="([a-z]+)" selected>', sample))
    parent = m.group(1)
    product = re.search(r'按今日价格自动更新 · ([^<]+)</div>', sample).group(1)
    para = re.search(r'<p>(按今天[^<]+)</p>', sample).group(1)
    grams = float(re.search(r' ([\d.]+) 克、损耗', para).group(1))
    loss = float(re.search(r'损耗 ([\d.]+)%', para).group(1))
    unit = re.search(r'一万(.)约', para).group(1)
    mat = "PVC树脂" if "每米PVC树脂" in para else ""
    options = [float(v) for v in re.findall(r'<tr><td>([\d.]+) 克</td>', sample)]
    return parent, product, grams, loss, unit, mat, options


def cost_paragraph(series, parent, product, grams, loss, unit, mat, today):
    dates = [d for d, _ in series[parent]]
    i = dates.index(today)
    # the published costs are computed from the rounded int prices
    # (the same p/m/y values embedded in the pages' const C)
    price = int(round(series[parent][i][1]))
    single, wan, per_ton = _costs(price, grams, loss)
    parts = []
    for j in (i - 30, i - 365):
        s_then, _, _ = _costs(int(round(series[parent][j][1])), grams, loss)
        diff = round((single - s_then) * 10000)
        parts.append((diff, "多" if diff >= 0 else "少"))
    return (f"按今天{NAMES[parent]}基准价 {price:,.0f} 元/吨、每{unit}{mat} {_g(grams)} 克、"
            f"损耗 {_g(loss)}% 计算，一{unit}{product}的原料成本约 {single:.3f} 元，"
            f"一万{unit}约 {wan:,} 元，1吨料大约能做 {per_ton:,} {unit}。"
            f"比一个月前{parts[0][1]} {abs(parts[0][0]):,} 元/万{unit}，"
            f"比一年前{parts[1][1]} {abs(parts[1][0]):,} 元/万{unit}。")


def render_cost_page(sample, series, today):
    parent, product, grams, loss, unit, mat, options = product_params(sample)
    para = cost_paragraph(series, parent, product, grams, loss, unit, mat, today)
    old_para = re.search(r'<p>(按今天[^<]+)</p>', sample).group(1)
    h = sample.replace(old_para, para)
    for prop in ('name="description"', 'property="og:description"'):
        h = re.sub(rf'(<meta {prop} content=")[^"]*(")',
                   lambda m: m.group(1) + _meta_truncate(para) + m.group(2), h, count=1)
    h = re.sub(r'\d{4}-\d{2}-\d{2}( 按今日价格自动更新 · )',
               today + r'\g<1>', h, count=1)
    price = int(round(dict(series[parent])[today]))
    rows = ""
    for g in options:
        s, w, n = _costs(price, g, loss)
        rows += (f'<tr><td>{_g(g)} 克</td><td>{s:.3f} 元</td>'
                 f'<td>{w:,} 元</td><td class="n">{n:,}</td></tr>')
    h = re.sub(r'(<tr><th>克重</th>.*?</tr>)(<tr><td>[\d.]+ 克</td>.*?</tr>)+',
               lambda m: m.group(1) + rows, h, count=1, flags=re.S)
    h = re.sub(r'(<input id="pr" type="number" value=")\d+(")',
               rf'\g<1>{int(round(price))}\g<2>', h, count=1)
    h = render_const_c(h, series, today)
    return h


def render_cost_index(sample, series, today, page_samples):
    h = sample
    for slug, psample in page_samples.items():
        parent, product, grams, loss, unit, mat, _ = product_params(psample)
        price = int(round(dict(series[parent])[today]))
        single, wan, _ = _costs(price, grams, loss)
        row = (f'<tr><td><a href="/cost/{slug}/">{product}</a></td>'
               f'<td>{_g(grams)} 克/{unit}</td><td>{single:.3f} 元</td>'
               f'<td>{wan:,} 元</td></tr>')
        h = re.sub(r'<tr><td><a href="/cost/' + slug + r'/">.*?</tr>',
                   lambda m: row, h, count=1, flags=re.S)
    return _stamps(h, today)
