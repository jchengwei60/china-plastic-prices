"""Render the /news/ industry-dynamics page.

Built on the /alerts/ template shell (head/nav/footer) with the
title, meta, canonical and <main> replaced. Items come from
state/news.json (生意社橡塑动态， filtered and tagged by
pipeline.news). Titles link to the source article; summaries are
the source's own meta descriptions and are labelled as such.

The page shows the last 7 days of items, newest first, capped at 60.
"""
from __future__ import annotations

import html
import re
from datetime import date, timedelta

from .news import VARIETY_NAMES

DESC = ("塑料行业动态聚合：PP、PE、PVC、ABS、PET等品种的装置检修、"
        "涨价函、产能投放、进出口与市场行情，来源生意社，每日更新。")


def _main(items, today):
    cutoff = (date.fromisoformat(today) - timedelta(days=6)).isoformat()
    shown = [it for it in items if it["date"] >= cutoff][:60]
    parts = [
        "<h1>塑料行业动态</h1>",
        "<p>聚合生意社橡塑资讯，按品种标注装置检修、涨价、产能、"
        "进出口与市场行情，每日随价格数据更新。标题与摘要来自"
        "生意社，点击标题查看原文。</p>",
    ]
    if not shown:
        parts.append("<p>暂无动态，敬请关注。</p>")
    cur = None
    for it in shown:
        if it["date"] != cur:
            if cur is not None:
                parts.append("</ul>")
            cur = it["date"]
            d = date.fromisoformat(cur)
            parts.append(f"<h2>{d.month}月{d.day}日</h2><ul>")
        tags = [VARIETY_NAMES[s] for s in it.get("varieties", [])]
        tags += it.get("cats", [])
        tag = f"（{'·'.join(tags)}）" if tags else ""
        line = (f"<li>{html.escape(it.get('time', ''))} "
                f"<a href=\"{html.escape(it['url'])}\" target=\"_blank\" "
                f"rel=\"noopener\">{html.escape(it['title'])}</a>"
                f"{html.escape(tag)}")
        if it.get("summary"):
            line += (f"<br><small>{html.escape(it['summary'])}"
                     f"（来源：生意社）</small>")
        parts.append(line + "</li>")
    if shown:
        parts.append("</ul>")
    parts.append(
        "<p><small>本页为资讯聚合与索引，版权归原出处所有；"
        "价格数据见<a href=\"/pinzhong/\">品种价格</a>，"
        "单日涨跌超2%的异动见<a href=\"/alerts/\">异动记录</a>。"
        "</small></p>")
    return "".join(parts)


def render_news(sample, items, today):
    h = sample.replace("<title>塑料价格异动_塑价365</title>",
                       "<title>塑料行业动态_塑价365</title>")
    h = h.replace('content="塑料价格异动_塑价365"',
                  'content="塑料行业动态_塑价365"')
    h = re.sub(r'(name="description" content=")[^"]*(")',
               r"\g<1>" + DESC + r"\g<2>", h, count=1)
    h = re.sub(r'(property="og:description" content=")[^"]*(")',
               r"\g<1>" + DESC + r"\g<2>", h, count=1)
    h = h.replace("https://pla365.com/alerts/",
                  "https://pla365.com/news/")
    h = re.sub(r"<main>.*</main>",
               lambda m: "<main>" + _main(items, today) + "</main>",
               h, count=1, flags=re.S)
    return h
