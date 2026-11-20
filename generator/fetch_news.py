"""Fetch industry news into generator/state/news.json (best-effort).

Standalone entry used by the news trial workflow; the daily pipeline
calls the same update through run_daily. Also writes a readable
digest of the last two days to drafts/news-latest.md for inspection.

Run from the repo root:
    python generator/fetch_news.py
"""
from __future__ import annotations

import asyncio
import json
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from pipeline.news import format_lines, items_between  # noqa: E402
from pipeline.scrape_news import update_news  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / "generator" / "state" / "news.json"


async def run(today):
    from playwright.async_api import async_playwright
    state = {"items": []}
    if STATE.exists():
        state = json.loads(STATE.read_text(encoding="utf-8"))
    async with async_playwright() as pw:
        browser = await pw.chromium.launch()
        page = await browser.new_page()
        try:
            state, added = await update_news(page, state, today)
        finally:
            await browser.close()
    STATE.write_text(json.dumps(state, ensure_ascii=False, indent=1),
                     encoding="utf-8")
    yday = (date.fromisoformat(today) - timedelta(days=1)).isoformat()
    recent = items_between(state["items"], yday, today)
    lines = [f"# 行业动态速览 · {today}", "",
             f"近两日共 {len(recent)} 条（全库 {len(state['items'])} 条，"
             f"本次新增 {added} 条）。", ""]
    lines += format_lines(recent)
    out = ROOT / "drafts" / "news-latest.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"news: {len(state['items'])} stored, {added} new, "
          f"{len(recent)} in last 2 days")


if __name__ == "__main__":
    import os
    today = os.environ.get("PLA365_TODAY") or \
        date.today().isoformat()
    asyncio.run(run(today))
