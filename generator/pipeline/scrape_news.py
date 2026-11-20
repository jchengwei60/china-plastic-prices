"""Scrape 生意社橡塑动态 news lists with Playwright.

The list pages are noisy: most entries are auto-generated 均差 notes,
vendor quote posts and rubber items. pipeline.news.classify filters
and tags what survives. Summaries are the detail pages' own meta
descriptions (attributed to 生意社 wherever shown).

Lists scraped (50 items each, newest first):
- 橡塑动态 p1 + p2 (depth: the valuable items publish all day)
- 橡塑国际动态 p1 (oil / geopolitics / overseas markets)
"""
from __future__ import annotations

import re

from .news import classify

LISTS = [
    "https://www.100ppi.com/news/list-15---1.html",
    "https://www.100ppi.com/news/list-15---2.html",
    "https://www.100ppi.com/news/list-15-11--1.html",
]
TIME_RE = re.compile(r"(\d{2}):(\d{2})")
TAG_RE = re.compile(r"\[([^\]]{1,6})\]")
DATE_IN_URL = re.compile(r"detail-(\d{4})(\d{2})(\d{2})-")

_JS_COLLECT = """
els => els.map(a => {
  let n = a;
  for (let i = 0; i < 6 && n; i++) {
    if (/\\d{2}:\\d{2}/.test(n.innerText || '')) break;
    n = n.parentElement;
  }
  return {href: a.href, title: (a.innerText || '').trim(),
          row: n ? (n.innerText || '').trim() : (a.innerText || '').trim()};
})
"""


def parse_news_rows(raw):
    """[{href, title, row}] -> classified item dicts (no summaries)."""
    out = []
    seen = set()
    for r in raw:
        href = r.get("href", "")
        m = DATE_IN_URL.search(href)
        title = (r.get("title") or "").strip()
        if not m or not title or href in seen:
            continue
        seen.add(href)
        date = f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
        row = r.get("row") or title
        tm = TIME_RE.search(row)
        tg = TAG_RE.search(row)
        if tg and tg.group(1) in ("均差", "招聘"):
            continue
        keep, varieties, cats = classify(title)
        if not keep:
            continue
        out.append({
            "date": date,
            "time": tm.group(0) if tm else "",
            "tag": tg.group(1) if tg else "",
            "title": title,
            "url": href,
            "varieties": varieties,
            "cats": cats,
            "summary": "",
        })
    return out


async def scrape_news_list(page, url):
    await page.goto(url, wait_until="domcontentloaded", timeout=60000)
    await page.wait_for_selector('a[href*="/news/detail-"]', timeout=30000)
    raw = await page.eval_on_selector_all(
        'a[href*="/news/detail-"]', _JS_COLLECT)
    return parse_news_rows(raw)


async def fetch_detail(page, url):
    """(full title, meta description) from a detail page.

    List pages truncate long titles, so the detail page's own title
    wins when it extends the list title. ('', '') on any failure."""
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=45000)
        data = await page.evaluate(
            "() => { const m = document.querySelector("
            "'meta[name=\"description\"]'); "
            "const h = document.querySelector('h1'); "
            "return {desc: m ? m.content : '', "
            "title: h ? h.innerText : '', doc: document.title || ''}; }")
        doc = (data.get("doc") or "").strip()
        for sep in (" - 生意社", "_生意社", "-生意社", " | 生意社",
                    " - 商品动态", " - 大宗商品动态"):
            if sep in doc:
                doc = doc.split(sep)[0].strip()
        if len(doc) > len((data.get("title") or "").strip()):
            data["title"] = doc
        desc = re.sub(r"\s+", " ", (data.get("desc") or "")).strip()
        if len(desc) > 110:
            cut = desc[:110]
            for sep in ("。", "；", "，"):
                idx = cut.rfind(sep)
                if idx >= 60:
                    cut = cut[:idx + 1] if sep != "，" else cut[:idx]
                    break
            desc = cut
        title = re.sub(r"\s+", " ", (data.get("title") or "")).strip()
        # Section labels ride along in the page title / h1; they are
        # never part of the headline itself.
        for sep in (" - 商品动态", " - 大宗商品动态", " - 生意社",
                    "_生意社", " | 生意社"):
            if sep in title:
                title = title.split(sep)[0].strip()
        return title, desc
    except Exception:
        return "", ""


async def update_news(page, state, today, summary_cap=12):
    """Scrape all lists, merge into state, fetch summaries for the
    newest items that lack one. Returns (new_state, added_count).
    Raises only if every list failed (caller treats news as
    best-effort and keeps the old state)."""
    from .news import merge_items
    items, failures = [], 0
    for url in LISTS:
        try:
            items += await scrape_news_list(page, url)
        except Exception:
            failures += 1
    if failures == len(LISTS):
        raise RuntimeError("all news lists failed")
    state, added = merge_items(state, items, today)
    lacking = [it for it in state["items"] if not it.get("summary")]
    for it in lacking[:summary_cap]:
        title, desc = await fetch_detail(page, it["url"])
        if desc:
            it["summary"] = desc
        core_new = title.lstrip("生意社：") if title else ""
        core_old = it["title"].lstrip("生意社：")
        if title and len(title) > len(it["title"]) and \
                core_new[:6] and core_new[:6] == core_old[:6]:
            it["title"] = title
    return state, added
