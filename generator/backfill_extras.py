"""One-off backfill of the 7 board varieties' (extras) price history.

The extras series seeded from the published site only reach back to
2026-07-28 (EPS: 2026-09-01). The 生意社橡塑大宗榜 keeps dated archives
(URL date = board date - 1 day) reaching back well past 2025, so this
script walks the archives from 2025-10-09 (the main varieties' history
start) to the latest date already in state, parses each board with the
production parser, and merges every missing (date, price) into
generator/state/extras.json.

Safety rules:
- Existing entries always win; overlapping dates are only counted as
  conflicts (board values can be revised after publication, like the
  known PS case) and reported, never overwritten.
- If fewer than 100 boards parse, or overlap conflicts exceed 30, the
  script aborts without writing anything.
- EPS joined the board late, so early boards simply have no EPS row;
  it keeps whatever history the boards actually contain.

Run from the repo root:  python generator/backfill_extras.py
Writes a machine-readable summary to generator/state/backfill_report.json.
"""
from __future__ import annotations

import asyncio
import json
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from pipeline.scrape_board import parse_board  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / "generator" / "state" / "extras.json"
REPORT = ROOT / "generator" / "state" / "backfill_report.json"
START = date(2025, 10, 9)
EXTRAS = ["eps", "pc", "pa6", "pa66", "eva", "pmma", "pp-fiber"]
WORKERS = 4
MIN_BOARDS = 100
MAX_CONFLICTS = 30


def archive_url(board_date: date) -> str:
    prev = board_date - timedelta(days=1)
    return f"https://top.100ppi.com/zdb/detail-day-{prev:%Y-%m%d}-15.html"


async def fetch_board(page, board_date: date):
    """Return parse_board() output for the archive of board_date, or
    None when the archive is missing/unparseable/date-mismatched."""
    try:
        await page.goto(archive_url(board_date), wait_until="domcontentloaded",
                        timeout=60000)
        await page.wait_for_selector("table", timeout=20000)
        heading = await page.title()
        rows = await page.eval_on_selector_all(
            "table tr",
            "els => els.map(tr => Array.from(tr.querySelectorAll('td,th'))"
            ".map(td => td.innerText.trim()))")
        board = parse_board(rows, heading)
    except Exception:
        return None
    if board["date"] != board_date.isoformat():
        return None
    return board


async def collect(end: date):
    from playwright.async_api import async_playwright

    days = []
    d = START
    while d <= end:
        days.append(d)
        d += timedelta(days=1)
    boards = {}
    queue = asyncio.Queue()
    for d in days:
        queue.put_nowait(d)

    async with async_playwright() as pw:
        browser = await pw.chromium.launch()

        async def worker():
            page = await browser.new_page()
            while True:
                try:
                    d = queue.get_nowait()
                except asyncio.QueueEmpty:
                    break
                board = await fetch_board(page, d)
                if board:
                    boards[d.isoformat()] = board["items"]
                await asyncio.sleep(0.3)
            await page.close()

        await asyncio.gather(*[worker() for _ in range(WORKERS)])
        await browser.close()
    return boards


def main():
    state = json.loads(STATE.read_text(encoding="utf-8"))
    end = max(date.fromisoformat(state[s]["series"][-1][0]) for s in EXTRAS)
    print(f"backfill range: {START} .. {end}", flush=True)
    boards = asyncio.run(collect(end))
    print(f"boards parsed: {len(boards)}", flush=True)
    if len(boards) < MIN_BOARDS:
        print("ABORT: too few boards parsed; state untouched")
        return 1

    report = {"range": [START.isoformat(), end.isoformat()],
              "boards_parsed": len(boards), "slugs": {}}
    total_conflicts = 0
    for slug in EXTRAS:
        ent = state[slug]
        have = {d: p for d, p in ent["series"]}
        added, conflicts = [], []
        for bdate in sorted(boards):
            item = boards[bdate].get(slug)
            if not item:
                continue
            price = item["price"]
            if bdate in have:
                if abs(have[bdate] - price) > 0.01:
                    conflicts.append([bdate, have[bdate], price])
            else:
                have[bdate] = price
                added.append(bdate)
        ent["series"] = sorted(have.items())
        total_conflicts += len(conflicts)
        report["slugs"][slug] = {
            "before": len(ent["series"]) - len(added),
            "added": len(added),
            "after": len(ent["series"]),
            "first": ent["series"][0][0],
            "last": ent["series"][-1][0],
            "conflicts": conflicts[:10],
            "conflict_count": len(conflicts),
        }
        print(f"{slug}: +{len(added)} entries, now {len(ent['series'])} "
              f"from {ent['series'][0][0]}, conflicts {len(conflicts)}",
              flush=True)

    if total_conflicts > MAX_CONFLICTS:
        print(f"ABORT: {total_conflicts} overlap conflicts; state untouched")
        return 1

    STATE.write_text(json.dumps(state, ensure_ascii=False, indent=1),
                     encoding="utf-8")
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=1),
                      encoding="utf-8")
    print("state updated")
    return 0


if __name__ == "__main__":
    sys.exit(main())
