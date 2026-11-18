"""Render /wenda/ （常见问题）: 23 Q&As whose answers update daily.

Dynamic answers (the rest stay as written):
- 8 variety price answers (day/week/month/year changes)
- biggest mover, year-on-year ranking, cheapest-to-dearest ranking
- 4 pair-spread answers (same pairs as /spread/)
- 3 position answers (PP/PVC/LLDPE: 366-entry range + percentile;
  position bands 70/30 — only 偏高 is observed in the sample)
- 2 basis answers (PP/PVC, from sf_basis.csv's latest row)
- the PP food-box cost answer (same math as /cost/pp-food-box/)
Each answer appears twice (visible card + FAQ JSON-LD); both copies
are replaced. Verified in tests/verify_wenda.py — PS's daily change
differs by the known source-revision artifact.
"""
from __future__ import annotations

import re

from .basis_data import load_sf_basis
from .dataio import NAMES
from .render_cost import _costs
from .render_history import _m_d, _stamps
from .render_spread import PAIRS

SLUGS = ["pp", "lldpe", "hdpe", "ldpe", "pvc", "abs", "ps", "pet"]
FUT_NAME = {"pp": "聚丙烯PP", "pvc": "PVC"}


def _chg(ent, i, back):
    return (ent[i][1] / ent[i - back][1] - 1) * 100


def _word(v):
    return ("涨" if v >= 0 else "跌") + f"{abs(v):.1f}%"


def _suffix(today):
    return f"（生意社品种基准价，数据日期{today}，塑价365整理）"


def build_answers(series, basis_rows, today):
    md = _m_d(today)
    idx = {s: [d for d, _ in series[s]].index(today) for s in SLUGS}
    ans = {}
    year_chg = {}
    for s in SLUGS:
        ent, i = series[s], idx[s]
        price = ent[i][1]
        year_chg[s] = _chg(ent, i, 365)
        ans[f"{NAMES[s]}今天多少钱一吨？"] = (
            f"{md}{NAMES[s]}基准价{price:,.0f}元/吨，日涨跌{_chg(ent, i, 1):.2f}%；"
            f"较一周前{_word(_chg(ent, i, 7))}，较一个月前{_word(_chg(ent, i, 30))}，"
            f"较一年前{_word(year_chg[s])}{_suffix(today)}。")
    chgs = {s: _chg(series[s], idx[s], 1) for s in SLUGS}
    top = bot = SLUGS[0]
    for s in SLUGS:  # ties: the last variety in list order wins
        if chgs[s] >= chgs[top]:
            top = s
        if chgs[s] <= chgs[bot]:
            bot = s
    ans["今天哪种塑料原料涨得最多、哪种跌得最多？"] = (
        f"{md}8个主要品种中，日涨幅最大的是{NAMES[top]}（{chgs[top]:.2f}%，"
        f"{series[top][idx[top]][1]:,.0f}元/吨），最弱的是{NAMES[bot]}（{chgs[bot]:.2f}%，"
        f"{series[bot][idx[bot]][1]:,.0f}元/吨）{_suffix(today)}。")
    ranked = sorted(SLUGS, key=lambda s: -year_chg[s])
    ans["塑料原料价格比去年贵了多少？"] = (
        "与一年前相比：" + "；".join(f"{NAMES[s]}{_word(year_chg[s])}" for s in ranked)
        + _suffix(today) + "。")
    by_price = sorted(SLUGS, key=lambda s: series[s][idx[s]][1])
    ans["现在哪种塑料原料最便宜、哪种最贵？"] = (
        f"{md}按基准价从低到高：" + "、".join(
            f"{NAMES[s]} {series[s][idx[s]][1]:,.0f}" for s in by_price)
        + "（元/吨）" + _suffix(today) + "。")
    for _, a, b in PAIRS:
        pa, pb = series[a][idx[a]][1], series[b][idx[b]][1]
        winner, diff = (NAMES[a], pa - pb) if pa >= pb else (NAMES[b], pb - pa)
        ans[f"{NAMES[a]}和{NAMES[b]}哪个贵？差多少？"] = (
            f"{md}{NAMES[a]}基准价{pa:,.0f}元/吨，{NAMES[b]}基准价{pb:,.0f}元/吨，"
            f"{winner}贵{diff:,.0f}元/吨{_suffix(today)}。价差的近一年走势和分位见价差页。")
    for s in ("pp", "pvc", "lldpe"):
        ent, i = series[s], idx[s]
        win = [p for _, p in ent[i - 365: i + 1]]
        price = ent[i][1]
        pct = int(round(100 * sum(1 for v in win if v <= price) / len(win)))
        band = "偏高" if pct >= 70 else ("偏低" if pct <= 30 else "中间")
        ans[f"{NAMES[s]}价格现在算高还是低？还会涨（跌）吗？"] = (
            f"{md}{NAMES[s]}基准价{price:,.0f}元/吨，近一年区间{min(win):,.0f}～{max(win):,.0f}元/吨，"
            f"当前高于近一年{pct}%的日子，处于{band}位置{_suffix(today)}。"
            f"价格后面怎么走没人能保证，工厂采购可按用量分批买，并关注期货和石化出厂价变化。")
    for s in ("pp", "pvc"):
        row = basis_rows[s][-1]
        ans[f"{NAMES[s]}期货和现货差多少？"] = (
            f"{row['date']}大商所{FUT_NAME[s]}主力连续收盘{row['close']:,.0f}元/吨，"
            f"生意社现货基准价{row['spot']:,.0f}元/吨，基差{row['basis']:+,.0f}元/吨"
            f"（现货减期货，正数为现货升水）。")
    price = int(round(series["pp"][idx["pp"]][1]))
    single, wan, per_ton = _costs(price, 18, 3)
    ans["一吨PP能做多少个餐盒？原料成本多少？"] = (
        f"按每个餐盒18克、损耗3%（假设）计算，一吨PP约做{per_ton:,}个；"
        f"按{md}PP拉丝基准价{price:,}元/吨，每个原料成本约{single:.3f}元，"
        f"一万个约{wan:,}元。克重不同结果不同，可在成本页改成自己的规格。")
    return ans


def render_wenda(sample, series, basis_csv_text, today):
    rows = load_sf_basis(basis_csv_text)
    answers = build_answers(series, rows, today)
    h = sample
    for q, new in answers.items():
        pat = re.compile(
            r'(<h2 style="font-size:17px;margin:0 0 6px">' + re.escape(q) +
            r'</h2><p>)[^<]*(</p>)')
        h = pat.sub(lambda m: m.group(1) + new + m.group(2), h, count=1)
        # JSON-LD copy: the same answer text inside the FAQPage script
        pat2 = re.compile(r'("name": "' + re.escape(q) +
                          r'", "acceptedAnswer": \{"@type": "Answer", "text": ")[^"]*(")')
        h = pat2.sub(lambda m: m.group(1) + new + m.group(2), h, count=1)
    h = re.sub(r'("dateModified": ")\d{4}-\d{2}-\d{2}(")', rf'\g<1>{today}\g<2>', h, count=1)
    h = re.sub(r'(<h1>塑料价格常见问题（)[^）]+(更新）</h1>)',
               rf'\g<1>{_m_d(today)}\g<2>', h, count=1)
    return _stamps(h, today)
