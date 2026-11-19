"""Article entry points injected into the homepage and variety pages
(Jiang approved 2026-11-19): until now the data pages carried no link
into the articles at all, so article traffic depended entirely on the
WeChat push. The sections reuse the article pages' own related-list
markup (<h2> + <ul><li><a>) and sit right before the 公众号 QR box.
"""
from __future__ import annotations

from .articles_meta import ARTICLES


def _li(a):
    return f'<li><a href="{a[0]}">{a[1]}</a></li>'


def home_section(n=4):
    lis = "".join(_li(a) for a in ARTICLES[:n])
    return (f'<h2>行情解读</h2><ul>{lis}'
            f'<li><a href="/articles/">全部文章 ›</a></li></ul>')


def variety_section(slug, n=4):
    rel = [a for a in ARTICLES if slug in a[4]]
    if len(rel) < 2:
        # Fill with the evergreen guides first, then general pieces,
        # so varieties with no dedicated article still offer reading.
        pool = ([a for a in ARTICLES if a[3] == "采购干货"]
                + [a for a in ARTICLES if not a[4] and a[3] != "采购干货"])
        seen = {a[0] for a in rel}
        for a in pool:
            if len(rel) >= n:
                break
            if a[0] not in seen:
                rel.append(a)
                seen.add(a[0])
    lis = "".join(_li(a) for a in rel[:n])
    return f'<h2>相关解读</h2><ul>{lis}</ul>'


def inject(html, section):
    """Insert the section before the 公众号 QR box (fallback: before
    </main>). Idempotent: a page already carrying the section is
    returned unchanged."""
    if section.split("<ul>")[0] in html:
        return html
    anchor = '<div class="box qr">'
    if anchor in html:
        return html.replace(anchor, section + anchor, 1)
    if "</main>" in html:
        return html.replace("</main>", section + "</main>", 1)
    return html
