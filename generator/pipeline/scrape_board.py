"""Scrape the 生意社橡塑大宗榜 daily board (top.100ppi.com) with a
real browser, per Jiang's 2026-11-18 decision (no cookie/direct
scrapes of 生意社).

The board is published around 17:00 each day, so a morning run sees
yesterday's board — matching the site's one-day lag for the 7 board
varieties (EPS, PC, PA6, PA66, EVA, PMMA, PP纤维料). Each row gives
the day's benchmark price and the 同比 (year-on-year) figure the
variety pages display.
"""
from __future__ import annotations

import re

BOARD_URL = "https://top.100ppi.com/zdb/detail-day---15.html"

# board commodity name (parens normalised) -> pipeline slug
BULK_TO_SLUG = {
    "EPS": "eps", "PC": "pc", "PA6": "pa6", "PA66": "pa66",
    "EVA": "eva", "PMMA": "pmma", "PP(纤维)": "pp-fiber",
    "PP(拉丝)": "pp", "LLDPE": "lldpe", "HDPE": "hdpe", "LDPE": "ldpe",
    "PVC": "pvc", "ABS": "abs", "PS": "ps", "PET": "pet",
}


def _norm_name(name):
    return (name.replace("（", "(").replace("）", ")")
            .replace(" ", "").strip())


def parse_board(rows, heading):
    """rows: cell texts of the board table (header row included);
    heading: page heading text carrying the board date.
    Returns {"date": board_date, "items": {slug: {price, prev, yoy}}}."""
    m = re.search(r"(\d{4})年(\d{1,2})月(\d{1,2})日", heading)
    if not m:
        raise ValueError("board date not found in heading")
    date = f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    items = {}
    for row in rows:
        if len(row) < 7:
            continue
        slug = BULK_TO_SLUG.get(_norm_name(row[0]))
        if not slug:
            continue
        try:
            prev = float(row[2].replace(",", ""))
            price = float(row[3].replace(",", ""))
            yoy = float(row[6].replace("%", "").replace("+", ""))
        except ValueError:
            continue
        items[slug] = {"price": price, "prev": prev, "yoy": yoy}
    return {"date": date, "items": items}


async def scrape_board(page, url=BOARD_URL):
    """Drive an already-open Playwright page to the board and parse it."""
    await page.goto(url, wait_until="domcontentloaded", timeout=60000)
    await page.wait_for_selector("table", timeout=30000)
    heading = await page.title()
    rows = await page.eval_on_selector_all(
        "table tr",
        "els => els.map(tr => Array.from(tr.querySelectorAll('td,th'))"
        ".map(td => td.innerText.trim()))")
    return parse_board(rows, heading)
