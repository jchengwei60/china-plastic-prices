"""Generate the publish-ready WeChat （公众号） pack for the Monday
weekly report.

Companion to make_weekly_draft.py: same committed-state inputs, same
report week (the Mon-Sun week that just ended), but the output is a
finished package instead of an internal draft:

- drafts/wechat-<monday>.html — the article body with inline styles,
  ready to paste into the mp.weixin.qq.com editor. Every data section
  is filled in; the judgment parts are clearly marked 【待补】 boxes
  for Jiang to complete in the editor (nothing is invented).
- drafts/wechat-<monday>.md — the publishing checklist: title
  candidates, the summary (<=120 chars), cover suggestion, backend
  settings, and the fill-in list.

Run from the repo root:
    python generator/make_wechat_pack.py [YYYY-MM-DD]
The optional argument is the Monday the issue is published on.
"""
from __future__ import annotations

import json
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from pipeline.basis_data import load_sf_basis  # noqa: E402
from pipeline.compute import percentile, temperature_label  # noqa: E402
from pipeline.dataio import NAMES, load_history  # noqa: E402
from pipeline.news import items_between  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
FUT_NAMES = {"pp": "聚丙烯PP", "lldpe": "塑料LLDPE", "pvc": "PVC", "pet": "瓶片PR"}
UP, DN, FL = "#d93025", "#188038", "#666666"


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
    sub = [(d, p) for d, p in series if d <= upto]
    if not sub:
        return None, None
    pc = percentile(sub)
    return pc, temperature_label(pc)


def col(chg):
    return UP if chg > 0 else (DN if chg < 0 else FL)


def h2(text):
    return ('<section style="margin:26px 0 12px;padding:8px 12px;'
            'background:#f7f8fa;border-left:3px solid #333333;">'
            f'<strong style="font-size:16px;color:#222222;">{text}</strong>'
            '</section>')


def todo_box(title, lines):
    lis = "".join(
        f'<p style="margin:6px 0;font-size:15px;line-height:1.75;'
        f'color:#333333;">{ln}</p>' for ln in lines)
    return ('<section style="margin:18px 0;padding:12px 14px;'
            'border:1.5px dashed #d93025;border-radius:8px;'
            'background:#fff8f8;">'
            f'<p style="margin:0 0 6px;font-size:15px;color:#d93025;">'
            f'<strong>【待补】{title}</strong></p>{lis}</section>')


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
    series = load_history((ROOT / "data" / "history.csv")
                          .read_text(encoding="utf-8"))
    extras = json.loads((ROOT / "generator" / "state" / "extras.json")
                        .read_text(encoding="utf-8"))
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
    rows.sort(key=lambda r: -r[3])
    top = rows[0] if rows else None
    n_up = sum(1 for r in rows if r[3] > 0)
    n_dn = sum(1 for r in rows if r[3] < 0)

    basis = load_sf_basis((ROOT / "data" / "sf_basis.csv")
                          .read_text(encoding="utf-8"))
    basis_rows = []
    for slug in ["pp", "lldpe", "pvc", "pet"]:
        brows = basis.get(slug) or []
        now = next((r for r in reversed(brows) if r["date"] <= sun_s), None)
        prev = next((r for r in reversed(brows) if r["date"] <= prev_s), None)
        if now and prev:
            basis_rows.append((slug, now, prev))

    week_news = items_between(news_items, week_start, sun_s)

    # ---------- article HTML ----------
    H = []
    H.append('<section style="font-size:15px;line-height:1.75;'
             'color:#333333;">')
    if top:
        d = abs(top[1][1] - top[2][1])
        verb = "涨" if top[3] >= 0 else "跌"
        lead = (f"本周塑料价格 {n_up} 涨 {n_dn} 跌。动静最大的是"
                f"{names[top[0]]}：一周{verb} {fmt(d)} 元/吨"
                f"（{top[3]:+.2f}%），周末价 {fmt(top[1][1])} 元/吨，"
                f"采购温度「{top[5]}」。全周价格、基差和行业动态都在下面，"
                f"补不补的判断在文末。")
    else:
        lead = "本周塑料价格数据如下。"
    H.append(f'<p style="margin:0 0 10px;">{lead}</p>')
    H.append(todo_box("本周定调一句话",
                      ["（用一句话概括本周：比如「成本撑着、需求拖着」——"
                       "写完删掉本框。）"]))

    H.append(h2("本周价格"))
    trs = ['<tr><th style="padding:6px 8px;background:#f7f8fa;'
           'border:1px solid #e5e7eb;text-align:left;">品种</th>'
           '<th style="padding:6px 8px;background:#f7f8fa;'
           'border:1px solid #e5e7eb;text-align:right;">周末价</th>'
           '<th style="padding:6px 8px;background:#f7f8fa;'
           'border:1px solid #e5e7eb;text-align:right;">周涨跌</th>'
           '<th style="padding:6px 8px;background:#f7f8fa;'
           'border:1px solid #e5e7eb;text-align:left;">采购温度</th></tr>']
    for slug, c_now, c_prev, wchg, pc, lab in rows:
        star = "*" if slug in extras and slug != "pc" else ""
        trs.append(
            f'<tr><td style="padding:6px 8px;border:1px solid #e5e7eb;">'
            f'{names[slug]}{star}</td>'
            f'<td style="padding:6px 8px;border:1px solid #e5e7eb;'
            f'text-align:right;">{fmt(c_now[1])}</td>'
            f'<td style="padding:6px 8px;border:1px solid #e5e7eb;'
            f'text-align:right;color:{col(wchg)};">{wchg:+.2f}%</td>'
            f'<td style="padding:6px 8px;border:1px solid #e5e7eb;">'
            f'{lab or "—"}（{pc:.0f}%）</td></tr>')
    H.append('<table style="width:100%;border-collapse:collapse;'
             'font-size:14px;">' + "".join(trs) + "</table>")
    H.append('<p style="margin:8px 0 0;font-size:13px;color:#888888;">'
             '生意社品种基准价，元/吨；带 * 为大宗榜品种，分位按实际'
             '观测点计算（PC 已补齐日度数据，按近一年窗口计算）。</p>')

    H.append(h2("本周异动（单日涨跌 ≥2%）"))
    if alerts:
        for dt, slug, ch, p in alerts:
            H.append(f'<p style="margin:6px 0;">{dt[5:]} {names[slug]}：'
                     f'<span style="color:{col(ch)};">{ch:+.2f}%</span>'
                     f'（{fmt(p)} 元/吨）</p>')
    else:
        H.append('<p style="margin:6px 0;">本周无单日异动。</p>')

    if basis_rows:
        H.append(h2("期货与基差"))
        trs = ['<tr><th style="padding:6px 8px;background:#f7f8fa;'
               'border:1px solid #e5e7eb;text-align:left;">品种</th>'
               '<th style="padding:6px 8px;background:#f7f8fa;'
               'border:1px solid #e5e7eb;text-align:right;">现货</th>'
               '<th style="padding:6px 8px;background:#f7f8fa;'
               'border:1px solid #e5e7eb;text-align:right;">期货收盘</th>'
               '<th style="padding:6px 8px;background:#f7f8fa;'
               'border:1px solid #e5e7eb;text-align:right;">基差</th>'
               '<th style="padding:6px 8px;background:#f7f8fa;'
               'border:1px solid #e5e7eb;text-align:right;">基差周变化</th></tr>']
        for slug, now, prev in basis_rows:
            bch = now["basis"] - prev["basis"]
            trs.append(
                f'<tr><td style="padding:6px 8px;border:1px solid '
                f'#e5e7eb;">{FUT_NAMES[slug]}</td>'
                f'<td style="padding:6px 8px;border:1px solid #e5e7eb;'
                f'text-align:right;">{fmt(now["spot"])}</td>'
                f'<td style="padding:6px 8px;border:1px solid #e5e7eb;'
                f'text-align:right;">{fmt(now["close"])}</td>'
                f'<td style="padding:6px 8px;border:1px solid #e5e7eb;'
                f'text-align:right;">{now["basis"]:+,.0f}</td>'
                f'<td style="padding:6px 8px;border:1px solid #e5e7eb;'
                f'text-align:right;color:{col(bch)};">{bch:+,.0f}</td></tr>')
        H.append('<table style="width:100%;border-collapse:collapse;'
                 'font-size:14px;">' + "".join(trs) + "</table>")
        H.append('<p style="margin:8px 0 0;font-size:13px;color:#888888;">'
                 '基差 = 生意社现货基准价 − 期货主力收盘价。</p>')

    if week_news:
        H.append(h2("行业动态"))
        for it in week_news[:8]:
            H.append(f'<p style="margin:6px 0;">· {it["title"]}'
                     f'<span style="color:#888888;">（{it["date"][5:]}）'
                     f'</span></p>')
        H.append('<p style="margin:8px 0 0;font-size:13px;'
                 'color:#888888;">来源：生意社资讯，完整动态见 '
                 'pla365.com/news/</p>')

    if band_changes:
        H.append(h2("温度变化"))
        for slug, a, b in band_changes:
            H.append(f'<p style="margin:6px 0;">{names[slug]}：'
                     f'{a} → {b}</p>')

    H.append(todo_box("这波为什么涨/跌",
                      ["成本（原油/丙烯/煤等）：", "供应（检修、开工率、新装置）：",
                       "需求（下游开工、订单）："]))
    H.append(todo_box("现在补不补，看库存",
                      ["库存不到一周的：", "库存还有两三周的：",
                       "有大单要锁成本的："]))
    H.append(todo_box("下周关注", ["（写 1–3 个要盯的变量或价位。）"]))
    H.append('<p style="margin:22px 0 6px;font-size:13px;color:#888888;">'
             '数据来源：生意社品种基准价、期货主力收盘价（经新浪财经），'
             '基差与采购温度按本站公开规则计算。仅供参考。</p>')
    H.append('<p style="margin:6px 0;">每天的最新价格在 pla365.com，'
             '回复「报价」领取本周价格表；觉得有用，转给做采购的同事。</p>')
    H.append('</section>')
    html_out = "\n".join(H)

    # ---------- checklist ----------
    def title_for(slug, c_now, c_prev, wchg):
        d = abs(c_now[1] - c_prev[1])
        verb = "涨" if wchg >= 0 else "跌"
        return (f"塑料价格周报{monday.month}月{monday.day}日："
                f"{names[slug]}一周{verb}{fmt(d)}元，现在补不补？")

    titles = []
    if top:
        titles.append(title_for(top[0], top[1], top[2], top[3]))
        others = [r for r in rows if r[0] != top[0] and abs(r[3]) >= 1]
        if others:
            titles.append(title_for(others[0][0], others[0][1],
                                    others[0][2], others[0][3]))
    if alerts:
        dt, slug, ch, p = alerts[0]
        titles.append(f"{names[slug]}单日{'涨' if ch > 0 else '跌'}"
                      f"{abs(ch):.1f}%，发生了什么？")
    summary = lead[:110]
    L = [f"# 公众号成品包（{week_start} 至 {sun_s}，"
         f"{monday.isoformat()} 发布）", "",
         "## 标题（选一）"]
    L += [f"{i}. {t}" for i, t in enumerate(titles, 1)]
    L += ["", "## 摘要（粘贴到摘要框）", summary, "",
          "## 封面",
          "用当天每日一图：https://pla365.com/today/today.jpg"
          "（或本周异动品种的品种页走势图截图）。", "",
          "## 正文",
          f"同目录 wechat-{monday.isoformat()}.html：打开后全选复制，"
          "粘贴到公众号编辑器。文中 4 个红色虚线框是【待补】，"
          "填完把框删掉。", "",
          "## 待补清单",
          "1. 本周定调一句话", "2. 这波为什么涨/跌（成本/供应/需求）",
          "3. 现在补不补（按三档库存）", "4. 下周关注", "",
          "## 发布设置",
          "- 群发额度：服务号每月 4 次，本篇占 1 次；群发前确认本月余量",
          "- 多图文：头条放周报，二条可带一篇专题/干货轮转",
          "- 原创声明：开；留言：开（账号无留言功能则跳过）",
          "- 阅读原文：https://pla365.com/",
          "- 发布时间：周一 08:00 左右（采购上班路上刷手机的时段）",
          "- 群发前自检：待补框已删、标题已选、封面已传、"
          "预览发到自己手机看一遍", ""]
    md_out = "\n".join(L)

    ddir = ROOT / "drafts"
    ddir.mkdir(exist_ok=True)
    (ddir / f"wechat-{monday.isoformat()}.html").write_text(
        html_out, encoding="utf-8")
    (ddir / f"wechat-{monday.isoformat()}.md").write_text(
        md_out, encoding="utf-8")
    print(f"wrote drafts/wechat-{monday.isoformat()}.html/.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
