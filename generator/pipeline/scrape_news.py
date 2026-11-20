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


async def fetch_summary(page, url):
    """The detail page's meta description, cleaned; '' on any failure."""
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=45000)
        desc = await page.evaluate(
            "() => { const m = document.querySelector("
            "'meta[name=\"description\"]'); return m ? m.content : ''; }")
        desc = re.sub(r"\s+", " ", (desc or "")).strip()
        return desc[:110]
    except Exception:
        return ""


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
        it["summary"] = await fetch_summary(page, it["url"])
    return state, added
