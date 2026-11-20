"""Generate the Monday weekly-report data draft （底稿）.

Reads only committed pipeline state (data/history.csv, data/sf_basis.csv,
generator/state/extras.json) — no scraping — and writes a Markdown draft
to drafts/weekly-<monday>.md with every data section filled in:

- headline candidates (biggest weekly mover, in the site's title style)
- weekly price table for all 15 varieties (close, weekly change,
  current purchase temperature / percentile)
- the week's single-day alerts (|change| >= 2%, the /alerts/ rule)
- futures & basis table (week change of basis and of the futures close)
- temperature-band changes during the week
- the stored judgments from /fupan/ with their 14-day outcomes

Judgment itself （为什么涨/跌， 补不补， 下周看什么） is left as a short
prompted framework for Jiang to fill — the draft deliberately contains
no invented reasons.

Run from the repo root:
    python generator/make_weekly_draft.py [YYYY-MM-DD]
The optional argument is the Monday the draft is issued on; the report
week is the Mon-Sun week that just ended. Default: the most recent
Monday (today if today is Monday).
"""
from __future__ import annotations

import html
import json
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from pipeline.articles_meta import ARTICLES  # noqa: E402
from pipeline.basis_data import load_sf_basis  # noqa: E402
from pipeline.compute import percentile, temperature_label  # noqa: E402
from pipeline.dataio import NAMES, load_history  # noqa: E402
from pipeline.news import format_lines, items_between  # noqa: E402
from pipeline.render_misc import JUDGMENTS  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
FUT_NAMES = {"pp": "聚丙烯PP", "lldpe": "塑料LLDPE", "pvc": "PVC", "pet": "瓶片PR"}


def on_or_before(series, d):
    out = None
    for dt, p in series:
        if dt <= d:
            out = (dt, p)
        else:
            break
    return out


def fmt(v, dec=0):
    return f"{v:,.{dec}f}"


def pct(part, whole):
    return (part / whole - 1) * 100 if whole else 0.0


def band(series, upto):
    """(percentile, temperature label) at the last entry <= upto."""
    sub = [(d, p) for d, p in series if d <= upto]
    if not sub:
        return None, None
    pc = percentile(sub)
    return pc, temperature_label(pc)


def main():
    if len(sys.argv) > 1:
        monday = date.fromisoformat(sys.argv[1])
    else:
        today = date.today()
        monday = today - timedelta(days=today.weekday())
    sunday = monday - timedelta(days=1)
    prev_sunday = sunday - timedelta(days=7)
    sun_s, prev_s = sunday.isoformat(), prev_sunday.isoformat()
    week_start = (sunday - timedelta(days=6)).isoformat()

    news_file = ROOT / "generator" / "state" / "news.json"
    news_items = (json.loads(news_file.read_text(encoding="utf-8"))
                  .get("items", []) if news_file.exists() else [])

    series = load_history((ROOT / "data" / "history.csv").read_text(encoding="utf-8"))
    extras = json.loads((ROOT / "generator" / "state" / "extras.json").read_text(encoding="utf-8"))
    for slug, ent in extras.items():
        series[slug] = [(d, float(p)) for d, p in ent["series"]]
    names = dict(NAMES)
    for slug, ent in extras.items():
        names[slug] = ent["name"]
    order = list(NAMES) + list(extras)

    rows, alerts, band_changes = [], [], []
    for slug in order:
        ser = series[slug]
        c_now, c_prev = on_or_before(ser, sun_s), on_or_before(ser, prev_s)
        if not c_now or not c_prev:
            continue
        wchg = pct(c_now[1], c_prev[1])
        pc, lab = band(ser, sun_s)
        rows.append((slug, c_now, c_prev, wchg, pc, lab))
        prev_ent = None
        for dt, p in ser:
            if prev_ent and prev_s < dt <= sun_s:
                ch = pct(p, prev_ent[1])
                if abs(ch) >= 2:
                    alerts.append((dt, slug, ch, p))
            prev_ent = (dt, p)
        _, lab_prev = band(ser, prev_s)
        if lab and lab_prev and lab != lab_prev:
            band_changes.append((slug, lab_prev, lab))

    rows_by_abs = sorted(rows, key=lambda r: -abs(r[3]))
    top = rows_by_abs[0] if rows_by_abs else None

    def title_for(r):
        slug, c_now, c_prev, wchg, _, _ = r
        d = abs(c_now[1] - c_prev[1])
        verb = "涨" if wchg >= 0 else "跌"
        return (f"塑料价格周报{monday.month}月{monday.day}日："
                f"{names[slug]}一周{verb}{fmt(d)}元，（为什么/补不补——待补）")

    basis = load_sf_basis((ROOT / "data" / "sf_basis.csv").read_text(encoding="utf-8"))
    basis_rows = []
    for slug in ["pp", "lldpe", "pvc", "pet"]:
        brows = basis.get(slug) or []
        now = next((r for r in reversed(brows) if r["date"] <= sun_s), None)
        prev = next((r for r in reversed(brows) if r["date"] <= prev_s), None)
        if now and prev:
            basis_rows.append((slug, now, prev))

    L = []
    L.append(f"# 周报底稿（{week_start} 至 {sun_s}，{monday.isoformat()} 发布）")
    L.append("")
    L.append("## 候选标题")
    if top:
        L.append(f"- {title_for(top)}")
        others = [r for r in rows_by_abs if r[0] != top[0] and abs(r[3]) >= 1]
        if others:
            L.append(f"- {title_for(others[0])}")
    L.append("")
    L.append("## 本周价格（生意社基准价，元/吨）")
    L.append("")
    L.append("| 品种 | 周末价 | 周涨跌 | 周涨跌% | 采购温度（分位） |")
    L.append("| --- | ---: | ---: | ---: | --- |")
    for slug, c_now, c_prev, wchg, pc, lab in sorted(rows, key=lambda r: -r[3]):
        star = "*" if slug in extras else ""
        L.append(f"| {names[slug]}{star} | {fmt(c_now[1])} | "
                 f"{c_now[1] - c_prev[1]:+,.0f} | {wchg:+.2f}% | "
                 f"{lab or '—'}（{pc:.0f}%） |")
    L.append("")
    L.append(f"数据截至 {sun_s}（周末取最近一个有数据的日子）；带 * 为大宗榜品种，"
             "分位按实际观测点计算。")
    L.append("")
    L.append("## 本周异动（单日涨跌 ≥2%；大宗榜品种为相邻两期榜单变化）")
    L.append("")
    if alerts:
        for dt, slug, ch, p in alerts:
            L.append(f"- {dt} {names[slug]}：{ch:+.2f}%（{fmt(p)} 元/吨）")
    else:
        L.append("- 本周无单日异动。")
    L.append("")
    L.append("## 期货与基差")
    L.append("")
    L.append("| 品种 | 现货 | 主力合约 | 期货收盘 | 基差 | 基差周变化 | 期货周涨跌 |")
    L.append("| --- | ---: | --- | ---: | ---: | ---: | ---: |")
    for slug, now, prev in basis_rows:
        L.append(f"| {FUT_NAMES[slug]} | {fmt(now['spot'])} | {now['contract']} | "
                 f"{fmt(now['close'])} | {now['basis']:+,.0f} | "
                 f"{now['basis'] - prev['basis']:+,.0f} | "
                 f"{pct(now['close'], prev['close']):+.2f}% |")
    L.append("")
    L.append(f"基差 = 生意社现货基准价 − 期货主力收盘价；取 {sun_s} 及之前最近的交易日。")
    L.append("")
    L.append("## 温度变化")
    L.append("")
    if band_changes:
        for slug, a, b in band_changes:
            L.append(f"- {names[slug]}：{a} → {b}")
    else:
        L.append("- 本周无品种温度档位变化。")
    L.append("")
    week_news = items_between(news_items, week_start, sun_s)
    L.append("## 行业动态（本周，生意社资讯）")
    L.append("")
    if week_news:
        L += format_lines(week_news[:15])
    else:
        L.append("- 本周暂无抓取到的行业动态（新闻状态为空或本周无匹配条目）。")
    L.append("")
    L.append("## 本周可写选题（按站内文章空白优先）")
    L.append("")
    cov = {}
    for a in ARTICLES:
        for s in a[4]:
            cov[s] = cov.get(s, 0) + 1
    wchg_by_slug = {r[0]: r[3] for r in rows}
    angles = {"检修": "供应收缩能持续多久、复产时间表、对价格的支撑",
              "涨价": "涨价函的落地力度、下游接单情况、与现货价差",
              "政策": "政策影响的品种与执行时间、进出口量变化",
              "产能": "新产能投放节奏与价格中枢、老装置出清"}
    cands = []
    for it in week_news:
        hot = [c for c in it.get("cats", []) if c in angles]
        if not hot:
            continue
        for s in it.get("varieties", []) or ["macro"]:
            cands.append((cov.get(s, 0) if s != "macro" else 2,
                          it, s, hot[0]))
    cands.sort(key=lambda x: x[0])
    picked, seen_slugs = [], set()
    for _, it, s, cat in cands:
        if s in seen_slugs or len(picked) >= 4:
            continue
        seen_slugs.add(s)
        picked.append((it, s, cat))
    if picked:
        for it, s, cat in picked:
            vname = names.get(s, "通用")
            move = (f"，本周{vname}{'涨' if wchg_by_slug[s] >= 0 else '跌'}"
                    f"{abs(wchg_by_slug[s]):.2f}%"
                    if s in wchg_by_slug else "")
            L.append(f"- 【{vname}·{cat}】{it['title']}（{it['date'][5:]}）{move}")
            L.append(f"  可写角度：{angles[cat]}")
            L.append(f"  素材：{it['url']}")
    else:
        L.append("- 本周无突出的检修/涨价/政策/产能类选题。")
    L.append("")
    L.append("## 判断跟踪（复盘页现有记录）")
    L.append("")
    for jdate, slug, judgment, trigger, _art in JUDGMENTS:
        ser = series[slug]
        start = on_or_before(ser, jdate)
        tgt = (date.fromisoformat(jdate) + timedelta(days=14)).isoformat()
        end = next(((d, p) for d, p in ser if d >= tgt), None)
        if start and end:
            res = f"14天后 {pct(end[1], start[1]):+.1f}%（{end[0]}）"
        else:
            res = "待验证"
        L.append(f"- {jdate} {names[slug]}：{html.unescape(judgment)}")
        L.append(f"  触发条件：{html.unescape(trigger)}；结果：{res}")
    L.append("")
    L.append("（本周如发布新判断，把日期、品种、方向和触发条件记下来，"
             "发布后同步登记进复盘系统。）")
    L.append("")
    L.append("## 待补：判断部分（框架）")
    L.append("")
    L.append("### 这波为什么涨/跌")
    L.append("- 成本（原油/丙烯/煤等）：")
    L.append("- 供应（检修、开工率、新装置）：")
    L.append("- 需求（下游开工、订单）：")
    L.append("")
    L.append("### 现在补不补，看库存")
    L.append("- 库存不到一周的：")
    L.append("- 库存还有两三周的：")
    L.append("- 有大单要锁成本的：")
    L.append("")
    L.append("### 下周关注")
    L.append("- ")
    L.append("")
    L.append("## 数据来源")
    L.append("")
    L.append("价格为生意社（100ppi.com）品种基准价（市场均价，非具体牌号成交价），"
             "期货为主力合约收盘价（经新浪财经），基差、温度按本站公开规则计算。"
             "仅供参考，不构成交易建议。")
    L.append("")

    out = ROOT / "drafts" / f"weekly-{monday.isoformat()}.md"
    out.parent.mkdir(exist_ok=True)
    out.write_text("\n".join(L), encoding="utf-8")
    print(f"wrote {out.relative_to(ROOT)}")
    if top:
        print(f"top mover: {names[top[0]]} {top[3]:+.2f}%")
    print(f"alerts: {len(alerts)}, band changes: {len(band_changes)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
