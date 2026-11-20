"""Render sitemap.xml by structural substitution on the previous build.

The 2026-11-10 bundle sitemap is the template: 135 URLs, every one
with <lastmod>2026-11-10</lastmod> and <changefreq>daily</changefreq>
— including static pages (articles, tools, cost pages) whose own
content did not change that day. The original generator evidently
stamps every URL with the build date, so this renderer does the same:
every lastmod becomes ctx["today"].

One dynamic part: the /history/YYYY-MM/ month entries. The sitemap
lists one per month covered by the price series (2025-10..2026-11,
newest first, just before the /history/ index entry). When a new
month starts, its entry must appear, so render_sitemap() inserts any
series month missing from the template, in newest-first order, in
exactly the published entry format. Month entries already present
are left where they are; nothing is ever deleted.

Validated by re-rendering 2026-11-10 and diffing
(tests/verify_sitemap.py).
"""
from __future__ import annotations

import re

HISTORY_INDEX = "<url><loc>https://pla365.com/history/</loc>"


def _month_entry(month, today):
    return (
        f"<url><loc>https://pla365.com/history/{month}/</loc>"
        f"<lastmod>{today}</lastmod><changefreq>daily</changefreq></url>"
    )


def render_sitemap(ctx, sample, series=None):
    """Regenerate sitemap.xml for ctx["today"].

    `sample` is the previous build's sitemap.xml (the URL inventory);
    `series` is {slug: [(date, price), ...]} — only its date range is
    used, to add any missing /history/YYYY-MM/ month entries.
    """
    today = ctx["today"]
    out = re.sub(r"<lastmod>[^<]*</lastmod>",
                 f"<lastmod>{today}</lastmod>", sample)
    if "https://pla365.com/news/" not in out:
        entry = ("<url><loc>https://pla365.com/news/</loc>"
                 f"<lastmod>{today}</lastmod>"
                 "<changefreq>daily</changefreq></url>")
        anchor = "<url><loc>https://pla365.com/alerts/</loc>"
        idx = out.find(anchor)
        if idx != -1:
            out = out[:idx] + entry + out[idx:]
    if series:
        dates = [d for d, _ in next(iter(series.values()))] if series else []
        months = sorted({d[:7] for d in dates}, reverse=True)
        present = set(re.findall(
            r"<loc>https://pla365\.com/history/(\d{4}-\d{2})/</loc>", out))
        missing = [m for m in months if m not in present]
        for m in missing:
            # Insert in newest-first order: before the first existing
            # month entry older than m, else before the /history/ index.
            entry = _month_entry(m, today)
            placed = False
            for match in re.finditer(
                    r"<url><loc>https://pla365\.com/history/(\d{4}-\d{2})/</loc>",
                    out):
                if match.group(1) < m:
                    out = out[:match.start()] + entry + out[match.start():]
                    placed = True
                    break
            if not placed:
                idx = out.find(HISTORY_INDEX)
                if idx == -1:
                    raise ValueError("sitemap template has no /history/ entry")
                out = out[:idx] + entry + out[idx:]
    return out
