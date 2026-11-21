"""pla365 daily run: scrape -> update state -> build -> deploy -> save.

Run from the china-plastic-prices repo root (GitHub Actions) or any
checkout with the same layout:

    data/history.csv  data/sf_basis.csv  data/latest.csv   (state)
    generator/        this package: templates/, state/extras.json,
                      assets/, templates_manifest.json
    daily/            per-day latest.json snapshots (repo record)

Behaviour: any main-variety scrape or futures failure aborts the run
BEFORE anything is written or deployed (the site keeps yesterday's
data and the stale-data watch alerts). The board (extras) is
best-effort: on failure the extras keep their last values.

Gap handling (e.g. after the 2026-11-10..18 outage): missing days in
the main series are backfilled from each detail page's chart series,
then from dated board archives, then — for stretches of <=3 days,
i.e. weekends, when 生意社 carries Friday's price over — by carrying
the previous price forward. Board varieties are backfilled from the
dated board archives (their series only ever held board days).
Deploy happens only when CLOUDFLARE_API_TOKEN is set in the env.
"""
from __future__ import annotations

import datetime as _dt
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from pipeline.basis_data import append_basis_row, dump_sf_basis, load_sf_basis
from pipeline.build import build_all, load_templates, pack_worker
from pipeline.dataio import (build_latest, dump_history, dump_json,
                             load_history)
from pipeline.deploy import deploy
from pipeline.futures import continuous_state, fetch_main_contracts, latest_completed
from pipeline.scrape_100ppi import fetch_panels

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GEN = os.path.join(ROOT, "generator")
FUT_SLUGS = ("pp", "lldpe", "pvc", "pet")
MAINS = ("pp", "lldpe", "hdpe", "ldpe", "pvc", "abs", "ps", "pet")


def _days_between(first, last):
    """Calendar dates strictly between first and last (exclusive)."""
    d0 = _dt.date.fromisoformat(first)
    d1 = _dt.date.fromisoformat(last)
    return [(d0 + _dt.timedelta(days=i)).isoformat()
            for i in range(1, (d1 - d0).days)]


def _fill_short_gaps(ent, max_gap=3):
    """Carry the previous price over holes of at most max_gap days
    (the 生意社 weekend convention the mains get from their panels).
    Mutates and returns the [date, price] list."""
    if len(ent) < 2:
        return ent
    out = [ent[0]]
    for date, price in ent[1:]:
        prev = out[-1][0]
        gap = (_dt.date.fromisoformat(date)
               - _dt.date.fromisoformat(prev)).days - 1
        if 0 < gap <= max_gap:
            p = out[-1][1]
            d0 = _dt.date.fromisoformat(prev)
            for i in range(1, gap + 1):
                out.append([(d0 + _dt.timedelta(days=i)).isoformat(), p])
        out.append([date, price])
    ent[:] = out
    return ent


def _merge_point(ent, date, price):
    """Insert/replace (date, price) in a sorted [(date, price)] list."""
    for i, (d, _) in enumerate(ent):
        if d == date:
            ent[i] = (date, price)
            return
        if d > date:
            ent.insert(i, (date, price))
            return
    ent.append((date, price))


def main():
    today = _dt.date.today().isoformat()
    print(f"[pla365] daily run for {today}")

    series = load_history(open(f"{ROOT}/data/history.csv", encoding="utf-8").read())
    basis_text = open(f"{ROOT}/data/sf_basis.csv", encoding="utf-8").read()
    basis_rows = load_sf_basis(basis_text)
    latest_csv_text = open(f"{ROOT}/data/latest.csv", encoding="utf-8").read()
    extras_state = json.load(open(f"{GEN}/state/extras.json", encoding="utf-8"))
    news_path = f"{GEN}/state/news.json"
    if os.path.exists(news_path):
        news_state = json.load(open(news_path, encoding="utf-8"))
    else:
        news_state = {"items": []}
    spot_path = f"{GEN}/state/spot.json"
    if os.path.exists(spot_path):
        spot_state = json.load(open(spot_path, encoding="utf-8"))
    else:
        spot_state = {"days": {}}
    templates, manifest = load_templates(f"{GEN}/templates",
                                         f"{GEN}/templates_manifest.json")

    gap = any(series[s][-1][0] < today for s in MAINS) or \
        any(extras_state[s]["series"][-1][0] < today for s in extras_state)
    # 1) scrape the 8 main varieties (real browser)
    panels = fetch_panels(with_chart=gap)
    failed = [s for s, p in panels.items() if not p.get("price")]
    if failed:
        print(f"[pla365] ABORT: no price for {failed}")
        return 1
    # backfill from the pages' chart series first
    for slug in MAINS:
        for d, price in panels[slug].get("chart") or []:
            if series[slug][-1][0] < d < today:
                _merge_point(series[slug], d, price)
    updated = {slug: panels[slug]["updated"] for slug in MAINS}
    print("[pla365] mains scraped:", {s: panels[s]["price"] for s in MAINS})

    # 2) boards: latest + dated archives for any missing days
    missing = set()
    for slug in MAINS:
        missing.update(_days_between(series[slug][-1][0], today))
    extras_last = min(extras_state[s]["series"][-1][0] for s in extras_state)
    missing.update(_days_between(extras_last, today))
    try:
        import asyncio
        boards = asyncio.run(_boards(sorted(missing)))
    except Exception as exc:
        boards = {}
        print(f"[pla365] board scrape failed (continuing): {exc}")
    for bdate in sorted(boards):
        items = boards[bdate]["items"]
        for slug in MAINS:
            if slug in items and series[slug][-1][0] < bdate < today:
                _merge_point(series[slug], bdate, items[slug]["price"])
        for slug, item in items.items():
            if slug not in extras_state:
                continue
            ent = extras_state[slug]["series"]
            if ent[-1][0] < bdate:
                ent.append([bdate, item["price"]])
                extras_state[slug]["yoy"] = item["yoy"]
            elif ent[-1][0] == bdate:
                ent[-1] = [bdate, item["price"]]
                extras_state[slug]["yoy"] = item["yoy"]
    if boards:
        print(f"[pla365] boards merged for: {sorted(boards)}")
    # weekend carry-over for short remaining holes in the main series
    for slug in MAINS:
        holes = _days_between(series[slug][-1][0], today)
        if 0 < len(holes) <= 3:
            ent = series[slug]
            price = ent[-1][1]
            for d in holes:
                ent.append((d, price))
    # PC is promoted (2026-11-21): keep its board series at daily
    # density with the same short-hole carry-over, so its percentile
    # basis matches the mains (see pipeline/context.py PROMOTED).
    _fill_short_gaps(extras_state["pc"]["series"])
    for slug in MAINS:
        ent = series[slug]
        if ent[-1][0] == today:
            ent[-1] = (today, panels[slug]["price"])
        elif ent[-1][0] < today:
            ent.append((today, panels[slug]["price"]))

    # 3) futures: continuous state for pages + main-contract basis rows
    futures = {}
    for slug in FUT_SLUGS:
        st = continuous_state(slug, today, series[slug][0][0])
        if st is None:
            print(f"[pla365] ABORT: no futures data for {slug}")
            return 1
        futures[slug] = {"close": st["close"], "chg": st["chg"],
                         "date": st["date"], "settle": st["settle"],
                         "fut_series": st["fut_series"]}
    mc = fetch_main_contracts()
    for slug in FUT_SLUGS:
        lc = latest_completed(slug, today, mc)
        if not lc:
            continue
        spot = None
        for d, p in series[slug]:
            if d <= lc["date"]:
                spot = p
            else:
                break
        if spot is not None and lc["date"] > basis_rows[slug][-1]["date"]:
            append_basis_row(basis_rows, slug, lc["date"], spot,
                             lc["contract"], lc["close"])
            print(f"[pla365] basis row {slug} {lc['date']} spot {spot} "
                  f"close {lc['close']} ({lc['contract']})")
    basis_text = dump_sf_basis(basis_rows)

    # 3b) industry news (best-effort: never blocks the price update)
    try:
        import asyncio
        news_state, n_added = asyncio.run(_news(news_state, today))
        print(f"[pla365] news updated: {len(news_state['items'])} items, "
              f"{n_added} new")
    except Exception as exc:
        print(f"[pla365] news scrape failed (continuing): {exc}")

    # 3c) spot reference quotes (grade level; best-effort, rides on
    # the same detail-page visits as the panels)
    spot_today = {s: panels[s].get("spot") or [] for s in panels}
    if any(spot_today.values()):
        spot_state["days"][today] = spot_today
    for d in sorted(spot_state["days"])[:-14]:
        del spot_state["days"][d]
    latest_spot = (spot_state["days"][max(spot_state["days"])]
                   if spot_state["days"] else {})
    print(f"[pla365] spot quotes: "
          f"{sum(len(v) for v in latest_spot.values())} rows "
          f"({', '.join(s for s, v in latest_spot.items() if v)})")

    # 4) build the bundle
    fmap = build_all(templates, manifest, series, extras_state, basis_text,
                     latest_csv_text, futures, updated, today,
                     f"{GEN}/assets",
                     news_items=news_state.get("items", []),
                     spot=latest_spot)
    worker_js = pack_worker(fmap)
    print(f"[pla365] bundle built: {len(fmap)} entries, "
          f"{len(worker_js)} chars")

    # 5) deploy (only when the token is configured)
    token = os.environ.get("CLOUDFLARE_API_TOKEN")
    if token:
        account = os.environ["CLOUDFLARE_ACCOUNT_ID"]
        deploy(worker_js, account, token)
        print("[pla365] deployed to Cloudflare")
    else:
        os.makedirs(f"{GEN}/dist", exist_ok=True)
        with open(f"{GEN}/dist/worker.js", "w", encoding="utf-8") as f:
            f.write(worker_js)
        print("[pla365] no CLOUDFLARE_API_TOKEN; worker.js saved to dist/")

    # 6) persist state + repo data files
    with open(f"{ROOT}/data/history.csv", "w", encoding="utf-8") as f:
        f.write(dump_history(series))
    with open(f"{ROOT}/data/sf_basis.csv", "w", encoding="utf-8") as f:
        f.write(basis_text)
    with open(f"{ROOT}/data/latest.csv", "w", encoding="utf-8") as f:
        f.write(fmap["/data/latest.csv"][0])
    payload = build_latest(series, updated)
    with open(f"{ROOT}/data/latest.json", "w", encoding="utf-8") as f:
        f.write(dump_json(payload))
    with open(f"{ROOT}/daily/{today}.json", "w", encoding="utf-8") as f:
        f.write(dump_json(payload))
    with open(f"{GEN}/state/extras.json", "w", encoding="utf-8") as f:
        json.dump(extras_state, f, ensure_ascii=False, indent=1)
    with open(news_path, "w", encoding="utf-8") as f:
        json.dump(news_state, f, ensure_ascii=False, indent=1)
    with open(spot_path, "w", encoding="utf-8") as f:
        json.dump(spot_state, f, ensure_ascii=False, indent=1)
    print("[pla365] state saved")
    return 0


async def _boards(want_dates):
    """Fetch the latest board plus dated archives for want_dates
    (board dates, ascending). A dated archive lives at
    detail-day-{previous day}-15.html; each fetch is validated
    against the requested date and skipped on mismatch."""
    from playwright.async_api import async_playwright
    from pipeline.scrape_board import scrape_board
    out = {}
    async with async_playwright() as pw:
        browser = await pw.chromium.launch()
        page = await browser.new_page()
        try:
            latest = await scrape_board(page)
            out[latest["date"]] = latest
            for want in want_dates:
                if want in out or want >= latest["date"]:
                    continue
                prev = (_dt.date.fromisoformat(want)
                        - _dt.timedelta(days=1)).strftime("%Y-%m%d")
                url = f"https://top.100ppi.com/zdb/detail-day-{prev}-15.html"
                try:
                    board = await scrape_board(page, url)
                except Exception as exc:
                    print(f"[pla365] board archive {want} failed: {exc}")
                    continue
                if board["date"] == want:
                    out[want] = board
                else:
                    print(f"[pla365] board archive {want}: got {board['date']}, skipped")
        finally:
            await browser.close()
    return out


async def _news(state, today):
    """Scrape the 生意社 news lists into the rolling state."""
    from playwright.async_api import async_playwright
    from pipeline.scrape_news import update_news
    async with async_playwright() as pw:
        browser = await pw.chromium.launch()
        page = await browser.new_page()
        try:
            return await update_news(page, state, today)
        finally:
            await browser.close()


if __name__ == "__main__":
    raise SystemExit(main())
