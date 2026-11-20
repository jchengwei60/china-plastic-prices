"""Generate an alert-day push pack （推送包） for days when at least one
variety moves >= 2% in a day (the site's own /alerts/ rule).

Reads only committed pipeline state (data/history.csv, data/sf_basis.csv,
generator/state/extras.json) — no scraping — and, when the target date
has alerts, writes drafts/alert-<date>.md containing everything Jiang
needs to publish the same evening:

- headline candidates in the site's title style (+ platform variants
  for 百家号/头条号/知乎）
- the alert table (price, day change, purchase temperature)
- the full 15-variety day table and the futures/basis table
- a WeChat article framework with the data sentences pre-filled and
  the judgment parts left as prompts (no invented reasons, same rule
  as the weekly draft)
- a 30-second short-video script with the day's numbers filled in
- a judgment-registration line for the /fupan/ scoring system

When the target date has no alerts, nothing is written and the script
exits 0 — most days are not alert days.

Run from the repo root:
    python generator/make_alert_pack.py [YYYY-MM-DD]
The optional argument is the data date to build the pack for; default
is the latest date in history.csv.
"""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from pipeline.basis_data import load_sf_basis  # noqa: E402
from pipeline.compute import percentile, temperature_label  # noqa: E402
from pipeline.dataio import NAMES, SLUGS, load_history  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
FUT_NAMES = {"pp": "聚丙烯PP", "lldpe": "塑料LLDPE", "pvc": "PVC", "pet": "瓶片PR"}
WEEKDAYS = "一二三四五六日"
ALERT_PCT = 2.0


def up_to(series, d):
    return [(dt, p) for dt, p in series if dt <= d]


def day_move(series, d):
    """(price, prev_price, chg_pct, chg_abs) for the entry on date d,
    or None when the series has no entry on d or no previous entry."""
    rows = up_to(series, d)
    if len(rows) < 2 or rows[-1][0] != d:
        return None
    prev, cur = rows[-2][1], rows[-1][1]
    return cur, prev, (cur - prev) / prev * 100.0, cur - prev


def fmt_pct(x):
    return f"{x:+.2f}%"


def main():
    series = load_history(
        (ROOT / "data" / "history.csv").read_text(encoding="utf-8"))
    extras = json.loads(
        (ROOT / "generator" / "state" / "extras.json").read_text(
            encoding="utf-8"))
    basis = load_sf_basis(
        (ROOT / "data" / "sf_basis.csv").read_text(encoding="utf-8-sig"))

    if len(sys.argv) > 1:
        target = sys.argv[1]
    else:
        target = max(s[-1][0] for s in series.values())
    y, m, dd = (int(x) for x in target.split("-"))
    md = f"{m}月{dd}日"
    wd = WEEKDAYS[date(y, m, dd).weekday()]

    # --- collect the day's moves for all 15 varieties ---
    moves = {}   # slug -> (name, price, pct, chg, is_extra, temp, pctile)
    for slug in SLUGS:
        mv = day_move(series[slug], target)
        if mv is None:
            continue
        cur, _prev, pct, chg = mv
        pctile = percentile(up_to(series[slug], target))
        moves[slug] = (NAMES[slug], cur, pct, chg, False,
                       temperature_label(pctile), pctile)
    for slug, st in extras.items():
        rows = [(dt, p) for dt, p in st["series"] if dt <= target]
        if len(rows) < 2 or rows[-1][0] != target:
            continue
        prev, cur = rows[-2][1], rows[-1][1]
        pct = (cur - prev) / prev * 100.0
        pctile = percentile(rows)
        moves[slug] = (st["name"], cur, pct, cur - prev, True,
                       temperature_label(pctile), pctile)

    alerts = {s: v for s, v in moves.items() if abs(v[2]) >= ALERT_PCT}
    if not alerts:
        print(f"{target}: no variety moved >= {ALERT_PCT}% - no pack")
        return
    ranked = sorted(alerts.items(), key=lambda kv: -abs(kv[1][2]))
    top_slug, top = ranked[0]
    top_dir = "涨" if top[2] > 0 else "跌"

    out = []
    out.append(f"# 异动日推送包 · {target}（周{wd}）")
    out.append("")
    trig = "、".join(f"{v[0]}{fmt_pct(v[2])}" for _s, v in ranked)
    out.append(f"触发：{trig}（单日涨跌达到 ±2% 的异动线）。")
    out.append("")

    # --- headline candidates ---
    out.append("## 标题候选（挑一条，补上立场再用）")
    for slug, v in ranked:
        name, cur, pct, chg, _e, _t, _p = v
        d = "涨" if pct > 0 else "跌"
        out.append(
            f"- {name}价格{md}：基准价{cur:.0f}元/吨，单日{d}{abs(chg):.0f}元"
            f"（{fmt_pct(pct)}），【立场待填：我追 / 我不追 / 分批】")
    if len(ranked) >= 2:
        names = "、".join(v[0] for _s, v in ranked[:3])
        out.append(
            f"- 塑料价格{md}：{len(ranked)}个品种异动，{names}领{top_dir}，"
            f"【立场待填】")
    if top_slug in basis:
        rows = [r for r in basis[top_slug] if r["date"] <= target]
        if rows:
            r = rows[-1]
            out.append(
                f"- {top[0]}价格{md}：现货{r['spot']:.0f}、期货{r['close']:.0f}，"
                f"基差{r['basis']:+.0f}，【立场待填】")
    out.append("")
    out.append("平台变体（同一篇内容换标题）：")
    out.append(
        f"- 百家号/头条号：{top[0]}一天{top_dir}{abs(top[2]):.2f}%，"
        f"现在补货划算吗？{md}最新报价")
    out.append(
        f"- 知乎：如何看待{md}{top[0]}{top_dir}{abs(top[2]):.2f}%？"
        f"采购现在该出手吗？")
    out.append("")

    # --- alert table ---
    out.append("## 异动数据")
    out.append("")
    out.append("| 品种 | 今日价（元/吨） | 涨跌（元） | 涨跌幅 | 采购温度 |")
    out.append("|---|---|---|---|---|")
    for _s, v in ranked:
        name, cur, pct, chg, _e, temp, pctile = v
        out.append(f"| {name} | {cur:.0f} | {chg:+.0f} | {fmt_pct(pct)} "
                   f"| {temp}（近一年{pctile:.0f}%分位） |")
    out.append("")

    # --- full day table ---
    out.append("## 全品种今日价（15 个）")
    out.append("")
    out.append("| 品种 | 今日价 | 涨跌幅 | 品种 | 今日价 | 涨跌幅 |")
    out.append("|---|---|---|---|---|---|")
    all_rows = []
    for slug in SLUGS:
        if slug in moves:
            v = moves[slug]
            all_rows.append((v[0], v[1], v[2]))
    for slug in extras:
        if slug in moves:
            v = moves[slug]
            all_rows.append((v[0] + "*", v[1], v[2]))
    for i in range(0, len(all_rows), 2):
        left = all_rows[i]
        right = all_rows[i + 1] if i + 1 < len(all_rows) else None
        ltxt = f"{left[0]} | {left[1]:.0f} | {fmt_pct(left[2])}"
        rtxt = (f"{right[0]} | {right[1]:.0f} | {fmt_pct(right[2])}"
                if right is not None else " |  | ")
        out.append(f"| {ltxt} | {rtxt} |")
    out.append("")
    out.append("* 次要品种为生意社大宗榜相邻两期涨跌。")
    out.append("")

    # --- futures & basis ---
    out.append("## 期货与基差")
    out.append("")
    out.append("| 品种 | 生意社基准价 | 主力合约 | 期货价 | 基差 | 基差较昨日 |")
    out.append("|---|---|---|---|---|---|")
    for slug in ("pp", "lldpe", "pvc", "pet"):
        rows = [r for r in basis.get(slug, []) if r["date"] <= target]
        if not rows:
            continue
        r = rows[-1]
        bchg = (f"{r['basis'] - rows[-2]['basis']:+.0f}"
                if len(rows) >= 2 else "—")
        out.append(f"| {FUT_NAMES[slug]} | {r['spot']:.0f} | {r['contract']} "
                   f"| {r['close']:.0f} | {r['basis']:+.0f} | {bchg} |")
    out.append("")
    out.append("（基差 = 生意社品种基准价 − 期货主力收盘；期货为最近一个交易日。）")
    out.append("")

    # --- WeChat article framework ---
    top_sentence = (
        f"{md}，{top[0]}基准价{top[1]:.0f}元/吨，单日{top_dir}"
        f"{abs(top[3]):.0f}元（{fmt_pct(top[2])}），"
        f"采购温度{top[5]}（近一年{top[6]:.0f}%分位）。")
    out.append("## 公众号文章框架（判断部分待填，不要原样发）")
    out.append("")
    out.append(f"开头（数据句已备好）：{top_sentence}")
    out.append("")
    out.append("为什么涨/跌【待填，从有的写：成本（原油、期货盘面）／"
               "供应（检修、开工率、新装置）／需求（下游订单、补库）】")
    out.append("")
    out.append("追还是等【待填：立场（追／等／分批）+ 一句理由 + "
               "一个触发价位（比如跌破 X 或站稳 Y 就改变主意）】")
    out.append("")
    out.append("我可能错在哪【待填：出现什么情况说明这次判断错了】")
    out.append("")
    out.append("固定收尾（可直接用）：价格数据来自生意社基准价与大宗榜，"
               "期货为前一交易日收盘。判断只代表当日看法，不构成采购建议；"
               "14 天后本站复盘页会公开对错。")
    out.append("")

    # --- short-video script ---
    out.append("## 短视频脚本（约 30 秒，数字已填）")
    out.append("")
    second = ""
    if len(ranked) >= 2:
        s2 = ranked[1][1]
        second = (f"；{s2[0]}报{s2[1]:.0f}元/吨，"
                  f"{'涨' if s2[2] > 0 else '跌'}{abs(s2[2]):.2f}%")
    out.append(f"- 0–5 秒：今天塑料价格异动——{top[0]}{top_dir}了"
               f"{abs(top[2]):.2f}%。")
    out.append(f"- 5–15 秒：{top[0]}报{top[1]:.0f}元/吨，"
               f"一天{top_dir}{abs(top[3]):.0f}元{second}。")
    out.append(f"- 15–25 秒：这个价在近一年里算{top[5]}。"
               f"【立场句待填：所以我的建议是……】")
    out.append("- 25–30 秒：每天的价格和判断，关注塑价365。")
    out.append("- 画面：今日分享卡做底，字幕逐句上；封面标题用上面的候选标题。")
    out.append("")

    # --- judgment registration ---
    out.append("## 判断登记（发完文章把这一行补全发我，我记进复盘系统）")
    out.append("")
    for slug, v in ranked:
        out.append(f"- 日期 {target}｜品种 {v[0]}｜判断【追／等／分批】"
                   f"｜触发条件【待填】")
    out.append("")
    out.append("---")
    out.append(f"数据来源：生意社基准价/橡塑大宗榜（{target}），"
               "期货为最近交易日收盘。本包由管线自动生成，"
               "【待填】部分未经填写不要直接发布。")

    path = ROOT / "drafts" / f"alert-{target}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(out) + "\n", encoding="utf-8")
    print(f"wrote {path.relative_to(ROOT)} "
          f"({len(ranked)} alert(s), top: {top[0]} {fmt_pct(top[2])})")


if __name__ == "__main__":
    main()
