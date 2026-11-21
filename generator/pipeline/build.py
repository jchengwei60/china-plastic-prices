"""Assemble the full pla365 site bundle (the Worker's F map).

Inputs are the frozen page templates (the 2026-11-10 site, in bundle
storage form: HTML as text, binaries as base64 text) plus the
evolving state (variety series, board extras, basis rows, futures,
update stamps). Every dynamic page is re-rendered from its template;
static pages are carried over with the daily date stamps applied —
the same thing the old generator's daily rebuild did.

build_all returns {path: (content, content_type, is_binary)} with
content in bundle storage form (base64 text for binary entries).
pack_worker serialises it into worker.js (byte-compatible with the
original packing: Python json.dumps with (', ', ': ') separators,
verified to round-trip the published bundle exactly).
"""
from __future__ import annotations

import base64
import io
import json
import os
import re

from .basis_data import dump_sf_basis, load_sf_basis
from .context import build_context
from .dataio import build_latest, dump_history, dump_json, latest_csv_rows
from .render_alerts import render_alerts, render_alerts_xml
from .render_basis import render_basis
from .render_cost import (render_const_c, render_cost_index,
                          render_cost_page)
from .render_grades import render_grade, render_grade_index
from .render_history import _stamps, render_day, render_index, render_month
from .render_home import render_home
from .render_misc import (make_xlsx, render_download, render_fupan,
                          render_llms, render_today_page)
from .render_news import render_news
from .render_pinzhong import render_pinzhong
from .render_rank import render_rank
from .render_sitemap import render_sitemap
from .render_spread import PAIRS, render_spread, render_spread_index
from .render_today_image import render_today_image
from .render_variety import EXTRAS, render_variety
from .render_wenda import render_wenda
from .render_wendu import render_wendu

MAINS = ["pp", "lldpe", "hdpe", "ldpe", "pvc", "abs", "ps", "pet"]
FUT_MAINS = ["pp", "lldpe", "pvc", "pet"]
TOOLS_CONST_C = ["cost", "import", "letter", "pass-through", "proof", "tax"]
HANDLER_PATH = os.path.join(os.path.dirname(__file__), "worker_handler.js")


def load_templates(templates_dir, manifest_path):
    manifest = json.load(open(manifest_path, encoding="utf-8"))
    templates = {}
    for path in manifest:
        fp = os.path.join(templates_dir, path.lstrip("/"))
        with open(fp, encoding="utf-8") as f:
            templates[path] = f.read()
    return templates, manifest


def build_all(templates, manifest, series, extras_state, basis_text,
              latest_csv_text, futures, updated, today, assets_dir,
              news_items=None):
    """futures: {slug: {close, chg, date, settle, fut_series}} for the
    four futures varieties. extras_state: {slug: {name, bulk, yoy,
    series}}. Returns the F map."""
    basis_rows = load_sf_basis(basis_text)
    extras_list = [{"slug": s, "name": extras_state[s]["name"],
                    "series": [tuple(x) for x in extras_state[s]["series"]]}
                   for s in EXTRAS]
    futures_ctx = {s: {"close": futures[s]["close"], "chg": futures[s]["chg"],
                       "date": futures[s]["date"]} for s in FUT_MAINS}
    ctx = build_context(series, extras_list, futures_ctx, today, updated)

    out = {}

    def put(path, content, binary=False, ctype=None):
        if ctype is None:
            ctype = manifest.get(path, ["text/html; charset=utf-8", binary])[0]
        out[path] = (content, ctype, binary)

    def tpl(path):
        return templates[path]

    put("/index.html", render_home(ctx, tpl("/index.html")))
    put("/wendu/index.html", render_wendu(ctx, tpl("/wendu/index.html")))
    put("/basis/index.html",
        render_basis({"today": today, "basis": basis_rows}, tpl("/basis/index.html")))
    put("/pinzhong/index.html", render_pinzhong(ctx, tpl("/pinzhong/index.html")))
    put("/rank/index.html", render_rank(ctx, tpl("/rank/index.html"), series))
    put("/alerts/index.html",
        render_alerts({"today": today}, tpl("/alerts/index.html"), series))
    put("/alerts.xml", render_alerts_xml(series))
    put("/news/index.html",
        render_news(tpl("/alerts/index.html"), news_items or [], today))

    for slug in MAINS:
        kw = {}
        if slug in FUT_MAINS:
            kw = {"fut_series": futures[slug]["fut_series"],
                  "settle": futures[slug]["settle"]}
        put(f"/{slug}/index.html",
            render_variety(ctx, tpl(f"/{slug}/index.html"), slug, series[slug], **kw))
    for slug in EXTRAS:
        st = extras_state[slug]
        put(f"/{slug}/index.html",
            render_variety(ctx, tpl(f"/{slug}/index.html"), slug,
                           [tuple(x) for x in st["series"]],
                           yoy=st["yoy"], bulk=st["bulk"]))

    # history: day pages = template days + today; months from series
    day_dates = sorted({p.split("/")[2] for p in templates
                        if re.fullmatch(r"/history/\d{4}-\d{2}-\d{2}/index\.html", p)}
                       | {today})
    months = sorted({d[:7] for ent in series.values() for d, _ in ent})
    # Day pages are render-once snapshots: the published ones hold the
    # values as scraped on their morning (生意社 later revised some),
    # so past days are carried over; only today's page is rendered.
    existing_days = sorted(templates_dayset(templates))
    day_shell = tpl(f"/history/{existing_days[-1]}/index.html")
    shell = templates.get(f"/history/{today}/index.html", day_shell)
    put(f"/history/{today}/index.html", render_day(today, series, shell, today))
    month_shell = tpl("/history/2026-11/index.html")
    for ym in months:
        shell = templates.get(f"/history/{ym}/index.html", month_shell)
        put(f"/history/{ym}/index.html",
            render_month(ym, series, shell, today, day_dates))
    put("/history/index.html",
        render_index(series, tpl("/history/index.html"), today, day_dates))

    for path in templates:
        m = re.fullmatch(r"/grade/([a-z0-9-]+)/index\.html", path)
        if m:
            put(path, render_grade(tpl(path), series, today, updated))
    put("/grade/index.html", render_grade_index(tpl("/grade/index.html"), series, today))

    for slug, a, b in PAIRS:
        put(f"/spread/{slug}/index.html",
            render_spread(tpl(f"/spread/{slug}/index.html"), series, a, b, today))
    put("/spread/index.html", render_spread_index(tpl("/spread/index.html"), series, today))

    cost_samples = {}
    for path in templates:
        m = re.fullmatch(r"/cost/([a-z0-9-]+)/index\.html", path)
        if m:
            cost_samples[m.group(1)] = tpl(path)
            put(path, render_cost_page(tpl(path), series, today))
    put("/cost/index.html",
        render_cost_index(tpl("/cost/index.html"), series, today, cost_samples))

    for t in TOOLS_CONST_C:
        p = f"/tools/{t}/index.html"
        put(p, render_const_c(tpl(p), series, today))

    put("/wenda/index.html", render_wenda(tpl("/wenda/index.html"), series,
                                          basis_text, today))
    put("/fupan/index.html", render_fupan(tpl("/fupan/index.html"), series, today))
    put("/llms.txt", render_llms(tpl("/llms.txt"), series, today))
    put("/download/index.html", render_download(tpl("/download/index.html"), today))
    xlsx_bytes = make_xlsx(base64.b64decode(tpl("/download/plastic-cost-template.xlsx")),
                           series, updated, today)
    put("/download/plastic-cost-template.xlsx",
        base64.b64encode(xlsx_bytes).decode(), binary=True)
    put("/today/index.html", render_today_page(tpl("/today/index.html"), today))
    img = render_today_image(series, {"eps": [tuple(x) for x in extras_state["eps"]["series"]]},
                             today, assets_dir)
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=88)
    put("/today/today.jpg", base64.b64encode(buf.getvalue()).decode(), binary=True)
    put("/sitemap.xml", render_sitemap({"today": today}, tpl("/sitemap.xml"), series))

    # data files
    payload = build_latest(series, updated)
    put("/data/history.csv", dump_history(series))
    put("/data/latest.json", dump_json(payload))
    kept = [ln for ln in latest_csv_text.splitlines()
            if ln and not ln.startswith(today + ",")]
    rows = [",".join(r) for r in latest_csv_rows(payload)]
    put("/data/latest.csv", "\n".join(kept + rows) + "\n")
    put("/data/sf_basis.csv", dump_sf_basis(basis_rows))

    # everything else: carry over, stamping HTML pages
    for path, content in templates.items():
        if path in out:
            continue
        ctype, binary = manifest[path]
        if ctype.startswith("text/html"):
            content = _stamps(content, today)
        out[path] = (content, ctype, binary)

    # The 解读 section's pill nav gains an 行业动态 entry (the /news/
    # page), on every page that carries that nav.
    for path in list(out):
        content, ctype, binary = out[path]
        if binary or "text/html" not in ctype:
            continue
        new = content.replace(
            '<a href="/history/">历史价格</a></nav>',
            '<a href="/history/">历史价格</a>'
            '<a href="/news/">行业动态</a></nav>')
        new = new.replace(
            '<a href="/history/" class="on">历史价格</a></nav>',
            '<a href="/history/" class="on">历史价格</a>'
            '<a href="/news/">行业动态</a></nav>')
        if new != content:
            out[path] = (new, ctype, binary)

    # The AI-assistance disclosure lives once in the site-wide footer
    # (moved out of the individual articles, 2026-11-21).
    for path in list(out):
        content, ctype, binary = out[path]
        if binary or "text/html" not in ctype:
            continue
        if "本站行情文章由AI辅助生成" in content:
            continue
        new = content.replace(
            "仅供参考。©",
            "仅供参考。本站行情文章由AI辅助生成，经人工审核后发布。©")
        if new != content:
            out[path] = (new, ctype, binary)
    return out


def templates_dayset(templates):
    return {p.split("/")[2] for p in templates
            if re.fullmatch(r"/history/\d{4}-\d{2}-\d{2}/index\.html", p)}


def pack_worker(fmap):
    obj = {}
    for path in sorted(fmap):
        content, ctype, binary = fmap[path]
        entry = [content, ctype]
        if binary:
            entry.append(True)
        obj[path] = entry
    handler = open(HANDLER_PATH, encoding="utf-8").read()
    return "const F = " + json.dumps(obj, ensure_ascii=False,
                                     separators=(", ", ": ")) + ";\n" + handler
