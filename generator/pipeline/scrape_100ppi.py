"""Scrape 生意社 (100ppi.com) benchmark prices with a real browser.

Why a browser: plain HTTP requests get a JS security-check page
(verified 2026-11-17); a real Chromium passes it transparently
(verified the same day via the cloud browser, which read the PP page:
10450.00 元/吨, updated 11-17 16:00, -2.79%).

Only two values are needed per variety page: the latest benchmark price
and its update stamp ("MM-DD HH:MM"). Change %, 3-month stats and
percentiles are all computed from our own history (see compute.py), so
the parser anchors on the page's rendered text, not on DOM structure.

Runs under Playwright (GitHub Actions installs it; see workflow).
"""
from __future__ import annotations

import re

from .dataio import SOURCES

# "更新时间：11-17 16:00" as rendered on the detail pages
RE_UPDATED = re.compile(r"更新时间[:：]\s*(\d{2}-\d{2})\s+(\d{2}:\d{2})")
# The price panel shows the benchmark prominently as e.g. "10450.00"
# followed by 元/吨; the first such number in the panel area is the price.
RE_PRICE = re.compile(r"([0-9]{3,6}(?:\.[0-9]{1,2})?)\s*元/吨")


def parse_panel(text):
    """Extract {price, updated} from a detail page's rendered text."""
    m = RE_UPDATED.search(text)
    updated = f"{m.group(1)} {m.group(2)}" if m else ""
    price = None
    # Prefer a price near the update stamp (same panel); fall back to the
    # first 元/吨 figure on the page.
    if m:
        near = text[max(0, m.start() - 600): m.start() + 200]
        pm = RE_PRICE.search(near)
        if pm:
            price = float(pm.group(1))
    if price is None:
        pm = RE_PRICE.search(text)
        if pm:
            price = float(pm.group(1))
    return {"price": price, "updated": updated}


def fetch_panels(slugs=None, timeout_ms=45000, with_chart=False):
    """Open each variety's detail page in Chromium and parse its panel.

    Returns {slug: {price, updated, source}}; price is None on failure.
    With with_chart=True each result also carries "chart": the daily
    series read from the page's chart (for gap backfill), or [].
    """
    from playwright.sync_api import sync_playwright

    slugs = slugs or list(SOURCES)
    out = {}
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page()
        for slug in slugs:
            url = SOURCES[slug]
            try:
                page.goto(url, timeout=timeout_ms, wait_until="domcontentloaded")
                page.wait_for_timeout(2500)  # let any check/JS settle
                text = page.inner_text("body")
                parsed = parse_panel(text)
                if with_chart:
                    chart = extract_chart_series(page)
                    # trust the chart only if its last point is the panel price
                    if chart and parsed["price"] is not None and \
                            abs(chart[-1][1] - parsed["price"]) > 0.01:
                        chart = []
                    parsed["chart"] = chart
            except Exception as exc:  # keep going; caller decides
                parsed = {"price": None, "updated": "", "error": str(exc)}
            parsed["source"] = url
            out[slug] = parsed
        browser.close()
    return out


def _norm_chart_series(raw):
    """Normalise ECharts option data into [(date, price)] or []."""
    out = []
    for item in raw or []:
        d = v = None
        if isinstance(item, (list, tuple)) and len(item) >= 2:
            d, v = item[0], item[1]
        elif isinstance(item, dict) and "value" in item:
            val = item["value"]
            if isinstance(val, (list, tuple)) and len(val) >= 2:
                d, v = val[0], val[1]
        if isinstance(d, str) and len(d) == 10 and d[4] == "-":
            try:
                out.append((d, float(v)))
            except (TypeError, ValueError):
                pass
    return sorted(out)


def extract_chart_series(page):
    """Best-effort: pull the benchmark's daily series from the detail
    page's ECharts instance (the page renders ~3 months of daily
    values into a chart; there is no data table). Returns [] when the
    chart cannot be read — callers fall back to the panel price."""
    try:
        data = page.evaluate(
            """() => {
              const found = [];
              if (!window.echarts) return found;
              document.querySelectorAll('div[_echarts_instance_]').forEach(el => {
                const inst = window.echarts.getInstanceByDom(el);
                if (!inst) return;
                const opt = inst.getOption();
                const axes = (opt.xAxis || []).map(a => a.data || []);
                (opt.series || []).forEach((s, i) => {
                  if (!Array.isArray(s.data) || s.data.length < 20) return;
                  let rows = s.data;
                  if (typeof rows[0] === 'number' && axes[i] && axes[i].length === rows.length) {
                    rows = rows.map((v, j) => [axes[i][j], v]);
                  }
                  found.push(rows);
                });
              });
              return found;
            }""")
    except Exception:
        return []
    best = []
    for rows in data or []:
        series = _norm_chart_series(rows)
        if len(series) > len(best):
            best = series
    return best
