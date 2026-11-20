"""Industry-news classification, state handling and formatting.

Items come from pipeline.scrape_news (生意社橡塑动态 lists). This module
is pure logic: it filters the noisy auto-generated list entries
（均差 notes, vendor quote posts), tags the rest by variety and
category, maintains the rolling 14-day state, and formats sections
for the weekly draft, the alert pack and the /news/ site page.

Editorial rules (same as the rest of the pipeline):
- only items matching one of the site's 15 varieties or a macro
  keyword survive; everything else (rubbers, vendor quotes, 均差
  auto-notes, job posts) is dropped;
- summaries are the source pages' own meta descriptions, always
  shown with the source name attached - never rewritten, never
  presented as our own reporting.
"""
from __future__ import annotations

import re
from datetime import date, timedelta

# Latin codes need letter boundaries so EPS does not match PS,
# LLDPE does not match LDPE and PA66 does not match PA6.
VARIETY_PATTERNS = [
    ("lldpe", [r"(?<![A-Za-z])LLDPE(?![A-Za-z])", "线性低密度", "线性聚乙烯"]),
    ("pa66", [r"(?<![A-Za-z])PA66(?![0-9A-Za-z])", "尼龙66", "PA66切片"]),
    ("pp", [r"(?<![A-Za-z])PP(?![A-Za-z])", "聚丙烯"]),
    ("hdpe", [r"(?<![A-Za-z])HDPE(?![A-Za-z])", "高密度聚乙烯"]),
    ("ldpe", [r"(?<![A-Za-z])LDPE(?![A-Za-z])", "低密度聚乙烯", "高压聚乙烯"]),
    ("pvc", [r"(?<![A-Za-z])PVC(?![A-Za-z])", "聚氯乙烯", "电石法"]),
    ("abs", [r"(?<![A-Za-z])ABS(?![A-Za-z])"]),
    ("eps", [r"(?<![A-Za-z])EPS(?![A-Za-z])", "可发性聚苯乙烯"]),
    ("ps", [r"(?<![A-Za-z])PS(?![A-Za-z])", "聚苯乙烯"]),
    ("pet", [r"(?<![A-Za-z])PET(?![A-Za-z])", "瓶片", "聚酯切片", "涤纶"]),
    ("pc", [r"(?<![A-Za-z])PC(?![A-Za-z])", "聚碳酸酯"]),
    ("pa6", [r"(?<![A-Za-z])PA6(?![0-9A-Za-z])", "尼龙6", "己内酰胺", "锦纶"]),
    ("eva", [r"(?<![A-Za-z])EVA(?![A-Za-z])", "乙烯-醋酸乙烯"]),
    ("pmma", [r"(?<![A-Za-z])PMMA(?![A-Za-z])", "有机玻璃", "亚克力"]),
    ("ppf", ["PP纤维", "纤维料", "丙纶短纤"]),
]
VARIETY_NAMES = {
    "pp": "PP拉丝", "lldpe": "LLDPE", "hdpe": "HDPE", "ldpe": "LDPE",
    "pvc": "PVC", "abs": "ABS", "ps": "PS", "pet": "PET",
    "eps": "EPS", "pc": "PC", "pa6": "PA6", "pa66": "PA66",
    "eva": "EVA", "pmma": "PMMA", "ppf": "PP纤维料",
}
MACRO_WORDS = ["原油", "布伦特", "WTI", "期货", "涨价函", "检修", "停车",
               "停产", "开工率", "新产能", "投产", "反倾销", "关税",
               "出口退税", "库存", "地缘", "欧佩克", "OPEC", "海运",
               "运价", "天然气", "煤炭", "纯碱", "甲醇", "苯乙烯",
               "丙烯", "乙烯"]
CATEGORY_WORDS = [
    ("检修", ["检修", "停车", "停产", "装置故障", "降负"]),
    ("涨价", ["涨价函", "调涨", "上调", "提价", "涨价"]),
    ("政策", ["反倾销", "关税", "出口退税", "政策", "公告", "标准", "立案"]),
    ("产能", ["投产", "新装置", "扩产", "产能", "试车", "开车"]),
    ("进出口", ["进口量", "出口量", "进出口", "到港"]),
    ("行情", ["行情", "走势", "评述", "分析", "展望", "预测"]),
]
DROP_TAGS = {"均差", "招聘"}
DROP_TITLE_WORDS = ["商品报价动态", "报价动态（", "均差", "招聘"]


def classify(title):
    """(keep, varieties, cats) for one headline."""
    for w in DROP_TITLE_WORDS:
        if w in title:
            return False, [], []
    varieties = []
    for slug, pats in VARIETY_PATTERNS:
        for p in pats:
            if (re.search(p, title) if ("<" in p or "(?" in p)
                    else (p in title)):
                varieties.append(slug)
                break
    macro = any(w in title for w in MACRO_WORDS)
    if not varieties and not macro:
        return False, [], []
    cats = []
    for cat, words in CATEGORY_WORDS:
        if any(w in title for w in words):
            cats.append(cat)
    return True, varieties, cats[:2]


def merge_items(state, new_items, today, keep_days=14):
    """Merge new items into state {items: [...]} by URL, prune old."""
    by_url = {it["url"]: it for it in state.get("items", [])}
    added = 0
    for it in new_items:
        if it["url"] not in by_url:
            added += 1
        by_url[it["url"]] = it
    cutoff = (date.fromisoformat(today)
              - timedelta(days=keep_days)).isoformat()
    items = [it for it in by_url.values() if it["date"] >= cutoff]
    items.sort(key=lambda it: (it["date"], it.get("time", "")),
               reverse=True)
    return {"items": items}, added


def items_between(items, d1, d2):
    return [it for it in items if d1 <= it["date"] <= d2]


def tag_text(it):
    names = [VARIETY_NAMES[s] for s in it.get("varieties", [])]
    names += it.get("cats", [])
    return "·".join(names)


def format_lines(items, with_summary=True):
    """Markdown lines for drafts: one item per line, source attached."""
    out = []
    for it in items:
        head = f"- [{tag_text(it)}] {it['title']}"
        head += f"（{it['date'][5:]} {it.get('time', '')}，生意社）"
        out.append(head)
        if with_summary and it.get("summary"):
            out.append(f"  摘要：{it['summary']}")
        out.append(f"  链接：{it['url']}")
    return out
